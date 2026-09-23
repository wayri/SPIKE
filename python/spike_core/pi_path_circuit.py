"""Compile reviewed multi-net PI paths into the native linear circuit engine.

The compiler keeps three concerns explicit and auditable:

* terminal excitation comes from ``AnalysisSpec.sources`` and ``loads``;
* every copper segment binds to one reviewed PEEC RLCG network; and
* every cross-net transition is a reviewed component model between two pads.

No package copper, return connection, or ideal short is inferred. Nonlinear
component models remain assigned to the reviewed ngspice workflow.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List

from .contracts import AnalysisSpec, DesignIR
from .native_circuit_result import native_mna_to_analysis_result
from .native_mna import REQUEST_CONTRACT, run_native_mna, validate_native_mna_request
from .pi_path import validate_pi_path


COMPILE_CONTRACT = "spike/pi-path-circuit-compile/v1"
_NETWORK_CONTRACT = "spike/rlgc-network/v1"
_SUFFIXES = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
}


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.:+-]", "_", _text(value)).strip("_")[:100] or "item"


def _number(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, str):
        match = re.fullmatch(
            r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[tgkmunpf])?\s*",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError("requires a scalar with an optional SPICE engineering suffix")
        result = float(match.group(1)) * _SUFFIXES.get((match.group(2) or "").lower(), 1.0)
    else:
        result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0) or (nonnegative and result < 0.0):
        raise ValueError("requires a finite physically valid scalar")
    return result


def _network_list(extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    networks = (extraction_result.get("networks") or {}).get("parasitics", [])
    return networks if isinstance(networks, list) else []


def _expected_segment_pads(path: Dict[str, Any], index: int) -> tuple[str, str]:
    transitions = path.get("transitions") or []
    start = (
        (path.get("source_terminal") or {}).get("pad_id")
        if index == 0 else transitions[index - 1].get("output_pad_id")
    )
    stop = (
        (path.get("load_terminal") or {}).get("pad_id")
        if index == len(path.get("segments") or []) - 1 else transitions[index].get("input_pad_id")
    )
    return _text(start), _text(stop)


def _append_rlcg(
    elements: List[Dict[str, Any]],
    identifier: str,
    start: str,
    stop: str,
    ground: str,
    values: Dict[str, float],
    provenance: Dict[str, Any],
) -> None:
    resistance = values["resistance_ohm"]
    inductance = values["inductance_h"]
    capacitance = values["capacitance_f"]
    conductance = values["conductance_s"]
    cursor = start
    if resistance > 0.0:
        next_node = f"{identifier}:r" if inductance > 0.0 else stop
        elements.append({
            "id": f"{identifier}:R", "type": "resistor",
            "positive_node": cursor, "negative_node": next_node,
            "resistance_ohm": resistance, **provenance,
        })
        cursor = next_node
    if inductance > 0.0:
        elements.append({
            "id": f"{identifier}:L", "type": "inductor",
            "positive_node": cursor, "negative_node": stop,
            "inductance_h": inductance, **provenance,
        })
    if capacitance > 0.0:
        elements.append({
            "id": f"{identifier}:C", "type": "capacitor",
            "positive_node": stop, "negative_node": ground,
            "capacitance_f": capacitance, **provenance,
        })
    if conductance > 0.0:
        elements.append({
            "id": f"{identifier}:G", "type": "resistor",
            "positive_node": stop, "negative_node": ground,
            "resistance_ohm": 1.0 / conductance, **provenance,
        })


def _profile(terminal: Dict[str, Any], value: float) -> Dict[str, Any]:
    profile = terminal.get("profile") if isinstance(terminal.get("profile"), dict) else {}
    kind = _text(profile.get("kind") or "constant").lower()
    if kind == "constant":
        return {"type": "constant", "value": value}
    if kind == "step":
        return {
            "type": "step", "initial": _number(profile.get("initial_value", 0.0)),
            "final": value, "delay_s": _number(profile.get("delay_s", 0.0), nonnegative=True),
            "rise_time_s": _number(profile.get("rise_time_s", 0.0), nonnegative=True),
        }
    if kind == "pulse":
        return {
            "type": "pulse", "low": _number(profile.get("initial_value", 0.0)), "high": value,
            "delay_s": _number(profile.get("delay_s", 0.0), nonnegative=True),
            "rise_time_s": _number(profile.get("rise_time_s", 0.0), nonnegative=True),
            "fall_time_s": _number(profile.get("fall_time_s", 0.0), nonnegative=True),
            "pulse_width_s": _number(profile.get("pulse_width_s"), positive=True),
            "period_s": _number(profile.get("period_s"), positive=True),
        }
    if kind in {"pwl", "piecewise_linear"}:
        points = profile.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError("piecewise-linear profile requires explicit points")
        return {"type": "pwl", "points": points}
    raise ValueError(f"unsupported terminal profile {kind or 'missing'}")


def _analysis(spec: AnalysisSpec) -> Dict[str, Any]:
    if spec.mode == "ac":
        return {
            "mode": "ac", "start_hz": float(spec.frequency_start_hz or 0.0),
            "stop_hz": float(spec.frequency_stop_hz or 0.0),
            "points": int(spec.frequency_points), "scale": "log",
        }
    if spec.mode == "transient":
        return {
            "mode": "transient",
            "time_step_s": float(spec.transient.get("time_step_s", 0.0)),
            "stop_time_s": float(spec.transient.get("stop_time_s", 0.0)),
        }
    return {"mode": "operating_point"}


def _model_value(model: Dict[str, Any], key: str, *, positive: bool = True) -> float:
    parameters = model.get("parameters") if isinstance(model.get("parameters"), dict) else {}
    aliases = {
        "resistance_ohm": ("connection_resistance_ohm", "dc_resistance_ohm", "series_resistance_ohm"),
        "inductance_h": ("series_inductance_h",),
        "capacitance_f": ("series_capacitance_f",),
    }
    for candidate in (key, *aliases.get(key, ())):
        if candidate in parameters:
            return _number(parameters[candidate], positive=positive)
        if candidate in model:
            return _number(model[candidate], positive=positive)
    return _number(model.get("value"), positive=positive)


def _append_transition(
    elements: List[Dict[str, Any]],
    transition: Dict[str, Any],
    interface: Dict[str, Any],
    start: str,
    stop: str,
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    model = transition.get("model") if isinstance(transition.get("model"), dict) else {}
    primitive = _text(model.get("primitive") or model.get("type")).lower()
    identifier = f"X_{_token(interface['id'])}"
    common = {
        "source_component_ref": interface.get("component_ref", ""),
        "source_input_pad_id": interface.get("input_pad_id", ""),
        "source_output_pad_id": interface.get("output_pad_id", ""),
        "source_model_ref": interface.get("model_ref", ""),
    }
    try:
        if primitive in {"resistor", "linearized_component"}:
            resistance = interface.get("dc_resistance_ohm")
            resistance = _number(resistance, positive=True)
            elements.append({
                "id": f"{identifier}:R", "type": "resistor", "positive_node": start,
                "negative_node": stop, "resistance_ohm": resistance, **common,
            })
        elif primitive == "inductor":
            resistance = model.get("series_resistance_ohm", model.get("dc_resistance_ohm", 0.0))
            resistance = _number(resistance, nonnegative=True)
            cursor = start
            if resistance > 0.0:
                cursor = f"{identifier}:r"
                elements.append({
                    "id": f"{identifier}:R", "type": "resistor", "positive_node": start,
                    "negative_node": cursor, "resistance_ohm": resistance, **common,
                })
            elements.append({
                "id": f"{identifier}:L", "type": "inductor", "positive_node": cursor,
                "negative_node": stop, "inductance_h": _model_value(model, "inductance_h"), **common,
            })
        elif primitive == "capacitor":
            elements.append({
                "id": f"{identifier}:C", "type": "capacitor", "positive_node": start,
                "negative_node": stop, "capacitance_f": _model_value(model, "capacitance_f"), **common,
            })
        else:
            issues.append(_issue(
                "PI_PATH_CIRCUIT_MODEL_UNSUPPORTED_NATIVE",
                f"{interface.get('component_ref') or interface['id']} uses {primitive or 'an unspecified model'}; assign a reviewed linear R, L, or C model or use ngspice for nonlinear/subcircuit behavior.",
                f"transitions[{interface['id']}].model",
            ))
    except (TypeError, ValueError) as exc:
        issues.append(_issue(
            "PI_PATH_CIRCUIT_MODEL_VALUE_INVALID",
            f"{interface.get('component_ref') or interface['id']} {exc}.",
            f"transitions[{interface['id']}].model",
        ))
    return issues


def compile_pi_path_to_native_mna(
    design: DesignIR,
    spec: AnalysisSpec,
    extraction_result: Dict[str, Any],
    segment_mappings: Iterable[Dict[str, Any]],
    *,
    resource_limits: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile an explicitly mapped PI path and reviewed RLCG extraction."""

    path = spec.options.get("pi_path") if isinstance(spec.options.get("pi_path"), dict) else {}
    validation = validate_pi_path(path, design, spec.mode)
    issues: List[Dict[str, str]] = list(validation.get("issues") or [])
    segments = path.get("segments") if isinstance(path.get("segments"), list) else []
    mappings = list(segment_mappings)
    networks = _network_list(extraction_result)
    if spec.mode not in {"dc", "ac", "transient"}:
        issues.append(_issue("PI_PATH_CIRCUIT_MODE_UNSUPPORTED", "PI path circuit compilation supports dc, ac, and transient modes.", "spec.mode"))
    if len(mappings) != len(segments):
        issues.append(_issue(
            "PI_PATH_CIRCUIT_SEGMENT_MAPPING_INCOMPLETE",
            "Every ordered copper segment requires exactly one reviewed PEEC RLCG mapping.",
            "segment_mappings",
        ))
    if not networks:
        issues.append(_issue("PI_PATH_CIRCUIT_EXTRACTION_REQUIRED", "A PEEC result containing RLCG networks is required.", "extraction_result"))
    if not spec.sources or not spec.loads:
        issues.append(_issue("PI_PATH_CIRCUIT_TERMINALS_REQUIRED", "At least one source and one load are required.", "spec"))
    if issues:
        return {"contract": COMPILE_CONTRACT, "status": "blocked", "issues": issues, "path_validation": validation, "request": None}

    ground = _text((spec.return_path or {}).get("circuit_node") or (spec.return_path or {}).get("net") or "0")
    mapping_by_segment: Dict[str, Dict[str, Any]] = {}
    used_networks: set[int] = set()
    for index, mapping in enumerate(mappings):
        mapping_path = f"segment_mappings[{index}]"
        segment_id = _text(mapping.get("segment_id"))
        if segment_id in mapping_by_segment:
            issues.append(_issue("PI_PATH_CIRCUIT_SEGMENT_MAPPING_DUPLICATE", f"Segment {segment_id} is mapped more than once.", mapping_path))
            continue
        if mapping.get("endpoint_reviewed") is not True:
            issues.append(_issue("PI_PATH_CIRCUIT_ENDPOINT_REVIEW_REQUIRED", "Each segment mapping must be explicitly endpoint_reviewed.", mapping_path))
        try:
            network_index = int(mapping.get("network_index"))
        except (TypeError, ValueError):
            issues.append(_issue("PI_PATH_CIRCUIT_NETWORK_INDEX_INVALID", "network_index must be an integer.", mapping_path))
            continue
        if network_index < 0 or network_index >= len(networks) or network_index in used_networks:
            issues.append(_issue("PI_PATH_CIRCUIT_NETWORK_INDEX_INVALID", "The mapped RLCG network is unavailable or already used.", mapping_path))
            continue
        mapping_by_segment[segment_id] = mapping
        used_networks.add(network_index)

    elements: List[Dict[str, Any]] = []
    segment_nodes: List[tuple[str, str]] = []
    bindings: List[Dict[str, Any]] = []
    for index, segment in enumerate(segments):
        segment_id = _text(segment.get("id"))
        mapping = mapping_by_segment.get(segment_id)
        if mapping is None:
            issues.append(_issue("PI_PATH_CIRCUIT_SEGMENT_MAPPING_MISSING", f"Segment {segment_id} has no reviewed RLCG mapping.", f"segments[{index}]"))
            continue
        network_index = int(mapping["network_index"])
        network = networks[network_index]
        expected_start, expected_stop = _expected_segment_pads(path, index)
        if _text(mapping.get("from_pad_id")) != expected_start or _text(mapping.get("to_pad_id")) != expected_stop:
            issues.append(_issue(
                "PI_PATH_CIRCUIT_ENDPOINT_PAD_MISMATCH",
                f"Segment {segment_id} must map reviewed pads {expected_start} to {expected_stop}.",
                f"segment_mappings[{index}]",
            ))
        if network.get("contract") != _NETWORK_CONTRACT or _text(network.get("net")) != _text(segment.get("net")):
            issues.append(_issue(
                "PI_PATH_CIRCUIT_NETWORK_MISMATCH",
                f"RLCG network {network_index} is not a {_NETWORK_CONTRACT} model for {_text(segment.get('net'))}.",
                f"segment_mappings[{index}]",
            ))
            continue
        try:
            values = {
                key: _number(network.get(key, 0.0), nonnegative=True)
                for key in ("resistance_ohm", "inductance_h", "capacitance_f", "conductance_s")
            }
        except (TypeError, ValueError) as exc:
            issues.append(_issue("PI_PATH_CIRCUIT_RLCG_INVALID", f"RLCG network {network_index} {exc}.", f"segment_mappings[{index}]"))
            continue
        if values["resistance_ohm"] <= 0.0 and values["inductance_h"] <= 0.0:
            issues.append(_issue("PI_PATH_CIRCUIT_SERIES_RL_REQUIRED", f"Segment {segment_id} requires positive series R or L; no ideal short is inserted.", f"segment_mappings[{index}]"))
            continue
        start, stop = f"path:{_token(segment_id)}:in", f"path:{_token(segment_id)}:out"
        segment_nodes.append((start, stop))
        provenance = {
            "source_segment_id": segment_id, "source_net": _text(segment.get("net")),
            "source_network_index": network_index, "source_result_id": _text(extraction_result.get("analysis_id")),
            "source_from_pad_id": expected_start, "source_to_pad_id": expected_stop,
        }
        _append_rlcg(elements, f"P_{_token(segment_id)}", start, stop, ground, values, provenance)
        bindings.append({**provenance, "circuit_from_node": start, "circuit_to_node": stop, **values})

    transitions = path.get("transitions") or []
    interfaces = validation.get("interfaces") or []
    if len(segment_nodes) == len(segments):
        for index, (transition, interface) in enumerate(zip(transitions, interfaces)):
            issues.extend(_append_transition(elements, transition, interface, segment_nodes[index][1], segment_nodes[index + 1][0]))

    if not issues and segment_nodes:
        source = next((item for item in spec.sources if _text(item.get("net")) == _text(segments[0].get("net"))), spec.sources[0])
        load = next((item for item in spec.loads if _text(item.get("net")) == _text(segments[-1].get("net"))), spec.loads[0])
        try:
            source_value = _number(source.get("voltage_v", source.get("voltage", 0.0)))
            load_value = _number(load.get("current_a", load.get("current", 0.0)))
            source_element: Dict[str, Any] = {
                "id": "V_PATH_SOURCE", "type": "voltage_source",
                "positive_node": segment_nodes[0][0], "negative_node": ground,
                "dc_value": source_value,
                "source_terminal_id": _text(source.get("id")),
                "source_pad_id": _text((path.get("source_terminal") or {}).get("pad_id")),
            }
            load_element: Dict[str, Any] = {
                "id": "I_PATH_LOAD", "type": "current_source",
                "positive_node": segment_nodes[-1][1], "negative_node": ground,
                "dc_value": load_value,
                "source_terminal_id": _text(load.get("id")),
                "source_pad_id": _text((path.get("load_terminal") or {}).get("pad_id")),
            }
            if spec.mode == "ac":
                source_element["ac_magnitude"] = _number(source.get("ac_magnitude_v", source_value), nonnegative=True)
                source_element["ac_phase_deg"] = _number(source.get("ac_phase_deg", 0.0))
                load_element["ac_magnitude"] = _number(load.get("ac_magnitude_a", load_value), nonnegative=True)
                load_element["ac_phase_deg"] = _number(load.get("ac_phase_deg", 0.0))
            elif spec.mode == "transient":
                source_element["waveform"] = _profile(source, source_value)
                load_element["waveform"] = _profile(load, load_value)
            elements.extend((source_element, load_element))
        except (TypeError, ValueError) as exc:
            issues.append(_issue("PI_PATH_CIRCUIT_TERMINAL_VALUE_INVALID", str(exc), "spec.sources/loads"))

    if issues:
        return {"contract": COMPILE_CONTRACT, "status": "blocked", "issues": issues, "path_validation": validation, "request": None}

    limits = dict(resource_limits or {})
    limits.setdefault("memory_limit_gb", float(spec.mesh.get("solver_memory_limit_gb", 2.0) or 2.0))
    request = {
        "contract": REQUEST_CONTRACT,
        "request_id": _text(spec.analysis_id) or f"pi-path-{_token(path.get('id'))}",
        "ground_node": ground,
        "analysis": _analysis(spec),
        "elements": elements,
        "resource_limits": limits,
        "provenance": {
            "compiler": "spike.pi_path_circuit", "compile_contract": COMPILE_CONTRACT,
            "pi_path_id": _text(path.get("id")), "topology_inference": False,
            "reviewed_segment_endpoints": True, "segment_bindings": bindings,
            "extraction_model_status": _text(extraction_result.get("model_status")),
        },
    }
    native_validation = validate_native_mna_request(request)
    return {
        "contract": COMPILE_CONTRACT,
        "status": "ready" if native_validation["valid"] else "blocked",
        "issues": native_validation["issues"],
        "path_validation": validation,
        "native_validation": native_validation,
        "segment_bindings": bindings,
        "request": request,
    }


