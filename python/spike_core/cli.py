"""Headless SPIKE interface for local automation, reports, and CI."""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import tempfile
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .batch_report import (
    BATCH_RESULT_CONTRACT,
    REPORT_DATA_CONTRACT,
    BatchReportError,
    normalize_pi_batch_report,
)
from .benchmarks import run_solver_benchmarks
from .contracts import CONTRACT_VERSION, AnalysisSpec, DesignIR
from .design_ir_v2 import DesignIRV2
from .field_circuit_cosim import REQUEST_CONTRACT as FIELD_CIRCUIT_REQUEST_CONTRACT
from .openems_benchmarks import evaluate_mesh_convergence, run_patch_antenna_benchmark
from .pi_release_qualification import load_json_report, qualify_pi_release
from .project_package import PROJECT_FORMAT_V3, ProjectPackageError, read_project
from .service import handle
from .spice_workspace import SPICE_WORKSPACE_CONTRACT
from .sparameters import (
    analyze_network,
    read_touchstone,
    renormalize_s,
    write_touchstone,
)
from .si_channel import REQUEST_CONTRACT as SI_CHANNEL_REQUEST_CONTRACT, analyze_uniform_design_channel
from .si_workflow import run_si_workflow


from . import __version__ as CLI_VERSION
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_ANALYSIS = 2
EXIT_VALIDATION = 3
EXIT_WARNING = 4
PDN_CANDIDATE_CONTRACT = "spike/pdn-candidate-set/v1"
MAX_PDN_CANDIDATES = 4096
FIELD_CIRCUIT_PACKAGE_CONTRACT = "spike/field-circuit-cosimulation-package/v1"
FIELD_CIRCUIT_PACKAGE_VALIDATION_CONTRACT = "spike/field-circuit-cosimulation-package-validation/v1"


class CliError(RuntimeError):
    pass


def _read_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"{path} is not valid JSON: {exc}") from exc


def _read_json(path: Path) -> Dict[str, Any]:
    value = _read_json_value(path)
    if not isinstance(value, dict):
        raise CliError(f"{path} must contain a JSON object.")
    return value


