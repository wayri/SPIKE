"""Manifest-bound exact single-constraint MCAD placement transaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .assembly_geometric_constraints import apply_single_geometric_constraint
from .assembly_package_shapes import canonicalize_assembly_package_shapes, selector_inventory_sha256
from .design_ir_v2 import AssemblyIRV1
from .project_package import ProjectPackageError, read_project, write_spike_package


def apply_assembly_geometric_constraint_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    allowed = {"project_path", "expected_manifest_payload_sha256", "constraint_id", "moving_part_id"}
    if set(params) != allowed:
        raise ProjectPackageError("Exact geometric application requires only project, manifest, constraint, and moving-part identities.")
    project_path = Path(str(params.get("project_path", "")))
    if not project_path.is_file():
        raise ProjectPackageError("Open a saved SPIKE project before applying an exact geometric constraint.")
    opened = read_project(project_path, include_members=True)
    if opened.migrated:
        raise ProjectPackageError("Migrate and save the legacy project before applying exact geometric constraints.")
    expected = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected or expected != actual:
        raise ProjectPackageError("The project changed since it was verified; reopen it before applying exact geometric constraints.")
    assembly_raw, models, index_raw = (
        opened.payload.get("assembly_ir"), opened.payload.get("models"), opened.payload.get("assembly_package_shapes"),
    )
    if not all(isinstance(value, dict) and value for value in (assembly_raw, models, index_raw)):
        raise ProjectPackageError("Exact geometric application requires AssemblyIR, model index, and package-shape records.")
    assembly = AssemblyIRV1.from_dict(assembly_raw)
    index = canonicalize_assembly_package_shapes(index_raw, assembly.to_dict(), models)
    constraint_id = str(params.get("constraint_id", "")).strip()
    moving_part_id = str(params.get("moving_part_id", "")).strip()
    if not constraint_id or not moving_part_id:
        raise ProjectPackageError("constraint_id and moving_part_id are required.")
    outcome = apply_single_geometric_constraint(assembly, models, index, constraint_id, moving_part_id)
    affected_shapes = [shape for shape in index["shapes"] if shape["part_id"] in {outcome["anchor_part_id"], moving_part_id}]
    payload = dict(opened.payload)
    payload["assembly_ir"] = assembly.to_dict()
    audit = list(payload.get("audit") or [])
    audit.append({
        "event": "assembly_geometric_constraint_applied",
        **outcome,
        "shape_bindings": [{
            "shape_id": shape["shape_id"],
            "source_sha256": shape["source_sha256"],
            "topology_artifact_sha256": shape["topology_artifact_sha256"],
            "selector_inventory_sha256": selector_inventory_sha256(shape["entities"]),
            "kernel": shape["kernel"],
        } for shape in affected_shapes],
        "shape_artifacts_unchanged": True,
        "contacts_or_bonds_inferred": False,
        "solver_ready": False,
    })
    payload["audit"] = audit
    manifest = write_spike_package(
        project_path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members, application_version=application_version,
    )
    part = next(item for item in assembly.to_dict()["parts"] if item["id"] == moving_part_id)
    return {
        "contract": "spike/assembly-geometric-constraint-application-result/v1",
        **outcome, "part": part, "shape_artifacts_unchanged": True,
        "contacts_or_bonds_inferred": False, "solver_ready": False,
        "project_path": str(project_path.resolve()), "manifest": manifest,
    }
