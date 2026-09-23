"""Project package and design-import request handlers for the worker service."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict
import zlib

from .project_package import (
    ProjectPackageError, manifest_signature_payload, read_project, read_visual_model_artifacts,
    write_spike_package,
)
from .design_ir_v2 import AssemblyIRV1, DesignIRV2
from .design_ir_v2_schema import CoordinateFrame, ModelReference, canonical_uuid, content_digest
from .assembly_frames import validate_rigid_transform
from .assembly_package_shapes import (
    ASSEMBLY_PACKAGE_SHAPES_V1, PACKAGE_SHAPE_KERNEL_V1, model_transform_sha256,
)
from .mcad_importer import McadImportError, import_mcad_artifact
from .mcad_package_shape import McadPackageShapeError, extract_step_package_shape
from .mcad_selector_preview import McadSelectorPreviewError
from .mcad_tessellation import McadTessellationError, tessellate_step_to_glb
from .project_model_artifacts import read_project_source_artifact, read_step_model_artifact
from .service_helpers import error_response, operation_id
from .service_project import (
    canonicalize_project_payload, design_source_digest, frontend_project_payload,
    has_authoritative_source_identity, import_design, merge_project_payload,
)
from .service_project_topology import update_assembly_topology_setup
from .service_project_assembly import handle_assembly_project_request
from .service_project_mcad_placement import handle_mcad_placement_project_request
from .service_project_selector_preview import generate_mcad_selector_preview_in_project, read_mcad_selector_previews
from .normalized_source_codec import compact_normalized_source_for_open
from .service_project_persistence import project_for_desktop, prepare_persistent_state, read_persistent_artifact
from .project_state_artifacts import hydrate_result_state


def handle_project_request(
    method: Any, params: Dict[str, Any], *, request_id: Any, application_version: str,
) -> Dict[str, Any] | None:
    """Handle project persistence and import requests, or return ``None``."""
    if method in {"read_project_state_artifact", "read_project_visual_bundle"}:
        try:
            return {"ok": True, "result": read_persistent_artifact(method, params)}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response("SPIKE-BE-PACKAGE-E-0001", str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
    assembly_response = handle_assembly_project_request(method, params, request_id=request_id, application_version=application_version)
    if assembly_response is not None:
        return assembly_response
    placement_response = handle_mcad_placement_project_request(
        method, params, request_id=request_id, application_version=application_version,
    )
    if placement_response is not None:
        return placement_response
    if method == "generate_mcad_selector_preview_in_project":
        try:
            return {"ok": True, "result": generate_mcad_selector_preview_in_project(
                params, application_version=application_version,
            )}
        except (OSError, ValueError, TypeError, ProjectPackageError, McadSelectorPreviewError) as exc:
            return error_response(
                "SPIKE-BE-IMPORT-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "update_assembly_topology_setup_in_project":
        try:
            return {"ok": True, "result": update_assembly_topology_setup(
                params, application_version=application_version,
            )}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response(
                "SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "read_project_package":
        try:
            path = Path(str(params.get("path", "")))
            if not path.is_file():
                raise ProjectPackageError("The selected SPIKE project does not exist.")
            opened = read_project(path)
            projected = project_for_desktop(opened.payload, frontend_project_payload(opened.payload))
            canonical_payload = opened.payload
            if not params.get("defer_artifacts") and not opened.migrated:
                digest = str(opened.manifest.get("manifest_payload_sha256", ""))
                projected = hydrate_result_state(projected, path, digest)
                canonical_payload = hydrate_result_state(canonical_payload, path, digest)
            elif params.get("defer_artifacts"):
                canonical_payload = {"design_ir": opened.payload.get("design_ir")}
            projected_design = projected.get("design") if isinstance(projected.get("design"), dict) else {}
            canonical_design = opened.payload.get("design_ir") if isinstance(opened.payload.get("design_ir"), dict) else {}
            if not str(projected_design.get("source_board", "")) and not opened.migrated:
                source = canonical_design.get("source") if isinstance(canonical_design.get("source"), dict) else {}
                artifact_uri = str(source.get("artifact_path", ""))
                source_digest = str(source.get("source_digest", ""))
                if artifact_uri:
                    source_bytes = read_project_source_artifact(
                        path,
                        artifact_uri,
                        expected_manifest_payload_sha256=str(opened.manifest.get("manifest_payload_sha256", "")),
                        expected_source_sha256=source_digest,
                    )
                    try:
                        source_text = source_bytes.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise ProjectPackageError("The canonical design source is not UTF-8 text.") from exc
                    projected_design = dict(projected_design)
                    projected_design.update({
                        "source_board": source_text,
                        "source_file": Path(artifact_uri.removeprefix("package:")).name,
                        "source_format": str(source.get("source_format", "")),
                    })
                    projected["design"] = projected_design
            if params.get("compact_normalized_source"):
                projected_design = projected.get("design") if isinstance(projected.get("design"), dict) else {}
                source_board = projected_design.get("source_board")
                if projected_design.get("source_format") == "spike-normalized" and isinstance(source_board, (str, dict)):
                    projected_design = dict(projected_design)
                    projected_design["source_board"] = compact_normalized_source_for_open(source_board)
                    # The same canonical design is already returned once in
                    # result.canonical.design_ir.
                    projected_design.pop("canonical_design", None)
                    projected["design"] = projected_design
            return {"ok": True, "result": {
                "contract": "spike/project-open-result/v1",
                "project": projected,
                "canonical": canonical_payload,
                "manifest": opened.manifest,
                "manifest_signature": {
                    "present": opened.signature_present,
                    "verified": opened.signature_verified,
                    "signed_payload_base64url": (
                        base64.urlsafe_b64encode(manifest_signature_payload(opened.manifest))
                        .rstrip(b"=")
                        .decode("ascii")
                        if opened.signature_present else None
                    ),
                },
                "migrated": opened.migrated,
                "source_format": opened.source_format,
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response(
                "SPIKE-BE-PACKAGE-E-0001", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "read_project_model_artifacts":
        try:
            path = Path(str(params.get("path", "")))
            model_ids = params.get("model_ids")
            expected_manifest_digest = params.get("expected_manifest_payload_sha256")
            if not path.is_file():
                raise ProjectPackageError("The selected SPIKE project does not exist.")
            if not isinstance(model_ids, list):
                raise ProjectPackageError("Visual model identifiers must be an array.")
            artifacts = read_visual_model_artifacts(
                path,
                model_ids,
                expected_manifest_payload_sha256=expected_manifest_digest,
            )
            return {"ok": True, "result": {
                "contract": "spike/project-model-artifacts/v1",
                "artifacts": [{
                    **{key: value for key, value in artifact.items() if key != "artifact"},
                    "artifact_base64": base64.b64encode(artifact["artifact"]).decode("ascii"),
                } for artifact in artifacts],
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response(
                "SPIKE-BE-PACKAGE-E-0001", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "read_project_package_shape_selector_previews":
        try:
            return {"ok": True, "result": read_mcad_selector_previews(params)}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response(
                "SPIKE-BE-PACKAGE-E-0001", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "write_project_package":
        try:
            path = Path(str(params.get("path", "")))
            snapshot = params.get("snapshot")
            if not path.name or not isinstance(snapshot, dict):
                raise ProjectPackageError("A destination path and project snapshot are required.")
            source_identity_is_authoritative = has_authoritative_source_identity(snapshot)
            payload, source_artifacts = canonicalize_project_payload(snapshot)
            preserved_members: Dict[str, bytes] = {}
            base_package_path = str(params.get("base_package_path", "")).strip()
            if base_package_path:
                base_path = Path(base_package_path)
                if not base_path.is_file():
                    raise ProjectPackageError("The source SPIKE package selected for lossless Save As does not exist.")
                base = read_project(base_path, include_members=True)
                if not base.migrated:
                    base_digest = design_source_digest(base.payload)
                    updated_digest = design_source_digest(payload)
                    payload = merge_project_payload(base.payload, payload)
                    preserved_members = base.members
                    if (
                        source_identity_is_authoritative
                        and base_digest and updated_digest
                        and base_digest != updated_digest
                    ):
                        payload["geometry"] = {"contract": "spike/geometry-index/v1", "tables": []}
                        payload.setdefault("extensions", {}).pop("board_visuals", None)
                        preserved_members = {
                            name: data for name, data in preserved_members.items()
                            if not name.startswith(("geometry/", "visuals/"))
                        }
                        payload.setdefault("audit", []).append({
                            "event": "geometry_cache_invalidated",
                            "reason": "design_source_digest_changed",
                            "previous_source_digest": base_digest,
                            "current_source_digest": updated_digest,
                        })
            generate_geometry_tables = (
                bool(params["generate_geometry_tables"])
                if "generate_geometry_tables" in params
                else not any(
                    name.startswith("geometry/") and name.endswith(".arrow")
                    for name in preserved_members
                )
            )
            # Arrow is an optional acceleration/runtime dependency.  Saving a
            # project must remain functional on a minimal worker; geometry
            # tables can be generated later when the pinned runtime is present.
            if generate_geometry_tables:
                try:
                    import pyarrow  # type: ignore[import-not-found]  # noqa: F401
                except ImportError:
                    generate_geometry_tables = False
            payload, preserved_members = prepare_persistent_state(payload, params.get("visuals"), preserved_members)
            manifest = write_spike_package(
                path,
                payload,
                profile=str(params.get("profile", "portable_project")),
                source_artifacts=source_artifacts,
                preserved_members=preserved_members,
                generate_geometry_tables=generate_geometry_tables,
                application_version=application_version,
            )
            return {"ok": True, "result": {
                "contract": "spike/project-save-result/v1",
                "path": str(path.resolve()),
                "manifest": manifest,
                "design_id": str((payload.get("design_ir") or {}).get("design_id", "")),
                "design_ir": payload.get("design_ir"),
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError) as exc:
            return error_response(
                "SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "attach_mcad_part_to_project":
        try:
            project_path = Path(str(params.get("project_path", "")))
            source_path = Path(str(params.get("source_path", "")))
            if not project_path.is_file():
                raise ProjectPackageError("Save the SPIKE project before attaching an MCAD part.")
            opened = read_project(project_path, include_members=True)
            if opened.migrated:
                raise ProjectPackageError("Migrate and save the legacy project before attaching MCAD parts.")
            frame = params.get("frame")
            outcome = import_mcad_artifact(
                source_path,
                name=str(params.get("name", "")),
                part_type=str(params.get("part_type", "mechanical")),
                material_id=str(params.get("material_id", "")),
                frame=frame if isinstance(frame, dict) else None,
            )
            validate_rigid_transform(outcome.part.frame.transform, "Initial MCAD placement")
            payload = dict(opened.payload)
            project = dict(payload.get("project") or {})
            assembly_raw = payload.get("assembly_ir")
            if isinstance(assembly_raw, dict):
                assembly = AssemblyIRV1.from_dict(assembly_raw)
            else:
                project_identity = str(project.get("id") or project.get("name") or project_path.stem)
                assembly = AssemblyIRV1(
                    assembly_id=canonical_uuid("spike", content_digest(project), "assembly", project_identity),
                    name=f"{str(project.get('name') or project_path.stem)} assembly",
                    frame=CoordinateFrame(frame_id="assembly"),
                )
            assembly.parts = [item for item in assembly.parts if item.id != outcome.part.id]
            assembly.parts.append(outcome.part)
            assembly.__post_init__()
            payload["assembly_ir"] = assembly.to_dict()

            model_index = dict(payload.get("models") or {})
            models = model_index.get("models", [])
            if not isinstance(models, list):
                raise ProjectPackageError("The project model index is invalid: models must be an array.")
            models = [item for item in models if not isinstance(item, dict) or item.get("id") != outcome.model.id]
            models.append(outcome.to_dict()["model"])
            model_index.update({"contract": "spike/model-index/v1", "models": models})
            payload["models"] = model_index
            audit = list(payload.get("audit") or [])
            audit.append({
                "event": "mcad_part_attached",
                "part_id": outcome.part.id,
                "model_id": outcome.model.id,
                "source_sha256": outcome.model.digest,
                "source_format": outcome.report.source_format,
            })
            payload["audit"] = audit
            manifest = write_spike_package(
                project_path,
                payload,
                profile=str(opened.manifest.get("profile", "portable_project")),
                preserved_members=opened.members,
                model_artifacts={outcome.artifact_name: outcome.artifact_bytes},
                application_version=application_version,
            )
            return {"ok": True, "result": {
                **outcome.to_dict(),
                "project_path": str(project_path.resolve()),
                "manifest": manifest,
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError, McadImportError) as exc:
            return error_response(
                "SPIKE-BE-IMPORT-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "tessellate_mcad_part_in_project":
        try:
            project_path = Path(str(params.get("project_path", "")))
            if not project_path.is_file():
                raise ProjectPackageError("Open a saved SPIKE project before tessellating an MCAD part.")
            opened = read_project(project_path, include_members=True)
            if opened.migrated:
                raise ProjectPackageError("Migrate and save the legacy project before tessellating MCAD parts.")
            expected_manifest = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
            actual_manifest = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
            if not expected_manifest or expected_manifest != actual_manifest:
                raise ProjectPackageError("The project changed since it was verified; reopen it before STEP tessellation.")
            part_id = str(params.get("part_id", "")).strip()
            assembly_raw = opened.payload.get("assembly_ir")
            if not part_id or not isinstance(assembly_raw, dict):
                raise ProjectPackageError("A valid AssemblyIR part_id is required for STEP tessellation.")
            assembly = AssemblyIRV1.from_dict(assembly_raw)
            part = next((item for item in assembly.parts if item.id == part_id), None)
            if part is None:
                raise ProjectPackageError(f"AssemblyIR part {part_id} does not exist.")
            model_index = dict(opened.payload.get("models") or {})
            models = model_index.get("models")
            if not isinstance(models, list):
                raise ProjectPackageError("The project model index is invalid: models must be an array.")
            source_model = next((item for item in models if isinstance(item, dict) and item.get("id") == part.model_id), None)
            if source_model is None or source_model.get("model_type") != "step":
                raise ProjectPackageError("Only a part currently backed by retained STEP/STP can be tessellated.")
            source_artifact = read_step_model_artifact(
                project_path, part.model_id, expected_manifest_payload_sha256=expected_manifest,
            )
            source_uri = str(source_model.get("uri", ""))
            outcome = tessellate_step_to_glb(
                source_artifact["artifact"], source_name=Path(source_uri.removeprefix("package:")).name,
            )
            derived_model_id = canonical_uuid(
                "step-visual", outcome.source_sha256, outcome.artifact_sha256, str(source_model["id"]),
            )
            derived_model = ModelReference(
                id=derived_model_id,
                source_id=f"{str(source_model.get('source_id', ''))}:tessellated-visual",
                name=f"{str(source_model.get('name') or part.name)} visual",
                model_type="glb",
                uri=f"package:models/artifacts/{outcome.artifact_name}",
                digest=outcome.artifact_sha256,
                transform=list(source_model.get("transform") or []),
                extensions={"spike.mcad.tessellation": {
                    **outcome.to_dict(), "source_model_id": str(source_model["id"]),
                    "source_uri": source_uri, "visual_only": True, "solver_ready": False,
                }},
            )
            models = [item for item in models if not isinstance(item, dict) or item.get("id") != derived_model_id]
            models.append({key: value for key, value in vars(derived_model).items()})
            model_index.update({"contract": "spike/model-index/v1", "models": models})
            previous_model_id = part.model_id
            part.model_id = derived_model_id
            extensions = dict(part.extensions or {})
            extensions["spike.mcad.tessellation"] = {
                **outcome.to_dict(), "source_model_id": previous_model_id,
                "derived_model_id": derived_model_id, "visual_only": True, "solver_ready": False,
            }
            part.extensions = extensions
            assembly.__post_init__()
            payload = dict(opened.payload)
            payload["assembly_ir"] = assembly.to_dict()
            payload["models"] = model_index
            audit = list(payload.get("audit") or [])
            audit.append({
                "event": "mcad_part_tessellated", "part_id": part.id,
                "source_model_id": previous_model_id, "derived_model_id": derived_model_id,
                "source_sha256": outcome.source_sha256, "derived_sha256": outcome.artifact_sha256,
                "visual_only": True, "solver_ready": False,
            })
            payload["audit"] = audit
            manifest = write_spike_package(
                project_path, payload, profile=str(opened.manifest.get("profile", "portable_project")),
                preserved_members=opened.members,
                model_artifacts={outcome.artifact_name: outcome.artifact_bytes},
                application_version=application_version,
            )
            return {"ok": True, "result": {
                "contract": "spike/mcad-part-tessellation-result/v1",
                "part": next(item for item in assembly.to_dict()["parts"] if item["id"] == part.id),
                "source_model_id": previous_model_id, "derived_model": vars(derived_model),
                "tessellation": outcome.to_dict(), "project_path": str(project_path.resolve()),
                "manifest": manifest,
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError, McadTessellationError) as exc:
            return error_response(
                "SPIKE-BE-IMPORT-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method == "extract_mcad_package_shape_in_project":
        try:
            project_path = Path(str(params.get("project_path", "")))
            if not project_path.is_file():
                raise ProjectPackageError("Open a saved SPIKE project before extracting exact MCAD topology.")
            opened = read_project(project_path, include_members=True)
            if opened.migrated:
                raise ProjectPackageError("Migrate and save the legacy project before extracting exact MCAD topology.")
            expected_manifest = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
            actual_manifest = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
            if not expected_manifest or expected_manifest != actual_manifest:
                raise ProjectPackageError(
                    "The project changed since it was verified; reopen it before exact STEP topology extraction."
                )
            part_id = str(params.get("part_id", "")).strip()
            assembly_raw = opened.payload.get("assembly_ir")
            if not part_id or not isinstance(assembly_raw, dict):
                raise ProjectPackageError("A valid AssemblyIR part_id is required for exact STEP topology extraction.")
            assembly = AssemblyIRV1.from_dict(assembly_raw)
            part = next((item for item in assembly.parts if item.id == part_id), None)
            if part is None:
                raise ProjectPackageError(f"AssemblyIR part {part_id} does not exist.")
            model_index = dict(opened.payload.get("models") or {})
            models = model_index.get("models")
            if not isinstance(models, list):
                raise ProjectPackageError("The project model index is invalid: models must be an array.")
            by_id = {
                str(item.get("id")): item for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            current_model = by_id.get(part.model_id)
            source_model_id = part.model_id if current_model and current_model.get("model_type") == "step" else ""
            tessellation = (part.extensions or {}).get("spike.mcad.tessellation")
            if not source_model_id and isinstance(tessellation, dict):
                source_model_id = str(tessellation.get("source_model_id", "")).strip()
            source_model = by_id.get(source_model_id)
            if source_model is None or source_model.get("model_type") != "step":
                raise ProjectPackageError(
                    "Exact topology extraction requires a retained STEP/STP model owned by the selected part."
                )
            source_artifact = read_step_model_artifact(
                project_path, source_model_id,
                expected_manifest_payload_sha256=expected_manifest,
            )
            source_uri = str(source_model.get("uri", ""))
            outcome = extract_step_package_shape(
                source_artifact["artifact"],
                source_name=Path(source_uri.removeprefix("package:")).name,
            )
            if outcome.source_sha256 != str(source_model.get("digest", "")):
                raise ProjectPackageError("Exact topology extraction did not preserve the retained STEP digest identity.")
            shape_id = canonical_uuid("step", outcome.source_sha256, "package-shape", source_model_id)
            topology_ids = {
                (item["kind"], item["native_persistent_id"]): canonical_uuid(
                    "step", outcome.source_sha256, item["kind"], item["native_persistent_id"],
                )
                for item in outcome.entities
            }
            entities = []
            for item in outcome.entities:
                support = item["support"]
                axis_native_id = support["axis_native_persistent_id"]
                axis_topology_id = (
                    topology_ids.get(("axis", axis_native_id)) if axis_native_id is not None else None
                )
                if axis_native_id is not None and axis_topology_id is None:
                    raise ProjectPackageError("Exact topology extraction returned an unresolved support axis.")
                entities.append({
                    "topology_id": topology_ids[(item["kind"], item["native_persistent_id"])],
                    "kind": item["kind"],
                    "native_persistent_id": item["native_persistent_id"],
                    "fingerprint_sha256": item["fingerprint_sha256"],
                    "support": {
                        "surface_kind": support["surface_kind"],
                        "curve_kind": support["curve_kind"],
                        "axis_topology_id": axis_topology_id,
                    },
                    "geometry": item["geometry"],
                })
            shape = {
                "shape_id": shape_id,
                "part_id": part.id,
                "source_model_id": source_model_id,
                "source_artifact_uri": source_uri,
                "source_sha256": outcome.source_sha256,
                "topology_artifact_uri": f"package:geometry/package-shapes/{outcome.artifact_name}",
                "topology_artifact_sha256": outcome.artifact_sha256,
                "kernel": {
                    "id": outcome.kernel_id,
                    "contract": PACKAGE_SHAPE_KERNEL_V1,
                    "version": outcome.kernel_version,
                },
                "extraction": {
                    "status": "complete",
                    "source_format": "step",
                    "source_model_transform_sha256": model_transform_sha256(source_model.get("transform", [])),
                    "topology_ready": True,
                    "solver_ready": False,
                },
                "entities": entities,
                "extensions": {"spike.mcad.package_shape": {
                    "freecad_version": outcome.freecad_version,
                    "shape_count": outcome.shape_count,
                }},
            }
            existing = opened.payload.get("assembly_package_shapes")
            if existing in (None, {}):
                package_shapes = {
                    "contract": ASSEMBLY_PACKAGE_SHAPES_V1,
                    "assembly_id": assembly.assembly_id,
                    "shapes": [],
                    "constraints": [],
                    "thermal_contact_bindings": [],
                    "electrical_bond_bindings": [],
                    "extensions": {},
                    "metadata": {},
                }
            elif isinstance(existing, dict):
                package_shapes = dict(existing)
            else:
                raise ProjectPackageError("The project package-shape index is invalid.")
            prior_shapes = package_shapes.get("shapes")
            if not isinstance(prior_shapes, list):
                raise ProjectPackageError("The project package-shape index has an invalid shapes array.")
            package_shapes["shapes"] = [
                item for item in prior_shapes
                if not isinstance(item, dict) or item.get("shape_id") != shape_id
            ] + [shape]
            payload = dict(opened.payload)
            payload["assembly_package_shapes"] = package_shapes
            audit = list(payload.get("audit") or [])
            audit.append({
                "event": "mcad_package_shape_extracted",
                "part_id": part.id,
                "source_model_id": source_model_id,
                "shape_id": shape_id,
                "source_sha256": outcome.source_sha256,
                "topology_artifact_sha256": outcome.artifact_sha256,
                "entity_count": outcome.entity_count,
                "topology_ready": True,
                "solver_ready": False,
            })
            payload["audit"] = audit
            claimed_members = {
                str(item.get("topology_artifact_uri", "")).removeprefix("package:")
                for item in package_shapes["shapes"] if isinstance(item, dict)
            }
            claimed_members.update(
                str(item["selector_preview"].get("artifact_uri", "")).removeprefix("package:")
                for item in package_shapes["shapes"]
                if isinstance(item, dict) and isinstance(item.get("selector_preview"), dict)
            )
            preserved_members = {
                name: data for name, data in opened.members.items()
                if not name.startswith("geometry/package-shapes/") or name in claimed_members
            }
            manifest = write_spike_package(
                project_path, payload,
                profile=str(opened.manifest.get("profile", "portable_project")),
                preserved_members=preserved_members,
                package_shape_artifacts={outcome.artifact_name: outcome.artifact_bytes},
                application_version=application_version,
            )
            return {"ok": True, "result": {
                "contract": "spike/mcad-package-shape-extraction-result/v1",
                "part_id": part.id,
                "source_model_id": source_model_id,
                "shape_id": shape_id,
                "topology_artifact_sha256": outcome.artifact_sha256,
                "entity_count": outcome.entity_count,
                "kernel": shape["kernel"],
                "topology_ready": True,
                "solver_ready": False,
                "project_path": str(project_path.resolve()),
                "manifest": manifest,
            }}
        except (OSError, ValueError, TypeError, ProjectPackageError, McadPackageShapeError) as exc:
            return error_response(
                "SPIKE-BE-IMPORT-E-0002", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    if method in {"load_design", "import_design_v2"}:
        path = params.get("path", "")
        if not path:
            return {"ok": False, "error": "A design path is required."}
        try:
            if method == "import_design_v2":
                result = import_design(path, str(params.get("format_hint", "")), with_report=True, options=params.get("options"))
                if params.get("include_snapshot"):
                    legacy_design = DesignIRV2.from_dict(result["design"]).to_v1().to_dict()
                    if params.get("snapshot_only"):
                        # Keep canonical v2 authoritative for persistence, but
                        # avoid serializing large ODB provenance/geometry three
                        # times. The source digest plus stable feature IDs locate
                        # exact raw records in the original package. Artwork is
                        # retained on canonical metadata; the legacy projection
                        # keeps solver/render geometry.
                        import copy
                        canonical = copy.deepcopy(result["design"])
                        canonical_metadata = canonical.get("metadata", {})
                        legacy_metadata = legacy_design.get("metadata", {})
                        raw_legacy_zones = json.dumps(
                            legacy_design.get("zones", []), ensure_ascii=False, separators=(",", ":"),
                        ).encode("utf-8")
                        canonical_metadata.pop("import_report", None)
                        for key in ("odb_artwork", "odb_packages", "odb_subnets", "odb_retained",
                                    "import_report", "manufacturing_drills"):
                            legacy_metadata.pop(key, None)
                        for collection in ("layers", "nets", "tracks", "pads", "vias", "zones", "components"):
                            for entity in legacy_design.get(collection, []):
                                if isinstance(entity, dict):
                                    entity.pop("odb_source", None)
                        # Zones are by far the largest normalized collection and
                        # canonical v2 already carries their complete typed
                        # boundaries. Transport consumers use canonical zones;
                        # omitting the duplicate legacy copy keeps one worker
                        # frame below the desktop limit without losing data.
                        legacy_design["zones"] = []
                        zone_sources = []
                        for zone in canonical.get("zones", []):
                            extensions = zone.get("extensions")
                            if isinstance(extensions, dict):
                                legacy_zone = extensions.get("spike.v1")
                                if isinstance(legacy_zone, dict) and "odb_source" in legacy_zone:
                                    zone_sources.append({"id": zone.get("source_id") or zone.get("id"),
                                                         "odb_source": legacy_zone["odb_source"]})
                                extensions.pop("spike.v1", None)
                        if zone_sources:
                            raw_sources = json.dumps(zone_sources, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                            canonical_metadata["odb_zone_sources"] = {
                                "contract": "spike/odb-source-table/v1", "encoding": "zlib+base64+json",
                                "sha256": hashlib.sha256(raw_sources).hexdigest(), "count": len(zone_sources),
                                "data": base64.b64encode(zlib.compress(raw_sources, level=9)).decode("ascii"),
                            }
                        canonical_metadata["transport_projection"] = {
                            "contract": "spike/odb-transport-projection/v1",
                            "authoritative_odb_artwork": "canonical_design.metadata.odb_artwork",
                            "raw_source_lookup": "source.source_digest + entity.source_id",
                            "legacy_omitted_collections": ["zones"],
                            "legacy_zones_archive": {
                                "contract": "spike/odb-legacy-zones/v1", "encoding": "zlib+base64+json",
                                "sha256": hashlib.sha256(raw_legacy_zones).hexdigest(),
                                "bytes": len(raw_legacy_zones),
                                "count": len(canonical.get("zones", [])),
                                "data": base64.b64encode(zlib.compress(raw_legacy_zones, level=9)).decode("ascii"),
                            },
                        }
                        return {"ok": True, "result": {"snapshot": {
                            "contract": "spike/design-snapshot/v1",
                            "design": legacy_design,
                            "canonical_design": canonical,
                            "report": result["report"],
                        }}}
                    result["snapshot"] = {"contract": "spike/design-snapshot/v1", "design": legacy_design, "canonical_design": result["design"], "report": result["report"]}
                return {"ok": True, "result": result}
            return {"ok": True, "result": import_design(path, str(params.get("format_hint", "")), options=params.get("options"))}
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            return error_response(
                "SPIKE-BE-IMPORT-E-0001", str(exc), error_type=type(exc).__name__,
                operation_id=operation_id(request_id),
            )
    return None
