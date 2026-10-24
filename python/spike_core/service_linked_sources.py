# SPDX-License-Identifier: Apache-2.0
"""Reviewed, manifest-bound refresh of explicitly linked on-disk CAD sources.

No editor IPC or source writes occur here. Existing importers own interpretation;
project replacement uses the package writer's compare-and-swap guard.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import re
from typing import Any

from .mcad_importer import SUPPORTED_MCAD_EXTENSIONS, import_mcad_artifact
from .project_package import ProjectPackageError, _source_member_name, write_spike_package
from .service_helpers import error_response, operation_id
from .service_project import import_design
from .service_project_mcad_placement import _open_current_project
from .service_project_persistence import without_saved_results
from .spider_v2 import SpiDeRV2

MAX_LINKED_SOURCE_BYTES = 64 * 1024 * 1024
METHODS = {"linked_source_status", "prepare_linked_source_update", "link_project_source", "apply_linked_source_update"}


def _path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A linked source path is required.")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Linked source paths must be absolute local filesystem paths.")
    path = candidate.resolve()
    if path.suffix.lower() not in {".kicad_pcb", *SUPPORTED_MCAD_EXTENSIONS}:
        raise ValueError("Link a KiCad PCB, STEP/STP, GLB or self-contained glTF file.")
    return path


def _digest(value: Any, *, required=False) -> str:
    value = str(value or "").lower().strip()
    if (value or required) and not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("A canonical SHA-256 source fingerprint is required.")
    return value


def _read(path: Path) -> tuple[bytes, dict]:
    before = path.stat()
    if not path.is_file() or not 0 < before.st_size <= MAX_LINKED_SOURCE_BYTES:
        raise ValueError("Linked source must be a nonempty file no larger than 64 MiB.")
    with path.open("rb") as stream:
        data = stream.read(MAX_LINKED_SOURCE_BYTES + 1)
    after = path.stat()
    if len(data) > MAX_LINKED_SOURCE_BYTES or len(data) != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Linked source changed while being read; save it and retry.")
    return data, {"path": str(path), "kind": "board" if path.suffix.lower() == ".kicad_pcb" else "model",
                  "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "mtime_ns": after.st_mtime_ns}


def _status(params: dict) -> dict:
    path = _path(params.get("path"))
    expected = _digest(params.get("expected_sha256"))
    try:
        _, source = _read(path)
    except FileNotFoundError:
        return {"contract": "spike/linked-source-status/v1", "path": str(path), "status": "missing"}
    return {"contract": "spike/linked-source-status/v1", **source,
            "status": "unlinked" if not expected else "unchanged" if expected == source["sha256"] else "changed"}


def _prepare(params: dict) -> tuple[dict, bytes]:
    path = _path(params.get("path"))
    raw, source = _read(path)
    if source["kind"] == "board":
        outcome = import_design(str(path), "kicad_pcb", with_report=True)
        canonical = outcome["design"]
        outcome["snapshot"] = {"contract": "spike/design-snapshot/v1", "canonical_design": canonical,
                               "design": SpiDeRV2.from_dict(canonical).to_v1(allow_unprojected_arcs=True).to_dict(), "report": outcome["report"]}
    else:
        imported = import_mcad_artifact(path)
        outcome = imported.to_dict()
        if imported.artifact_bytes != raw:
            raise ValueError("Linked source changed during import; preview it again.")
    if outcome["report"]["source_sha256"] != source["sha256"] or _read(path)[1]["sha256"] != source["sha256"]:
        raise ValueError("Linked source changed during import; preview it again.")
    source.update(contract="spike/linked-source-status/v1", status="unchanged" if params.get("expected_sha256") == source["sha256"] else "changed")
    return {"contract": "spike/linked-source-update-preview/v1", "source": source, "kind": source["kind"], "outcome": outcome}, raw


def _linked_params(params: dict) -> dict:
    if "path" in params or "source_path" in params:
        raise ValueError("Source paths are resolved from the saved project link, not request overrides.")
    _, opened = _open_current_project(params, "inspecting a linked CAD source", include_members=False)
    kind, ident = str(params.get("target_kind", "")), str(params.get("target_id", ""))
    _target(opened.payload, kind, ident)
    link = next((row for row in _links(opened.payload) if (row.get("target_kind"), row.get("target_id")) == (kind, ident)), None)
    if link is None:
        raise ValueError("This project target has no saved source link.")
    return {"path": link["path"], "expected_sha256": params.get("expected_sha256", link["sha256"])}


def linked_source_status(params: dict) -> dict:
    return _status(_linked_params(params))


def prepare_linked_source_update(params: dict) -> dict:
    linked = _linked_params(params)
    _digest(linked.get("expected_sha256"))
    return _prepare(linked)[0]


def _target(payload: dict, kind: str, ident: str) -> dict:
    if kind == "board":
        designs = [payload.get("design_ir") or {}, *((payload.get("assembly_designs") or {}).get("designs") or [])]
        target = next((row for row in designs if row.get("design_id") == ident), None)
    elif kind == "model":
        target = next((row for row in (payload.get("models") or {}).get("models", []) if row.get("id") == ident), None)
    else:
        raise ValueError("target_kind must be board or model.")
    if not ident or target is None:
        raise ValueError("The linked source target does not exist in this project.")
    return target


def _links(payload: dict) -> list:
    links = payload.setdefault("analyses", {}).setdefault("linked_sources", [])
    if not isinstance(links, list) or any(not isinstance(row, dict) or row.get("target_kind") not in {"board", "model"}
                                         or not isinstance(row.get("target_id"), str) for row in links):
        raise ValueError("Saved linked_sources must be an array of board/model target records.")
    return links


def _save(path, opened, payload, params, version, **artifacts):
    legacy = (payload.get("extensions") or {}).get("legacy")
    if isinstance(legacy, dict):
        legacy.setdefault("analysis", {})["linked_sources"] = copy.deepcopy(_links(payload))
    members = opened.members
    if (payload.get("design_ir") or {}) != (opened.payload.get("design_ir") or {}):
        # Arrow rows are a derived view bound to the complete canonical digest.
        # A refresh must never retain tables from the previous board revision.
        payload["geometry"] = {"contract": "spike/geometry-index/v1", "tables": []}
        members = {name: data for name, data in members.items()
                   if not (name.startswith("geometry/") and name.endswith(".arrow"))}
    return write_spike_package(path, payload, profile=opened.manifest.get("profile", "portable_project"),
        preserved_members=members, application_version=version,
        expected_manifest_payload_sha256=params["expected_manifest_payload_sha256"], **artifacts)


def link_project_source(params: dict, *, application_version: str) -> dict:
    path, opened = _open_current_project(params, "linking a CAD source")
    payload = copy.deepcopy(opened.payload)
    kind, ident = str(params.get("target_kind", "")), str(params.get("target_id", ""))
    target = _target(payload, kind, ident)
    links = [row for row in _links(payload) if (row.get("target_kind"), row.get("target_id")) != (kind, ident)]
    source = None
    if not params.get("unlink"):
        source = _status(params)
        digest = (target.get("source") or {}).get("source_digest") if kind == "board" else target.get("digest")
        if source.get("kind") != kind or source.get("sha256") != digest:
            raise ValueError("Link the exact retained source revision first; the selected file does not match this target's fingerprint.")
        links.append({"target_kind": kind, "target_id": ident, **{key: source[key] for key in ("path", "sha256", "size_bytes", "mtime_ns")}})
    payload["analyses"]["linked_sources"] = links
    manifest = _save(path, opened, payload, params, application_version)
    return {"contract": "spike/linked-source-link-result/v1", "project_path": str(path.resolve()), "manifest": manifest, "source": source}


def _ids(value: Any) -> set[str]:
    found = set()
    if isinstance(value, dict):
        for key in ("id", "source_id"):
            if isinstance(value.get(key), str) and value[key]:
                found.add(value[key])
        for row in value.values():
            found.update(_ids(row))
    elif isinstance(value, list):
        for row in value:
            found.update(_ids(row))
    return found


def _references(value: Any, removed: set[str], path="setup") -> list[str]:
    if isinstance(value, str):
        return [path] if value in removed else []
    if isinstance(value, dict):
        return [hit for key, row in value.items() for hit in _references(row, removed, f"{path}.{key}")]
    if isinstance(value, list):
        return [hit for i, row in enumerate(value) for hit in _references(row, removed, f"{path}[{i}]")]
    return []


def _replace_board(payload: dict, old: dict, preview: dict, raw: bytes) -> dict:
    fresh = copy.deepcopy(preview["outcome"]["design"])
    fresh["design_id"] = old["design_id"]
    fresh["frame"] = copy.deepcopy(old["frame"])
    for key in ("component_bonds", "constraints", "simulation_models", "variants"):
        if old.get(key):
            fresh[key] = copy.deepcopy(old[key])
    fresh["metadata"] = {**copy.deepcopy(old.get("metadata") or {}), **fresh.get("metadata", {})}
    fresh["vendor_extensions"] = {**copy.deepcopy(old.get("vendor_extensions") or {}), **fresh.get("vendor_extensions", {})}
    removed = _ids(old) - _ids(fresh)
    refs = _references({"analyses": payload.get("analyses"), "assembly": payload.get("assembly_ir"),
                        "topology": payload.get("assembly_package_shapes"), "design_setups": {
                            key: old.get(key) for key in ("component_bonds", "constraints", "simulation_models", "variants", "vendor_extensions")},
                        "legacy_design_setups": {key: ((payload.get("extensions") or {}).get("legacy", {}).get("design") or {}).get(key)
                            for key in ("component_bonds", "topologies", "model_assignments")}, "legacy_setups": {
                            key: (payload.get("extensions") or {}).get("legacy", {}).get(key)
                            for key in ("analysis", "thermal", "emi", "spice")}}, removed)
    if refs:
        raise ValueError("Source update would remove referenced entities; review these setups first: " + ", ".join(refs[:8]))
    fresh["source"]["artifact_path"] = "package:" + _source_member_name(Path(preview["source"]["path"]).name, preview["source"]["sha256"])
    active = (payload.get("design_ir") or {}).get("design_id") == old["design_id"]
    if active:
        payload["design_ir"] = fresh
    retained = payload.get("assembly_designs") or {}
    if isinstance(retained.get("designs"), list):
        retained["designs"] = [fresh if row.get("design_id") == old["design_id"] else row for row in retained["designs"]]
    legacy = (payload.get("extensions") or {}).get("legacy")
    if isinstance(legacy, dict):
        if active:
            previous = legacy.get("design") or {}
            projected = SpiDeRV2.from_dict(fresh).to_v1(allow_unprojected_arcs=True).to_dict()
            legacy["design"] = {**previous, **projected,
                "source_board": raw.decode("utf-8-sig"), "source_file": preview["source"]["path"], "source_format": "kicad", "canonical_design": fresh}
            for key in ("component_bonds", "topologies", "model_assignments"):
                if key in previous:
                    legacy["design"][key] = copy.deepcopy(previous[key])
        legacy.pop("board_visuals", None)
    payload.setdefault("extensions", {}).pop("board_visuals", None)
    return {"source_artifacts": {Path(preview["source"]["path"]).name: raw}}


def _replace_model(payload: dict, old: dict, preview: dict, raw: bytes) -> dict:
    fresh = copy.deepcopy(preview["outcome"]["model"])
    if fresh["model_type"] != old["model_type"]:
        raise ValueError("Linked refresh cannot change the model format; attach the new format separately.")
    derived = {row["id"] for row in payload["models"]["models"]
               if ((row.get("extensions") or {}).get("spike.mcad.tessellation") or {}).get("source_model_id") == old["id"]}
    affected = {row["id"] for row in (payload.get("assembly_ir") or {}).get("parts", [])
                if row.get("model_id") in ({old["id"]} | derived)
                or ((row.get("extensions") or {}).get("spike.mcad.tessellation") or {}).get("source_model_id") == old["id"]}
    assembly = payload.get("assembly_ir") or {}
    if _references({key: assembly.get(key) for key in ("thermal_contacts", "electrical_bonds")}, affected):
        raise ValueError("Changed mechanical geometry has assembly thermal contacts or electrical bonds; review/remove them before refresh.")
    topology = payload.get("assembly_package_shapes") or {}
    shapes = [row for row in topology.get("shapes", []) if row.get("part_id") in affected]
    if shapes:
        shape_ids = {row["shape_id"] for row in shapes}
        refs = _references({key: topology.get(key) for key in ("constraints", "thermal_contact_bindings", "electrical_bond_bindings")}, shape_ids | affected)
        if refs:
            raise ValueError("Changed mechanical topology has active constraints or contact bindings; remove/review them before refresh.")
        topology["shapes"] = [row for row in topology["shapes"] if row.get("part_id") not in affected]
    fresh["id"] = old["id"]
    fresh["name"] = old.get("name", fresh["name"])
    fresh["transform"] = copy.deepcopy(old.get("transform", []))
    fresh["extensions"] = {**copy.deepcopy(old.get("extensions") or {}), **fresh.get("extensions", {})}
    fresh["extensions"].pop("spike.mcad.tessellation", None)
    if any(row.get("target_kind") == "model" and row.get("target_id") in derived for row in _links(payload)):
        raise ValueError("A derived visual model has its own source link; unlink it before refreshing its STEP source.")
    payload["models"]["models"] = [fresh if row.get("id") == old["id"] else row for row in payload["models"]["models"] if row.get("id") not in derived]
    for row in (payload.get("assembly_ir") or {}).get("parts", []):
        if row.get("id") in affected:
            row["model_id"] = old["id"]
            row["source_id"] = preview["outcome"]["part"]["source_id"]
            row.setdefault("extensions", {}).pop("spike.mcad.tessellation", None)
            row["extensions"]["spike.mcad"] = copy.deepcopy(preview["outcome"]["part"]["extensions"]["spike.mcad"])
    return {"model_artifacts": {preview["outcome"]["artifact_name"]: raw}}


def apply_linked_source_update(params: dict, *, application_version: str) -> dict:
    if "path" in params or "source_path" in params:
        raise ValueError("Source paths are resolved from the saved project link, not request overrides.")
    path, opened = _open_current_project(params, "refreshing linked CAD data")
    payload = without_saved_results(opened.payload)
    kind, ident = str(params.get("target_kind", "")), str(params.get("target_id", ""))
    old = _target(payload, kind, ident)
    link = next((row for row in _links(payload) if (row.get("target_kind"), row.get("target_id")) == (kind, ident)), None)
    if link is None:
        raise ValueError("Link this project target before refreshing it.")
    expected = _digest(params.get("expected_sha256"), required=True)
    preview, raw = _prepare({"path": link["path"], "expected_sha256": link["sha256"]})
    if expected != preview["source"]["sha256"]:
        raise ValueError("Source changed after preview; review the new revision before applying it.")
    if expected == link["sha256"]:
        return {"contract": "spike/linked-source-apply-result/v1", "project_path": str(path.resolve()), "manifest": opened.manifest, "source": preview["source"], "no_op": True}
    if params.get("invalidate_results") is not True:
        raise ValueError("Review and explicitly accept invalidating saved results before applying changed geometry (invalidate_results=true).")
    artifacts = _replace_board(payload, old, preview, raw) if kind == "board" else _replace_model(payload, old, preview, raw)
    for key in ("sha256", "size_bytes", "mtime_ns"):
        link[key] = preview["source"][key]
    payload["reports"] = {}
    legacy = (payload.get("extensions") or {}).get("legacy")
    if isinstance(legacy, dict):
        legacy["reports"] = {}
    payload.setdefault("audit", []).append({"event": "linked_source_updated", "target_kind": kind, "target_id": ident,
        "source_sha256": expected, "results_invalidated": True, "requires_setup_review": True})
    manifest = _save(path, opened, payload, params, application_version, **artifacts)
    return {"contract": "spike/linked-source-apply-result/v1", "project_path": str(path.resolve()), "manifest": manifest,
            "source": preview["source"], "no_op": False, "requires_setup_review": True}


def handle_linked_source_request(method, params, *, request_id, application_version):
    if method not in METHODS:
        return None
    try:
        functions = {"linked_source_status": linked_source_status, "prepare_linked_source_update": prepare_linked_source_update,
                     "link_project_source": link_project_source, "apply_linked_source_update": apply_linked_source_update}
        kwargs = {"application_version": application_version} if method in {"link_project_source", "apply_linked_source_update"} else {}
        return {"ok": True, "result": functions[method](params, **kwargs)}
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return error_response("SPIKE-BE-IMPORT-E-0002", str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
