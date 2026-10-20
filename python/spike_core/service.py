"""JSON-line local worker API.
The protocol is deliberately transport-neutral: Tauri can spawn this process,
while a future cloud worker can expose the same request/response shapes over HTTP.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from .kicad_schematic_importer import handle_kicad_schematic_request, KicadSchematicViewError
from .connectivity_view_importer import handle_connectivity_view_request, ConnectivityViewError
from .acceleration import acceleration_catalog
from .capabilities import capabilities
from .capability_ledger import native_capability_ledger
from .benchmarks import run_solver_benchmarks
from .dependencies import dependency_status, verify_lockfile
from .emi import screen_emi_setup, validate_emi_setup
from .environment_profiles import (
    ENVIRONMENT_PROFILE_CONTRACT,
    ENVIRONMENT_PROFILE_VALIDATION_CONTRACT,
    SUPPORTED_DOMAINS,
    EnvironmentProfileError,
    create_user_defined_profile,
    list_environment_profiles,
    materialize_environment_profile as materialize_environment_profile_data,
    validate_environment_profile as validate_environment_profile_data,
)
from .contracts import AnalysisSpec, SpiDeR, ValidationIssue
from .spider_v2 import SpiDeRV2
from .converter_study import converter_capabilities, run_converter_study, validate_converter_study
from .errors import error_envelope
from .convergence import run_mesh_convergence
from .geometry import extract_net_geometry
from .extensions import ExtensionPackageManager, ExtensionRegistry, default_extension_roots
from .service_script_workspace import handle_script_workspace_request
from .emerge_runtime_updates import handle_emerge_update_request, invoke_extension_with_update_guard
from .si_protocol_suites import (
    SiProtocolSuiteError,
    plan_si_protocol_analysis,
    validate_si_protocol_suite,
)
from .si_channel import SiChannelError, analyze_uniform_design_channel
from .si_workflow import run_si_workflow, workflow_catalog
from .si_ibis import parse_ibis
from .si_protocol_test_runner import SiProtocolTestRunnerError, run_si_protocol_test_suite
from .external_engines import external_engine_catalog
from .solver_blocks import handle_solver_blocks
from .solver_plugins import default_solver_registry
from .solver_manager import (
    recommend_emi_nets,
    recommend_solver,
    register_external_solver,
    select_solver,
    solver_manager_catalog,
    tune_solver,
    unregister_external_solver,
)
from .spice_workspace import compose_spice_workspace, validate_spice_workspace
from .spider_api import handle_spider_request
from .service_spider import dispatch_spider_request
from .service_studio_board_coupling import handle_studio_board_cosimulation_request
from .studio_bridge import handle_studio_bridge_request
from .spikes_runtime import handle_worker_method as handle_spikes_worker_method
from .native_mna import run_native_mna, validate_native_mna_request
from .native_circuit_compiler import (
    compile_spice_workspace_to_native_mna,
    run_spice_workspace_native_mna,
)
from .owned_spice_workspace import (
    run_owned_spice_workspace,
    validate_owned_spice_workspace_request,
)
from .field_circuit_cosim import (
    run_iterative_field_circuit_cosimulation,
    validate_field_circuit_request,
)
from .peec_field_provider import NativePeecFieldReductionProvider
from .topology_circuit import bridge_topology_to_analysis_spec, validate_topology_circuit
from .peec_spice_export import (
    import_peec_rlcg,
    list_peec_spice_networks,
    run_staged_hybrid_cosimulation,
)
from .sparselizard_adapter import prepare_sparselizard_case, run_sparselizard_case
from .sparselizard_runtime import detect_sparselizard_runtime
from .sparselizard_validation import evaluate_sparselizard_validation
from .spikes_layout_adapter import (
    SpikesLayoutAdapterError,
    map_layout_results,
    preflight_layout_candidate,
    prepare_native_jobs,
    validate_layout_request,
)
from .layout_metric_registry import (
    LayoutMetricRegistryError,
    negotiate_layout_requirements,
    validate_metric_registry,
    validate_requirements_for_launch,
)
from .preflight import build_mesh_preview, preflight_analysis
from .pdn import optimize_pdn, review_pdn
from .pi_path import validate_pi_path
from .pi_path_circuit import compile_pi_path_to_native_mna, run_pi_path_native_mna
from .power_tree import extract_power_path
from .service_helpers import (
    build_solver_catalog, error_response, export_step, operation_id,
    prepare_visual_bundle,
)
from .worker_protocol import serve_json_lines
from .service_assembly_handlers import handle_assembly_request, prepare_analysis_scope
from .assembly_analysis_scope import attach_scope_provenance
from .service_project import importer_catalog
from .service_project_handlers import handle_project_request
from .service_extension_packages import handle_extension_package_request
from .service_simulation_handlers import handle_simulation_request
from .service_meshing import handle_meshing_request
from .service_assembly_field import handle_assembly_field_request
from .service_engineering_review import validate_design
from .kicad_importer import import_kicad_design as _design_from_kicad
from .external_pi_result_validation import validate_external_pi_multiport
from . import __version__


_solver_registry = default_solver_registry()
_extension_registry = ExtensionRegistry()
_extension_packages = ExtensionPackageManager()
_bundled_extension_root = Path(__file__).resolve().parents[2] / "extensions"
_extension_registry.discover(default_extension_roots(), trusted_roots=[_bundled_extension_root])


def _refresh_extensions(*, revoke_trust: set[str] | None = None) -> None:
    revoked = revoke_trust or set()
    trusted = [item["id"] for item in _extension_registry.catalog()
               if item.get("trusted") and not item.get("bundled") and item["id"] not in revoked]
    _extension_registry.reset()
    _extension_registry.discover(
        default_extension_roots(), trusted_ids=trusted, trusted_roots=[_bundled_extension_root],
    )
def _solver_catalog(*, refresh_external: bool = False) -> list[Dict[str, Any]]:
    return build_solver_catalog(_solver_registry, refresh_external=refresh_external)


_operation_id = operation_id
_error_response = error_response
_export_step = export_step


def handle(request: Dict[str, Any]) -> Dict[str, Any]:
    return dispatch_spider_request(request, _dispatch)


def _dispatch(request: Dict[str, Any]) -> Dict[str, Any]:
    method = request.get("method")
    params = request.get("params", {})
    spider_result = handle_spider_request(method, params)
    if spider_result is not None:
        return {"ok": True, "result": spider_result}
    if method in {"app_update_check", "app_update_download"}:
        from .app_updates import handle_app_update
        return handle_app_update(method, params, request.get("id"))
    if method in {"review_engineering", "quick_engineering_tool"}:
        from .service_engineering_review import handle_engineering_review
        return handle_engineering_review(method, params)
    if method in {"parallel_pool_catalog", "run_parallel_batch"}:
        from .service_parallel_pool import handle_parallel_request
        return handle_parallel_request(method, params, request_id=request.get("id"))
    if isinstance(method, str) and method.startswith("assistant_"):
        from .service_assistant import handle_assistant_request
        response = handle_assistant_request(method, params, request.get("id"))
        if response is not None: return response
    emerge_update_result = handle_emerge_update_request(method, params)
    if emerge_update_result is not None:
        return emerge_update_result
    if method == "health":
        return {"ok": True, "result": {
            "contract": "spike/worker-health/v1",
            "status": "ready",
            "worker_version": __version__,
            "analysis_contract": "spike/v1",
            "protocol": "json-line",
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
        }}
    if method == "capabilities":
        result = capabilities()
        result["solver_plugins"] = _solver_registry.catalog()
        result["acceleration"] = acceleration_catalog()
        result["native_capability_ledger"] = native_capability_ledger()
        return {"ok": True, "result": result}
    if method == "capability_ledger":
        return {"ok": True, "result": native_capability_ledger()}
    spikes_result = handle_spikes_worker_method(method, params)
    if spikes_result is not None:
        return {"ok": True, "result": spikes_result}
    if method == "list_accelerators":
        return {"ok": True, "result": acceleration_catalog()}
    if method == "list_environment_profiles":
        return {"ok": True, "result": {
            "contract": "spike/environment-profile-catalog/v1",
            "profile_contract": ENVIRONMENT_PROFILE_CONTRACT,
            "validation_contract": ENVIRONMENT_PROFILE_VALIDATION_CONTRACT,
            "supported_domains": list(SUPPORTED_DOMAINS),
            "profiles": list_environment_profiles(),
        }}
    if method == "materialize_environment_profile":
        try:
            source = str(params.get("source", "preset")).strip().lower()
            profile_id = str(params.get("profile_id", "")).strip()
            if not profile_id:
                raise ValueError("An environment profile_id is required.")
            if source == "preset":
                overrides = params.get("overrides") or {}
                if not isinstance(overrides, dict):
                    raise TypeError("Environment preset overrides must be an object.")
                profile = materialize_environment_profile_data(profile_id, overrides)
            elif source == "user":
                name = str(params.get("name", "")).strip()
                if not name:
                    raise ValueError("A user environment profile name is required.")
                physical = params.get("physical") or {}
                if not isinstance(physical, dict):
                    raise TypeError("User environment physical inputs must be an object.")
                profile = create_user_defined_profile(
                    profile_id,
                    name,
                    physical,
                    source_title=str(params.get("source_title", "User-supplied environment inputs")),
                    source_locator=str(params.get("source_locator", "")),
                )
            else:
                raise ValueError("Environment profile source must be 'preset' or 'user'.")
            return {"ok": True, "result": profile}
        except (EnvironmentProfileError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "validate_environment_profile":
        try:
            profile = params.get("profile")
            if not isinstance(profile, dict):
                raise TypeError("An environment profile object is required.")
            domains = params.get("domains") or list(SUPPORTED_DOMAINS)
            if not isinstance(domains, list):
                raise TypeError("Environment validation domains must be an array.")
            return {"ok": True, "result": validate_environment_profile_data(profile, domains)}
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "benchmarks":
        return {"ok": True, "result": run_solver_benchmarks()}
    if method == "export_step":
        try:
            return {"ok": True, "result": _export_step(
                str(params.get("source_board", "")),
                str(params.get("source_file", "board.kicad_pcb")),
                params.get("options", {}),
            )}
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "list_solvers":
        return {"ok": True, "result": {
            "contract": "spike/solver-catalog/v1",
            "solvers": _solver_catalog(refresh_external=bool(params.get("refresh", False))),
        }}
    if method == "list_external_engines":
        return {"ok": True, "result": external_engine_catalog(refresh=bool(params.get("refresh", False)))}
    if method == "solver_blocks": return handle_solver_blocks(params)
    if method == "solver_manager":
        return {"ok": True, "result": solver_manager_catalog(
            _solver_registry.catalog(), refresh=bool(params.get("refresh", False)),
        )}
    if method == "sparselizard_runtime_status":
        return {"ok": True, "result": detect_sparselizard_runtime()}
    if method == "sparselizard_validation_status":
        return {"ok": True, "result": evaluate_sparselizard_validation(
            params.get("evidence_root") or None,
        )}
    if method == "recommend_solver":
        return {"ok": True, "result": recommend_solver(str(params.get("workload_id", "")), _solver_registry.catalog())}
    if method == "select_solver":
        try:
            return {"ok": True, "result": select_solver(
                str(params.get("workload_id", "")),
                str(params.get("solver_id", "")),
                _solver_registry.catalog(),
                refresh=bool(params.get("refresh", False)),
            )}
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "register_external_solver":
        return {"ok": True, "result": register_external_solver(
            str(params.get("engine_id", "")), str(params.get("path", "")), _solver_registry.catalog(),
        )}
    if method == "unregister_external_solver":
        return {"ok": True, "result": unregister_external_solver(
            str(params.get("engine_id", "")), _solver_registry.catalog(),
        )}
    if method == "tune_solver":
        return {"ok": True, "result": tune_solver(
            str(params.get("target_id", "")), params.get("values") or {}, _solver_registry.catalog(),
        )}
    if method == "recommend_emi_nets":
        return {"ok": True, "result": recommend_emi_nets(params.get("net_metrics") or [])}
    if method == "validate_si_protocol_suite":
        try:
            suite = params.get("suite")
            if not isinstance(suite, dict):
                raise SiProtocolSuiteError("A protocol-suite object is required.")
            return {"ok": True, "result": validate_si_protocol_suite(suite)}
        except (SiProtocolSuiteError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "plan_si_protocol_analysis":
        try:
            suite = params.get("suite")
            available = params.get("available_capabilities") or []
            if not isinstance(suite, dict) or not isinstance(available, list):
                raise SiProtocolSuiteError("suite must be an object and available_capabilities must be an array.")
            return {"ok": True, "result": plan_si_protocol_analysis(suite, available)}
        except (SiProtocolSuiteError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"run_si_workflow", "si_workflow_catalog", "inspect_si_ibis"}:
        try:
            if method == "si_workflow_catalog":
                result = workflow_catalog()
            elif method == "inspect_si_ibis":
                result = parse_ibis(params["text"], params.get("name", "model.ibs"))
            else:
                result = run_si_workflow(params["request"], params.get("design"))
            return {"ok": True, "result": result}
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "run_si_uniform_channel":
        try:
            design = SpiDeRV2.from_dict(params["design"])
            channel_request = params.get("request") or {}
            if not isinstance(channel_request, dict):
                raise SiChannelError("SI channel request must be an object.")
            return {"ok": True, "result": analyze_uniform_design_channel(design, channel_request)}
        except (KeyError, SiChannelError, TypeError, ValueError) as exc:
            return _error_response(
                "SPIKE-BE-SOLVER-E-0001",
                str(exc),
                operation_id=_operation_id(request.get("id")),
                context={"method": method, "capability": "si.quasi_tem_extraction"},
                error_type=type(exc).__name__,
            )
    if method == "run_si_protocol_test_suite":
        try:
            design = SpiDeRV2.from_dict(params["design"])
            suite_request = params.get("request") or {}
            if not isinstance(suite_request, dict):
                raise SiProtocolTestRunnerError("SI protocol test-suite request must be an object.")
            return {"ok": True, "result": run_si_protocol_test_suite(design, suite_request)}
        except (KeyError, SiChannelError, SiProtocolTestRunnerError, TypeError, ValueError) as exc:
            return _error_response(
                "SPIKE-BE-SOLVER-E-0001",
                str(exc),
                operation_id=_operation_id(request.get("id")),
                context={"method": method, "capability": "si.protocol_test_suite"},
                error_type=type(exc).__name__,
            )
    extension_package_result = handle_extension_package_request(
        method, params, _extension_registry, _extension_packages, _refresh_extensions,
    )
    if extension_package_result is not None:
        return extension_package_result
    if method == "discover_extensions":
        roots = params.get("roots") or [str(path) for path in default_extension_roots()]
        diagnostics = _extension_registry.discover(roots)
        browser = _extension_packages.browse(_extension_registry)
        return {"ok": True, "result": {
            "contract": "spike/extension-catalog/v1",
            "extensions": browser["extensions"],
            "diagnostics": diagnostics,
        }}
    if method == "invoke_extension":
        return invoke_extension_with_update_guard(_extension_registry, params)
    if method == "trust_extension":
        try:
            return {"ok": True, "result": _extension_registry.trust(str(params.get("extension_id", "")))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    trusted_extensions = ([item["id"] for item in _extension_registry.catalog() if item["trusted"]]
                          if method in {"run_python_script", "start_python_debug"} else [])
    script_workspace_response = handle_script_workspace_request(method, params, trusted_extension_ids=trusted_extensions)
    if script_workspace_response is not None:
        return script_workspace_response
    if method == "dependencies":
        return {"ok": True, "result": {"runtime": dependency_status(), "lockfile": verify_lockfile()}}
    if method == "list_importers":
        return {"ok": True, "result": {
            "contract": "spike/importer-catalog/v1",
            "importers": importer_catalog(),
        }}
    field_response = handle_assembly_field_request(method, params, request_id=request.get("id"))
    if field_response is not None:
        return field_response
    meshing_response = handle_meshing_request(method, params, request_id=request.get("id"))
    if meshing_response is not None:
        return meshing_response
    assembly_response = handle_assembly_request(
        method,
        params,
        request_id=request.get("id"),
    )
    if assembly_response is not None:
        return assembly_response
    project_response = handle_project_request(
        method,
        params,
        request_id=request.get("id"),
        application_version=__version__,
    )
    if project_response is not None:
        return project_response
    assembly_scope, scope_error = prepare_analysis_scope(method, params, request.get("id"))
    if scope_error is not None:
        return scope_error
    studio_bridge_response = handle_studio_bridge_request(method, params, Path(__file__).resolve().parents[2])
    if studio_bridge_response is not None:
        return studio_bridge_response
    studio_feedback_response = handle_studio_board_cosimulation_request(
        method, {key: value for key, value in params.items() if key != "assembly_scope"}, request_id=request.get("id"),
    )
    if studio_feedback_response is not None:
        if studio_feedback_response.get("ok") and "result" in studio_feedback_response:
            studio_feedback_response["result"] = attach_scope_provenance(studio_feedback_response["result"], assembly_scope)
        return studio_feedback_response
    if method in {"emi_preflight", "emi_screen"}:
        try:
            design = SpiDeR(**params["design"])
            operation = validate_emi_setup if method == "emi_preflight" else screen_emi_setup
            result = operation(design, params.get("setup") or {}, _solver_registry.catalog())
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "validate_design":
        design = SpiDeR(**params["design"])
        return {"ok": True, "result": validate_design(design)}
    if method == "preview_mesh":
        design = SpiDeR(**params["design"])
        spec = AnalysisSpec(**params.get("spec", {}))
        return {"ok": True, "result": build_mesh_preview(design, spec)}
    if method == "preflight_analysis":
        design = SpiDeR(**params["design"])
        spec = AnalysisSpec(**params.get("spec", {}))
        return {"ok": True, "result": preflight_analysis(design, spec, _solver_registry.catalog())}
    if method == "run_preflighted_analysis":
        design = SpiDeR(**params["design"])
        spec = AnalysisSpec(**params.get("spec", {}))
        preflight = preflight_analysis(design, spec, _solver_registry.catalog())
        compact_preflight = {
            key: value for key, value in preflight.items() if key != "mesh"
        }
        result = None
        if preflight.get("can_solve"):
            result = attach_scope_provenance(
                _solver_registry.run(design, spec).to_dict(), assembly_scope,
            )
        return {"ok": True, "result": {
            "contract": "spike/preflighted-analysis/v1",
            "status": "completed" if result and result.get("status") == "completed" else "blocked",
            "preflight": compact_preflight,
            "analysis_result": result,
        }}
    if method == "mesh_convergence":
        design = SpiDeR(**params["design"])
        spec = AnalysisSpec(**params.get("spec", {}))
        options = params.get("options", {})
        return {"ok": True, "result": run_mesh_convergence(
            design,
            spec,
            _solver_registry.run,
            levels=options.get("levels", (2.0, 1.0, 0.5)),
            metric_tolerance=options.get("metric_tolerance"),
            density_tolerance=options.get("density_tolerance"),
            minimum_levels=options.get("minimum_levels", 3),
            stop_when_converged=options.get("stop_when_converged", True),
        )}
    if method == "pdn_review":
        return {"ok": True, "result": review_pdn(
            params["result"],
            float(params["target_ohm"]),
            str(params.get("net", "")),
            params.get("candidates", []),
        )}
    if method == "pdn_optimize":
        return {"ok": True, "result": optimize_pdn(
            params["result"],
            float(params["target_ohm"]),
            str(params.get("net", "")),
            params.get("capacitor_library", []),
            params.get("constraints", {}),
        )}
    if method in {
        "validate_layout_evaluation",
        "validate_layout_metric_registry",
        "negotiate_layout_requirements",
        "preflight_layout_candidate",
        "prepare_layout_native_jobs",
        "map_layout_evaluation_results",
    }:
        try:
            layout_request = params.get("request")
            if method == "validate_layout_evaluation":
                result = validate_layout_request(layout_request)
            elif method == "validate_layout_metric_registry":
                result = validate_metric_registry(params.get("registry")).to_dict()
            elif method == "negotiate_layout_requirements":
                normalized = validate_layout_request(layout_request)
                result = asdict(negotiate_layout_requirements(
                    normalized,
                    params.get("registry"),
                    batch_size=params.get("batch_size", 1),
                    incremental=params.get("incremental", False),
                    change_kind=params.get("change_kind"),
                ))
            elif method == "preflight_layout_candidate":
                result = preflight_layout_candidate(
                    layout_request,
                    params.get("candidate"),
                    baseline=params.get("baseline"),
                    parent=params.get("parent"),
                )
            elif method == "prepare_layout_native_jobs":
                normalized = validate_layout_request(layout_request)
                validate_requirements_for_launch(
                    normalized,
                    params.get("registry"),
                    batch_size=params.get("batch_size", 1),
                    incremental=params.get("incremental", False),
                    change_kind=params.get("change_kind"),
                )
                preflight_layout_candidate(
                    normalized,
                    params.get("candidate"),
                    baseline=params.get("baseline"),
                    parent=params.get("parent"),
                )
                candidate_v2 = SpiDeRV2.from_dict(params["candidate"])
                result = prepare_native_jobs(normalized, candidate_v2.to_v1())
            else:
                result = map_layout_results(
                    layout_request,
                    params.get("native_results", {}),
                    external_results=params.get("external_results"),
                )
            return {"ok": True, "result": result}
        except SpikesLayoutAdapterError as exc:
            response = _error_response(
                "SPIKE-BE-IPC-E-0001",
                str(exc),
                operation_id=_operation_id(request.get("id")),
                context={"method": method, "layout_error_code": exc.code},
                error_type=type(exc).__name__,
            )
            response["layout_error_code"] = exc.code
            return response
        except LayoutMetricRegistryError as exc:
            response = _error_response(
                "SPIKE-BE-IPC-E-0001",
                str(exc),
                operation_id=_operation_id(request.get("id")),
                context={"method": method, "layout_error_code": exc.code},
                error_type=type(exc).__name__,
            )
            response["layout_error_code"] = exc.code
            return response
        except (KeyError, TypeError, ValueError) as exc:
            return _error_response(
                "SPIKE-BE-IPC-E-0001",
                "Layout worker parameters are missing or malformed.",
                operation_id=_operation_id(request.get("id")),
                detail=str(exc)[:4096],
                context={"method": method},
                error_type=type(exc).__name__,
            )
    if method == "import_external_pi_multiport":
        return {"ok": True, "result": validate_external_pi_multiport(
            params["result"],
            expected_engine_id=str(params.get("expected_engine_id", "")),
            expected_frequencies_hz=params.get("expected_frequencies_hz"),
        )}
    if method in {"validate_spice_workspace", "compose_spice_workspace"}:
        try:
            design = SpiDeR(**params["design"])
            workspace = params.get("workspace") or {}
            operation = validate_spice_workspace if method == "validate_spice_workspace" else compose_spice_workspace
            return {"ok": True, "result": operation(workspace, design)}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"validate_native_mna", "run_native_mna"}:
        try:
            circuit_request = params.get("request") or {}
            operation = validate_native_mna_request if method == "validate_native_mna" else run_native_mna
            return {"ok": True, "result": operation(circuit_request)}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"compile_spice_workspace_native_mna", "run_spice_workspace_native_mna"}:
        try:
            design = SpiDeR(**params["design"])
            operation = (
                compile_spice_workspace_to_native_mna
                if method == "compile_spice_workspace_native_mna"
                else run_spice_workspace_native_mna
            )
            result = operation(
                params.get("workspace") or {},
                design,
                resource_limits=params.get("resource_limits"),
            )
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"validate_owned_spice_workspace", "run_owned_spice_workspace"}:
        try:
            design = SpiDeR(**params["design"])
            circuit_request = params.get("request") or {}
            operation = (
                validate_owned_spice_workspace_request
                if method == "validate_owned_spice_workspace"
                else run_owned_spice_workspace
            )
            result = operation(circuit_request, design)
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
            return _error_response(
                "SPIKE-BE-SPICE-E-0054", str(exc), error_type=type(exc).__name__,
                operation_id=_operation_id(request.get("id")),
            )
    if method == "validate_field_circuit_cosimulation":
        return {"ok": True, "result": validate_field_circuit_request(params.get("request") or {})}
    if method == "run_field_circuit_cosimulation":
        try:
            design = SpiDeR(**params["design"])
            field_spec = AnalysisSpec(**params["field_analysis_spec"])
            provider = NativePeecFieldReductionProvider(design, field_spec)
            result = run_iterative_field_circuit_cosimulation(
                design,
                params.get("workspace") or {},
                params.get("request") or {},
                provider,
            )
            return {"ok": True, "result": attach_scope_provenance(result, assembly_scope)}
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return _error_response(
                "SPIKE-BE-SPICE-E-0043",
                str(exc),
                error_type=type(exc).__name__,
                operation_id=_operation_id(request.get("id")),
            )
    if method in {"converter_capabilities", "validate_converter_study", "run_converter_study"}:
        try:
            if method == "converter_capabilities":
                result = converter_capabilities()
            else:
                design = SpiDeR(**params["design"])
                study = params.get("study") or {}
                if method == "validate_converter_study":
                    result = validate_converter_study(study, design)
                else:
                    result = run_converter_study(
                        design,
                        study,
                        params.get("extraction_result"),
                        timeout_seconds=int(params.get("timeout_seconds", 120)),
                    )
            return {"ok": True, "result": result}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"validate_topology_circuit", "bridge_topology_to_analysis_spec"}:
        try:
            design = SpiDeR(**params["design"])
            topology = params.get("topology") or {}
            if method == "validate_topology_circuit":
                result = validate_topology_circuit(topology, design)
            else:
                result = bridge_topology_to_analysis_spec(
                    topology,
                    design,
                    AnalysisSpec(**params.get("spec", {})),
                )
            return {"ok": True, "result": result}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "validate_pi_path":
        try:
            return {"ok": True, "result": validate_pi_path(
                params.get("path") or {},
                SpiDeR(**params["design"]),
                str(params.get("mode", "dc")),
            )}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"compile_pi_path_native_mna", "run_pi_path_native_mna"}:
        try:
            design = SpiDeR(**params["design"])
            spec = AnalysisSpec(**params["spec"])
            operation = (
                compile_pi_path_to_native_mna
                if method == "compile_pi_path_native_mna"
                else run_pi_path_native_mna
            )
            return {"ok": True, "result": operation(
                design,
                spec,
                params.get("extraction_result") or {},
                params.get("segment_mappings") or [],
                resource_limits=params.get("resource_limits"),
            )}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method in {"list_peec_spice_networks", "import_peec_rlcg", "run_hybrid_cosimulation"}:
        try:
            if method == "list_peec_spice_networks":
                result = list_peec_spice_networks(params["extraction_result"])
            elif method == "import_peec_rlcg":
                result = import_peec_rlcg(
                    params["extraction_result"],
                    params["workspace"],
                    params.get("mappings", []),
                )
            else:
                result = run_staged_hybrid_cosimulation(
                    SpiDeR(**params["design"]),
                    params["extraction_result"],
                    params["workspace"],
                    params.get("mappings", []),
                    timeout_seconds=int(params.get("timeout_seconds", 120)),
                )
            return {"ok": True, "result": result}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "prepare_sparselizard_case":
        try:
            return {"ok": True, "result": prepare_sparselizard_case(
                SpiDeR(**params["design"]),
                AnalysisSpec(**params["spec"]),
                params["output_dir"],
                solver_geometry=params.get("solver_geometry"),
                ports=params.get("ports"),
            )}
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "run_sparselizard_case":
        try:
            return {"ok": True, "result": run_sparselizard_case(
                params["case_dir"],
                executable=params.get("executable"),
                timeout_s=int(params.get("timeout_s", 3600)),
                memory_limit_mb=int(params.get("memory_limit_mb", 4096)),
            )}
        except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    if method == "extract_net_geometry":
        design = SpiDeR(**params["design"])
        return {"ok": True, "result": extract_net_geometry(design, params.get("net_name", ""))}
    if method == "extract_power_path":
        try:
            design = SpiDeR(**params["design"])
            return {"ok": True, "result": extract_power_path(
                design,
                params.get("source"),
                params.get("sink"),
                ground_nets=params.get("ground_nets"),
            )}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "type": type(exc).__name__}
    # Retain this compatibility seam so existing embedders can patch the
    # public service symbol without reaching into the split handler module.
    if method == "prepare_visual_bundle":
        return {"ok": True, "result": prepare_visual_bundle(params)}
    try:
        schematic = handle_kicad_schematic_request(method, params)
        if schematic is None:
            schematic = handle_connectivity_view_request(method, params)
        if schematic is not None:
            return {"ok": True, "result": schematic}
    except (KicadSchematicViewError, ConnectivityViewError, OSError, ValueError, TimeoutError, subprocess.TimeoutExpired, UnicodeError) as exc:
        return _error_response("SPIKE-BE-IPC-E-0001", str(exc), context={"method": method}, error_type=type(exc).__name__)
    simulation_response = handle_simulation_request(
        method, params, assembly_scope=assembly_scope, solver_registry=_solver_registry,
    )
    if simulation_response is not None:
        return simulation_response
    return _error_response(
        "SPIKE-BE-IPC-E-0002",
        f"Unknown worker method: {method}",
        operation_id=_operation_id(request.get("id")),
        context={"method": method},
        error_type="UnknownWorkerMethod",
    )
def main() -> int:
    return serve_json_lines(handle, __version__)


if __name__ == "__main__":
    raise SystemExit(main())