def _field_circuit_package(path: Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Load and structurally validate the explicit field/circuit input tuple."""

    package = _read_json(path)
    issues: List[Dict[str, str]] = []
    if package.get("contract") != FIELD_CIRCUIT_PACKAGE_CONTRACT:
        issues.append({
            "code": "SPIKE-CLI-FIELDCIRCUIT-E-0001",
            "severity": "error",
            "path": "contract",
            "message": f"Expected {FIELD_CIRCUIT_PACKAGE_CONTRACT}.",
        })

    expected = {
        "design": CONTRACT_VERSION,
        "workspace": SPICE_WORKSPACE_CONTRACT,
        "request": FIELD_CIRCUIT_REQUEST_CONTRACT,
        "field_analysis_spec": CONTRACT_VERSION,
    }
    for key, contract in expected.items():
        value = package.get(key)
        if not isinstance(value, dict):
            issues.append({
                "code": "SPIKE-CLI-FIELDCIRCUIT-E-0001",
                "severity": "error",
                "path": key,
                "message": f"{key} must be an object using {contract}.",
            })
        elif value.get("contract") != contract:
            issues.append({
                "code": "SPIKE-CLI-FIELDCIRCUIT-E-0001",
                "severity": "error",
                "path": f"{key}.contract",
                "message": f"{key} must use {contract}.",
            })

    field_spec = package.get("field_analysis_spec")
    if isinstance(field_spec, dict):
        if str(field_spec.get("mode", "")).strip() not in {"ac", "broadband_hf"}:
            issues.append({
                "code": "SPIKE-CLI-FIELDCIRCUIT-E-0001",
                "severity": "error",
                "path": "field_analysis_spec.mode",
                "message": "field_analysis_spec.mode must be ac or broadband_hf for the native PEEC provider.",
            })
        if not str(field_spec.get("analysis_id", "")).strip():
            issues.append({
                "code": "SPIKE-CLI-FIELDCIRCUIT-E-0001",
                "severity": "error",
                "path": "field_analysis_spec.analysis_id",
                "message": "field_analysis_spec.analysis_id is required for stable PEEC mapping.",
            })

    return package, {
        "contract": FIELD_CIRCUIT_PACKAGE_VALIDATION_CONTRACT,
        "valid": not issues,
        "package_contract": FIELD_CIRCUIT_PACKAGE_CONTRACT,
        "issues": issues,
    }


def _validate_field_circuit_package(
    package: Dict[str, Any],
    structural_validation: Dict[str, Any],
) -> Dict[str, Any]:
    """Combine structural and service validation without attempting a solve."""

    if not structural_validation["valid"]:
        return structural_validation

    validation = _response(
        "validate_field_circuit_cosimulation",
        {"request": package["request"]},
    )["result"]
    return {
        "contract": FIELD_CIRCUIT_PACKAGE_VALIDATION_CONTRACT,
        "valid": bool(validation.get("valid")),
        "package_contract": FIELD_CIRCUIT_PACKAGE_CONTRACT,
        "coupling_validation": validation,
        "issues": list(structural_validation["issues"]) + list(validation.get("issues", [])),
    }


def _response(method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    response = handle({"method": method, "params": params or {}})
    if not response.get("ok"):
        raise CliError(str(response.get("error", f"{method} failed")))
    return response


def _load_kicad_source(source: str, name: str = "embedded.kicad_pcb") -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="spike-cli-") as directory:
        path = Path(directory) / Path(name).name
        path.write_text(source, encoding="utf-8")
        design = _response("load_design", {"path": str(path)})["result"]
        design["source_path"] = f"embedded:{Path(name).name}"
        design.setdefault("metadata", {})["source_embedded"] = True
        return design


def load_design(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise CliError(f"Design input does not exist: {path}")
    if path.suffix.lower() == ".kicad_pcb":
        return _response("load_design", {"path": str(path.resolve())})["result"]
    if path.suffix.lower() == ".spike":
        opened = read_project(path)
        design_v2 = opened.payload.get("design_ir")
        if not isinstance(design_v2, dict):
            raise CliError(f"{path} does not contain DesignIR v2.")
        design = DesignIRV2.from_dict(design_v2).to_v1().to_dict()
        design.setdefault("metadata", {})["source_embedded"] = True
        design["source_path"] = f"package:{path.resolve()}"
        return design
    data = _read_json(path)
    if data.get("contract") == CONTRACT_VERSION and any(key in data for key in ("tracks", "zones", "pads")):
        return data
    if isinstance(data.get("design"), dict):
        design = data["design"]
        if any(key in design for key in ("tracks", "zones", "pads")):
            return design
        if design.get("source_board"):
            return _load_kicad_source(str(design["source_board"]), str(design.get("source_file", "embedded.kicad_pcb")))
    raise CliError(f"{path} is not a DesignIR, analysis request, or SPIKE project containing a board.")


def terminal(value: str) -> Dict[str, Any]:
    """Parse X,Y,LAYER,VALUE[,CONTACT_R[,PACKAGE_R]]."""
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {4, 5, 6}:
        raise argparse.ArgumentTypeError("Expected X,Y,LAYER,VALUE[,CONTACT_R[,PACKAGE_R]]")
    try:
        result = {
            "position_mm": [float(parts[0]), float(parts[1])],
            "layer": parts[2],
            "value": float(parts[3]),
            "contact_resistance_ohm": float(parts[4]) if len(parts) >= 5 else 0.0,
            "package_resistance_ohm": float(parts[5]) if len(parts) >= 6 else 0.0,
        }
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Terminal coordinates, value, and resistance must be numeric.") from exc
    if result["contact_resistance_ohm"] < 0 or result["package_resistance_ohm"] < 0:
        raise argparse.ArgumentTypeError("Terminal resistance cannot be negative.")
    return result


def waveform(value: str) -> Dict[str, Any]:
    """Parse constant, step, pulse, short/long pulse, or PWL controls."""

    parts = [part.strip() for part in value.split(",")]
    kind = parts[0].lower().replace("-", "_") if parts else ""
    if kind == "constant" and len(parts) == 1:
        return {"kind": "constant"}
    if kind in {"short_pulse", "long_pulse"} and len(parts) == 1:
        return {
            "kind": "pulse",
            "initial_value": 0.0,
            "delay_s": 1e-5 if kind == "short_pulse" else 1e-4,
            "rise_time_s": 1e-7 if kind == "short_pulse" else 1e-6,
            "pulse_width_s": 1e-5 if kind == "short_pulse" else 1e-3,
            "fall_time_s": 1e-7 if kind == "short_pulse" else 1e-6,
            "period_s": 2.5e-5 if kind == "short_pulse" else 2e-3,
        }
    try:
        if kind == "step" and len(parts) == 4:
            return {"kind": "step", "initial_value": float(parts[1]), "delay_s": float(parts[2]), "rise_time_s": float(parts[3])}
        if kind == "pulse" and len(parts) == 7:
            return {
                "kind": "pulse", "initial_value": float(parts[1]), "delay_s": float(parts[2]),
                "rise_time_s": float(parts[3]), "pulse_width_s": float(parts[4]),
                "fall_time_s": float(parts[5]), "period_s": float(parts[6]),
            }
        if kind in {"pwl", "piecewise_linear"} and len(parts) >= 2:
            return {"kind": "piecewise_linear", "points": ",".join(parts[1:]).replace(";", ",")}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Waveform times and values must be numeric.") from exc
    raise argparse.ArgumentTypeError(
        "Expected constant, short-pulse, long-pulse, step,LOW,DELAY,RISE, "
        "pulse,LOW,DELAY,RISE,HIGH_TIME,FALL,PERIOD, or pwl,T0:V0;T1:V1"
    )


def port(value: str) -> Dict[str, Any]:
    """Parse X,Y,LAYER[,NAME] for an AC extraction port."""
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {3, 4}:
        raise argparse.ArgumentTypeError("Expected X,Y,LAYER[,NAME]")
    try:
        result = {
            "position_mm": [float(parts[0]), float(parts[1])],
            "layer": parts[2],
        }
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port coordinates must be numeric.") from exc
    if len(parts) == 4:
        result["name"] = parts[3]
    return result


def tuning_assignment(value: str) -> tuple[str, Any]:
    """Parse an allowlisted solver tuning assignment as KEY=JSON_VALUE."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected KEY=VALUE")
    key, raw = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("A tuning key is required.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw.strip()
    return key, parsed


def _terminal_payload(item: Dict[str, Any], kind: str, index: int) -> Dict[str, Any]:
    result = dict(item)
    value = result.pop("value")
    result.setdefault("id", f"cli-{kind}-{index + 1}")
    result["voltage_v" if kind == "source" else "current_a"] = value
    return result


def _design_summary(design: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contract": design.get("contract", CONTRACT_VERSION),
        "name": design.get("name", "Untitled"),
        "source_format": design.get("source_format", "unknown"),
        "source_path": design.get("source_path", ""),
        "technology": design.get("technology", "rigid"),
        "counts": {
            "layers": len(design.get("layers", [])),
            "nets": len(design.get("nets", [])),
            "tracks": len(design.get("tracks", [])),
            "vias": len(design.get("vias", [])),
            "pads": len(design.get("pads", [])),
            "zones": len(design.get("zones", [])),
            "components": len(design.get("components", [])),
            "stackup_layers": len(design.get("stackup", [])),
            "regions": len(design.get("regions", [])),
            "bends": len(design.get("bends", [])),
        },
        "issues": design.get("issues", []),
    }


def _result_exit(result: Any, fail_on_warning: bool = False) -> int:
    if not isinstance(result, dict):
        return EXIT_OK
    if result.get("contract") == "spike/sparselizard-validation-report/v1" and result.get("status") != "validated":
        return EXIT_VALIDATION
    if result.get("contract") == "spike/pi-release-qualification/v1" and result.get("status") != "passed":
        return EXIT_VALIDATION
    if result.get("valid") is False:
        return EXIT_VALIDATION
    if result.get("can_supply_solver_inputs") is False:
        return EXIT_VALIDATION
    status = str(result.get("status", "completed"))
    if status not in {
        "completed", "completed_screening_only", "not_run", "pass", "passed", "ready", "preview",
        "prepared_review_required", "ready_to_prepare", "ready_to_screen", "ready_to_run", "review_required",
        "setup_completed",
    }:
        return EXIT_ANALYSIS
    issues = result.get("issues", [])
    if fail_on_warning and any(item.get("severity") == "warning" for item in issues if isinstance(item, dict)):
        return EXIT_WARNING
    return EXIT_OK


def _text(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    if value.get("contract") == "spike/touchstone-analysis/v1":
        frequency = value.get("frequency", {})
        checks = value.get("checks", {})
        return "\n".join([
            f"Touchstone: {value.get('source', '')}",
            f"Ports: {value.get('port_count', 0)}",
            f"Frequency: {float(frequency.get('start_hz', 0)):.6g} to {float(frequency.get('stop_hz', 0)):.6g} Hz ({frequency.get('count', 0)} points)",
            f"Reference impedance: {value.get('reference_impedance_ohm', [])} ohm",
            f"Passivity: {checks.get('passivity', {}).get('status', 'unknown')} (worst singular value {float(checks.get('passivity', {}).get('worst_singular_value', 0)):.6g})",
            f"Reciprocity: {checks.get('reciprocity', {}).get('status', 'unknown')} (worst error {float(checks.get('reciprocity', {}).get('worst_error', 0)):.6g})",
            f"Causality: {checks.get('causality', {}).get('status', 'unknown')}",
        ])
    if "status" in value and "model_status" in value:
        summary = value.get("summary", {})
        lines = [
            f"Status: {value.get('status')}",
            f"Model: {value.get('model_status')}",
            f"Analysis: {value.get('mode', 'unknown')} ({value.get('analysis_id', '')})",
        ]
        if "max_voltage_drop_v" in summary:
            lines.append(f"Maximum voltage drop: {float(summary['max_voltage_drop_v']) * 1000:.6g} mV")
        if "max_current_density_a_mm2" in summary:
            lines.append(f"Maximum current density: {float(summary['max_current_density_a_mm2']):.6g} A/mm^2")
        if summary.get("geometry_counts"):
            lines.append("Geometry: " + ", ".join(f"{key}={count}" for key, count in summary["geometry_counts"].items()))
        for issue in value.get("issues", []):
            lines.append(f"[{str(issue.get('severity', 'info')).upper()}] {issue.get('code', '')}: {issue.get('message', '')}")
        return "\n".join(lines)
    if "counts" in value and isinstance(value["counts"], dict):
        lines = [f"{value.get('name', 'SPIKE design')} ({value.get('source_format', 'unknown')})"]
        lines.append(f"Technology: {value.get('technology', 'rigid')}")
        lines.extend(f"{key.replace('_', ' ').title()}: {count}" for key, count in value["counts"].items())
        return "\n".join(lines)
    return json.dumps(value, indent=2, default=str)


def _write_output(value: Any, args: argparse.Namespace) -> None:
    content = json.dumps(value, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None, default=str)
    if args.output_format == "text":
        content = _text(value)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    if not args.quiet:
        print(content)


def _analysis_request(args: argparse.Namespace, analysis_mode: str = "dc") -> Dict[str, Any]:
    design = load_design(args.design)
    sources = [_terminal_payload(item, "source", index) for index, item in enumerate(args.source)]
    loads = [_terminal_payload(item, "load", index) for index, item in enumerate(args.load)]
    if analysis_mode == "transient":
        source_profiles = list(args.source_waveform or [])
        load_profiles = list(args.load_waveform or [])

        def apply_profiles(terminals: List[Dict[str, Any]], profiles: List[Dict[str, Any]], label: str) -> None:
            if not profiles:
                for item in terminals:
                    item["profile"] = {"kind": "constant"}
                return
            if len(profiles) not in {1, len(terminals)}:
                raise CliError(f"Provide one --{label}-waveform for all terminals or one per --{label} terminal.")
            for index, item in enumerate(terminals):
                item["profile"] = profiles[0] if len(profiles) == 1 else profiles[index]

        apply_profiles(sources, source_profiles, "source")
        apply_profiles(loads, load_profiles, "load")
    explicit_return = bool(args.return_net)
    return_mode = args.return_mode if explicit_return else "implicit"
    return_sources = [_terminal_payload(item, "source", index) for index, item in enumerate(args.return_source or [])]
    return_loads = [_terminal_payload(item, "load", index) for index, item in enumerate(args.return_load or [])]
    if explicit_return and not return_sources:
        raise CliError("--return-net requires at least one --return-source terminal.")
    if explicit_return and len(return_loads) != len(loads):
        raise CliError("Provide one --return-load terminal for each --load terminal.")
    sources = [
        {**item, "net": args.net[0], "terminal_role": "source_positive", "domain_id": args.domain_id}
        for item in sources
    ] + ([
        {**item, "net": args.return_net, "voltage_v": 0.0, "terminal_role": "source_return", "domain_id": args.domain_id}
        for item in return_sources
    ] if explicit_return else [])
    positive_loads = [
        {**item, "net": args.net[0], "terminal_role": "load_positive", "pair_id": f"load-pair-{index + 1}", "domain_id": args.domain_id}
        for index, item in enumerate(loads)
    ]
    paired_returns = [
        {**item, "net": args.return_net, "current_a": -abs(float(loads[index]["current_a"])), "terminal_role": "load_return", "pair_id": f"load-pair-{index + 1}", "domain_id": args.domain_id}
        for index, item in enumerate(return_loads)
    ] if explicit_return else []
    spec = {
        "contract": CONTRACT_VERSION,
        "analysis_id": args.analysis_id or "",
        "mode": analysis_mode,
        "solver_id": args.solver,
        "formulation": args.formulation,
        "required_capabilities": (
            ["transient_waveforms", "geometry_transient", "partial_inductance"]
            + (["distributed_capacitance"] if args.capacitance_model != "none" else [])
            + ["voltage_drop", "current_density", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance"]
            if analysis_mode == "transient"
            else ["dc_resistance", "tracks", "through_vias", "pads", "copper_zones"]
        ) + (["explicit_return_path"] if explicit_return else []) + (["isolated_power_domain"] if return_mode == "isolated_secondary" else []),
        "net_names": list(dict.fromkeys(args.net + ([args.return_net] if explicit_return else []))),
        "sources": sources,
        "loads": positive_loads + paired_returns,
        "return_path": {"mode": return_mode, "net": args.return_net or "", "domain_id": args.domain_id, "galvanically_isolated": return_mode == "isolated_secondary"},
        "transient": ({
            "stop_time_s": args.stop_time_s,
            "time_step_s": args.time_step_s or min(args.stop_time_s / 1000.0, 1e-6),
            "time_step_mode": "manual" if args.time_step_s is not None else "auto",
            "output_decimation": args.output_decimation,
            "output_decimation_mode": args.output_decimation_mode,
            "playback_fps": args.playback_fps,
            "initial_condition": args.initial_condition,
            "integration": "backward_euler",
            "max_internal_steps": args.max_internal_steps,
            "max_output_frames": args.max_output_frames,
            "max_branches": args.max_transient_branches,
            "max_solver_time_s": args.max_solver_time_s,
            "memory_budget_mb": args.memory_budget_mb,
            "capacitance_model": args.capacitance_model,
            "visual_sample_limit": args.visual_sample_limit,
        } if analysis_mode == "transient" else {}),
        "mesh": {
            "target_size_mm": args.mesh_size_mm,
            "zone_cell_mm": args.zone_cell_mm,
            "max_zone_cells": args.max_zone_cells,
            "max_conductors": args.max_conductors,
            "solver_memory_limit_gb": args.memory_limit_gb,
            "via_model": args.via_model,
            "via_plating_thickness_mm": args.via_plating_mm,
            "board_thickness_mm": args.board_thickness_mm,
        },
        "limits": {
            "max_voltage_drop_mv": args.max_drop_mv,
            "max_current_density_a_mm2": args.max_density,
        },
        "options": {"via_model": args.via_model},
    }
    return {"contract": "spike/analysis-request/v1", "design": design, "spec": spec}


def _ac_analysis_request(args: argparse.Namespace) -> Dict[str, Any]:
    design = load_design(args.design)
    capabilities = ["frequency_dependent_impedance", "partial_inductance"]
    if args.skin_effect:
        capabilities.append("skin_effect")
    if args.roughness_model != "none":
        capabilities.append("surface_roughness")
    if args.capacitance_model != "none":
        capabilities.extend(["capacitance_extraction", "dielectric_loss"])
    return {
        "contract": "spike/analysis-request/v1",
        "design": design,
        "spec": {
            "contract": CONTRACT_VERSION,
            "analysis_id": args.analysis_id or "",
            "mode": "ac",
            "solver_id": args.solver,
            "formulation": args.formulation,
            "required_capabilities": capabilities,
            "net_names": args.net,
            "sources": [
                {**item, "id": item.get("name", f"cli-ac-source-{index + 1}")}
                for index, item in enumerate(args.source or [])
            ],
            "loads": [
                {**item, "id": item.get("name", f"cli-ac-load-{index + 1}")}
                for index, item in enumerate(args.load or [])
            ],
            "return_path": {
                "mode": "explicit" if args.return_net else "implicit",
                "net": args.return_net or "",
            },
            "frequency_start_hz": args.start_hz,
            "frequency_stop_hz": args.stop_hz,
            "frequency_points": args.points,
            "mesh": {
                "target_size_mm": args.mesh_size_mm,
                "zone_cell_mm": args.zone_cell_mm,
                "max_zone_cells": args.max_zone_cells,
                "max_conductors": args.max_conductors,
                "solver_memory_limit_gb": args.memory_limit_gb,
                "via_model": args.via_model,
                "via_plating_thickness_mm": args.via_plating_mm,
                "max_preview_cells": args.max_preview_cells,
            },
            "options": {
                "via_model": args.via_model,
                "include_dielectric": args.capacitance_model != "none",
                "capacitance_model": args.capacitance_model,
                "conductor_models": {
                    "skin_effect": args.skin_effect,
                    "surface_roughness_model": args.roughness_model,
                    "rms_roughness_um": args.roughness_um,
                },
            },
        },
    }


def _project_request(path: Path) -> Dict[str, Any]:
    assembly_scope = None
    if path.suffix.lower() == ".spike":
        opened = read_project(path)
        extensions = opened.payload.get("extensions")
        project = extensions.get("legacy") if isinstance(extensions, dict) else None
        if not isinstance(project, dict):
            project = {
                "format": PROJECT_FORMAT_V3,
                "project": opened.payload.get("project", {}),
                "analysis": opened.payload.get("analyses", {}),
            }
    else:
        project = _read_json(path)
    design = load_design(path)
    if path.suffix.lower() == ".spike" and isinstance(opened.payload.get("assembly_ir"), dict):
        assembly = opened.payload["assembly_ir"]
        active_design_id = str(design.get("metadata", {}).get("design_ir_v2_id") or design.get("design_id") or "").strip()
        matching_boards = [board for board in assembly.get("boards", []) if isinstance(board, dict) and str(board.get("design_id", "")).strip() == active_design_id]
        if len(matching_boards) != 1:
            raise CliError(
                f"Project analysis requires exactly one AssemblyIR board instance for active design {active_design_id!r}; found {len(matching_boards)}."
            )
        assembly_scope = {
            "contract": "spike/assembly-analysis-scope/v1", "mode": "active_board_only",
            "assembly": assembly, "active_board_id": matching_boards[0].get("id"), "active_design_id": active_design_id,
            "project_manifest_digest": str(opened.manifest.get("manifest_payload_sha256") or ""),
        }
    analysis = project.get("analysis", {})
    setup = analysis.get("pi_setup", {})
    mode_name = str(analysis.get("mode", "DC IR Drop"))
    mode = "ac" if "AC" in mode_name.upper() else "dc"

    def project_terminals(kind: str, items: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        result = []
        for index, item in enumerate(items if items is not None else setup.get(kind, [])):
            layer = str(item.get("layer", "auto"))
            terminal_item = {
                "id": item.get("id", f"project-{kind}-{index + 1}"),
                "position_mm": [float(item.get("x", 0)), float(item.get("y", 0))],
                "contact_resistance_ohm": float(item.get("contactResistance", 0) or 0),
                "package_resistance_ohm": float(item.get("packageResistance", 0) or 0),
                "voltage_v" if kind == "sources" else "current_a": float(item.get("value", 0)),
            }
            if layer and layer != "auto":
                terminal_item["layer"] = layer
            else:
                terminal_item["layer_scope"] = "connected_conductor"
                terminal_item["layer_candidates"] = item.get("layers", [])
            if item.get("anchorId"):
                terminal_item["geometry_anchor"] = {"id": item["anchorId"], "type": item.get("anchorType", "geometry")}
            result.append(terminal_item)
        return result

    power_net = str(setup.get("net", ""))
    return_setup = setup.get("returnPath", {})
    return_mode = str(return_setup.get("mode", "implicit")) if mode == "dc" else "implicit"
    explicit_return = return_mode in {"explicit", "isolated_secondary"}
    return_net = str(return_setup.get("net", ""))
    domain_id = str(return_setup.get("domainId", "main"))
    positive_sources = [{**item, "net": power_net, "terminal_role": "source_positive", "domain_id": domain_id} for item in project_terminals("sources")]
    positive_loads = [{**item, "net": power_net, "terminal_role": "load_positive", "pair_id": f"load-pair-{index + 1}", "domain_id": domain_id} for index, item in enumerate(project_terminals("loads"))]
    return_sources = [{**item, "net": return_net, "voltage_v": 0.0, "terminal_role": "source_return", "domain_id": domain_id} for item in project_terminals("sources", return_setup.get("sources", []))] if explicit_return else []
    raw_return_loads = project_terminals("loads", return_setup.get("loads", [])) if explicit_return else []
    return_loads = [{**item, "net": return_net, "current_a": -abs(float(positive_loads[index].get("current_a", 0))), "terminal_role": "load_return", "pair_id": f"load-pair-{index + 1}", "domain_id": domain_id} for index, item in enumerate(raw_return_loads) if index < len(positive_loads)]

    return {
        "contract": "spike/analysis-request/v1",
        "assembly_scope": assembly_scope,
        "design": design,
        "spec": {
            "contract": CONTRACT_VERSION,
            "analysis_id": f"project-{path.stem}",
            "mode": mode,
            "solver_id": analysis.get("solver_id", "auto"),
            "formulation": analysis.get("formulation", "auto"),
            "required_capabilities": (["explicit_return_path"] if explicit_return else []) + (["isolated_power_domain"] if return_mode == "isolated_secondary" else []),
            "net_names": list(dict.fromkeys(([power_net] if power_net else analysis.get("power_nets", [])) + ([return_net] if explicit_return and return_net else []))),
            "sources": positive_sources + return_sources,
            "loads": positive_loads + return_loads,
            "return_path": {"mode": return_mode, "net": return_net if explicit_return else "", "domain_id": domain_id, "galvanically_isolated": return_mode == "isolated_secondary"},
            "frequency_start_hz": float(setup.get("frequencyStart", 10000)),
            "frequency_stop_hz": float(setup.get("frequencyStop", 10000000)),
            "frequency_points": int(setup.get("frequencyPoints", 101)),
            "limits": {
                "max_voltage_drop_mv": float(analysis.get("limits", {}).get("drop", 50)),
                "max_current_density_a_mm2": float(analysis.get("limits", {}).get("density", 100)),
            },
        },
    }


def execute_request(request: Dict[str, Any]) -> Dict[str, Any]:
    if request.get("contract") == "spike/analysis-request/v1":
        design = request.get("design")
        spec = request.get("spec", {})
    elif "design" in request and "spec" in request:
        design = request["design"]
        spec = request["spec"]
    else:
        raise CliError("Expected a spike/analysis-request/v1 object containing design and spec.")
    if not isinstance(design, dict) or not isinstance(spec, dict):
        raise CliError("Analysis request design and spec must be JSON objects.")

    params = {"design": design, "spec": spec, "assembly_scope": request.get("assembly_scope")}
    preflight = _response("preflight_analysis", params)["result"]
    if not preflight.get("can_solve"):
        return preflight
    return _response("run_analysis", params)["result"]


def execute_batch(manifest: Dict[str, Any], continue_on_error: bool = False) -> Dict[str, Any]:
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise CliError("Batch manifest must contain a non-empty jobs array.")
    results = []
    for index, job in enumerate(jobs):
        try:
            request = job if isinstance(job, dict) and "design" in job else job.get("request", {})
            result = execute_request(request)
            results.append({"index": index, "id": job.get("id", f"job-{index + 1}"), "result": result})
            if result.get("status") != "completed" and not continue_on_error:
                break
        except (CliError, KeyError, TypeError) as exc:
            results.append({"index": index, "id": job.get("id", f"job-{index + 1}") if isinstance(job, dict) else f"job-{index + 1}", "error": str(exc)})
            if not continue_on_error:
                break
    return {
        "contract": "spike/analysis-batch-result/v1",
        "status": "completed" if results and all(item.get("result", {}).get("status") == "completed" for item in results) else "failed",
        "requested": len(jobs),
        "completed": sum(item.get("result", {}).get("status") == "completed" for item in results),
        "failed": sum("error" in item or item.get("result", {}).get("status") != "completed" for item in results),
        "results": results,
    }


def _html_report(result: Dict[str, Any]) -> str:
    summary = result.get("summary", {})
    issues = "".join(
        f"<tr><td>{html.escape(str(item.get('severity', '')))}</td><td>{html.escape(str(item.get('code', '')))}</td><td>{html.escape(str(item.get('message', '')))}</td></tr>"
        for item in result.get("issues", [])
    )
    parasitics = result.get("networks", {}).get("parasitics", [])
    impedance_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(network.get('net', '')))}</td>"
        f"<td>{float(point.get('frequency_hz', 0)):.6g}</td>"
        f"<td>{float(point.get('resistance_ohm', 0)):.9g}</td>"
        f"<td>{float(point.get('reactance_ohm', 0)):.9g}</td>"
        f"<td>{float(point.get('magnitude_ohm', 0)):.9g}</td>"
        f"<td>{float(point.get('phase_deg', 0)):.6g}</td>"
        "</tr>"
        for network in parasitics
        for point in network.get("impedance", [])
    )
    impedance_table = (
        "<h2>Frequency-dependent impedance</h2><table>"
        "<tr><th>Net</th><th>Frequency (Hz)</th><th>R (ohm)</th>"
        "<th>X (ohm)</th><th>|Z| (ohm)</th><th>Phase (deg)</th></tr>"
        f"{impedance_rows}</table>"
        if impedance_rows
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>SPIKE Analysis Report</title>
<style>body{{font:14px Arial;color:#243038;margin:40px}}h1{{color:#9a6416}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd5d9;padding:8px;text-align:left}}pre{{background:#f3f5f6;padding:16px;overflow:auto}}</style></head>
<body><h1>SPIKE Analysis Report</h1><table>
<tr><th>Status</th><td>{html.escape(str(result.get("status", "")))}</td></tr>
<tr><th>Model status</th><td>{html.escape(str(result.get("model_status", "")))}</td></tr>
<tr><th>Mode</th><td>{html.escape(str(result.get("mode", "")))}</td></tr>
<tr><th>Maximum voltage drop</th><td>{float(summary.get("max_voltage_drop_v", 0)) * 1000:.6g} mV</td></tr>
<tr><th>Maximum current density</th><td>{float(summary.get("max_current_density_a_mm2", 0)):.6g} A/mm^2</td></tr>
</table><h2>Issues</h2><table><tr><th>Severity</th><th>Code</th><th>Message</th></tr>{issues}</table>
{impedance_table}<h2>Provenance</h2><pre>{html.escape(json.dumps(result.get("provenance", {}), indent=2, default=str))}</pre></body></html>"""


def _html_batch_report(report: Dict[str, Any]) -> str:
    """Render the bounded PI batch-report contract without raw solver payloads."""

    metric_names = sorted({key for job in report["jobs"] for key in job["metrics"]})
    headers = ["Job", "Mode", "Nets", "Status", "Model", "Solver", *metric_names]
    rows = []
    for job in report["jobs"]:
        values = [
            job["id"], job["mode"], ", ".join(job["nets"]), job["status"],
            job["model_status"], job["solver"],
            *(job["metrics"].get(name, "") for name in metric_names),
        ]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>")
    issue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(issue['job_id'])}</td>"
        f"<td>{html.escape(issue['severity'])}</td>"
        f"<td>{html.escape(issue['code'])}</td>"
        f"<td>{html.escape(issue['message'])}</td>"
        "</tr>"
        for issue in report["issues"]
    ) or "<tr><td colspan=\"4\">No issues recorded.</td></tr>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>SPIKE PI Batch Report</title>
<style>body{{font:14px Arial;color:#243038;margin:40px}}h1{{color:#9a6416}}table{{border-collapse:collapse;width:100%;margin:12px 0 28px}}th,td{{border:1px solid #ccd5d9;padding:7px;text-align:left;vertical-align:top}}th{{background:#e8eef0}}pre{{background:#f3f5f6;padding:16px;overflow:auto}}</style></head>
<body><h1>SPIKE Power Integrity Batch Report</h1>
<p>Numerical and validity states are reproduced per job. Incomplete jobs remain visible and are not promoted.</p>
<h2>Batch Summary</h2><pre>{html.escape(json.dumps(report['totals'], indent=2, default=str))}</pre>
<h2>Analysis Jobs</h2><table><tr>{''.join(f'<th>{html.escape(name)}</th>' for name in headers)}</tr>{''.join(rows)}</table>
<h2>Issues</h2><table><tr><th>Job</th><th>Severity</th><th>Code</th><th>Message</th></tr>{issue_rows}</table>
<h2>Provenance</h2><pre>{html.escape(json.dumps(report['provenance'], indent=2, default=str))}</pre></body></html>"""


def _csv_result(result: Dict[str, Any]) -> str:
    stream = StringIO()
    parasitics = result.get("networks", {}).get("parasitics", [])
    if any(network.get("impedance") for network in parasitics):
        fieldnames = [
            "net", "source_node", "sink_node", "frequency_hz",
            "resistance_ohm", "reactance_ohm", "magnitude_ohm", "phase_deg",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for network in parasitics:
            for point in network.get("impedance", []):
                writer.writerow({
                    "net": network.get("net", ""),
                    "source_node": network.get("source_node", ""),
                    "sink_node": network.get("sink_node", ""),
                    **{key: point.get(key, "") for key in fieldnames[3:]},
                })
        return stream.getvalue()
    writer = csv.DictWriter(stream, fieldnames=["id", "kind", "net", "layer", "resistance_ohm", "current_a", "current_density_a_mm2", "voltage_drop_v"])
    writer.writeheader()
    for edge in result.get("fields", {}).get("edge_results", []):
        writer.writerow({key: edge.get(key, "") for key in writer.fieldnames})
    return stream.getvalue()


def _csv_batch_report(report: Dict[str, Any]) -> str:
    metric_names = sorted({key for job in report["jobs"] for key in job["metrics"]})
    fields = ["index", "id", "mode", "nets", "status", "model_status", "solver", *metric_names, "issue_count"]
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for job in report["jobs"]:
        writer.writerow({
            "index": job["index"],
            "id": job["id"],
            "mode": job["mode"],
            "nets": ";".join(job["nets"]),
            "status": job["status"],
            "model_status": job["model_status"],
            "solver": job["solver"],
            **job["metrics"],
            "issue_count": len(job["issues"]),
        })
    return stream.getvalue()


def _batch_as_pdf_result(report: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt normalized batch data to the existing audited PDF renderer."""

    summary = dict(report["totals"])
    summary["jobs"] = "; ".join(
        f"{job['id']}={job['mode']}/{job['status']}/{job['model_status']}"
        for job in report["jobs"]
    )
    return {
        "mode": "pi_batch",
        "status": report["status"],
        "model_status": "mixed",
        "summary": summary,
        "issues": report["issues"],
        "probes": [],
        "provenance": report["provenance"],
    }


def _write_pdf_report(result: Dict[str, Any], output: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        _write_basic_pdf_report(result, output)
        return

    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#8a5a12")
    styles["Heading2"].textColor = colors.HexColor("#243a43")
    styles["Code"].fontName = "Courier"
    styles["Code"].fontSize = 6.5
    styles["Code"].leading = 8

    def paragraph(value: Any, style: str = "BodyText"):
        return Paragraph(html.escape(str(value if value is not None else "")), styles[style])

    def table(rows: List[List[Any]], widths: List[float] | None = None):
        value = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        value.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17242b")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aebbc1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return value

    summary = result.get("summary", {})
    story = [
        paragraph("SPIKE Power Integrity Engineering Report", "Title"),
        paragraph("Numerical and validity states are reproduced from the solver result. Unsupported or unconverged physics are not promoted to validated."),
        Spacer(1, 5 * mm),
        table([
            [paragraph("Field"), paragraph("Value")],
            [paragraph("Analysis"), paragraph(result.get("mode", ""))],
            [paragraph("Result status"), paragraph(result.get("status", ""))],
            [paragraph("Model status"), paragraph(result.get("model_status", ""))],
            [paragraph("Solver"), paragraph(result.get("provenance", {}).get("solver", result.get("provenance", {}).get("solver_plugin", "")))],
            [paragraph("Mesh convergence"), paragraph(summary.get("mesh_convergence_status", "not run"))],
        ], [45 * mm, 125 * mm]),
        paragraph("Numerical Summary", "Heading2"),
        table([[paragraph("Metric"), paragraph("Value")]] + [[paragraph(key), paragraph(value)] for key, value in sorted(summary.items())], [75 * mm, 95 * mm]),
        paragraph("Warnings, Limits, and Validity", "Heading2"),
    ]
    issue_rows = [[paragraph("Severity"), paragraph("Code"), paragraph("Message"), paragraph("Status")]]
    for issue in result.get("issues", []):
        issue_rows.append([paragraph(issue.get("severity", "")), paragraph(issue.get("code", "")), paragraph(issue.get("message", "")), paragraph(issue.get("status", ""))])
    if len(issue_rows) == 1:
        issue_rows.append([paragraph("info"), paragraph("NONE"), paragraph("No result issues were recorded."), paragraph("closed")])
    story.append(table(issue_rows, [18 * mm, 38 * mm, 92 * mm, 22 * mm]))

    story.append(paragraph("Probe Table", "Heading2"))
    probe_rows = [[paragraph("Probe"), paragraph("Net / layer"), paragraph("Voltage (V)"), paragraph("Drop (mV)"), paragraph("Density (A/mm2)")]]
    for probe in result.get("probes", []):
        drop = probe.get("voltage_drop_v")
        probe_rows.append([
            paragraph(probe.get("name", probe.get("id", ""))),
            paragraph(f"{probe.get('net', '')} / {probe.get('layer', '')}"),
            paragraph(probe.get("voltage_v", "-")),
            paragraph("-" if drop is None else float(drop) * 1000),
            paragraph(probe.get("peak_adjacent_current_density_a_mm2", "-")),
        ])
    if len(probe_rows) == 1:
        probe_rows.append([paragraph("No probes"), paragraph(""), paragraph(""), paragraph(""), paragraph("")])
    story.append(table(probe_rows, [35 * mm, 45 * mm, 28 * mm, 28 * mm, 34 * mm]))
    story.extend([
        PageBreak(),
        paragraph("Solver Provenance", "Heading2"),
        Preformatted(json.dumps(result.get("provenance", {}), indent=2, default=str), styles["Code"], maxLineLength=112),
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c4ced2"))
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#61747c"))
        canvas.drawString(18 * mm, 8 * mm, "SPIKE Power Integrity Engineering Report")
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def _write_basic_pdf_report(result: Dict[str, Any], output: Path) -> None:
    """Write a compact, valid PDF when the optional ReportLab runtime is absent."""

    summary = result.get("summary", {})
    lines = [
        "SPIKE Engineering Analysis Report",
        "",
        f"Analysis: {result.get('mode', '')}",
        f"Result status: {result.get('status', '')}",
        f"Model status: {result.get('model_status', '')}",
        f"Solver: {result.get('provenance', {}).get('solver', result.get('provenance', {}).get('solver_plugin', ''))}",
        "",
        "Numerical summary",
    ]
    lines.extend(f"{key}: {value}" for key, value in sorted(summary.items()))
    lines.extend(["", "Warnings, limits, and validity"])
    issues = result.get("issues", [])
    if issues:
        lines.extend(
            f"[{issue.get('severity', 'info')}] {issue.get('code', '')}: {issue.get('message', '')}"
            for issue in issues
        )
    else:
        lines.append("No result issues were recorded.")
    lines.extend(["", "Probe table"])
    probes = result.get("probes", [])
    if probes:
        lines.extend(
            f"{probe.get('name', probe.get('id', ''))}: {probe.get('net', '')} / {probe.get('layer', '')}, "
            f"V={probe.get('voltage_v', '-')}, drop={probe.get('voltage_drop_v', '-')}, "
            f"J={probe.get('peak_adjacent_current_density_a_mm2', '-')}"
            for probe in probes
        )
    else:
        lines.append("No probes were recorded.")

    def pdf_text(value: str) -> str:
        ascii_value = value.encode("ascii", "replace").decode("ascii")
        return ascii_value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pages = [lines[index:index + 48] for index in range(0, len(lines), 48)] or [[]]
    objects: List[bytes] = []

    def add_object(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    catalog_id = add_object(b"")
    pages_id = add_object(b"")
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: List[int] = []
    for page_number, page_lines in enumerate(pages, start=1):
        commands = [b"BT", b"/F1 10 Tf", b"48 800 Td"]
        for line_number, line in enumerate(page_lines):
            if line_number:
                commands.append(b"0 -15 Td")
            commands.append(f"({pdf_text(str(line))}) Tj".encode("ascii"))
        commands.extend([
            b"0 -24 Td",
            f"(Page {page_number} of {len(pages)}) Tj".encode("ascii"),
            b"ET",
        ])
        stream = b"\n".join(commands)
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")

    payload = bytearray(b"%PDF-1.4\n%SPIKE\n")
    offsets = [0]
    for object_id, value in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(value)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)


def _configure_dc_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("design", type=Path)
    parser.add_argument("--net", action="append", required=True, help="Net name; repeat for multi-net networks")
    parser.add_argument("--source", action="append", required=True, type=terminal, metavar="X,Y,LAYER,V[,CONTACT_R[,PACKAGE_R]]")
    parser.add_argument("--load", action="append", required=True, type=terminal, metavar="X,Y,LAYER,A[,CONTACT_R[,PACKAGE_R]]")
    parser.add_argument("--return-net", help="Explicit return or local ground net")
    parser.add_argument("--return-source", action="append", type=terminal, metavar="X,Y,LAYER,0[,CONTACT_R[,PACKAGE_R]]", help="Source-side return/reference terminal")
    parser.add_argument("--return-load", action="append", type=terminal, metavar="X,Y,LAYER,A[,CONTACT_R[,PACKAGE_R]]", help="Load-side return terminal; one per --load")
    parser.add_argument("--return-mode", choices=["explicit", "isolated_secondary"], default="explicit")
    parser.add_argument("--domain-id", default="main", help="Power/isolation domain identifier")
    parser.add_argument("--solver", default="auto")
    parser.add_argument("--formulation", default="auto")
    parser.add_argument("--analysis-id", default="")
    parser.add_argument("--max-drop-mv", type=float, default=50.0)
    parser.add_argument("--max-density", type=float, default=100.0)
    parser.add_argument("--mesh-size-mm", type=float, default=1.0)
    parser.add_argument("--zone-cell-mm", type=float, default=1.0)
    parser.add_argument("--max-zone-cells", type=int, default=3000)
    parser.add_argument("--max-conductors", type=int, help="Optional branch cap within the RAM-admitted solver capacity")
    parser.add_argument("--memory-limit-gb", type=float, default=2.0, help="Solver workspace limit in GB; minimum 2 GB")
    parser.add_argument("--via-model", choices=["extracted", "plated_cylinder"], default="extracted")
    parser.add_argument("--via-plating-mm", type=float, default=0.025)
    parser.add_argument("--board-thickness-mm", type=float, default=1.6)
    parser.add_argument("--save-request", type=Path, help="Save the normalized request")


def _configure_ac_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("design", type=Path)
    parser.add_argument("--net", action="append", required=True)
    parser.add_argument("--start-hz", type=float, required=True)
    parser.add_argument("--stop-hz", type=float, required=True)
    parser.add_argument("--points", type=int, default=101)
    parser.add_argument("--source", action="append", type=port, metavar="X,Y,LAYER[,NAME]")
    parser.add_argument("--load", action="append", type=port, metavar="X,Y,LAYER[,NAME]")
    parser.add_argument("--mesh-size-mm", type=float, default=1.0)
    parser.add_argument("--zone-cell-mm", type=float, default=1.0)
    parser.add_argument("--max-zone-cells", type=int, default=3000)
    parser.add_argument("--max-conductors", type=int, help="Optional branch cap within the RAM-admitted solver capacity")
    parser.add_argument("--memory-limit-gb", type=float, default=2.0, help="Solver workspace limit in GB; minimum 2 GB")
    parser.add_argument("--via-model", choices=["extracted", "plated_cylinder"], default="extracted")
    parser.add_argument("--via-plating-mm", type=float, default=0.025)
    parser.add_argument("--max-preview-cells", type=int, default=25000)
    parser.add_argument("--skin-effect", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--return-net", help="Explicit return/reference conductor for capacitance extraction")
    parser.add_argument("--capacitance-model", choices=["auto", "stackup_shunt", "none"], default="auto")
    parser.add_argument("--roughness-model", choices=["none", "hammerstad"], default="none")
    parser.add_argument("--roughness-um", type=float, default=0.0, help="RMS copper roughness in micrometres")
    parser.add_argument("--solver", default="spike.peec_2_5d")
    parser.add_argument("--formulation", default="peec_2_5d")
    parser.add_argument("--analysis-id", default="")
    parser.add_argument("--save-request", type=Path, help="Save the normalized request")


def _configure_transient_parser(parser: argparse.ArgumentParser) -> None:
    _configure_dc_parser(parser)
    parser.set_defaults(solver="spike.peec_rl_transient", formulation="peec_rl_transient")
    parser.add_argument("--stop-time-s", type=float, required=True, help="Transient stop time in seconds")
    parser.add_argument("--time-step-s", type=float, help="Backward-Euler integration step; omit for excitation-based automatic selection")
    parser.add_argument("--output-decimation", type=int, default=10, help="Save one result frame every N integration steps")
    parser.add_argument("--output-decimation-mode", choices=["auto", "manual"], default="auto", help="Allow SPIKE to increase decimation to meet frame/memory limits")
    parser.add_argument("--playback-fps", type=int, default=20, help="Preferred desktop/report playback rate")
    parser.add_argument("--initial-condition", choices=["operating_point", "zero"], default="operating_point")
    parser.add_argument("--source-waveform", action="append", type=waveform, metavar="PROFILE", help="Source waveform; one value broadcasts or repeat per --source")
    parser.add_argument("--load-waveform", action="append", type=waveform, metavar="PROFILE", help="Load waveform; one value broadcasts or repeat per --load")
    parser.add_argument("--max-internal-steps", type=int, default=50000)
    parser.add_argument("--max-output-frames", type=int, default=1000)
    parser.add_argument("--max-transient-branches", type=int, help="Optional transient branch cap within the RAM-derived dense-workspace capacity")
    parser.add_argument("--max-solver-time-s", type=float, default=120.0, help="Wall-time limit for matrix extraction and integration")
    parser.add_argument("--memory-budget-mb", type=float, default=2048.0, help="Transient dense-workspace and saved-frame budget")
    parser.add_argument("--capacitance-model", choices=["auto", "stackup_shunt", "none"], default="auto")
    parser.add_argument("--visual-sample-limit", type=int, default=12000, help="Maximum node/branch samples stored per frame")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spike", description="SPIKE local-first PI/SI automation CLI")
    parser.add_argument("--version", action="version", version=f"SPIKE CLI {CLI_VERSION}")
    parser.add_argument("--output", "-o", type=Path, help="Write the command result to a file")
    parser.add_argument("--output-format", choices=["json", "text"], default="json")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    parser.add_argument("--quiet", action="store_true", help="Do not write the result to stdout")
    parser.add_argument("--fail-on-warning", action="store_true", help=f"Return exit code {EXIT_WARNING} when warnings exist")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities", help="Show worker and analysis capabilities")
    sub.add_parser("capability-ledger", help="Show native ownership, validation, and release gates for every workflow")
    project_inspect = sub.add_parser("project-inspect", help="Inspect a SPIKE v3 package or supported legacy project without extracting it")
    project_inspect.add_argument("project", type=Path)
    project_migrate = sub.add_parser("project-migrate", help="Migrate a legacy SPIKE JSON project into a secure v3 package")
    project_migrate.add_argument("project", type=Path)
    project_migrate.add_argument("destination", type=Path)
    solvers = sub.add_parser("solvers", help="List solver plugins and validity limits")
    solvers.add_argument("--available", action="store_true")
    sub.add_parser("extensions", help="List installed extension modules")
    sub.add_parser("accelerators", help="List optional numerical acceleration backends and selection policy")
    sub.add_parser("external-engines", help="List optional external engineering engines and adapter readiness")
    sub.add_parser("solver-manager", help="Show workload recommendations, registrations, tuning, and execution gates")
    sub.add_parser(
        "sparselizard-runtime-status",
        help="Verify the integrity-bound native sparseLizard runtime without enabling PCB solver capabilities",
    )
    sparselizard_validation = sub.add_parser(
        "sparselizard-validation-status",
        help="Evaluate signed-runtime, PETSc/MUMPS, convergence, and PCB fixture release gates",
    )
    sparselizard_validation.add_argument(
        "--evidence-root", type=Path,
        help="Directory containing spike/sparselizard-validation-evidence/v1 fixture results",
    )
    recommend = sub.add_parser("solver-recommend", help="Recommend the best currently runnable solver for a workload")
    recommend.add_argument("workload", choices=[
        "dc_pi", "quasistatic_ac_pi", "geometry_transient", "circuit_cosimulation",
        "fullwave_comparison", "thermal_airflow", "emi_radiation",
    ])
    register = sub.add_parser("solver-register", help="Register an explicit local external-engine path without installing it")
    register.add_argument("engine")
    register.add_argument("path", type=Path)
    unregister = sub.add_parser("solver-unregister", help="Forget an external-engine registration without deleting its files")
    unregister.add_argument("engine")
    tune = sub.add_parser("solver-tune", help="Save allowlisted, range-checked solver tuning values")
    tune.add_argument("target")
    tune.add_argument("setting", nargs="+", type=tuning_assignment, metavar="KEY=VALUE")
    sub.add_parser("dependencies", help="Verify the bundled dependency lock")
    sub.add_parser("benchmark", help="Run analytical, convergence, and native solver benchmarks")
    pi_qualification = sub.add_parser(
        "pi-release-qualification",
        help="Fail closed unless the packaged runtime and all stable PI workflow gates pass",
    )
    pi_qualification.add_argument(
        "--runtime-report",
        type=Path,
        default=Path("build/release-runtime-qualification.json"),
        help="Passing spike/release-runtime-qualification/v1 report",
    )
    pi_qualification.add_argument(
        "--benchmark-report",
        type=Path,
        help="Existing benchmark report; omit to run the native corpus now",
    )
    openems_benchmark = sub.add_parser(
        "openems-benchmark",
        help="Run the real openEMS simple-patch reference and mesh-convergence gate",
    )
    openems_benchmark.add_argument(
        "--mesh-resolution-mm",
        type=float,
        nargs="+",
        default=[5.0, 4.0, 3.0],
        help="One or more mesh resolutions; three are required for convergence",
    )
    openems_benchmark.add_argument("--case-root", type=Path, default=Path("build/validation/openems-reference"))
    openems_benchmark.add_argument("--max-timesteps", type=int, default=50000)
    openems_benchmark.add_argument("--timeout-seconds", type=int, default=600)

    sub.add_parser("environment-list", help="List built-in cross-domain environment profiles")
    environment_materialize = sub.add_parser(
        "environment-materialize",
        help="Materialize a built-in preset or a user-owned environment profile",
    )
    environment_sources = environment_materialize.add_subparsers(dest="environment_source", required=True)
    environment_preset = environment_sources.add_parser("preset", help="Copy a built-in profile with optional overrides")
    environment_preset.add_argument("profile_id")
    environment_preset.add_argument("--overrides", type=Path, help="JSON object recursively applied to the preset")
    environment_user = environment_sources.add_parser("user", help="Create a user-owned profile from explicit physical inputs")
    environment_user.add_argument("profile_id")
    environment_user.add_argument("--name", required=True)
    environment_user.add_argument("--physical", type=Path, help="JSON object containing explicit physical inputs")
    environment_user.add_argument("--source-title", default="User-supplied environment inputs")
    environment_user.add_argument("--source-locator", default="")

    environment_validate = sub.add_parser(
        "environment-validate",
        help="Validate environment input readiness for one or more solver domains",
    )
    environment_validate.add_argument("profile", type=Path, help="spike/environment-profile/v1 JSON")
    environment_validate.add_argument(
        "--domain",
        action="append",
        choices=["pi", "si", "thermal", "emi"],
        help="Requested solver domain; repeat as needed (defaults to all domains)",
    )

    import_design = sub.add_parser("import", aliases=["import-design"], help="Normalize an EDA design into DesignIR")
    import_design.add_argument("design", type=Path)
    import_design.add_argument("--format", default="", help="Explicit importer format (for example odb++)")
    import_design.add_argument("--step", default="", help="Select a board step in a multi-step ODB++ job")
    import_design.add_argument("--report", action="store_true", help="Return typed DesignIR and import quality report")

    validate = sub.add_parser("validate", help="Validate a design or SPIKE project")
    validate.add_argument("design", type=Path)

    inspect = sub.add_parser("inspect", help="Inspect normalized design content")
    inspect.add_argument("design", type=Path)
    inspect.add_argument("--section", choices=["summary", "nets", "layers", "components", "stackup", "regions", "bends", "issues", "all"], default="summary")

    extract = sub.add_parser("extract-net", help="Export complete geometry for one net")
    extract.add_argument("design", type=Path)
    extract.add_argument("--net", required=True)

    dc = sub.add_parser("analyze-dc", aliases=["dc"], help="Build and run a DC PI request")
    _configure_dc_parser(dc)
    setup_dc = sub.add_parser("setup-dc", help="Build a reproducible DC PI request without running it")
    _configure_dc_parser(setup_dc)

    ac = sub.add_parser("analyze-ac", aliases=["ac"], help="Build and run a hybrid PEEC R/L/C/G request")
    _configure_ac_parser(ac)
    setup_ac = sub.add_parser("setup-ac", help="Build a reproducible AC PEEC request without running it")
    _configure_ac_parser(setup_ac)

    transient = sub.add_parser("analyze-transient", aliases=["transient"], help="Run a geometry-derived quasi-static PEEC RLC transient")
    _configure_transient_parser(transient)
    setup_transient = sub.add_parser("setup-transient", help="Build a reproducible quasi-static PEEC RLC transient request without running it")
    _configure_transient_parser(setup_transient)

    preflight = sub.add_parser("preflight", help="Validate an analysis request and generate its pre-solve mesh")
    preflight.add_argument("request", type=Path)
    preflight.add_argument("--include-cells", action="store_true", help="Include full mesh cell geometry in terminal/JSON output")

    preview = sub.add_parser("mesh-preview", help="Generate a pre-solve mesh from an analysis request")
    preview.add_argument("request", type=Path)
    preview.add_argument(
        "--dimension",
        choices=["surface_2_5d", "volume_3d"],
        help="Override the request mesh representation.",
    )
    preview.add_argument(
        "--target-size-mm",
        type=float,
        help="Override the request target mesh size.",
    )

    converge = sub.add_parser("converge", help="Run coarse-to-fine PI mesh convergence from an analysis request")
    converge.add_argument("request", type=Path)
    converge.add_argument("--levels", type=float, nargs="+", default=[2.0, 1.0, 0.5], help="Strictly decreasing mesh scale factors")
    converge.add_argument("--metric-tolerance-percent", type=float, help="Override all non-density metric tolerances")
    converge.add_argument("--density-tolerance-percent", type=float, help="Override peak current-density tolerance")

    run = sub.add_parser("run", help="Execute an analysis request, batch manifest, or SPIKE project")
    run.add_argument("input", type=Path)
    run.add_argument("--continue-on-error", action="store_true")

    emi_preflight = sub.add_parser("emi-preflight", help="Validate a versioned EMI setup without running field physics")
    emi_preflight.add_argument("design", type=Path, help="DesignIR, KiCad board, or SPIKE project")
    emi_preflight.add_argument("setup", type=Path, help="spike/emi-setup/v1 JSON")

    emi_screen = sub.add_parser("emi-screen", help="Rank EMI review nets from supplied pre-pass metrics")
    emi_screen.add_argument("design", type=Path, help="DesignIR, KiCad board, or SPIKE project")
    emi_screen.add_argument("setup", type=Path, help="spike/emi-setup/v1 JSON")

    openems_prepare = sub.add_parser("openems-prepare", help="Prepare an inspectable openEMS case from an analysis request")
    openems_prepare.add_argument("request", type=Path, help="spike/analysis-request/v1 JSON with selected nets and optional explicit ports")
    openems_prepare.add_argument("--case-dir", type=Path, help="New output directory; defaults to the local SPIKE job store")
    openems_prepare.add_argument("--mesh-resolution-mm", type=float, default=0.5)
    openems_prepare.add_argument("--max-solver-time-s", type=int, default=3600)

    openems_run = sub.add_parser("openems-run", help="Build or execute a prepared SPIKE openEMS case")
    openems_run.add_argument("case_dir", type=Path)
    openems_run.add_argument("--setup-only", action="store_true", help="Generate the CSXCAD XML without running FDTD")
    openems_run.add_argument("--timeout-seconds", type=int, default=3600)

    sparselizard_prepare = sub.add_parser(
        "sparselizard-prepare",
        help="Prepare a reviewed differential-port PI multiport case for sparseLizard",
    )
    sparselizard_prepare.add_argument("request", type=Path, help="spike/analysis-request/v1 JSON with options.ports")
    sparselizard_prepare.add_argument("--case-dir", type=Path, required=True)

    sparselizard_run = sub.add_parser(
        "sparselizard-run",
        help="Execute a prepared case through an exact spike-sparselizard-adapter executable",
    )
    sparselizard_run.add_argument("case_dir", type=Path)
    sparselizard_run.add_argument("--adapter", type=Path, help="Explicit local adapter; otherwise use registration or PATH")
    sparselizard_run.add_argument("--timeout-seconds", type=int, default=3600)
    sparselizard_run.add_argument("--memory-limit-mb", type=int, default=4096)

    report = sub.add_parser("report", help="Generate a report from an AnalysisResult JSON file")
    report.add_argument("result", type=Path)
    report.add_argument("--report-format", choices=["html", "pdf", "csv", "json"], default="html")
    report.add_argument("--report-output", type=Path, required=True)

    compare = sub.add_parser("compare", help="Compare two AnalysisResult files")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--tolerance-percent", type=float, default=1.0)

    pdn = sub.add_parser("pdn-review", help="Check an AC result against a PDN target and screen lumped decoupling candidates")
    pdn.add_argument("result", type=Path)
    pdn.add_argument("--target-ohm", type=float, required=True)
    pdn.add_argument("--net", default="")
    pdn.add_argument("--candidate", action="append", default=[], metavar="ID,C_F,ESR_OHM,ESL_H[,COUNT]", help="Lumped shunt capacitor candidate; repeat as needed")
    pdn.add_argument("--candidate-file", action="append", default=[], type=Path, help="JSON candidate, candidate array, or object containing a candidates array; repeat as needed")

    pdn_optimize = sub.add_parser(
        "pdn-optimize",
        help="Search explicit capacitor ports and a finite component library using a PDN multiport result",
    )
    pdn_optimize.add_argument("result", type=Path)
    pdn_optimize.add_argument("--target-ohm", type=float, required=True)
    pdn_optimize.add_argument("--net", default="")
    pdn_optimize.add_argument("--library", type=Path, required=True, help="PDN optimization request or capacitor-library JSON")
    pdn_optimize.add_argument("--constraints", type=Path, help="Optional JSON object overriding optimization constraints")

    external_pi_import = sub.add_parser(
        "external-pi-import",
        help="Validate and normalize an external PI multiport result for PDN analysis",
    )
    external_pi_import.add_argument("result", type=Path)
    external_pi_import.add_argument("--engine-id", default="")
    external_pi_import.add_argument(
        "--frequency-grid",
        type=Path,
        help="Optional JSON frequency array or object with frequency_hz",
    )

    peec_spice_import = sub.add_parser(
        "peec-spice-import",
        help="Import reviewed PEEC RLCG networks into a visual SPICE workspace",
    )
    peec_spice_import.add_argument("extraction_result", type=Path)
    peec_spice_import.add_argument("workspace", type=Path)
    peec_spice_import.add_argument("mappings", type=Path, help="JSON array of reviewed network-to-circuit-node mappings")

    hybrid = sub.add_parser(
        "hybrid-run",
        help="Run reviewed PEEC RLCG plus explicit component models through ngspice",
    )
    hybrid.add_argument("design", type=Path)
    hybrid.add_argument("extraction_result", type=Path)
    hybrid.add_argument("workspace", type=Path)
    hybrid.add_argument("mappings", type=Path)
    hybrid.add_argument("--timeout-seconds", type=int, default=120)

    native_mna_validate = sub.add_parser(
        "native-mna-validate",
        help="Validate a versioned native linear MNA circuit request without solving it",
    )
    native_mna_validate.add_argument("request", type=Path)
    native_mna_run = sub.add_parser(
        "native-mna-run",
        help="Run a versioned native linear MNA DC, AC, or transient circuit request",
    )
    native_mna_run.add_argument("request", type=Path)

    native_workspace_compile = sub.add_parser(
        "native-workspace-compile",
        help="Compile a reviewed visual SPICE workspace into the native linear MNA contract",
    )
    native_workspace_compile.add_argument("design", type=Path)
    native_workspace_compile.add_argument("workspace", type=Path)
    native_workspace_run = sub.add_parser(
        "native-workspace-run",
        help="Compile and run a reviewed visual SPICE workspace with the native linear MNA engine",
    )
    native_workspace_run.add_argument("design", type=Path)
    native_workspace_run.add_argument("workspace", type=Path)

    field_circuit_validate = sub.add_parser(
        "field-circuit-validate",
        help="Fail-closed validation for a reviewed DesignIR, SPICE workspace, and PEEC field-circuit package",
    )
    field_circuit_validate.add_argument(
        "package",
        type=Path,
        help=f"{FIELD_CIRCUIT_PACKAGE_CONTRACT} JSON input",
    )
    field_circuit_run = sub.add_parser(
        "field-circuit-run",
        help="Run a reviewed field-circuit co-simulation through the native PEEC reduction provider",
    )
    field_circuit_run.add_argument(
        "package",
        type=Path,
        help=f"{FIELD_CIRCUIT_PACKAGE_CONTRACT} JSON input",
    )

    converter = sub.add_parser(
        "converter-study",
        help="Run a reviewed PWM converter study through ngspice, optional PEEC, analytics, and thermal handoff",
    )
    converter.add_argument("design", type=Path)
    converter.add_argument("study", type=Path, help="spike/converter-study/v1 JSON")
    converter.add_argument("--extraction-result", type=Path, help="Optional PEEC result required when the study declares peec mappings")
    converter.add_argument("--timeout-seconds", type=int, default=120)

    thermal = sub.add_parser("thermal-estimate", help="Run the explicit first-order compact thermal RC estimator")
    thermal.add_argument("scenario", type=Path, help="ThermalScenario JSON or an object containing a scenario field")

    sparam = sub.add_parser(
        "sparam-inspect",
        aliases=["touchstone"],
        help="Inspect Touchstone data, network traces, and validity checks",
    )
    sparam.add_argument("network", type=Path)
    sparam.add_argument(
        "--trace-limit",
        type=int,
        default=2000,
        help="Maximum serialized points per S-parameter trace",
    )

    renormalize = sub.add_parser(
        "sparam-renormalize",
        help="Convert a Touchstone network to a new real reference impedance",
    )
    renormalize.add_argument("network", type=Path)
    renormalize.add_argument("--to-ohms", type=float, required=True)
    renormalize.add_argument("--touchstone-output", type=Path, required=True)
    renormalize.add_argument("--format", choices=["RI", "MA", "DB"], default="RI")
    si_channel = sub.add_parser(
        "si-geometry-channel",
        help="Run the bounded straight DesignIR v2 geometry-to-RLGC/S/TDR/TDT/NRZ-eye channel",
    )
    si_channel.add_argument("design", type=Path, help="DesignIR v2 JSON or object containing design_ir")
    si_channel.add_argument("request", type=Path, help=f"{SI_CHANNEL_REQUEST_CONTRACT} JSON")
    si_workflow = sub.add_parser("si-workflow", help="Run an experimental source/receiver/passive loaded SI study")
    si_workflow.add_argument("request", type=Path, help="SI workflow request JSON")
    si_workflow.add_argument("--design", type=Path, help="Optional canonical DesignIR v2 JSON for geometry extraction")
    si_workflow.add_argument("--touchstone-output", type=Path, help="Export the edited channel (without endpoint loading)")
    harness_pi = sub.add_parser("harness-pi", help="Run explicit-pin lumped DC harness PI (experimental)")
    harness_pi.add_argument("--request", required=True, type=Path, help="spike/harness-pi-request/v1 JSON")
    tetra = sub.add_parser("tetra-mesh", help="Generate first-order tetrahedra from typed solids using the admitted local OCC runtime")
    tetra.add_argument("--request", required=True, type=Path)
    tetra.add_argument("--timeout-s", type=int, default=180)
    tetra.add_argument("--memory-limit-mb", type=int, default=2048)
    return parser


def dispatch(args: argparse.Namespace) -> tuple[Any, int]:
    if args.command == "capabilities":
        result = _response("capabilities")["result"]
    elif args.command == "capability-ledger":
        result = _response("capability_ledger")["result"]
    elif args.command == "project-inspect":
        result = _response("read_project_package", {"path": str(args.project.resolve())})["result"]
        result = {
            "contract": result["contract"],
            "manifest": result["manifest"],
            "migrated": result["migrated"],
            "source_format": result["source_format"],
            "project": result["canonical"].get("project", {}),
            "design": {
                "contract": result["canonical"].get("design_ir", {}).get("contract", ""),
                "design_id": result["canonical"].get("design_ir", {}).get("design_id", ""),
                "name": result["canonical"].get("design_ir", {}).get("name", ""),
            },
        }
    elif args.command == "project-migrate":
        opened = _response("read_project_package", {"path": str(args.project.resolve())})["result"]
        if not opened.get("migrated"):
            raise CliError("project-migrate accepts a supported legacy JSON project; the input is already v3.")
        result = _response("write_project_package", {
            "path": str(args.destination.resolve()),
            # Use the canonical migrated payload, not the frontend projection.
            # The projection intentionally omits the legacy format/design wrapper
            # that canonicalize_project_payload needs to recognize a migrated
            # snapshot.  Passing the canonical payload also preserves analyses,
            # reports, models and migration audit data losslessly.
            "snapshot": opened["canonical"],
            "profile": "portable_project",
            # Legacy JSON projects do not carry Arrow geometry tables and
            # migration must remain usable on installations without pyarrow.
            "generate_geometry_tables": False,
        })["result"]
    elif args.command == "solvers":
        result = _response("list_solvers")["result"]
        if args.available:
            result = {**result, "solvers": [item for item in result.get("solvers", []) if item.get("state") in {"available", "experimental"}]}
    elif args.command == "extensions":
        result = _response("list_extensions")["result"]
    elif args.command == "accelerators":
        result = _response("list_accelerators")["result"]
    elif args.command == "external-engines":
        result = _response("list_external_engines")["result"]
    elif args.command == "solver-manager":
        result = _response("solver_manager")["result"]
    elif args.command == "sparselizard-runtime-status":
        result = _response("sparselizard_runtime_status")["result"]
    elif args.command == "sparselizard-validation-status":
        result = _response("sparselizard_validation_status", {
            "evidence_root": str(args.evidence_root.resolve()) if args.evidence_root else "",
        })["result"]
    elif args.command == "solver-recommend":
        result = _response("recommend_solver", {"workload_id": args.workload})["result"]
    elif args.command == "solver-register":
        result = _response("register_external_solver", {"engine_id": args.engine, "path": str(args.path)})["result"]
    elif args.command == "solver-unregister":
        result = _response("unregister_external_solver", {"engine_id": args.engine})["result"]
    elif args.command == "solver-tune":
        result = _response("tune_solver", {"target_id": args.target, "values": dict(args.setting or [])})["result"]
    elif args.command == "dependencies":
        result = _response("dependencies")["result"]
    elif args.command == "benchmark":
        result = run_solver_benchmarks()
    elif args.command == "pi-release-qualification":
        result = qualify_pi_release(
            load_json_report(args.runtime_report),
            load_json_report(args.benchmark_report) if args.benchmark_report else run_solver_benchmarks(),
        )
    elif args.command == "openems-benchmark":
        if any(value <= 0 for value in args.mesh_resolution_mm):
            raise CliError("openEMS mesh resolutions must be positive.")
        case_root = args.case_root.resolve()
        reports = [
            run_patch_antenna_benchmark(
                case_root / f"mesh-{resolution:g}mm",
                mesh_resolution_mm=resolution,
                max_timesteps=args.max_timesteps,
                timeout_seconds=args.timeout_seconds,
            )
            for resolution in args.mesh_resolution_mm
        ]
        convergence = evaluate_mesh_convergence(reports) if len(reports) >= 3 else None
        result = {
            "contract": "spike/openems-benchmark-suite/v1",
            "status": convergence.get("status") if convergence else reports[0].get("status"),
            "runs": reports,
            "convergence": convergence,
            "case_root": str(case_root),
        }
    elif args.command == "environment-list":
        result = _response("list_environment_profiles")["result"]
    elif args.command == "environment-materialize":
        if args.environment_source == "preset":
            overrides = _read_json(args.overrides) if args.overrides else {}
            result = _response("materialize_environment_profile", {
                "source": "preset",
                "profile_id": args.profile_id,
                "overrides": overrides,
            })["result"]
        else:
            physical = _read_json(args.physical) if args.physical else {}
            result = _response("materialize_environment_profile", {
                "source": "user",
                "profile_id": args.profile_id,
                "name": args.name,
                "physical": physical,
                "source_title": args.source_title,
                "source_locator": args.source_locator,
            })["result"]
    elif args.command == "environment-validate":
        profile = _read_json(args.profile)
        if isinstance(profile.get("profile"), dict):
            profile = profile["profile"]
        result = _response("validate_environment_profile", {
            "profile": profile,
            "domains": args.domain or ["pi", "si", "thermal", "emi"],
        })["result"]
    elif args.command in {"import", "import-design"}:
        if args.format or args.step or args.report or args.design.is_dir():
            result = _response("import_design_v2" if args.report else "load_design", {"path": str(args.design), "format_hint": args.format, "options": {"step": args.step} if args.step else {}})["result"]
        else:
            result = load_design(args.design)
    elif args.command == "validate":
        design = load_design(args.design)
        result = _response("validate_design", {"design": design})["result"]
    elif args.command == "inspect":
        design = load_design(args.design)
        result = _design_summary(design) if args.section == "summary" else design if args.section == "all" else design.get(args.section, [])
    elif args.command == "extract-net":
        design = load_design(args.design)
        result = _response("extract_net_geometry", {"design": design, "net_name": args.net})["result"]
    elif args.command == "setup-dc":
        if args.memory_limit_gb < 2:
            raise CliError("Solver memory limit must be at least 2 GB.")
        if args.via_plating_mm <= 0:
            raise CliError("Via plating thickness must be positive.")
        result = _analysis_request(args)
        if args.save_request:
            args.save_request.parent.mkdir(parents=True, exist_ok=True)
            args.save_request.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    elif args.command in {"analyze-dc", "dc"}:
        if args.memory_limit_gb < 2:
            raise CliError("Solver memory limit must be at least 2 GB.")
        if args.via_plating_mm <= 0:
            raise CliError("Via plating thickness must be positive.")
        request = _analysis_request(args)
        if args.save_request:
            args.save_request.parent.mkdir(parents=True, exist_ok=True)
            args.save_request.write_text(json.dumps(request, indent=2, default=str) + "\n", encoding="utf-8")
        result = execute_request(request)
    elif args.command == "setup-ac":
        if args.memory_limit_gb < 2:
            raise CliError("Solver memory limit must be at least 2 GB.")
        if args.start_hz <= 0 or args.stop_hz <= args.start_hz or args.points < 2:
            raise CliError("AC extraction requires 0 < start-hz < stop-hz and at least two points.")
        if args.via_plating_mm <= 0:
            raise CliError("Via plating thickness must be positive.")
        result = _ac_analysis_request(args)
        if args.save_request:
            args.save_request.parent.mkdir(parents=True, exist_ok=True)
            args.save_request.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    elif args.command in {"analyze-ac", "ac"}:
        if args.memory_limit_gb < 2:
            raise CliError("Solver memory limit must be at least 2 GB.")
        if args.start_hz <= 0 or args.stop_hz <= args.start_hz or args.points < 2:
            raise CliError("AC extraction requires 0 < start-hz < stop-hz and at least two points.")
        if args.via_plating_mm <= 0:
            raise CliError("Via plating thickness must be positive.")
        request = _ac_analysis_request(args)
        if args.save_request:
            args.save_request.parent.mkdir(parents=True, exist_ok=True)
            args.save_request.write_text(json.dumps(request, indent=2, default=str) + "\n", encoding="utf-8")
        result = execute_request(request)
    elif args.command in {"setup-transient", "analyze-transient", "transient"}:
        if args.stop_time_s <= 0 or args.time_step_s is not None and (args.time_step_s <= 0 or args.time_step_s > args.stop_time_s):
            raise CliError("Transient requires a positive stop time and, when supplied, 0 < time-step-s <= stop-time-s.")
        if args.output_decimation < 1 or args.max_internal_steps < 1 or args.max_output_frames < 2 or (args.max_transient_branches is not None and args.max_transient_branches < 16):
            raise CliError("Transient decimation and solver limits must be positive.")
        if not 1 <= args.playback_fps <= 30:
            raise CliError("Transient playback-fps must be between 1 and 30.")
        if args.via_plating_mm <= 0:
            raise CliError("Via plating thickness must be positive.")
        if args.max_solver_time_s <= 0 or args.memory_budget_mb < 32 or args.visual_sample_limit < 100:
            raise CliError("Transient solver time must be positive, memory budget at least 32 MB, and visual sample limit at least 100.")
        request = _analysis_request(args, "transient")
        if args.save_request:
            args.save_request.parent.mkdir(parents=True, exist_ok=True)
            args.save_request.write_text(json.dumps(request, indent=2, default=str) + "\n", encoding="utf-8")
        if args.command == "setup-transient":
            result = request
        else:
            result = execute_request(request)
    elif args.command == "converge":
        request = _read_json(args.request)
        if not isinstance(request.get("design"), dict) or not isinstance(request.get("spec"), dict):
            raise CliError("Expected an analysis request containing design and spec.")
        options = {
            "levels": args.levels,
            "metric_tolerance": None if args.metric_tolerance_percent is None else args.metric_tolerance_percent / 100,
            "density_tolerance": None if args.density_tolerance_percent is None else args.density_tolerance_percent / 100,
        }
        result = _response("mesh_convergence", {"design": request["design"], "spec": request["spec"], "options": options})["result"]
    elif args.command in {"preflight", "mesh-preview"}:
        request = _read_json(args.request)
        if not isinstance(request.get("design"), dict) or not isinstance(request.get("spec"), dict):
            raise CliError("Expected an analysis request containing design and spec.")
        if args.command == "mesh-preview" and (args.dimension or args.target_size_mm is not None):
            mesh = dict(request["spec"].get("mesh", {}))
            if args.dimension:
                mesh["dimension"] = args.dimension
            if args.target_size_mm is not None:
                if args.target_size_mm <= 0:
                    raise CliError("Mesh target size must be positive.")
                mesh["target_size_mm"] = args.target_size_mm
            request = {
                **request,
                "spec": {**request["spec"], "mesh": mesh},
            }
        method = "preflight_analysis" if args.command == "preflight" else "preview_mesh"
        result = _response(method, {"design": request["design"], "spec": request["spec"]})["result"]
        if args.command == "preflight" and not args.include_cells and isinstance(result.get("mesh"), dict):
            result = {**result, "mesh": {**result["mesh"]}}
            cells = result["mesh"].pop("cells", [])
            result["mesh"]["cell_count"] = result["mesh"].get("cell_count", len(cells))
    elif args.command == "run":
        if args.input.suffix.lower() == ".spike":
            result = execute_request(_project_request(args.input))
        else:
            value = _read_json(args.input)
            if value.get("format") in {"spike-project-package/v1", "spike-project-package/v2"}:
                result = execute_request(_project_request(args.input))
            elif value.get("contract") == "spike/analysis-batch/v1" or isinstance(value.get("jobs"), list):
                result = execute_batch(value, args.continue_on_error)
            else:
                result = execute_request(value)
    elif args.command in {"emi-preflight", "emi-screen"}:
        design = load_design(args.design)
        setup = _read_json(args.setup)
        method = "emi_preflight" if args.command == "emi-preflight" else "emi_screen"
        result = _response(method, {"design": design, "setup": setup})["result"]
    elif args.command == "openems-prepare":
        if args.mesh_resolution_mm <= 0 or args.max_solver_time_s <= 0:
            raise CliError("openEMS mesh resolution and solver time must be positive.")
        request = _read_json(args.request)
        if request.get("contract") != "spike/analysis-request/v1" or not isinstance(request.get("design"), dict) or not isinstance(request.get("spec"), dict):
            raise CliError("Expected a spike/analysis-request/v1 object containing design and spec.")
        result = _response("prepare_openems_case", {
            "design": request["design"],
            "spec": request["spec"],
            "output_dir": str(args.case_dir.resolve()) if args.case_dir else None,
            "options": {
                "mesh_resolution_mm": args.mesh_resolution_mm,
                "max_solver_time_s": args.max_solver_time_s,
            },
        })["result"]
    elif args.command == "openems-run":
        if args.timeout_seconds <= 0:
            raise CliError("openEMS timeout must be positive.")
        result = _response("run_openems_case", {
            "case_dir": str(args.case_dir.resolve()),
            "setup_only": args.setup_only,
            "timeout_seconds": args.timeout_seconds,
        })["result"]
    elif args.command == "sparselizard-prepare":
        request = _read_json(args.request)
        if (
            request.get("contract") != "spike/analysis-request/v1"
            or not isinstance(request.get("design"), dict)
            or not isinstance(request.get("spec"), dict)
        ):
            raise CliError("Expected a spike/analysis-request/v1 object containing design and spec.")
        options = request["spec"].get("options", {})
        ports = options.get("ports") if isinstance(options, dict) else None
        result = _response("prepare_sparselizard_case", {
            "design": request["design"],
            "spec": request["spec"],
            "ports": ports,
            "output_dir": str(args.case_dir.resolve()),
        })["result"]
    elif args.command == "sparselizard-run":
        if not 1 <= args.timeout_seconds <= 604800:
            raise CliError("sparseLizard timeout must be between 1 and 604800 seconds.")
        if not 128 <= args.memory_limit_mb <= 1_048_576:
            raise CliError("sparseLizard memory limit must be between 128 and 1048576 MiB.")
        result = _response("run_sparselizard_case", {
            "case_dir": str(args.case_dir.resolve()),
            "executable": str(args.adapter.resolve()) if args.adapter else None,
            "timeout_s": args.timeout_seconds,
            "memory_limit_mb": args.memory_limit_mb,
        })["result"]
    elif args.command == "report":
        result_data = _read_json(args.result)
        if "result" in result_data and isinstance(result_data["result"], dict):
            result_data = result_data["result"]
        is_batch = result_data.get("contract") == BATCH_RESULT_CONTRACT
        try:
            report_data = normalize_pi_batch_report(result_data) if is_batch else result_data
        except BatchReportError as exc:
            raise CliError(f"Cannot generate batch report: {exc}") from exc
        content = json.dumps(report_data, indent=2, default=str)
        if args.report_format == "html":
            content = _html_batch_report(report_data) if is_batch else _html_report(report_data)
        elif args.report_format == "csv":
            content = _csv_batch_report(report_data) if is_batch else _csv_result(report_data)
        if args.report_format == "pdf":
            _write_pdf_report(_batch_as_pdf_result(report_data) if is_batch else report_data, args.report_output)
        else:
            args.report_output.parent.mkdir(parents=True, exist_ok=True)
            args.report_output.write_text(content, encoding="utf-8")
        result = {
            "status": "completed",
            "report": str(args.report_output),
            "format": args.report_format,
            "source_contract": result_data.get("contract", ""),
            "report_contract": REPORT_DATA_CONTRACT if is_batch else "spike/analysis-report/v1",
        }
    elif args.command == "compare":
        baseline = _read_json(args.baseline)
        candidate = _read_json(args.candidate)
        if "result" in baseline:
            baseline = baseline["result"]
        if "result" in candidate:
            candidate = candidate["result"]
        metrics = {}
        exceeded = False
        comparison_keys = (
            "max_voltage_drop_v",
            "max_current_density_a_mm2",
            "total_copper_loss_w",
            "effective_path_resistance_ohm",
            "resistance_start_ohm",
            "resistance_stop_ohm",
            "partial_inductance_h",
        )
        for key in comparison_keys:
            if key not in baseline.get("summary", {}) and key not in candidate.get("summary", {}):
                continue
            before = float(baseline.get("summary", {}).get(key, 0))
            after = float(candidate.get("summary", {}).get(key, 0))
            percent = (after - before) / abs(before) * 100 if before else (0.0 if after == 0 else float("inf"))
            metrics[key] = {"baseline": before, "candidate": after, "change_percent": percent}
            exceeded = exceeded or percent > args.tolerance_percent
        result = {"contract": "spike/result-comparison/v1", "status": "regression" if exceeded else "pass", "tolerance_percent": args.tolerance_percent, "metrics": metrics}
    elif args.command == "pdn-review":
        source = _read_json(args.result)
        if "result" in source and isinstance(source["result"], dict):
            source = source["result"]
        candidates = []
        for raw in args.candidate:
            parts = [item.strip() for item in raw.split(",")]
            if len(parts) not in {4, 5}:
                raise CliError("PDN candidates use ID,C_F,ESR_OHM,ESL_H[,COUNT].")
            candidates.append({
                "id": parts[0],
                "capacitance_f": float(parts[1]),
                "esr_ohm": float(parts[2]),
                "esl_h": float(parts[3]),
                "count": int(parts[4]) if len(parts) == 5 else 1,
            })
        for path in args.candidate_file:
            candidate_data = _read_json_value(path)
            if isinstance(candidate_data, dict) and isinstance(candidate_data.get("candidates"), list):
                contract = candidate_data.get("contract")
                if contract is not None and contract != PDN_CANDIDATE_CONTRACT:
                    raise CliError(f"PDN candidate set {path} uses unsupported contract {contract!r}; expected {PDN_CANDIDATE_CONTRACT}.")
                candidate_data = candidate_data["candidates"]
            elif isinstance(candidate_data, dict):
                candidate_data = [candidate_data]
            if not isinstance(candidate_data, list) or any(not isinstance(item, dict) for item in candidate_data):
                raise CliError("PDN candidate files must contain a candidate object, an array of candidates, or a candidates array.")
            candidates.extend(candidate_data)
        if len(candidates) > MAX_PDN_CANDIDATES:
            raise CliError(f"PDN review accepts at most {MAX_PDN_CANDIDATES} candidates per run; received {len(candidates)}.")
        result = _response("pdn_review", {
            "result": source,
            "target_ohm": args.target_ohm,
            "net": args.net,
            "candidates": candidates,
        })["result"]
    elif args.command == "pdn-optimize":
        source = _read_json(args.result)
        if "result" in source and isinstance(source["result"], dict):
            source = source["result"]
        request = _read_json(args.library)
        contract = request.get("contract")
        if contract is not None and contract not in {
            "spike/pdn-optimization/v1",
            "spike/pdn-optimization-request/v1",
            "spike/pdn-capacitor-library/v1",
        }:
            raise CliError(
                f"PDN optimization input uses unsupported contract {contract!r}."
            )
        library = request.get("capacitor_library", request.get("components", request.get("candidates", [])))
        constraints = request.get("constraints", {})
        if not isinstance(library, list) or any(not isinstance(item, dict) for item in library):
            raise CliError("PDN optimization input must contain a capacitor_library array.")
        if not isinstance(constraints, dict):
            raise CliError("PDN optimization constraints must be an object.")
        if args.constraints:
            overrides = _read_json(args.constraints)
            constraints = {**constraints, **overrides}
        result = _response("pdn_optimize", {
            "result": source,
            "target_ohm": args.target_ohm,
            "net": args.net,
            "capacitor_library": library,
            "constraints": constraints,
        })["result"]
    elif args.command == "external-pi-import":
        external = _read_json(args.result)
        expected_frequencies = None
        if args.frequency_grid:
            grid = _read_json_value(args.frequency_grid)
            if isinstance(grid, dict):
                grid = grid.get("frequency_hz")
            if not isinstance(grid, list):
                raise CliError("External PI frequency grid must be a JSON array or frequency_hz array.")
            expected_frequencies = grid
        result = _response("import_external_pi_multiport", {
            "result": external,
            "expected_engine_id": args.engine_id,
            "expected_frequencies_hz": expected_frequencies,
        })["result"]
    elif args.command in {"peec-spice-import", "hybrid-run"}:
        extraction = _read_json(args.extraction_result)
        if "result" in extraction and isinstance(extraction["result"], dict):
            extraction = extraction["result"]
        workspace = _read_json(args.workspace)
        mappings = _read_json_value(args.mappings)
        if isinstance(mappings, dict):
            mappings = mappings.get("mappings")
        if not isinstance(mappings, list) or any(not isinstance(item, dict) for item in mappings):
            raise CliError("PEEC-to-SPICE mappings must be a JSON array or an object containing a mappings array.")
        if args.command == "peec-spice-import":
            result = _response("import_peec_rlcg", {
                "extraction_result": extraction,
                "workspace": workspace,
                "mappings": mappings,
            })["result"]
        else:
            design = load_design(args.design)
            if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
                raise CliError("Hybrid ngspice timeout must be between 1 and 3600 seconds.")
            result = _response("run_hybrid_cosimulation", {
                "design": design,
                "extraction_result": extraction,
                "workspace": workspace,
                "mappings": mappings,
                "timeout_seconds": args.timeout_seconds,
            })["result"]
    elif args.command in {"native-mna-validate", "native-mna-run"}:
        circuit_request = _read_json(args.request)
        method = "validate_native_mna" if args.command == "native-mna-validate" else "run_native_mna"
        result = _response(method, {"request": circuit_request})["result"]
    elif args.command in {"native-workspace-compile", "native-workspace-run"}:
        method = (
            "compile_spice_workspace_native_mna"
            if args.command == "native-workspace-compile"
            else "run_spice_workspace_native_mna"
        )
        result = _response(method, {
            "design": load_design(args.design),
            "workspace": _read_json(args.workspace),
        })["result"]
    elif args.command in {"field-circuit-validate", "field-circuit-run"}:
        package, structural_validation = _field_circuit_package(args.package)
        validation = _validate_field_circuit_package(package, structural_validation)
        if args.command == "field-circuit-validate" or not validation["valid"]:
            result = validation
        else:
            result = _response("run_field_circuit_cosimulation", {
                "design": package["design"],
                "workspace": package["workspace"],
                "request": package["request"],
                "field_analysis_spec": package["field_analysis_spec"],
            })["result"]
    elif args.command == "converter-study":
        if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
            raise CliError("Converter-study timeout must be between 1 and 3600 seconds.")
        study = _read_json(args.study)
        if study.get("contract") != "spike/converter-study/v1":
            raise CliError("Expected a spike/converter-study/v1 study.")
        extraction = _read_json(args.extraction_result) if args.extraction_result else None
        if isinstance(extraction, dict) and isinstance(extraction.get("result"), dict):
            extraction = extraction["result"]
        result = _response("run_converter_study", {
            "design": load_design(args.design),
            "study": study,
            "extraction_result": extraction,
            "timeout_seconds": args.timeout_seconds,
        })["result"]
    elif args.command == "thermal-estimate":
        scenario_data = _read_json(args.scenario)
        if isinstance(scenario_data.get("scenario"), dict):
            scenario_data = scenario_data["scenario"]
        if scenario_data.get("contract") != "spike/thermal/v1":
            raise CliError("Expected a spike/thermal/v1 scenario.")
        result = _response("estimate_thermal", {"scenario": scenario_data})["result"]
    elif args.command in {"sparam-inspect", "touchstone"}:
        if args.trace_limit < 2:
            raise CliError("Touchstone trace limit must be at least two points.")
        result = analyze_network(
            read_touchstone(args.network),
            trace_limit=args.trace_limit,
        )
    elif args.command == "sparam-renormalize":
        if args.to_ohms <= 0:
            raise CliError("The new reference impedance must be positive.")
        network = read_touchstone(args.network)
        converted = renormalize_s(
            network.s_parameters(),
            network.reference_impedance_ohm,
            args.to_ohms,
        )
        write_touchstone(
            args.touchstone_output,
            network.frequencies_hz,
            converted,
            args.to_ohms,
            data_format=args.format,
            comments=[
                "Renormalized by SPIKE",
                f"Source: {network.source}",
            ],
        )
        result = {
            "contract": "spike/touchstone-conversion/v1",
            "status": "completed",
            "source": network.source,
            "output": str(args.touchstone_output.resolve()),
            "port_count": network.port_count,
            "frequency_count": len(network.frequencies_hz),
            "old_reference_impedance_ohm": network.reference_impedance_ohm.tolist(),
            "new_reference_impedance_ohm": [args.to_ohms] * network.port_count,
            "data_format": args.format,
        }
    elif args.command == "tetra-mesh":
        if args.request.stat().st_size > 8 * 1024 * 1024:
            raise CliError("Tetrahedral mesh request exceeds 8 MiB.")
        result = _response("generate_tetrahedral_mesh", {"request": _read_json(args.request),
                           "timeout_s": args.timeout_s, "memory_limit_mb": args.memory_limit_mb})["result"]
    elif args.command == "harness-pi":
        if args.request.stat().st_size > 8 * 1024 * 1024:
            raise CliError("Harness PI request exceeds 8 MiB.")
        result = _response("run_harness_pi", {"request": _read_json(args.request)})["result"]
    elif args.command == "si-workflow":
        design_data = _read_json(args.design) if args.design else None
        if design_data and isinstance(design_data.get("design_ir"), dict):
            design_data = design_data["design_ir"]
        result = run_si_workflow(_read_json(args.request), design_data)
        if args.touchstone_output:
            network_export = result["touchstone"]
            if not network_export["text"]:
                raise CliError(network_export["error"] or "Touchstone export is unavailable.")
            expected_suffix = Path(network_export["name"]).suffix
            if args.touchstone_output.suffix.lower() != expected_suffix:
                raise CliError(f"Touchstone output requires the {expected_suffix} suffix.")
            args.touchstone_output.parent.mkdir(parents=True, exist_ok=True)
            args.touchstone_output.write_text(network_export["text"], encoding="ascii")
    elif args.command == "si-geometry-channel":
        design_data = _read_json(args.design)
        if isinstance(design_data.get("design_ir"), dict):
            design_data = design_data["design_ir"]
        request_data = _read_json(args.request)
        result = analyze_uniform_design_channel(
            DesignIRV2.from_dict(design_data),
            request_data,
        )
    else:
        raise CliError(f"Unsupported command: {args.command}")
    return result, _result_exit(result, args.fail_on_warning)


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result, exit_code = dispatch(args)
        _write_output(result, args)
        return exit_code
    except (CliError, OSError, ValueError, TypeError, KeyError) as exc:
        error = {"ok": False, "error": str(exc), "type": type(exc).__name__}
        _write_output(error, args)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