def run_pi_path_native_mna(
    design: DesignIR,
    spec: AnalysisSpec,
    extraction_result: Dict[str, Any],
    segment_mappings: Iterable[Dict[str, Any]],
    *,
    resource_limits: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    compiled = compile_pi_path_to_native_mna(
        design, spec, extraction_result, segment_mappings, resource_limits=resource_limits,
    )
    if compiled["status"] != "ready":
        return {"contract": COMPILE_CONTRACT, "status": "blocked", "compile": compiled, "result": None}
    result = run_native_mna(compiled["request"])
    analysis_result = native_mna_to_analysis_result(result, compiled["request"])
    extraction_networks = _network_list(extraction_result)
    analysis_result.networks.setdefault("parasitics", extraction_networks)
    analysis_result.provenance.update({
        "pi_path_compile_contract": COMPILE_CONTRACT,
        "pi_path_id": compiled["request"]["provenance"]["pi_path_id"],
        "segment_bindings": compiled["segment_bindings"],
        "segment_extraction_analysis_id": _text(extraction_result.get("analysis_id")),
        "spatial_binding": "reviewed_segment_endpoints",
        "spatial_fields_available": False,
    })
    return {
        "contract": COMPILE_CONTRACT, "status": result["status"], "compile": compiled,
        "result": result, "analysis_result": analysis_result.to_dict(),
    }


__all__ = ["COMPILE_CONTRACT", "compile_pi_path_to_native_mna", "run_pi_path_native_mna"]
