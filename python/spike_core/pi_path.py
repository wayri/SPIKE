"""Validated ordered power-path contracts for cross-net PI analysis.

A PCB net ends at a component pin. Consequently an end-to-end power path is
an ordered sequence of conductor segments joined by explicit component models.
This module validates that sequence without inventing copper geometry inside a
package.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from .contracts import DesignIR


PI_PATH_CONTRACT = "spike/pi-path/v1"
PI_PATH_VALIDATION_CONTRACT = "spike/pi-path-validation/v1"
_VALUE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[fpnumkgt]?)\s*(?:ohm|ohms|r)?\s*$", re.I)


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _net(item: Dict[str, Any]) -> str:
    return _text(item.get("net_name") or item.get("net"))


def _resistance(model: Dict[str, Any]) -> tuple[float | None, str]:
    for key in (
        "connection_resistance_ohm",
        "dc_resistance_ohm",
        "series_resistance_ohm",
        "resistance_ohm",
    ):
        if key in model and model[key] not in (None, ""):
            try:
                value = float(model[key])
                return (value, f"transition.model.{key}") if math.isfinite(value) and value >= 0 else (None, "")
            except (TypeError, ValueError):
                return None, ""
    if _text(model.get("primitive")).lower() != "resistor":
        return None, ""
    match = _VALUE.fullmatch(_text(model.get("value")))
    if not match:
        return None, ""
    multiplier = {
        "": 1.0, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
        "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12,
    }.get(match.group(2).lower())
    value = float(match.group(1)) * (multiplier if multiplier is not None else math.nan)
    return (value, "transition.model.value") if math.isfinite(value) and value >= 0 else (None, "")


def _component_resistance(design: DesignIR, reference: str) -> tuple[float | None, str]:
    """Read only explicit imported component resistance metadata.

    This is deliberately conservative: a missing or ambiguous model remains a
    validation error instead of becoming an invented ideal connection.
    """
    component = next((
        item for item in design.components
        if _text(item.get("reference") or item.get("ref")) == reference
    ), None)
    if component is None:
        return None, ""
    parameters = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
    model = {
        "primitive": component.get("primitive") or component.get("type"),
        "value": component.get("value"),
        **parameters,
    }
    value, source = _resistance(model)
    if value is not None:
        return value, f"design.component.{source.removeprefix('transition.model.')}"
    # A conventional R reference plus a parseable value is explicit enough to
    # use, while arbitrary component values remain capability-gated.
    if reference.upper().startswith("R"):
        value, _ = _resistance({"primitive": "resistor", "value": component.get("value")})
        if value is not None:
            return value, "design.component.value"
    return None, ""


def validate_pi_path(path: Dict[str, Any], design: DesignIR, mode: str = "dc") -> Dict[str, Any]:
    """Validate copper continuity and every explicit component transition."""

    issues: List[Dict[str, str]] = []
    if not isinstance(path, dict) or path.get("contract") != PI_PATH_CONTRACT:
        issues.append(_issue("PI_PATH_CONTRACT_INVALID", f"Expected {PI_PATH_CONTRACT}."))
        return {"contract": PI_PATH_VALIDATION_CONTRACT, "valid": False, "can_execute": False, "issues": issues, "interfaces": []}

    segments = path.get("segments")
    transitions = path.get("transitions")
    if not isinstance(segments, list) or not segments:
        issues.append(_issue("PI_PATH_SEGMENTS_REQUIRED", "A PI path requires at least one ordered copper segment.", "segments"))
        segments = []
    if not isinstance(transitions, list):
        issues.append(_issue("PI_PATH_TRANSITIONS_INVALID", "transitions must be an array.", "transitions"))
        transitions = []
    if len(transitions) != max(0, len(segments) - 1):
        issues.append(_issue("PI_PATH_ORDER_INCOMPLETE", "Each adjacent copper segment requires exactly one component transition.", "transitions"))

    segment_by_id: Dict[str, Dict[str, Any]] = {}
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            issues.append(_issue("PI_PATH_SEGMENT_INVALID", "Each segment must be an object.", f"segments[{index}]"))
            continue
        segment_id, net = _text(segment.get("id")), _text(segment.get("net"))
        if not segment_id or segment_id in segment_by_id:
            issues.append(_issue("PI_PATH_SEGMENT_ID_INVALID", "Segment IDs must be non-empty and unique.", f"segments[{index}].id"))
        if not net:
            issues.append(_issue("PI_PATH_SEGMENT_NET_REQUIRED", "Every segment requires a board net.", f"segments[{index}].net"))
        segment_by_id[segment_id] = segment

    pads = {_text(pad.get("id")): pad for pad in design.pads if _text(pad.get("id"))}
    interfaces: List[Dict[str, Any]] = []
    for index, transition in enumerate(transitions):
        path_key = f"transitions[{index}]"
        if not isinstance(transition, dict):
            issues.append(_issue("PI_PATH_TRANSITION_INVALID", "Each transition must be an object.", path_key))
            continue
        before = segment_by_id.get(_text(transition.get("from_segment_id")))
        after = segment_by_id.get(_text(transition.get("to_segment_id")))
        expected_before = segments[index] if index < len(segments) and isinstance(segments[index], dict) else None
        expected_after = segments[index + 1] if index + 1 < len(segments) and isinstance(segments[index + 1], dict) else None
        if before is not expected_before or after is not expected_after:
            issues.append(_issue("PI_PATH_TRANSITION_ORDER_INVALID", "Transition endpoints must match the adjacent ordered segments.", path_key))
            continue
        input_pad_id = _text(transition.get("input_pad_id"))
        output_pad_id = _text(transition.get("output_pad_id"))
        input_pad, output_pad = pads.get(input_pad_id), pads.get(output_pad_id)
        if input_pad is None or output_pad is None:
            issues.append(_issue("PI_PATH_TRANSITION_PAD_UNKNOWN", "Transition pin mapping references an unknown board pad.", path_key))
            continue
        if _net(input_pad) != _text(before.get("net")) or _net(output_pad) != _text(after.get("net")):
            issues.append(_issue("PI_PATH_TRANSITION_NET_MISMATCH", "Transition pads do not terminate on the declared adjacent nets.", path_key))
        reference = _text(transition.get("component_ref"))
        # DesignIR fixtures use ``ref``; KiCad import records the owner as ``component``.
        input_ref = _text(input_pad.get("ref") or input_pad.get("component"))
        output_ref = _text(output_pad.get("ref") or output_pad.get("component"))
        if reference and (input_ref != reference or output_ref != reference):
            issues.append(_issue("PI_PATH_TRANSITION_COMPONENT_MISMATCH", "Both transition pads must belong to the declared series component.", path_key))
        model = transition.get("model") if isinstance(transition.get("model"), dict) else {}
        primitive = _text(model.get("primitive") or model.get("type")).lower()
        resistance, resistance_source = _resistance(model)
        if resistance is None and reference:
            resistance, resistance_source = _component_resistance(design, reference)
        if mode == "dc" and resistance is None:
            issues.append(_issue(
                "PI_PATH_DC_MODEL_REQUIRED",
                f"{reference or 'Series component'} requires an explicit DC resistance or resistor value; nonlinear and reactive-only models must use the SPICE path.",
                f"{path_key}.model",
            ))
        interfaces.append({
            "id": _text(transition.get("id")) or f"transition-{index + 1}",
            "component_ref": reference,
            "input_pad_id": input_pad_id,
            "output_pad_id": output_pad_id,
            "from_net": _text(before.get("net")),
            "to_net": _text(after.get("net")),
            "primitive": primitive,
            "dc_resistance_ohm": resistance,
            "resistance_source": resistance_source,
            "model_ref": _text(model.get("model_ref")),
        })

    source_terminal = path.get("source_terminal") if isinstance(path.get("source_terminal"), dict) else {}
    load_terminal = path.get("load_terminal") if isinstance(path.get("load_terminal"), dict) else {}
    source_net = _text(source_terminal.get("net"))
    load_net = _text(load_terminal.get("net"))
    if segments and (source_net != _text(segments[0].get("net")) or load_net != _text(segments[-1].get("net"))):
        issues.append(_issue("PI_PATH_TERMINAL_NET_MISMATCH", "Source and load terminals must use the first and last ordered segment nets."))
    for role, terminal, expected_net in (
        ("source", source_terminal, source_net),
        ("load", load_terminal, load_net),
    ):
        pad_id = _text(terminal.get("pad_id"))
        pad = pads.get(pad_id)
        if pad is None:
            issues.append(_issue("PI_PATH_TERMINAL_PAD_UNKNOWN", f"The {role} terminal must reference an explicit board pad.", f"{role}_terminal.pad_id"))
        elif _net(pad) != expected_net:
            issues.append(_issue("PI_PATH_TERMINAL_PAD_NET_MISMATCH", f"The {role} terminal pad is not on {expected_net}.", f"{role}_terminal.pad_id"))

    return {
        "contract": PI_PATH_VALIDATION_CONTRACT,
        "valid": not issues,
        "can_execute": not issues and bool(segments),
        "mode": mode,
        "issues": issues,
        "interfaces": interfaces,
        "counts": {"segments": len(segments), "transitions": len(transitions)},
    }


__all__ = ["PI_PATH_CONTRACT", "PI_PATH_VALIDATION_CONTRACT", "validate_pi_path"]
