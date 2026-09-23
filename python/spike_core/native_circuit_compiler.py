"""Compile reviewed visual circuit intent into the native linear MNA contract.

This compiler never parses raw SPICE netlists. It accepts only validated visual
workspace assignments, explicit pin-to-node bindings, structured source
waveforms, and reviewed PEEC RLCG endpoints. Unsupported nonlinear or ambiguous
models are reported as blockers instead of being replaced with approximations.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .contracts import DesignIR
from .native_mna import REQUEST_CONTRACT, run_native_mna, validate_native_mna_request
from .native_circuit_result import native_mna_to_analysis_result
from .spice_workspace import SPICE_WORKSPACE_CONTRACT, validate_spice_workspace


COMPILE_CONTRACT = "spike/native-circuit-compile/v1"
SUPPORTED_PRIMITIVES = {
    "resistor", "capacitor", "inductor", "voltage_source", "current_source",
    "vccs", "vcvs", "cccs", "ccvs",
}
PARAMETER_KEYS = {
    "resistor": "resistance_ohm",
    "capacitor": "capacitance_f",
    "inductor": "inductance_h",
    "vccs": "transconductance_s",
    "vcvs": "gain",
    "cccs": "gain",
    "ccvs": "transresistance_ohm",
}


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _identifier(value: Any) -> str:
    return str(value or "").strip()


def _element_id(prefix: str, value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_.:+-]", "_", _identifier(value)).strip("_") or "item"
    return f"{prefix}{token[:100]}"


def _finite(value: Any, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("requires a plain finite scalar or an explicit structured parameter") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        raise ValueError("requires a finite positive scalar" if positive else "requires a finite scalar")
    return number


_SPICE_SUFFIXES = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def _spice_scalar(value: Any, *, positive: bool = False) -> float:
    """Parse one scalar with standard SPICE engineering suffixes.

    This deliberately does not parse expressions, directives, or waveforms.
    Structured waveform objects remain the only native transient source input.
    """

    if isinstance(value, str):
        token = value.strip()
        match = re.fullmatch(
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[tgkmunpf])?",
            token,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError("requires a scalar with an optional SPICE engineering suffix")
        number = float(match.group(1))
        suffix = (match.group(2) or "").lower()
        if suffix:
            number *= _SPICE_SUFFIXES[suffix]
        return _finite(number, positive=positive)
    return _finite(value, positive=positive)


def _parameter(model: Dict[str, Any], key: str, *, positive: bool = False) -> float:
    parameters = model.get("parameters") or {}
    value = parameters.get(key, model.get("value"))
    return _spice_scalar(value, positive=positive)


def _source_parameters(model: Dict[str, Any]) -> Dict[str, Any]:
    parameters = dict(model.get("parameters") or {})
    waveform = parameters.get("waveform")
    result: Dict[str, Any] = {}
    if waveform is not None:
        if not isinstance(waveform, dict):
            raise ValueError("parameters.waveform must be an explicit waveform object")
        result["waveform"] = waveform
    elif "dc_value" in parameters:
        result["dc_value"] = _finite(parameters["dc_value"])
    else:
        raw_value = model.get("value", 0.0)
        if isinstance(raw_value, str) and raw_value.strip().lower().startswith("dc "):
            raw_value = raw_value.strip()[3:].strip()
        result["dc_value"] = _spice_scalar(raw_value)
    if "ac_magnitude" in parameters:
        magnitude = _finite(parameters["ac_magnitude"])
        if magnitude < 0.0:
            raise ValueError("parameters.ac_magnitude must be nonnegative")
        result["ac_magnitude"] = magnitude
    if "ac_phase_deg" in parameters:
        result["ac_phase_deg"] = _finite(parameters["ac_phase_deg"])
    return result


def _analysis(workspace_analysis: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(workspace_analysis["mode"])
    if mode == "operating_point":
        return {"mode": mode}
    if mode == "transient":
        return {
            "mode": mode,
            "time_step_s": float(workspace_analysis["time_step_s"]),
            "stop_time_s": float(workspace_analysis["stop_time_s"]),
        }
    start = float(workspace_analysis["start_hz"])
    stop = float(workspace_analysis["stop_hz"])
    points_per_decade = int(float(workspace_analysis["points_per_decade"]))
    points = max(2, int(math.ceil(math.log10(stop / start) * points_per_decade)) + 1)
    return {"mode": "ac", "start_hz": start, "stop_hz": stop, "points": points, "scale": "log"}


def compile_spice_workspace_to_native_mna(
    workspace: Dict[str, Any],
    design: DesignIR,
    *,
    resource_limits: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile a reviewed workspace and PEEC lumped sections into native MNA."""

    workspace_validation = validate_spice_workspace(workspace, design)
    issues: List[Dict[str, str]] = []
    if not workspace_validation["can_run"]:
        issues.extend(workspace_validation["issues"])
        return {
            "contract": COMPILE_CONTRACT,
            "status": "blocked",
            "issues": issues,
            "warnings": workspace_validation["warnings"],
            "workspace_validation": workspace_validation,
            "request": None,
        }

    models = {str(model["id"]): model for model in workspace["models"]}
    assignments = [item for item in workspace["assignments"] if item.get("enabled", True)]
    compiled_ids = {_identifier(item["id"]): _element_id("A_", item["id"]) for item in assignments}
    elements: List[Dict[str, Any]] = []
    for index, assignment in enumerate(assignments):
        path = f"assignments[{index}]"
        model = models[str(assignment["model_id"])]
        primitive = _identifier(model.get("primitive")) if model.get("kind") == "primitive" else ""
        if primitive not in SUPPORTED_PRIMITIVES:
            issues.append(_issue(
                "NATIVE_CIRCUIT_MODEL_UNSUPPORTED",
                f"Model {model.get('id')} uses {primitive or model.get('kind')}; run it through the reviewed ngspice path or supply a supported linear model.",
                f"{path}.model_id",
            ))
            continue
        binding_by_pin = {_identifier(item.get("model_pin")): item for item in assignment["pin_bindings"]}
        nodes = [_identifier(binding_by_pin[_identifier(pin)].get("circuit_node")) for pin in model["pins"]]
        element: Dict[str, Any] = {
            "id": compiled_ids[_identifier(assignment["id"])],
            "type": primitive,
            "positive_node": nodes[0],
            "negative_node": nodes[1],
            "source_assignment_id": _identifier(assignment["id"]),
            "source_component_ref": _identifier(assignment.get("component_ref")),
        }
        try:
            if primitive in {"resistor", "capacitor", "inductor"}:
                key = PARAMETER_KEYS[primitive]
                element[key] = _parameter(model, key, positive=True)
            elif primitive in {"voltage_source", "current_source"}:
                element.update(_source_parameters(model))
            elif primitive in {"vccs", "vcvs"}:
                element["control_positive_node"] = nodes[2]
                element["control_negative_node"] = nodes[3]
                key = PARAMETER_KEYS[primitive]
                element[key] = _parameter(model, key)
            else:
                parameters = model.get("parameters") or {}
                control_assignment = _identifier(parameters.get("control_source_assignment_id"))
                if control_assignment not in compiled_ids:
                    raise ValueError(f"control assignment {control_assignment or 'missing'} is unavailable")
                element["control_source_id"] = compiled_ids[control_assignment]
                key = PARAMETER_KEYS[primitive]
                element[key] = _parameter(model, key)
        except ValueError as exc:
            issues.append(_issue("NATIVE_CIRCUIT_PARAMETER_INVALID", f"Model {model.get('id')} {exc}.", f"{path}.model_id"))
            continue
        elements.append(element)

    for index, parasitic in enumerate(item for item in workspace.get("parasitics", []) if item.get("enabled", True)):
        path = f"parasitics[{index}]"
        token = _element_id("P_", parasitic.get("id", index + 1))
        start = _identifier(parasitic["from_node"])
        stop = _identifier(parasitic["to_node"])
        reference = _identifier(parasitic.get("reference_node"))
        resistance = float(parasitic.get("resistance_ohm", 0.0) or 0.0)
        inductance = float(parasitic.get("inductance_h", 0.0) or 0.0)
        capacitance = float(parasitic.get("capacitance_f", 0.0) or 0.0)
        conductance = float(parasitic.get("conductance_s", 0.0) or 0.0)
        if resistance <= 0.0 and inductance <= 0.0:
            issues.append(_issue(
                "NATIVE_CIRCUIT_PARASITIC_SERIES_PATH_REQUIRED",
                "A reviewed PEEC section with distinct endpoints requires positive series R or L; no artificial short is inserted.",
                path,
            ))
            continue
        cursor = start
        if resistance > 0.0:
            next_node = f"{token}:r" if inductance > 0.0 else stop
            elements.append({"id": f"{token}:R", "type": "resistor", "positive_node": cursor, "negative_node": next_node, "resistance_ohm": resistance})
            cursor = next_node
        if inductance > 0.0:
            elements.append({"id": f"{token}:L", "type": "inductor", "positive_node": cursor, "negative_node": stop, "inductance_h": inductance})
        if capacitance > 0.0:
            elements.append({"id": f"{token}:C", "type": "capacitor", "positive_node": stop, "negative_node": reference, "capacitance_f": capacitance})
        if conductance > 0.0:
            elements.append({"id": f"{token}:G", "type": "resistor", "positive_node": stop, "negative_node": reference, "resistance_ohm": 1.0 / conductance})

    if issues:
        return {
            "contract": COMPILE_CONTRACT,
            "status": "blocked",
            "issues": issues,
            "warnings": workspace_validation["warnings"],
            "workspace_validation": workspace_validation,
            "request": None,
        }
    request = {
        "contract": REQUEST_CONTRACT,
        "request_id": _element_id("workspace_", workspace.get("name", "circuit")),
        "ground_node": str(workspace["ground_node"]),
        "analysis": _analysis(workspace["analysis"]),
        "elements": elements,
        "resource_limits": dict(resource_limits or {"memory_limit_gb": 2.0}),
        "provenance": {
            "compiler": "spike.native_circuit_compiler",
            "workspace_contract": SPICE_WORKSPACE_CONTRACT,
            "topology_inference": False,
            "reviewed_peec_endpoints": all(
                item.get("endpoint_reviewed") is True
                for item in workspace.get("parasitics", [])
                if item.get("enabled", True)
            ),
        },
    }
    native_validation = validate_native_mna_request(request)
    return {
        "contract": COMPILE_CONTRACT,
        "status": "ready" if native_validation["valid"] else "blocked",
        "issues": native_validation["issues"],
        "warnings": workspace_validation["warnings"],
        "workspace_validation": workspace_validation,
        "native_validation": native_validation,
        "request": request,
    }


def run_spice_workspace_native_mna(
    workspace: Dict[str, Any],
    design: DesignIR,
    *,
    resource_limits: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    compiled = compile_spice_workspace_to_native_mna(workspace, design, resource_limits=resource_limits)
    if compiled["status"] != "ready":
        return {"contract": COMPILE_CONTRACT, "status": "blocked", "compile": compiled, "result": None}
    result = run_native_mna(compiled["request"])
    return {
        "contract": COMPILE_CONTRACT,
        "status": result["status"],
        "compile": compiled,
        "result": result,
        "analysis_result": native_mna_to_analysis_result(result, compiled["request"]).to_dict(),
    }


__all__ = [
    "COMPILE_CONTRACT",
    "compile_spice_workspace_to_native_mna",
    "run_spice_workspace_native_mna",
]
