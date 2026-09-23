"""Manifest-bound AssemblyIR structure operations and request routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .assembly_designs import AssemblyDesignError, canonicalize_assembly_designs
from .design_ir_v2 import AssemblyIRV1
from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_helpers import error_response, operation_id
from .service_project_geometric_constraint import apply_assembly_geometric_constraint_in_project
from .service_assembly_import import import_into_assembly
from .harness_authoring import validate_harness_connections
from .assembly_frames import validate_rigid_transform
from .service_mcad_collaboration import export_mcad_session, preview_mcad_feedback, apply_mcad_feedback


def update_assembly_structure_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    fields = ("boards", "harnesses", "connector_mappings", "rigid_flex_links")
    allowed = {"project_path", "expected_manifest_payload_sha256", *fields}
    if set(params) != allowed:
        raise ProjectPackageError("Assembly structure updates require only project identity and the four structure arrays.")
    path = Path(str(params.get("project_path", "")))
    if not path.is_file():
        raise ProjectPackageError("Open a saved SPIKE project before editing assembly structure.")
    opened = read_project(path, include_members=True)
    if opened.migrated:
        raise ProjectPackageError("Migrate and save the legacy project before editing assembly structure.")
    expected = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected or expected != actual:
        raise ProjectPackageError("The project changed since it was verified; reopen it before editing assembly structure.")
    assembly_raw = opened.payload.get("assembly_ir")
    if not isinstance(assembly_raw, dict):
        raise ProjectPackageError("The project does not contain an editable AssemblyIR assembly.")
    replacement = dict(assembly_raw)
    for field in fields:
        value = params.get(field)
        if not isinstance(value, list):
            raise ProjectPackageError(f"AssemblyIR {field} must be an array.")
        replacement[field] = value
    assembly = AssemblyIRV1.from_dict(replacement)
    validate_harness_connections(assembly)
    for board in assembly.boards:
        validate_rigid_transform(board.frame.transform, f"Board {board.id} placement")
    board_ids = {board.id for board in assembly.boards}
    for harness in assembly.harnesses:
        endpoints = [harness.endpoint_a.split(":", 1)[0], harness.endpoint_b.split(":", 1)[0]]
        if any(endpoint not in board_ids for endpoint in endpoints):
            raise ProjectPackageError(f"Harness {harness.id} endpoints must resolve to retained board instances.")
        if endpoints[0] == endpoints[1]:
            raise ProjectPackageError(f"Harness {harness.id} must connect two distinct board instances.")
    retained = opened.payload.get("assembly_designs")
    active = opened.payload.get("design_ir")
    if retained:
        try:
            canonicalize_assembly_designs(retained, active, assembly.to_dict())
        except AssemblyDesignError as exc:
            raise ProjectPackageError(str(exc)) from exc
    else:
        active_id = str((active or {}).get("design_id", "")) if isinstance(active, dict) else ""
        if any(board.design_id != active_id for board in assembly.boards):
            raise ProjectPackageError("Retain every referenced DesignIR before assigning multiple board designs.")
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    audit = list(payload.get("audit") or [])
    audit.append({
        "event": "assembly_structure_updated",
        "board_count": len(assembly.boards), "harness_count": len(assembly.harnesses),
        "connector_mapping_count": len(assembly.connector_mappings),
        "rigid_flex_link_count": len(assembly.rigid_flex_links),
        "retained_design_count": len((retained or {}).get("designs", [])) if isinstance(retained, dict) else 1,
        "coupled_solver_ready": False,
    })
    payload["audit"] = audit
    manifest = write_spike_package(
        path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members, application_version=application_version,
    )
    return {
        "contract": "spike/assembly-structure-update-result/v1",
        "assembly_ir": assembly.to_dict(), "project_path": str(path.resolve()),
        "coupled_solver_ready": False, "manifest": manifest,
    }


def handle_assembly_project_request(method: Any, params: Dict[str, Any], *, request_id: Any, application_version: str) -> Dict[str, Any] | None:
    operations = {
        "export_mcad_session": export_mcad_session,
        "preview_mcad_feedback": preview_mcad_feedback,
        "apply_mcad_feedback": apply_mcad_feedback,
        "import_into_assembly_project": import_into_assembly,
        "apply_assembly_geometric_constraint_in_project": apply_assembly_geometric_constraint_in_project,
        "update_assembly_structure_in_project": update_assembly_structure_in_project,
    }
    operation = operations.get(method)
    if operation is None:
        return None
    try:
        return {"ok": True, "result": operation(params, application_version=application_version)}
    except (OSError, KeyError, AttributeError, ValueError, TypeError, ProjectPackageError) as exc:
        return error_response("SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
