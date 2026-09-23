"""Manifest-bound FreeCAD sessions and reviewed placement feedback."""
from __future__ import annotations

import base64
import copy
import math
from uuid import uuid4

from .assembly_frames import IDENTITY, enforce_placement_policy
from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import CoordinateFrame
from .mcad_export_design import _convert_rings, _rings_from_drawings
from .mcad_session_contract import SESSION, FEEDBACK, MAX_BYTES, digest, loads, validate
from .project_model_artifacts import read_step_model_artifact
from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_project_mcad_placement import _open_current_project, _editable_assembly


def _designs(payload):
    return (payload.get("assembly_designs") or {}).get("designs") or [payload["design_ir"]]


def _identity(payload, assembly):
    return {"project_id": str(payload["project"]["id"]), "assembly_id": assembly.assembly_id,
            "baseline_assembly_sha256": digest(assembly.to_dict()),
            "baseline_designs_sha256": digest(_designs(payload))}


def _board_geometry(design):
    design = DesignIRV2.from_dict(design).to_v1().to_dict()
    meta = design.get("metadata", {})
    rings = _convert_rings(meta["board_outline_rings"]) if meta.get("board_outline_rings") else _rings_from_drawings(meta.get("board_outline_drawings", []))
    heights = [layer.get("thickness_mm", layer.get("thickness")) for layer in design.get("stackup", [])]
    if not rings or not heights or any(isinstance(h, bool) or not isinstance(h, (int, float)) or not math.isfinite(h) or h <= 0 for h in heights):
        return None
    # Same datum as the existing MCAD board projection; explicitly disclosed.
    return {"type": "board_outline", "rings": rings, "height_mm": sum(heights), "z_mm": 0.0}


def export_mcad_session(params, *, application_version):
    path, opened = _open_current_project(params, "exporting a FreeCAD session", include_members=False)
    assembly = _editable_assembly(opened)
    if assembly.frame.parent_frame_id or tuple(assembly.frame.transform) != IDENTITY:
        raise ProjectPackageError("FreeCAD collaboration requires an identity assembly root.")
    entities = [*assembly.boards, *assembly.parts]
    frames = {e.frame.frame_id: e.id for e in entities}
    designs = {d["design_id"]: d for d in _designs(opened.payload)}
    models = {m["id"]: m for m in (opened.payload.get("models") or {}).get("models", [])}
    result = {"contract": SESSION, "session_id": str(uuid4()), **_identity(opened.payload, assembly),
              "objects": [], "assets": {}, "diagnostics": []}
    board_ids = {b.id for b in assembly.boards}
    for entity in entities:
        geometry = None
        kind = "board" if entity.id in board_ids else "group" if entity.part_type == "subassembly" else "part"
        if kind == "board":
            geometry = _board_geometry(designs[entity.design_id])
            result["diagnostics"].append(f"{entity.id}: board body only; components, drills, copper and flex bends omitted. Datum is source XY, stack top at Z=0, thickness toward +Z.")
        elif kind == "part" and models.get(entity.model_id, {}).get("model_type") == "step":
            model = models[entity.model_id]
            sha = model["digest"]
            if sha not in result["assets"]:
                artifact = read_step_model_artifact(path, entity.model_id, expected_manifest_payload_sha256=params["expected_manifest_payload_sha256"], max_total_bytes=20*1024**2)
                result["assets"][sha] = {"type": "step", "data_base64": base64.b64encode(artifact["artifact"]).decode()}
            geometry = {"type": "step", "asset_sha256": sha}
        if geometry is None and kind != "group":
            result["diagnostics"].append(f"{entity.id}: no supported solid available; exported as a placement origin only.")
        parent = entity.frame.parent_frame_id
        result["objects"].append({"id": entity.id, "name": entity.name or entity.id, "kind": kind,
            "parent_id": frames.get(parent), "transform": list(entity.frame.transform), "geometry": geometry})
        # Check the running total, not only the final (potentially huge) buffer.
        if sum(len(a["data_base64"]) for a in result["assets"].values()) > MAX_BYTES - 1024**2:
            raise ProjectPackageError("FreeCAD session exceeds the 32 MiB exchange budget.")
    if assembly.harnesses:
        result["diagnostics"].append("Harness connectivity and routes remain in SPIKE. Recheck routes after placement changes; cable geometry editing is not part of this session version.")
    result["diagnostics"].append("Feedback updates occurrence names and rigid placements only. New parts use Export SPIKE Assembly; topology, reparenting and ECAD edits need a new workflow.")
    return validate(result)


