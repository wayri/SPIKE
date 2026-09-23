"""Manifest-bound selector-preview generation for exact package shapes."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict

from .assembly_package_shapes import canonicalize_assembly_package_shapes
from .mcad_selector_preview import generate_selector_preview
from .project_package import ProjectPackageError, read_project, write_spike_package
from .project_model_artifacts import read_package_shape_selector_previews


def read_mcad_selector_previews(params: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(str(params.get("path", "")))
    shape_ids = params.get("shape_ids")
    if not path.is_file():
        raise ProjectPackageError("The selected SPIKE project does not exist.")
    if not isinstance(shape_ids, list):
        raise ProjectPackageError("Selector-preview shape identifiers must be an array.")
    artifacts = read_package_shape_selector_previews(
        path, shape_ids,
        expected_manifest_payload_sha256=params.get("expected_manifest_payload_sha256"),
    )
    return {
        "contract": "spike/project-package-shape-selector-previews/v1",
        "artifacts": [{
            **{key: value for key, value in artifact.items() if key != "artifact"},
            "artifact_base64": base64.b64encode(artifact["artifact"]).decode("ascii"),
        } for artifact in artifacts],
    }


def generate_mcad_selector_preview_in_project(
    params: Dict[str, Any], *, application_version: str,
) -> Dict[str, Any]:
    if set(params) != {"project_path", "expected_manifest_payload_sha256", "shape_id"}:
        raise ProjectPackageError("Selector-preview parameters must contain exactly project_path, expected manifest identity, and shape_id.")
    project_path = Path(str(params.get("project_path", "")))
    if not project_path.is_file():
        raise ProjectPackageError("Open a saved SPIKE project before generating an exact selector preview.")
    opened = read_project(project_path, include_members=True)
    if opened.migrated:
        raise ProjectPackageError("Migrate and save the legacy project before generating an exact selector preview.")
    expected_manifest = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual_manifest = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected_manifest or expected_manifest != actual_manifest:
        raise ProjectPackageError("The project changed since it was verified; reopen it before generating an exact selector preview.")
    shape_id = str(params.get("shape_id", "")).strip()
    index = opened.payload.get("assembly_package_shapes")
    if not shape_id or not isinstance(index, dict):
        raise ProjectPackageError("Extract an exact STEP package shape before generating its selector preview.")
    shape = next((item for item in index.get("shapes", []) if isinstance(item, dict) and item.get("shape_id") == shape_id), None)
    if shape is None:
        raise ProjectPackageError(f"Exact package shape {shape_id} does not exist.")
    topology_member = str(shape.get("topology_artifact_uri", "")).removeprefix("package:")
    topology_artifact = opened.members.get(topology_member)
    if topology_artifact is None:
        raise ProjectPackageError("The verified exact package-shape artifact is unavailable.")
    outcome = generate_selector_preview(
        topology_artifact, shape_id=shape_id, source_sha256=str(shape.get("source_sha256", "")),
        entities=shape.get("entities", []),
    )
    replacement = dict(index)
    replacement_shapes = []
    old_preview_member = ""
    for item in index.get("shapes", []):
        if not isinstance(item, dict) or item.get("shape_id") != shape_id:
            replacement_shapes.append(item)
            continue
        updated = dict(item)
        prior_preview = updated.get("selector_preview")
        if isinstance(prior_preview, dict):
            old_preview_member = str(prior_preview.get("artifact_uri", "")).removeprefix("package:")
        updated["selector_preview"] = {
            "contract": outcome.contract,
            "artifact_uri": f"package:geometry/package-shapes/{outcome.artifact_name}",
            "artifact_sha256": outcome.artifact_sha256,
            "source_sha256": outcome.source_sha256,
            "topology_artifact_sha256": outcome.topology_artifact_sha256,
            "selector_inventory_sha256": outcome.selector_inventory_sha256,
            "freecad_version": outcome.freecad_version,
            "linear_deflection_mm": outcome.linear_deflection_mm,
            "face_count": outcome.face_count,
            "edge_count": outcome.edge_count,
            "axis_count": outcome.axis_count,
            "visual_only": True,
            "solver_ready": False,
        }
        replacement_shapes.append(updated)
    replacement["shapes"] = replacement_shapes
    assembly = opened.payload.get("assembly_ir")
    models = opened.payload.get("models")
    replacement = canonicalize_assembly_package_shapes(replacement, assembly, models)
    payload = dict(opened.payload)
    payload["assembly_package_shapes"] = replacement
    audit = list(payload.get("audit") or [])
    audit.append({
        "event": "mcad_package_shape_selector_preview_generated",
        "shape_id": shape_id,
        "source_sha256": outcome.source_sha256,
        "topology_artifact_sha256": outcome.topology_artifact_sha256,
        "selector_inventory_sha256": outcome.selector_inventory_sha256,
        "artifact_sha256": outcome.artifact_sha256,
        "face_count": outcome.face_count, "edge_count": outcome.edge_count, "axis_count": outcome.axis_count,
        "visual_only": True, "solver_ready": False,
    })
    payload["audit"] = audit
    preserved_members = {
        name: data for name, data in opened.members.items()
        if not old_preview_member or name != old_preview_member
    }
    manifest = write_spike_package(
        project_path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
        package_shape_preview_artifacts={outcome.artifact_name: outcome.artifact_bytes},
        preserved_members=preserved_members, application_version=application_version,
    )
    return {
        "contract": "spike/mcad-package-shape-selector-preview-result/v1",
        "shape_id": shape_id,
        "part_id": shape["part_id"],
        "selector_preview": next(item["selector_preview"] for item in replacement["shapes"] if item["shape_id"] == shape_id),
        "visual_only": True, "solver_ready": False,
        "project_path": str(project_path.resolve()), "manifest": manifest,
    }
