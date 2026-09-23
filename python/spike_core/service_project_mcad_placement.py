"""Manifest-bound MCAD placement and assembly-semantic project operations."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict

from .assembly_frames import enforce_placement_policy, reparent_part_preserving_world, validate_rigid_transform
from .assembly_placement_policy import AssemblyPlacementPolicy
from .design_ir_v2 import AssemblyIRV1
from .design_ir_v2_schema import CoordinateFrame
from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_helpers import error_response, operation_id


def _open_current_project(
    params: Dict[str, Any], action: str, *, legacy_action: str | None = None,
    stale_action: str | None = None,
    include_members: bool = True,
):
    path = Path(str(params.get("project_path", "")))
    if not path.is_file():
        raise ProjectPackageError(f"Open a saved SPIKE project before {action}.")
    opened = read_project(path, include_members=include_members)
    if opened.migrated:
        raise ProjectPackageError(f"Migrate and save the legacy project before {legacy_action or action}.")
    expected = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected or expected != actual:
        raise ProjectPackageError(f"The project changed since it was verified; reopen it before {stale_action or action}.")
    return path, opened


def _editable_assembly(opened):
    assembly_raw = opened.payload.get("assembly_ir")
    if not isinstance(assembly_raw, dict):
        raise ProjectPackageError("The project does not contain an editable AssemblyIR assembly.")
    return AssemblyIRV1.from_dict(assembly_raw)


def _save(path: Path, opened: Any, payload: Dict[str, Any], application_version: str):
    return write_spike_package(
        path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members, application_version=application_version,
    )


def update_mcad_part_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    path, opened = _open_current_project(
        params, "editing an MCAD part", legacy_action="editing MCAD parts",
        stale_action="editing MCAD placement",
    )
    part_id = str(params.get("part_id", "")).strip()
    if not part_id:
        raise ProjectPackageError("An AssemblyIR part_id is required.")
    assembly = _editable_assembly(opened)
    part = next((item for item in assembly.parts if item.id == part_id), None)
    if part is None:
        raise ProjectPackageError(f"AssemblyIR part {part_id} does not exist.")
    frame_raw = params.get("frame")
    if not isinstance(frame_raw, dict):
        raise ProjectPackageError("A complete canonical coordinate frame is required.")
    requested_frame = CoordinateFrame(**{
        key: value for key, value in frame_raw.items() if key in CoordinateFrame.__dataclass_fields__
    })
    if "placement_policy" in params:
        raise ProjectPackageError("MCAD placement policy cannot be changed through the part placement operation.")
    enforce_placement_policy(part.frame.transform, requested_frame.transform, part.placement_policy)
    root_frame_id = assembly.frame.frame_id
    if requested_frame.frame_id != part.frame.frame_id:
        raise ProjectPackageError("MCAD placement edits cannot change the stable frame identity.")
    if (requested_frame.parent_frame_id or root_frame_id) != (part.frame.parent_frame_id or root_frame_id):
        raise ProjectPackageError("MCAD placement edits cannot change the stable parent-frame relationship.")
    name = str(params.get("name", part.name)).strip()
    part_type = str(params.get("part_type", part.part_type)).strip()
    material_id = str(params.get("material_id", part.material_id)).strip()
    if not name or not part_type:
        raise ProjectPackageError("MCAD part name and part_type must be non-empty.")
    visual = params.get("visual")
    if visual is not None:
        if not isinstance(visual, dict) or set(visual) != {"visible", "opacity"}:
            raise ProjectPackageError("MCAD visual settings must contain exactly visible and opacity values.")
        if not isinstance(visual["visible"], bool):
            raise ProjectPackageError("MCAD visual visible must be a boolean.")
        try:
            opacity = float(visual["opacity"])
        except (TypeError, ValueError) as exc:
            raise ProjectPackageError("MCAD visual opacity must be a finite number from 0 to 1.") from exc
        if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ProjectPackageError("MCAD visual opacity must be a finite number from 0 to 1.")
        part.extensions = {**(part.extensions or {}), "spike.visual": {"visible": visual["visible"], "opacity": opacity}}
    part.name, part.part_type, part.material_id, part.frame = name, part_type, material_id, requested_frame
    assembly.__post_init__()
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {
        "event": "mcad_part_updated", "part_id": part.id, "model_id": part.model_id,
        "frame_id": part.frame.frame_id, "parent_frame_id": part.frame.parent_frame_id,
        "material_id": part.material_id, "visual": dict(part.extensions.get("spike.visual") or {}),
    }]
    manifest = _save(path, opened, payload, application_version)
    return {"contract": "spike/mcad-part-update-result/v1", "part": next(item for item in assembly.to_dict()["parts"] if item["id"] == part.id), "project_path": str(path.resolve()), "manifest": manifest}


def update_mcad_placement_policy_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    path, opened = _open_current_project(params, "editing MCAD placement policy")
    part_id = str(params.get("part_id", "")).strip()
    if not part_id:
        raise ProjectPackageError("An AssemblyIR part_id is required.")
    policy_raw = params.get("placement_policy")
    if not isinstance(policy_raw, dict):
        raise ProjectPackageError("A complete assembly placement policy is required.")
    policy = AssemblyPlacementPolicy.from_dict(policy_raw)
    assembly = _editable_assembly(opened)
    part = next((item for item in assembly.parts if item.id == part_id), None)
    if part is None:
        raise ProjectPackageError(f"AssemblyIR part {part_id} does not exist.")
    validate_rigid_transform(part.frame.transform, "Existing MCAD placement")
    part.placement_policy = policy
    assembly.__post_init__()
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {"event": "mcad_placement_policy_updated", "part_id": part.id, "placement_policy": {"contract": policy.contract, "translation_snap_mm": policy.translation_snap_mm, "rotation_snap_deg": policy.rotation_snap_deg}, "frame_unchanged": True}]
    manifest = _save(path, opened, payload, application_version)
    return {"contract": "spike/mcad-placement-policy-update-result/v1", "part": next(item for item in assembly.to_dict()["parts"] if item["id"] == part.id), "project_path": str(path.resolve()), "manifest": manifest}


def reparent_mcad_part_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    path, opened = _open_current_project(
        params, "reparenting an MCAD part", legacy_action="reparenting MCAD parts",
        stale_action="reparenting MCAD parts",
    )
    part_id, new_parent = str(params.get("part_id", "")).strip(), str(params.get("new_parent_frame_id", "")).strip()
    if not part_id or not new_parent:
        raise ProjectPackageError("part_id and new_parent_frame_id are required for MCAD reparenting.")
    assembly = _editable_assembly(opened)
    old_parent, new_parent = reparent_part_preserving_world(assembly, part_id, new_parent)
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {"event": "mcad_part_reparented", "part_id": part_id, "old_parent_frame_id": old_parent, "new_parent_frame_id": new_parent, "world_transform_preserved": True}]
    manifest = _save(path, opened, payload, application_version)
    part = next(item for item in assembly.to_dict()["parts"] if item["id"] == part_id)
    return {"contract": "spike/mcad-part-reparent-result/v1", "part": part, "old_parent_frame_id": old_parent, "new_parent_frame_id": new_parent, "world_transform_preserved": True, "project_path": str(path.resolve()), "manifest": manifest}


def update_assembly_semantics_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    path, opened = _open_current_project(params, "editing assembly semantics")
    assembly_raw = opened.payload.get("assembly_ir")
    if not isinstance(assembly_raw, dict):
        raise ProjectPackageError("The project does not contain an editable AssemblyIR assembly.")
    replacement = dict(assembly_raw)
    for field in ("materials", "thermal_contacts", "electrical_bonds"):
        value = params.get(field)
        if not isinstance(value, list):
            raise ProjectPackageError(f"AssemblyIR {field} must be an array.")
        replacement[field] = value
    assembly = AssemblyIRV1.from_dict(replacement)
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {"event": "assembly_semantics_updated", "material_count": len(assembly.materials), "thermal_contact_count": len(assembly.thermal_contacts), "electrical_bond_count": len(assembly.electrical_bonds)}]
    manifest = _save(path, opened, payload, application_version)
    return {"contract": "spike/assembly-semantics-update-result/v1", "assembly_ir": assembly.to_dict(), "project_path": str(path.resolve()), "manifest": manifest}


def handle_mcad_placement_project_request(method: Any, params: Dict[str, Any], *, request_id: Any, application_version: str) -> Dict[str, Any] | None:
    operations = {
        "update_mcad_part_in_project": update_mcad_part_in_project,
        "update_mcad_placement_policy_in_project": update_mcad_placement_policy_in_project,
        "reparent_mcad_part_in_project": reparent_mcad_part_in_project,
        "update_assembly_semantics_in_project": update_assembly_semantics_in_project,
    }
    operation = operations.get(method)
    if operation is None:
        return None
    try:
        return {"ok": True, "result": operation(params, application_version=application_version)}
    except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
        return error_response("SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
