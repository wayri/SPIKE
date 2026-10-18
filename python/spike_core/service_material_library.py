# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound material assignment for AssemblyIR occurrences."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Mapping

from .material_library import MaterialError, load_catalog, material_snapshot, validate_material, validate_snapshot
from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_helpers import error_response, operation_id
from .service_project_persistence import without_saved_results
from .spider_v2 import AssemblyIRV1


def _invalidate_saved_results(payload: Dict[str, Any], before_assembly: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Archive the old context and clear outputs tied to prior properties."""
    cleaned = without_saved_results(payload)
    result_fields = {"latest_result", "active_result", "latest_channel_result", "field_result", "screening", "result"}

    def clear_shape(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("contract") == "spike/assembly-field-study-file/v1":
                return
            for key in list(value):
                if key in result_fields:
                    value[key] = None
                elif key == "result_history":
                    value[key] = []
                else:
                    clear_shape(value[key])
        elif isinstance(value, list):
            for item in value:
                clear_shape(item)

    clear_shape(cleaned.get("analyses"))
    legacy = (cleaned.get("extensions") or {}).get("legacy")
    if isinstance(legacy, dict):
        for key in ("analysis", "thermal", "emi", "spice"):
            clear_shape(legacy.get(key))
    changed = any(payload.get(key) != cleaned.get(key) for key in ("results", "analyses", "extensions"))
    if changed:
        history = cleaned.setdefault("extensions", {}).setdefault(
            "spike.material-assignment-history",
            {"contract": "spike/material-assignment-history/v1", "previous_states": []},
        )
        if not isinstance(history, dict) or not isinstance(history.get("previous_states"), list):
            raise ProjectPackageError("Material assignment history is malformed; repair it before assigning a material.")
        history["previous_states"].append({
            "assembly_ir": copy.deepcopy(before_assembly),
            "results": copy.deepcopy(payload.get("results")),
            "analyses": copy.deepcopy(payload.get("analyses")),
            "extensions": copy.deepcopy(payload.get("extensions")),
        })
    return cleaned, changed


def _open_current_project(params: Dict[str, Any], action: str):
    path = Path(str(params.get("project_path", "")))
    if not path.is_file():
        raise ProjectPackageError(f"Open a saved SPIKE project before {action}.")
    opened = read_project(path, include_members=True)
    if opened.migrated:
        raise ProjectPackageError(f"Migrate and save the legacy project before {action}.")
    expected = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected or expected != actual:
        raise ProjectPackageError(f"The project changed since it was verified; reopen it before {action}.")
    return path, opened


def _selected_record(params: Mapping[str, Any]) -> Dict[str, Any]:
    catalog_id = params.get("catalog_material_id")
    supplied = params.get("material")
    if bool(catalog_id) == (supplied is not None):
        raise ProjectPackageError("Provide exactly one catalog_material_id or material record.")
    if supplied is not None:
        return validate_material(supplied)
    wanted = str(catalog_id).strip()
    record = next((item for item in load_catalog() if item["id"] == wanted), None)
    if record is None:
        raise ProjectPackageError(f"Trusted material catalog ID {wanted!r} does not exist.")
    return record


def list_material_catalog(params: Mapping[str, Any] | None = None, *, application_version: str = "") -> Dict[str, Any]:
    """Return detached catalog records for selection and review."""
    project_path = Path(str((params or {}).get("project_path", "")))
    if not project_path.is_file():
        raise ProjectPackageError("Open a saved SPIKE project before browsing assembly materials.")
    return {"contract": "spike/material-catalog/v1", "materials": load_catalog()}


def assign_material_to_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    """Assign an immutable material snapshot to one part or board occurrence."""
    allowed = {
        "project_path", "expected_manifest_payload_sha256", "target_kind", "target_id",
        "layer_id", "catalog_material_id", "material",
    }
    if not set(params) <= allowed:
        raise ProjectPackageError("Material assignment contains unsupported parameters.")
    target_kind = str(params.get("target_kind", "")).strip()
    target_id = str(params.get("target_id", "")).strip()
    if target_kind not in {"part", "board", "board_layer"} or not target_id:
        raise ProjectPackageError("Material assignment requires target_kind part, board, or board_layer and a target_id.")
    record = _selected_record(params)
    snapshot = material_snapshot(record)
    validate_snapshot(snapshot)
    path, opened = _open_current_project(params, "assigning an assembly material")
    assembly_raw = opened.payload.get("assembly_ir")
    if not isinstance(assembly_raw, dict):
        raise ProjectPackageError("The project does not contain an editable AssemblyIR assembly.")
    # Validate the current graph, but edit its raw JSON representation so
    # geometry metadata introduced by newer writers remains exactly retained.
    AssemblyIRV1.from_dict(assembly_raw)
    replacement = copy.deepcopy(assembly_raw)
    collection = replacement["parts" if target_kind == "part" else "boards"]
    target = next((item for item in collection if isinstance(item, dict) and item.get("id") == target_id), None)
    if target is None:
        raise ProjectPackageError(f"AssemblyIR {target_kind} {target_id} does not exist.")
    extensions = target.setdefault("extensions", {})
    if not isinstance(extensions, dict):
        raise ProjectPackageError(f"AssemblyIR {target_kind} {target_id} extensions must be an object.")
    layer_id = None
    if target_kind == "board_layer":
        layer_id = str(params.get("layer_id", "")).strip()
        if not layer_id:
            raise ProjectPackageError("Board-layer material assignment requires an exact canonical layer_id.")
        design_id = str(target.get("design_id", ""))
        designs = {
            str(item.get("design_id", "")): item
            for item in (opened.payload.get("assembly_designs") or {}).get("designs", [])
            if isinstance(item, dict)
        }
        active = opened.payload.get("design_ir")
        if isinstance(active, dict):
            designs.setdefault(str(active.get("design_id", "")), active)
        design = designs.get(design_id)
        if not isinstance(design, dict):
            raise ProjectPackageError(f"Board occurrence {target_id} references an unretained design {design_id}.")
        layers = design.get("layers")
        if not isinstance(layers, list) or not any(
            isinstance(layer, dict) and str(layer.get("id", "")) == layer_id for layer in layers
        ):
            raise ProjectPackageError(f"Canonical layer {layer_id} does not exist in board occurrence {target_id}.")
        layer_materials = extensions.setdefault("spike.layer-materials", {})
        if not isinstance(layer_materials, dict):
            raise ProjectPackageError(f"AssemblyIR board {target_id} spike.layer-materials must be an object.")
        if layer_materials.get(layer_id) == snapshot:
            return {
                "contract": "spike/material-assignment-result/v1", "target_kind": target_kind,
                "target_id": target_id, "layer_id": layer_id, "material": snapshot,
                "active_results_invalidated": False, "unchanged": True,
                "project_path": str(path.resolve()), "manifest": copy.deepcopy(opened.manifest),
            }
        layer_materials[layer_id] = snapshot
    else:
        if extensions.get("spike.material") == snapshot:
            return {
                "contract": "spike/material-assignment-result/v1", "target_kind": target_kind,
                "target_id": target_id, "material": snapshot,
                "active_results_invalidated": False, "unchanged": True,
                "project_path": str(path.resolve()), "manifest": copy.deepcopy(opened.manifest),
            }
        extensions["spike.material"] = snapshot
    AssemblyIRV1.from_dict(replacement)

    candidate = copy.deepcopy(opened.payload)
    candidate["assembly_ir"] = replacement
    payload, invalidated = _invalidate_saved_results(candidate, assembly_raw)
    payload["audit"] = [*(payload.get("audit") or []), {
        "event": "assembly_material_assigned", "target_kind": target_kind,
        "target_id": target_id, "material_id": record["id"],
        "material_revision": record["revision"], "material_digest": snapshot["digest"],
        **({"layer_id": layer_id} if layer_id is not None else {}),
        "active_results_invalidated": invalidated,
    }]
    manifest = write_spike_package(
        path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members, application_version=application_version,
    )
    return {
        "contract": "spike/material-assignment-result/v1", "target_kind": target_kind,
        "target_id": target_id, **({"layer_id": layer_id} if layer_id is not None else {}),
        "material": snapshot, "active_results_invalidated": invalidated, "unchanged": False,
        "project_path": str(path.resolve()), "manifest": manifest,
    }


def handle_material_library_request(
    method: Any, params: Dict[str, Any], *, request_id: Any, application_version: str,
) -> Dict[str, Any] | None:
    operations = {
        "list_material_catalog": list_material_catalog,
        "assign_material_to_project": assign_material_to_project,
    }
    operation = operations.get(method)
    if operation is None:
        return None
    try:
        return {"ok": True, "result": operation(params, application_version=application_version)}
    except (OSError, ValueError, TypeError, MaterialError, ProjectPackageError) as exc:
        return error_response(
            "SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__,
            operation_id=operation_id(request_id),
        )
