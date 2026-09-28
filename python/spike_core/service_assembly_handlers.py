"""Worker handlers for CAD-neutral assembly operations."""

from __future__ import annotations

from typing import Any, Dict
import tempfile
from pathlib import Path

from .assembly_analysis_scope import AssemblyAnalysisScopeError, scope_from_params, validate_assembly_analysis_scope, validate_case_scope
from .assembly_resources import estimate_assembly_resources
from .contracts import DesignIR
from .multiboard_analysis import MultiboardAnalysisError, plan_multiboard_analysis
from .multiboard_execution import (
    MultiboardExecutionError,
    bind_coupled_reduced_network,
    compile_harness_electrical_network,
    run_independent_si_batch,
)
from .service_helpers import error_response, operation_id
from .harness_authoring import plan_harnesses
from .harness_pi import run_harness_pi


ASSEMBLY_SCOPED_METHODS = {
    "preview_mesh", "preflight_analysis", "mesh_convergence", "run_analysis", "run_preflighted_analysis", "emi_preflight", "emi_screen",
    "validate_spice_workspace", "compose_spice_workspace", "compile_spice_workspace_native_mna",
    "run_spice_workspace_native_mna", "run_field_circuit_cosimulation", "validate_converter_study",
    "run_converter_study", "validate_topology_circuit", "bridge_topology_to_analysis_spec", "validate_pi_path",
    "compile_pi_path_native_mna", "run_pi_path_native_mna", "run_hybrid_cosimulation", "prepare_sparselizard_case",
    "extract_net_geometry", "extract_power_path", "validate_thermal", "estimate_thermal", "prepare_thermal_case",
    "run_thermal_case", "run_component_thermal", "run_board_thermal",
    "prepare_openems_case", "run_openems_case",
}


def prepare_analysis_scope(method: str, params: Dict[str, Any], request_id: Any) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    if method not in ASSEMBLY_SCOPED_METHODS:
        return None, None
    try:
        design = DesignIR(**params["design"]) if params.get("design") else None
        scope = scope_from_params(params, design)
        if method in {"run_thermal_case", "run_openems_case"}:
            validate_case_scope(params["case_dir"], scope)
        return scope, None
    except (AssemblyAnalysisScopeError, KeyError, TypeError, ValueError) as exc:
        return None, error_response(
            "SPIKE-BE-IPC-E-0001", "The requested assembly analysis scope is invalid or unsupported.",
            operation_id=operation_id(request_id), detail=str(exc), context={"method": method, "boundary": "assembly_analysis_scope"},
            error_type=type(exc).__name__,
        )


def handle_assembly_request(
    method: str,
    params: Dict[str, Any],
    *,
    request_id: Any = None,
) -> Dict[str, Any] | None:
    """Handle assembly-scoped worker methods or return ``None``.

    Resource admission is intentionally separate from solver selection and
    validation. A blocked estimate is a successful, inspectable result; only a
    malformed request is returned as a worker error.
    """

    if method not in {
        "estimate_assembly_resources", "validate_assembly_analysis_scope", "plan_multiboard_analysis",
        "run_multiboard_si_independent_batch", "compile_multiboard_harness_network",
        "bind_multiboard_coupled_reduced_network",
        "plan_assembly_harnesses",
        "run_harness_pi",
        "generate_tetrahedral_mesh",
    }:
        return None
    try:
        if method == "generate_tetrahedral_mesh":
            from .gmsh_occ_runtime import run_occ_case
            if set(params) - {"request", "timeout_s", "memory_limit_mb"}:
                raise ValueError("Unexpected tetrahedral meshing parameters.")
            with tempfile.TemporaryDirectory(prefix="spike-tetra-") as directory:
                case = Path(directory) / "case"
                try:
                    result = run_occ_case(params.get("request") or {}, case,
                                          timeout_s=params.get("timeout_s", 180),
                                          memory_limit_mb=params.get("memory_limit_mb", 2048))
                except RuntimeError as exc:
                    # The temporary case is removed below; retain a bounded diagnostic.
                    log = case / "worker.log"
                    detail = ""
                    if log.is_file() and not log.is_symlink():
                        with log.open("rb") as stream:
                            detail = stream.read(8192).decode("utf-8", errors="replace")
                    raise RuntimeError("Tetrahedral generation failed. " + (detail or str(exc))) from exc
        elif method == "run_harness_pi":
            result = run_harness_pi(params.get("request") or {})
        elif method == "plan_assembly_harnesses":
            result = plan_harnesses(params.get("request") or {})
        elif method == "plan_multiboard_analysis":
            result = plan_multiboard_analysis(params.get("request") or {})
        elif method == "run_multiboard_si_independent_batch":
            result = run_independent_si_batch(params.get("request") or {})
        elif method == "compile_multiboard_harness_network":
            result = compile_harness_electrical_network(params.get("request") or {})
        elif method == "bind_multiboard_coupled_reduced_network":
            result = bind_coupled_reduced_network(params.get("request") or {})
        elif method == "validate_assembly_analysis_scope":
            design = DesignIR(**params["design"]) if params.get("design") else None
            result = validate_assembly_analysis_scope(params.get("assembly_scope") or {}, design)
        else:
            result = estimate_assembly_resources(
                params.get("assembly") or {},
                params.get("designs") or {},
                workload=str(params.get("workload") or ""),
                memory_limit_gb=params.get("memory_limit_gb"),
                cpu_limit=params.get("cpu_limit"),
                physical_memory_bytes=params.get("physical_memory_bytes"),
                machine_fraction=float(params.get("machine_fraction", 0.75)),
            )
    except (MultiboardAnalysisError, MultiboardExecutionError, KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
        return error_response(
            "SPIKE-BE-IPC-E-0001",
            "The assembly request is invalid.",
            operation_id=operation_id(request_id),
            detail=str(exc),
            context={"method": method},
            error_type=type(exc).__name__,
        )
    return {"ok": True, "result": result}
