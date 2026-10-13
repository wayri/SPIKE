# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound visual preparation for one retained assembly design."""

from __future__ import annotations

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Mapping

from .errors import error_envelope
from .project_model_artifacts import read_project_source_artifact, read_step_model_artifact
from .project_package import ProjectPackageError, read_project
from .service_helpers import prepare_visual_bundle
from .models import automatic_component_model_overrides
from .spider_v2 import SpiDeRV2


def _retained_design(payload: Mapping[str, Any], design_id: str) -> Dict[str, Any]:
    retained = payload.get("assembly_designs")
    designs = retained.get("designs") if isinstance(retained, Mapping) else None
    if not isinstance(designs, list):
        raise ProjectPackageError("The project does not retain an assembly design set.")
    for candidate in designs:
        if isinstance(candidate, Mapping) and candidate.get("design_id") == design_id:
            return SpiDeRV2.from_dict(candidate).to_dict()
    raise ProjectPackageError(f"The requested assembly design is not retained: {design_id}")


def _design_snapshot(design: Mapping[str, Any]) -> Dict[str, Any]:
    canonical = SpiDeRV2.from_dict(design)
    canonical_payload = canonical.to_dict()
    return {
        "contract": "spike/design-snapshot/v1",
        "design": canonical.to_v1(allow_unprojected_arcs=True).to_dict(),
        "canonical_design": canonical_payload,
        "report": {"issues": canonical_payload["issues"]},
    }


def _model_coverage(design: Mapping[str, Any], source_board: str) -> Dict[str, int]:
    components = [row for row in design.get("components", []) if isinstance(row, Mapping)]
    assigned = sum(bool(row.get("model_ids")) for row in components)
    references = len(re.findall(r'\(model\s+"([^"]+)"', source_board))
    return {
        "component_count": len(components),
        "model_assigned_component_count": assigned,
        "source_model_reference_count": references,
    }


def _stage_packaged_step_overrides(
    project_path: Path, expected_manifest: str, payload: Mapping[str, Any],
    design: Mapping[str, Any], source_board: str, root: Path,
) -> Dict[str, str]:
    """Stage manifest-verified STEP artifacts explicitly referenced by this board."""
    source_references = set(re.findall(r'\(model\s+"([^"]+)"', source_board))
    model_index = payload.get("models") if isinstance(payload.get("models"), Mapping) else {}
    indexed = {str(row.get("id")): row for row in model_index.get("models", []) if isinstance(row, Mapping)}
    design_models = {str(row.get("id")): row for row in design.get("models", []) if isinstance(row, Mapping)}
    requested = {
        model_id for component in design.get("components", []) if isinstance(component, Mapping)
        for model_id in component.get("model_ids", []) if isinstance(model_id, str)
    }
    if len(requested) > 256:
        raise ProjectPackageError("The retained design references too many packaged component models.")
    overrides: Dict[str, str] = {}
    remaining = 128 * 1024 * 1024
    for position, model_id in enumerate(sorted(requested)):
        index_model, source_model = indexed.get(model_id), design_models.get(model_id)
        if not index_model or not source_model or index_model.get("model_type") != "step":
            continue
        reference = str(source_model.get("uri", ""))
        if not reference or reference not in source_references:
            continue
        if remaining <= 0:
            raise ProjectPackageError("Packaged component models exceed the assembly visual byte budget.")
        artifact = read_step_model_artifact(
            project_path, model_id, expected_manifest_payload_sha256=expected_manifest,
            max_total_bytes=remaining,
        )
        data = bytes(artifact["artifact"])
        remaining -= len(data)
        existing = overrides.get(reference)
        if existing:
            if Path(existing).read_bytes() != data:
                raise ProjectPackageError(
                    f"Retained models assign conflicting packaged artifacts to source reference: {reference}"
                )
            continue
        staged = root / f"model-{position}.step"
        staged.write_bytes(data)
        overrides[reference] = str(staged)
    return overrides


def _visual_stage_diagnostic(stage: str, error: Exception) -> Dict[str, Any]:
    detail = str(error).strip() or "The exporter did not provide a diagnostic."
    return error_envelope(
        "SPIKE-BE-VIEW-E-0001",
        message=f"The {stage} visual preparation stage failed.",
        detail=f"{type(error).__name__}: {detail}",
        context={"stage": stage},
    )


