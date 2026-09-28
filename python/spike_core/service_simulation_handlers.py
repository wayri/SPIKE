# SPDX-License-Identifier: Apache-2.0
"""Model, visualization, thermal, EM-reference, and solver worker handlers."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from .assembly_analysis_scope import attach_scope_provenance, write_case_scope
from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .component_thermal import run_component_thermal
from .board_thermal import run_board_thermal
from .external_engines import prepare_openems_case, run_openems_case
from .models import (
    build_model_manifest,
    export_kicad_scene,
    kicad_scene_capabilities,
    search_model_library,
)
from .openfoam import openfoam_capabilities, prepare_case, run_case
from .openfoam_multiregion import prepare_multiregion_case, prepare_runnable_multiregion_case
from .openfoam_multiregion_execution import MultiRegionExecutionError, probe_v2606_commands, run_multiregion_case
from .openfoam_multiregion_validation import import_v2606_validation_evidence
from .openfoam_polymesh import OpenFoamPolyMeshError, write_polymesh
from .service_helpers import prepare_visual_bundle
from .thermal import ThermalScenario, estimate_compact_thermal, validate_scenario
from .thermal_field_job import execute_thermal_field_job, plan_thermal_field_job


def handle_simulation_request(
    method: Any,
    params: Dict[str, Any],
    *,
    assembly_scope: Dict[str, Any],
    solver_registry: Any,
    thermal_adapter_registry: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Handle model and simulation requests, or return ``None``."""
    if method == "model_manifest":
        design = DesignIR(**params["design"])
        return {"ok": True, "result": build_model_manifest(design.components)}
    if method == "model_library":
        additional_roots = [params["root"]] if params.get("root") else []
        return {
            "ok": True,
            "result": search_model_library(
                params.get("query", ""), int(params.get("limit", 200)), additional_roots,
            ),
        }
    if method == "scene_capabilities":
        return {"ok": True, "result": kicad_scene_capabilities()}
    if method == "prepare_3d_scene":
        return {"ok": True, "result": export_kicad_scene(
            params.get("board_path", ""),
            params.get("output_path", ""),
            int(params.get("timeout_seconds", 180)),
        )}
    if method == "prepare_visual_bundle":
        return {"ok": True, "result": prepare_visual_bundle(params)}
    if method == "thermal_capabilities":
        return {"ok": True, "result": openfoam_capabilities()}
    if method == "validate_thermal":
        return {"ok": True, "result": validate_scenario(ThermalScenario(**params["scenario"]))}
    if method == "estimate_thermal":
        return {"ok": True, "result": estimate_compact_thermal(ThermalScenario(**params["scenario"]))}
    if method == "run_component_thermal":
        return {"ok": True, "result": attach_scope_provenance(run_component_thermal(params), assembly_scope)}
    if method == "run_board_thermal":
        source = params.get("source_kicad_pcb")
        if source is not None:
            if not isinstance(source, str) or len(source.encode("utf-8")) > 32 * 1024 * 1024 or not source.lstrip().startswith("(kicad_pcb"):
                return {"ok": True, "result": {"contract": "spike/board-thermal-result/v1", "status": "blocked",
                    "model_status": "failed", "grid": None, "components": [], "summary": {},
                    "issues": [{"code": "BOARD_THERMAL_SOURCE_INVALID", "severity": "error",
                                "message": "KiCad board source is missing, invalid, or exceeds 32 MiB."}],
                    "provenance": {"solver_id": "spike.layered_board_thermal", "production_qualified": False}}}
            from .kicad_importer import import_kicad_design
            try:
                with tempfile.TemporaryDirectory(prefix="spike-board-thermal-") as temporary:
                    source_path = Path(temporary) / "source.kicad_pcb"
                    source_path.write_text(source, encoding="utf-8")
                    design = import_kicad_design(str(source_path))
            except (OSError, ValueError, RuntimeError, UnicodeError) as exc:
                return {"ok": True, "result": {"contract": "spike/board-thermal-result/v1", "status": "blocked",
                    "model_status": "failed", "grid": None, "components": [], "summary": {},
                    "issues": [{"code": "BOARD_THERMAL_SOURCE_IMPORT_FAILED", "severity": "error", "message": str(exc)}],
                    "provenance": {"solver_id": "spike.layered_board_thermal", "production_qualified": False}}}
        else:
            design = DesignIR(**params["design"])
        return {"ok": True, "result": attach_scope_provenance(run_board_thermal(design, params["request"]), assembly_scope)}
    if method == "plan_thermal_field_job":
        # Solver descriptors come from the worker-owned catalog.  A client may
        # select a solver ID but cannot inject its own qualification claims.
        return {"ok": True, "result": plan_thermal_field_job(params["request"])}
    if method == "execute_thermal_field_job":
        # Adapter objects are injected by the trusted host. A client can select
        # an ID but can never provide executable code or qualification claims.
        return {"ok": True, "result": execute_thermal_field_job(
            params["request"], adapter_registry=thermal_adapter_registry or {},
        )}
    if method == "prepare_thermal_case":
        scenario = ThermalScenario(**params["scenario"])
        output_dir = params.get("output_dir") or tempfile.mkdtemp(prefix="spike-openfoam-")
        result = prepare_case(scenario, output_dir)
        if result.get("case_dir") and result.get("status") != "blocked":
            write_case_scope(result["case_dir"], assembly_scope)
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "prepare_multiregion_thermal_case":
        output_dir = params.get("output_dir") or tempfile.mkdtemp(prefix="spike-openfoam-multiregion-")
        result = prepare_multiregion_case(params["request"], output_dir)
        if result.get("case_dir") and result.get("status") != "blocked":
            write_case_scope(result["case_dir"], assembly_scope)
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "materialize_openfoam_polymesh":
        output_dir = params.get("output_dir") or tempfile.mkdtemp(prefix="spike-openfoam-polymesh-")
        try:
            result = write_polymesh(params["request"], output_dir)
        except (KeyError, TypeError, ValueError, OSError, OpenFoamPolyMeshError) as exc:
            return {"ok": True, "result": {"status": "blocked", "message": str(exc), "qualification": {"production_qualified": False}}}
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "prepare_runnable_multiregion_thermal_case":
        output_dir = params.get("output_dir") or tempfile.mkdtemp(prefix="spike-openfoam-multiregion-runnable-")
        mesh_root = params.get("materialized_mesh_root")
        if not isinstance(mesh_root, str) or not mesh_root:
            return {"ok": True, "result": {"status": "blocked", "message": "materialized_mesh_root is required for runnable multi-region case preparation.", "qualification": {"production_qualified": False}}}
        result = prepare_runnable_multiregion_case(params["request"], output_dir, mesh_root)
        if result.get("case_dir") and result.get("status") == "prepared_runnable_case":
            write_case_scope(result["case_dir"], assembly_scope)
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "probe_openfoam_multiregion_runtime":
        return {"ok": True, "result": probe_v2606_commands()}
    if method == "validate_openfoam_multiregion_case":
        try:
            result = import_v2606_validation_evidence(params["case_dir"], result_record=params.get("result_record"))
        except (KeyError, TypeError, ValueError, OSError, MultiRegionExecutionError) as exc:
            result = {"status": "candidate_evidence_incomplete_or_failed", "candidate_passed": False, "message": str(exc), "qualification": {"production_qualified": False}}
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "run_multiregion_thermal_case":
        if not bool(params.get("allow_experimental", False)):
            result = {
                "status": "blocked", "fields": {},
                "message": "Multi-region OpenFOAM execution requires explicit allow_experimental=true.",
                "qualification": {"production_qualified": False, "field_result_produced": False},
            }
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        try:
            result = run_multiregion_case(
                params["case_dir"],
                timeout_s=int(params.get("timeout_seconds", 3600)),
                memory_limit_mb=int(params.get("memory_limit_mb", 4096)),
                output_limit_bytes=int(params.get("output_limit_bytes", 8 * 1024**3)),
            )
        except (KeyError, TypeError, ValueError, OSError, MultiRegionExecutionError) as exc:
            result = {"status": "failed", "fields": {}, "message": str(exc), "qualification": {"production_qualified": False, "field_result_produced": False}}
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "run_thermal_case":
        result = run_case(
            params["case_dir"],
            timeout_s=int(params.get("timeout_seconds", 3600)),
            memory_limit_mb=int(params.get("memory_limit_mb", 4096)),
            output_limit_bytes=int(params.get("output_limit_bytes", 8 * 1024**3)),
            allow_experimental=bool(params.get("allow_experimental", False)),
        )
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "prepare_openems_case":
        result = prepare_openems_case(
            DesignIR(**params["design"]),
            AnalysisSpec(**params.get("spec", {})),
            params.get("output_dir") or None,
            params.get("options") or {},
        )
        if result.get("case_dir") and result.get("status") not in {"blocked", "failed"}:
            write_case_scope(result["case_dir"], assembly_scope)
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "run_openems_case":
        result = run_openems_case(
            params["case_dir"],
            setup_only=bool(params.get("setup_only", False)),
            timeout_seconds=int(params.get("timeout_seconds", 3600)),
        )
        return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
    if method == "run_analysis":
        spec = AnalysisSpec(**params.get("spec", {}))
        if params.get("design"):
            result = solver_registry.run(DesignIR(**params["design"]), spec).to_dict()
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        result = AnalysisResult(
            analysis_id=spec.analysis_id or str(uuid.uuid4()),
            mode=spec.mode,
            status="blocked",
            model_status="unsupported",
            issues=[ValidationIssue(
                code="DESIGN_CONTEXT_REQUIRED",
                severity="error",
                message="Solver plugins require a normalized design context.",
                suggestion="Load a design or provide a valid DesignIR with the analysis request.",
            )],
            provenance={"worker": "python.spike_core.service", "contract": "spike/v1"},
        )
        return {"ok": True, "result": result.to_dict()}
    return None