def _preview(opened, feedback):
    validate(feedback)
    if feedback["contract"] != FEEDBACK: raise ProjectPackageError("Expected FreeCAD feedback.")
    assembly = _editable_assembly(opened)
    identity = _identity(opened.payload, assembly)
    for key in ("project_id", "assembly_id", "baseline_designs_sha256"):
        if feedback[key] != identity[key]: raise ProjectPackageError("Feedback belongs to another project, assembly or electrical revision.")
    # An identical accepted change is a no-op, including after reopening SPIKE.
    feedback_sha = digest(feedback)
    for event in reversed(opened.payload.get("audit") or []):
        if event.get("event") == "mcad_feedback_applied" and event.get("feedback_sha256") == feedback_sha:
            if event.get("result_assembly_sha256") != identity["baseline_assembly_sha256"]:
                raise ProjectPackageError("Assembly changed after this feedback was applied; export a fresh session.")
            return assembly, [], True
    if feedback["baseline_assembly_sha256"] != identity["baseline_assembly_sha256"]:
        raise ProjectPackageError("Assembly changed since session export; export a fresh session before applying feedback.")
    entities = {e.id: e for e in [*assembly.boards, *assembly.parts]}
    if {o["id"] for o in feedback["objects"]} != set(entities):
        raise ProjectPackageError("Feedback must retain every occurrence; additions and deletions require assembly import.")
    changes = []
    for row in feedback["objects"]:
        entity = entities[row["id"]]
        old = list(entity.frame.transform)
        moved = any(abs(a-b) > 1e-9 for a,b in zip(old, row["transform"]))
        renamed = row["name"] != entity.name
        if not moved and not renamed: continue
        enforce_placement_policy(old, row["transform"], getattr(entity, "placement_policy", None))
        changes.append({"id": entity.id, "before_name": entity.name, "after_name": row["name"],
                        "before_transform": old, "after_transform": row["transform"], "moved": moved})
        entity.name = row["name"]
        entity.frame = CoordinateFrame(**{**entity.frame.__dict__, "transform": tuple(row["transform"])})
    assembly.__post_init__()
    return assembly, changes, False


def preview_mcad_feedback(params, *, application_version):
    _, opened = _open_current_project(params, "reviewing FreeCAD feedback", include_members=False)
    feedback = loads(params["feedback_json"]) if "feedback_json" in params else params["feedback"]
    _, changes, repeated = _preview(opened, feedback)
    return {"contract": "spike/mcad-feedback-preview/v1", "changes": changes, "already_applied": repeated,
            "feedback": feedback, "feedback_sha256": digest(feedback), "measurements": feedback["measurements"],
            "warnings": ["Measurements describe the exported geometry only and are external, unverified observations.",
                         "Placement changes archive active results and require harness/contact/mesh review."]}


def _archive_results(payload, before_assembly):
    """Retain old result contexts without displaying them on moved geometry."""
    extensions = payload.setdefault("extensions", {})
    legacy = extensions.get("legacy") or {}
    history = extensions.setdefault("spike.mcad-collaboration", {}).setdefault("previous_states", [])
    history.append({"assembly_ir": before_assembly, "results": copy.deepcopy(payload.get("results")),
                    "analyses": copy.deepcopy(payload.get("analyses")),
                    "desktop_state": {k: copy.deepcopy(legacy[k]) for k in ("analysis", "results", "thermal", "emi", "spice") if k in legacy}})
    payload["results"] = {}
    # These are saved result-bearing state trees. Preserve setup fields; clear
    # known active results/history so old fields cannot reappear on reload.
    def clear(value):
        if isinstance(value, dict):
            for key in list(value):
                if key in {"latest_result", "active_result", "latest_channel_result", "field_result", "screening", "result"}:
                    value[key] = None
                elif key == "result_history": value[key] = []
                else: clear(value[key])
        elif isinstance(value, list):
            for child in value: clear(child)
    clear(payload.get("analyses"))
    for key in ("analysis", "thermal", "emi", "spice"): clear(legacy.get(key))
    if "results" in legacy: legacy["results"] = {}


def apply_mcad_feedback(params, *, application_version):
    path, opened = _open_current_project(params, "applying FreeCAD feedback")
    feedback = params["feedback"]
    validate(feedback)
    if params.get("reviewed_feedback_sha256") != digest(feedback):
        raise ProjectPackageError("Feedback changed after review; preview it again.")
    assembly, changes, repeated = _preview(opened, feedback)
    if repeated or not changes:
        return {"contract": "spike/mcad-feedback-applied/v1", "changes": [], "manifest": opened.manifest, "no_op": True}
    payload = copy.deepcopy(opened.payload)
    if any(row["moved"] for row in changes):
        _archive_results(payload, opened.payload["assembly_ir"])
    payload["assembly_ir"] = assembly.to_dict()
    payload.setdefault("audit", []).append({"event": "mcad_feedback_applied", "session_id": feedback["session_id"],
        "feedback_sha256": digest(feedback), "result_assembly_sha256": digest(assembly.to_dict()),
        "changes": changes, "measurements": feedback["measurements"], "requires_geometry_review": any(r["moved"] for r in changes)})
    if read_project(path).manifest.get("manifest_payload_sha256") != params["expected_manifest_payload_sha256"]:
        raise ProjectPackageError("Project changed during feedback processing; reopen before retrying.")
    manifest = write_spike_package(path, payload, preserved_members=opened.members,
        profile=opened.manifest.get("profile", "portable_project"), application_version=application_version)
    return {"contract": "spike/mcad-feedback-applied/v1", "changes": changes, "manifest": manifest, "no_op": False}
