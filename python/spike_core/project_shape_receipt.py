# SPDX-License-Identifier: Apache-2.0
"""Read-only preservation receipts over fully verified v3 project packages.

This inventories persisted evidence; it does not parse CAD or admit solver meshes.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .project_package import (
    ManifestVerifier, PackageLimits, ProjectPackageError, read_spike_package,
)


SHAPE_RECEIPT_CONTRACT = "spike/project-shape-receipt/v1"


def read_project_shape_receipt(
    path: str | Path,
    *,
    expected_manifest_payload_sha256: str | None = None,
    limits: PackageLimits | None = None,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> dict[str, Any]:
    """Verify package bytes and report saved shapes without retaining asset bytes.

    The optional manifest identity binds a receipt to an already opened project.
    Integrity verification is distinct from signature trust and CAD validity.
    """
    loaded = read_spike_package(
        path, limits=limits, include_members=False,
        signature_verifier=signature_verifier, require_signature=require_signature,
    )
    identity = loaded.manifest["manifest_payload_sha256"]
    if expected_manifest_payload_sha256 is not None and identity != expected_manifest_payload_sha256:
        raise ProjectPackageError("Shape receipt package changed; reopen the project.")
    records = {item["path"]: item for item in loaded.manifest["members"]}

    def artifact(member: str) -> dict[str, Any]:
        record = records[member.removeprefix("package:")]
        return {key: record[key] for key in ("path", "sha256", "size")}

    payload = loaded.payload
    design = payload["design_ir"]
    assembly = payload.get("assembly_ir") or {}
    models = payload.get("models", {}).get("models", [])
    shapes = payload.get("assembly_package_shapes", {}).get("shapes", [])
    source_assets = []
    previews = []
    for model in sorted(models, key=lambda item: item["id"]):
        item = {
            "model_id": model["id"], "model_type": model["model_type"],
            "artifact": artifact(model["uri"]), "transform": deepcopy(model["transform"]),
            "source_units": "not_inspected_by_receipt",
        }
        (source_assets if model["model_type"] == "step" else previews).append(item)

    topology = []
    for shape in sorted(shapes, key=lambda item: item["shape_id"]):
        topology.append({
            "shape_id": shape["shape_id"], "part_id": shape["part_id"],
            "source_model_id": shape["source_model_id"],
            "source_artifact": artifact(shape["source_artifact_uri"]),
            "topology_artifact": artifact(shape["topology_artifact_uri"]),
            "kernel": deepcopy(shape["kernel"]),
            "extraction": deepcopy(shape["extraction"]),
            "entity_counts": {kind: sum(entity["kind"] == kind for entity in shape["entities"])
                              for kind in sorted({entity["kind"] for entity in shape["entities"]})},
        })

    # File suffixes identify opaque retained assets, never CAD/mesh validity.
    opaque_brep = [artifact(name) for name in sorted(records)
                   if Path(name).suffix.lower() in {".brep", ".brp"}]
    mesh_assets = [artifact(name) for name in sorted(records)
                   if Path(name).suffix.lower() in {".msh", ".vtu", ".vtk", ".stl", ".ply"}]
    occurrences = []
    issues = []
    topology_models = {shape["source_model_id"] for shape in shapes}
    for model in source_assets:
        if model["model_id"] not in topology_models:
            issues.append({"code": "STEP_WITHOUT_TOPOLOGY", "model_id": model["model_id"]})
    for kind, items in (("board", assembly.get("boards", [])), ("part", assembly.get("parts", []))):
        for item in sorted(items, key=lambda value: value["id"]):
            occurrences.append({"kind": kind, **{key: deepcopy(item[key]) for key in
                                ("id", "design_id", "model_id", "part_type", "frame") if key in item}})
    if not source_assets:
        issues.append({"code": "NO_RETAINED_STEP_MODELS"})
    if not shapes:
        issues.append({"code": "NO_PACKAGE_SHAPE_TOPOLOGY"})

    geometry = payload.get("geometry", {})
    return {
        "contract": SHAPE_RECEIPT_CONTRACT,
        "manifest_payload_sha256": identity,
        "member_integrity_verified": True,
        "signature_verified": loaded.signature_verified,
        "design": {"design_id": design["design_id"],
                   "artifact": artifact("design/design-ir.json"),
                   "frame": deepcopy(design.get("frame", {}))},
        "assembly": {"assembly_id": assembly.get("assembly_id"),
                     "artifact": artifact("design/assembly-ir.json") if assembly else None,
                     "frame": deepcopy(assembly.get("frame", {})), "occurrences": occurrences},
        "retained_step_models": source_assets,
        "opaque_brep_assets": opaque_brep,
        "topology": topology,
        "topology_index_artifact": artifact("design/assembly-package-shapes.json") if shapes else None,
        "geometry_tables": deepcopy(geometry.get("tables", [])),
        "preview_models": previews,
        "mesh_assets_by_suffix": mesh_assets,
        "issues": issues,
        "limitations": [
            "Byte integrity and persisted metadata only; no CAD kernel roundtrip or geometric equivalence check.",
            "Canonical frames use millimetres and right handedness; STEP internal units are not parsed here.",
            "Package topology is an opaque kernel artifact; no BREP format is inferred from spkshape bytes.",
            "Mesh suffix inventory and preview models do not establish derivation links or solver mesh validity.",
            "No MoM/BEM, meshing, acceleration or solver-ready capability is established by this receipt.",
        ],
    }