def prepare_assembly_design_visual_bundle(params: Dict[str, Any]) -> Dict[str, Any]:
    """Read the exact retained source for ``design_id`` and prepare its visuals."""

    required = {"project_path", "expected_manifest_payload_sha256", "design_id", "stage"}
    if not required.issubset(params) or set(params) - required - {"component_model_overrides"}:
        raise ProjectPackageError(
            "Assembly design visual preparation requires exactly project_path, "
            "expected_manifest_payload_sha256, design_id, and stage."
        )
    project_path = Path(str(params["project_path"]))
    expected_manifest = str(params["expected_manifest_payload_sha256"]).strip().lower()
    design_id = str(params["design_id"]).strip()
    stage = str(params["stage"]).strip()
    component_overrides = params.get("component_model_overrides", {})
    if not isinstance(component_overrides, dict) or len(component_overrides) > 10000 or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in component_overrides.items()
    ):
        raise ProjectPackageError("Component model replacements must be a bounded reference/path map.")
    if not project_path.is_file():
        raise ProjectPackageError("The selected SPIKE project does not exist.")
    if not design_id:
        raise ProjectPackageError("An assembly design identity is required.")
    if stage not in {"source", "layout", "board", "components", "ready"}:
        raise ProjectPackageError(
            "Assembly design visual stage must be source, layout, board, components, or ready."
        )

    opened = read_project(project_path)
    actual_manifest = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if expected_manifest != actual_manifest:
        raise ProjectPackageError(
            "The project package changed after its opened manifest identity; reopen it before loading assembly visuals."
        )
    design = _retained_design(opened.payload, design_id)
    source = design.get("source") if isinstance(design.get("source"), Mapping) else {}
    artifact_uri = str(source.get("artifact_path", ""))
    source_digest = str(source.get("source_digest", ""))
    if not artifact_uri:
        raise ProjectPackageError(f"The retained assembly design has no packaged source artifact: {design_id}")
    source_bytes = read_project_source_artifact(
        project_path,
        artifact_uri,
        expected_manifest_payload_sha256=expected_manifest,
        expected_source_sha256=source_digest,
    )
    try:
        source_board = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectPackageError("The retained assembly design source is not UTF-8 text.") from exc
    source_file = Path(artifact_uri.removeprefix("package:")).name
    coverage = _model_coverage(design, source_board)
    source_result = {
        "design_id": design_id,
        "source_digest": source_digest,
        "source_file": source_file,
        "source_board": source_board,
        "snapshot": _design_snapshot(design),
        "quality": coverage,
    }
    if stage == "source":
        return source_result
    if stage in {"components", "ready"}:
        component_overrides = {**automatic_component_model_overrides(source_board), **component_overrides}
    if stage == "components" and coverage["source_model_reference_count"] == 0 and not component_overrides:
        raise ProjectPackageError(
            "The retained board has no source 3D model assignments "
            f"(0 of {coverage['component_count']} components); component geometry cannot be exported."
        )
    with tempfile.TemporaryDirectory(prefix="spike-assembly-models-") as directory:
        overrides = _stage_packaged_step_overrides(
            project_path, expected_manifest, opened.payload, design, source_board, Path(directory),
        )
        if stage == "ready":
            bundles: Dict[str, Any] = {}
            stage_errors: Dict[str, str] = {}
            stage_diagnostics: Dict[str, Dict[str, Any]] = {}
            requests = {
                ready_stage: {
                    "source_file": source_file,
                    "source_board": source_board,
                    "stage": ready_stage,
                }
                for ready_stage in ("layout", "board")
            }
            if coverage["source_model_reference_count"] or component_overrides:
                requests["components"] = {
                    "source_file": source_file,
                    "source_board": source_board,
                    "stage": "components",
                    "component_model_overrides": component_overrides,
                    **({"model_overrides": overrides} if overrides else {}),
                }
            # KiCad starts one isolated process per stage and every payload owns
            # a separate temporary directory. Running these independent exports
            # together removes their serial wall-time without sharing mutable
            # artifacts or weakening per-stage validation.
            with ThreadPoolExecutor(
                max_workers=len(requests), thread_name_prefix="spike-assembly-visual",
            ) as executor:
                futures = {
                    ready_stage: executor.submit(prepare_visual_bundle, request)
                    for ready_stage, request in requests.items()
                }
                # Consume in request order so response maps and diagnostics stay
                # deterministic even though completion order is intentionally not.
                for ready_stage, future in futures.items():
                    try:
                        bundles[ready_stage] = future.result()
                    except Exception as exc:  # Retain successful optional stages.
                        diagnostic = _visual_stage_diagnostic(ready_stage, exc)
                        stage_errors[ready_stage] = diagnostic["detail"].partition(": ")[2]
                        stage_diagnostics[ready_stage] = diagnostic
            for bundle in bundles.values():
                quality = bundle.get("quality") if isinstance(bundle.get("quality"), Mapping) else {}
                bundle["quality"] = {**quality, **coverage}
            return {
                "contract": "spike/assembly-visual-ready/v1",
                "status": "ready_with_errors" if stage_errors else "ready",
                "manifest_payload_sha256": actual_manifest,
                "source": source_result,
                "bundles": bundles,
                "stage_errors": stage_errors,
                "stage_diagnostics": stage_diagnostics,
                "recovery": {
                    "preserved_stages": list(bundles),
                    "retryable_stages": list(stage_errors),
                    "reopen_project_required": False,
                },
                "skipped_stages": ([] if coverage["source_model_reference_count"] or component_overrides else ["components"]),
            }
        result = prepare_visual_bundle({
            "source_file": source_file,
            "source_board": source_board,
            "stage": stage,
            "component_model_overrides": component_overrides,
            **({"model_overrides": overrides} if overrides else {}),
        })
        quality = result.get("quality") if isinstance(result.get("quality"), Mapping) else {}
        result["quality"] = {
            **quality, **coverage,
            "component_geometry_scene_loaded": bool(
                isinstance(result.get("scenes"), Mapping) and result["scenes"].get("components")
            ),
        }
        return result
