"""Manifest-bound updates for exact assembly topology setup records."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .assembly_package_shapes import canonicalize_assembly_package_shapes
from .design_ir_v2 import AssemblyIRV1
from .project_package import ProjectPackageError, read_project, write_spike_package


def update_assembly_topology_setup(
    params: Dict[str, Any],
    *,
    application_version: str,
) -> Dict[str, Any]:
    """Replace only constraint/binding definitions; exact shapes remain immutable."""

    allowed = {
        "project_path", "expected_manifest_payload_sha256", "constraints",
        "thermal_contact_bindings", "electrical_bond_bindings",
    }
    if set(params) != allowed:
        raise ProjectPackageError(
            "Exact topology setup parameters must contain only the project identity and three setup arrays."
        )
    project_path = Path(str(params.get("project_path", "")))
    if not project_path.is_file():
        raise ProjectPackageError("Open a saved SPIKE project before editing exact topology setup.")
    opened = read_project(project_path, include_members=True)
    if opened.migrated:
        raise ProjectPackageError("Migrate and save the legacy project before editing exact topology setup.")
    expected_manifest = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual_manifest = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected_manifest or expected_manifest != actual_manifest:
        raise ProjectPackageError(
            "The project changed since it was verified; reopen it before editing exact topology setup."
        )
    current = opened.payload.get("assembly_package_shapes")
    if not isinstance(current, dict) or not current:
        raise ProjectPackageError("Extract exact STEP package shapes before defining topology setup.")
    replacement = dict(current)
    fields = ("constraints", "thermal_contact_bindings", "electrical_bond_bindings")
    for field in fields:
        value = params.get(field)
        if not isinstance(value, list):
            raise ProjectPackageError(f"Assembly package-shape {field} must be an array.")
        replacement[field] = value
    assembly_raw = opened.payload.get("assembly_ir")
    models = opened.payload.get("models")
    if not isinstance(assembly_raw, dict) or not isinstance(models, dict):
        raise ProjectPackageError("Exact topology setup requires canonical AssemblyIR and model index records.")
    assembly = AssemblyIRV1.from_dict(assembly_raw)
    replacement = canonicalize_assembly_package_shapes(replacement, assembly.to_dict(), models)
    payload = dict(opened.payload)
    payload["assembly_package_shapes"] = replacement
    audit = list(payload.get("audit") or [])
    audit.append({
        "event": "assembly_topology_setup_updated",
        "constraint_count": len(replacement["constraints"]),
        "thermal_contact_binding_count": len(replacement["thermal_contact_bindings"]),
        "electrical_bond_binding_count": len(replacement["electrical_bond_bindings"]),
        "shape_artifacts_unchanged": True,
        "solver_ready": False,
    })
    payload["audit"] = audit
    manifest = write_spike_package(
        project_path,
        payload,
        profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members,
        application_version=application_version,
    )
    return {
        "contract": "spike/assembly-topology-setup-update-result/v1",
        "assembly_id": replacement["assembly_id"],
        "constraint_count": len(replacement["constraints"]),
        "thermal_contact_binding_count": len(replacement["thermal_contact_bindings"]),
        "electrical_bond_binding_count": len(replacement["electrical_bond_bindings"]),
        "shape_artifacts_unchanged": True,
        "solver_ready": False,
        "project_path": str(project_path.resolve()),
        "manifest": manifest,
    }
