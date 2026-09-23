"""Bounded PI topology-to-circuit handoff.

The visual power tree is useful for describing a board-level power path, but it
is not itself a circuit simulator.  This module turns the reviewable subset of
that tree into a stable ``AnalysisSpec.options`` payload.  Only explicit
two-terminal R/L/C pin-to-pin models are accepted.  Nonlinear devices,
behavioral expressions, regulators, transformers, and arbitrary subcircuits
are retained as structured unsupported-model notices; they are never silently
converted to a linear element or claimed as SPICE execution.

The result is deliberately a handoff contract.  A solver or the explicit
SPICE-workspace flow must opt in to consume it.  Existing DC, PEEC, and
ngspice plugins do not infer models from this payload.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple

from .contracts import AnalysisSpec, DesignIR


TOPOLOGY_CONTRACT = "spike/topology/v1"
TOPOLOGY_CIRCUIT_CONTRACT = "spike/topology-circuit/v1"
TOPOLOGY_CIRCUIT_VALIDATION_CONTRACT = "spike/topology-circuit-validation/v1"
MAX_NODES = 2048
MAX_EDGES = 8192
MAX_ELEMENTS = 1024
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:+-]{0,127}$")
VALUE_PATTERN = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
    r"(meg|[fpnumkgt]?)\s*(ohm|ohms|r|f|farad|farads|h|henry|henries)?\s*$",
    re.IGNORECASE,
)

_PRIMITIVE_ALIASES = {
    "r": "resistor",
    "resistor": "resistor",
    "resistance": "resistor",
    "c": "capacitor",
    "capacitor": "capacitor",
    "capacitance": "capacitor",
    "l": "inductor",
    "inductor": "inductor",
    "inductance": "inductor",
}
_NONLINEAR_TOKENS = {
    "behavioral",
    "bsource",
    "controlled_source",
    "diode",
    "fet",
    "mosfet",
    "nonlinear",
    "regulator",
    "switch",
    "transistor",
    "transformer",
    "voltage_dependent_resistance",
}
_PASSIVE_NODE_KINDS = {"passive"}
_STRUCTURAL_NODE_KINDS = {
    "source", "rail", "return", "load", "connector", "harness",
}
_VALID_NODE_KINDS = _STRUCTURAL_NODE_KINDS | _PASSIVE_NODE_KINDS | {
    "regulator", "transformer", "driver", "channel", "receiver", "termination",
}
_VALID_EDGE_KINDS = {"power", "return", "signal", "control"}


def _issue(code: str, message: str, *, severity: str = "error", path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "path": path}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _node_model(node: Dict[str, Any]) -> Dict[str, Any]:
    """Accept the documented snake/camel case model fields without guessing."""
    for key in ("circuit_model", "circuitModel", "model"):
        value = node.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _primitive(node: Dict[str, Any], model: Dict[str, Any]) -> str:
    for value in (
        model.get("primitive"), model.get("type"), model.get("kind"),
        node.get("simulationModel"), node.get("simulation_model"),
    ):
        candidate = _PRIMITIVE_ALIASES.get(_text(value).lower())
        if candidate:
            return candidate
    reference = _text(node.get("ref") or node.get("reference"))
    return _PRIMITIVE_ALIASES.get(reference[:1].lower(), "")


def _is_nonlinear_or_behavioral(node: Dict[str, Any], model: Dict[str, Any]) -> bool:
    values = (
        model.get("primitive"), model.get("type"), model.get("kind"),
        model.get("behavior"), node.get("simulationModel"), node.get("simulation_model"),
        node.get("kind"), node.get("label"), node.get("value"),
    )
    text = " ".join(_text(value).lower() for value in values)
    return any(token in text for token in _NONLINEAR_TOKENS)


def _parse_value(value: Any, primitive: str) -> Tuple[float | None, str]:
    raw = _text(value)
    match = VALUE_PATTERN.fullmatch(raw)
    if not match:
        return None, raw
    base = float(match.group(1))
    suffix = match.group(2).lower()
    multiplier = {
        "": 1.0, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
        "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12,
    }.get(suffix)
    unit = (match.group(3) or "").lower()
    allowed_units = {
        "resistor": {"", "ohm", "ohms", "r"},
        "capacitor": {"", "f", "farad", "farads"},
        "inductor": {"", "h", "henry", "henries"},
    }[primitive]
    if multiplier is None or unit not in allowed_units:
        return None, raw
    result = base * multiplier
    return (result if math.isfinite(result) and result > 0 else None), raw


def _pins(model: Dict[str, Any]) -> Any:
    return model.get("pins", model.get("pin_mappings", model.get("pinMappings")))


def _component_refs(design: DesignIR) -> set[str]:
    return {
        _text(item.get("reference") or item.get("ref"))
        for item in design.components
        if _text(item.get("reference") or item.get("ref"))
    }


def _pad_index(design: DesignIR) -> Dict[str, Dict[str, Any]]:
    return {_text(pad.get("id")): pad for pad in design.pads if _text(pad.get("id"))}


def _validate_common(topology: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    issues: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if not isinstance(topology, dict) or topology.get("contract") != TOPOLOGY_CONTRACT:
        return ([_issue("TOPOLOGY_CONTRACT_INVALID", f"Expected {TOPOLOGY_CONTRACT}.")], warnings, {}, [])
    if _text(topology.get("domain")) != "pi":
        issues.append(_issue("TOPOLOGY_DOMAIN_UNSUPPORTED", "The topology-to-circuit bridge currently accepts PI topology only.", path="domain"))
    nodes = topology.get("nodes", [])
    edges = topology.get("edges", [])
    if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
        issues.append(_issue("TOPOLOGY_NODE_COUNT_INVALID", f"nodes must be an array with at most {MAX_NODES} entries.", path="nodes"))
        nodes = []
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        issues.append(_issue("TOPOLOGY_EDGE_COUNT_INVALID", f"edges must be an array with at most {MAX_EDGES} entries.", path="edges"))
        edges = []
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        if not isinstance(node, dict):
            issues.append(_issue("TOPOLOGY_NODE_INVALID", "Each node must be an object.", path=path))
            continue
        node_id = _text(node.get("id"))
        if not IDENTIFIER.fullmatch(node_id):
            issues.append(_issue("TOPOLOGY_NODE_ID_INVALID", "Node IDs must be bounded identifiers.", path=f"{path}.id"))
            continue
        if node_id in node_by_id:
            issues.append(_issue("TOPOLOGY_NODE_ID_DUPLICATE", f"Duplicate node ID: {node_id}.", path=f"{path}.id"))
            continue
        if _text(node.get("kind")) not in _VALID_NODE_KINDS:
            issues.append(_issue("TOPOLOGY_NODE_KIND_INVALID", f"Unsupported topology node kind: {_text(node.get('kind')) or 'missing'}.", path=f"{path}.kind"))
        node_by_id[node_id] = node
    checked_edges: List[Dict[str, Any]] = []
    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        path = f"edges[{index}]"
        if not isinstance(edge, dict):
            issues.append(_issue("TOPOLOGY_EDGE_INVALID", "Each edge must be an object.", path=path))
            continue
        edge_id = _text(edge.get("id"))
        if not IDENTIFIER.fullmatch(edge_id):
            issues.append(_issue("TOPOLOGY_EDGE_ID_INVALID", "Edge IDs must be bounded identifiers.", path=f"{path}.id"))
        elif edge_id in edge_ids:
            issues.append(_issue("TOPOLOGY_EDGE_ID_DUPLICATE", f"Duplicate edge ID: {edge_id}.", path=f"{path}.id"))
        edge_ids.add(edge_id)
        start, stop = _text(edge.get("from")), _text(edge.get("to"))
        if start not in node_by_id or stop not in node_by_id:
            issues.append(_issue("TOPOLOGY_EDGE_ENDPOINT_UNKNOWN", "Every edge must reference existing nodes.", path=path))
            continue
        if start == stop:
            issues.append(_issue("TOPOLOGY_EDGE_SELF_LOOP", "Topology self-loops are not supported.", path=path))
        if _text(edge.get("kind")) not in _VALID_EDGE_KINDS:
            issues.append(_issue("TOPOLOGY_EDGE_KIND_INVALID", "Edges must be power, return, signal, or control.", path=f"{path}.kind"))
        checked_edges.append(edge)
    if not node_by_id:
        warnings.append(_issue("TOPOLOGY_EMPTY", "No topology nodes are defined.", severity="warning", path="nodes"))
    return issues, warnings, node_by_id, checked_edges


def _power_cycles(node_by_id: Dict[str, Dict[str, Any]], edges: Iterable[Dict[str, Any]]) -> bool:
    outgoing: Dict[str, List[str]] = {}
    for edge in edges:
        if edge.get("kind") == "power":
            outgoing.setdefault(_text(edge.get("from")), []).append(_text(edge.get("to")))
    active: set[str] = set()
    done: set[str] = set()
    def visit(node_id: str) -> bool:
        if node_id in active:
            return True
        if node_id in done:
            return False
        active.add(node_id)
        found = any(visit(child) for child in outgoing.get(node_id, []))
        active.remove(node_id)
        done.add(node_id)
        return found
    return any(visit(node_id) for node_id in node_by_id)


def validate_topology_circuit(topology: Dict[str, Any], design: DesignIR) -> Dict[str, Any]:
    """Validate a PI graph and report exactly what can be handed to a circuit path."""
    issues, warnings, node_by_id, edges = _validate_common(topology)
    pads = _pad_index(design)
    component_refs = _component_refs(design)
    power_in: Dict[str, List[Dict[str, Any]]] = {}
    power_out: Dict[str, List[Dict[str, Any]]] = {}
    returns: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        if edge.get("kind") == "power":
            power_out.setdefault(_text(edge.get("from")), []).append(edge)
            power_in.setdefault(_text(edge.get("to")), []).append(edge)
        elif edge.get("kind") == "return":
            returns.setdefault(_text(edge.get("from")), []).append(edge)
            returns.setdefault(_text(edge.get("to")), []).append(edge)
    if _power_cycles(node_by_id, edges):
        issues.append(_issue("TOPOLOGY_POWER_CYCLE", "The power path contains a directed cycle; use an explicit validated circuit workspace for meshed feedback networks.", path="edges"))

    elements: List[Dict[str, Any]] = []
    unsupported_models: List[Dict[str, Any]] = []
    for index, (node_id, node) in enumerate(node_by_id.items()):
        kind = _text(node.get("kind"))
        model = _node_model(node)
        primitive = _primitive(node, model)
        path = f"nodes[{index}]"
        has_declared_model = bool(model) or bool(_text(node.get("simulationModel") or node.get("simulation_model")))
        is_passive = kind in _PASSIVE_NODE_KINDS or primitive in _PRIMITIVE_ALIASES.values()
        if not is_passive:
            if kind not in _STRUCTURAL_NODE_KINDS and (has_declared_model or _is_nonlinear_or_behavioral(node, model)):
                unsupported_models.append({
                    "node_id": node_id,
                    "reference": _text(node.get("ref") or node.get("reference")),
                    "model": _text(model.get("type") or model.get("primitive") or node.get("simulationModel") or kind),
                    "reason": "This bridge does not execute nonlinear, behavioral, transformer, regulator, or arbitrary subcircuit models.",
                })
            continue
        if primitive not in {"resistor", "inductor", "capacitor"}:
            unsupported_models.append({
                "node_id": node_id,
                "reference": _text(node.get("ref") or node.get("reference")),
                "model": _text(model.get("type") or model.get("primitive") or node.get("simulationModel") or "passive"),
                "reason": "Only explicit two-terminal resistor, inductor, and capacitor models are supported by this bridge.",
            })
            continue
        pin_list = _pins(model)
        if not isinstance(pin_list, list) or len(pin_list) != 2:
            issues.append(_issue("TOPOLOGY_PIN_MODEL_REQUIRED", "Supported R/L/C elements require exactly two explicit pin mappings.", path=f"{path}.circuit_model.pins"))
            continue
        terminals: List[Dict[str, str]] = []
        for pin_index, pin in enumerate(pin_list):
            pin_path = f"{path}.circuit_model.pins[{pin_index}]"
            if not isinstance(pin, dict):
                issues.append(_issue("TOPOLOGY_PIN_MAPPING_INVALID", "Each pin mapping must be an object.", path=pin_path))
                continue
            pad_id = _text(pin.get("pad_id") or pin.get("padId"))
            circuit_node = _text(pin.get("circuit_node") or pin.get("circuitNode") or pin.get("node"))
            if not pad_id or pad_id not in pads:
                issues.append(_issue("TOPOLOGY_PIN_PAD_UNKNOWN", f"Pin mapping references unknown pad {pad_id or 'missing'}.", path=f"{pin_path}.pad_id"))
            if not IDENTIFIER.fullmatch(circuit_node):
                issues.append(_issue("TOPOLOGY_CIRCUIT_NODE_INVALID", "Pin mappings require bounded circuit-node names.", path=f"{pin_path}.circuit_node"))
            terminals.append({"pad_id": pad_id, "circuit_node": circuit_node})
        if len({terminal["pad_id"] for terminal in terminals}) != 2 or len({terminal["circuit_node"] for terminal in terminals}) != 2:
            issues.append(_issue("TOPOLOGY_PIN_ENDPOINTS_INVALID", "R/L/C pin mappings require two distinct pads and circuit nodes.", path=f"{path}.circuit_model.pins"))
        reference = _text(node.get("ref") or node.get("reference"))
        if reference and component_refs and reference not in component_refs:
            issues.append(_issue("TOPOLOGY_COMPONENT_UNKNOWN", f"Topology reference {reference} is not present in the design.", path=f"{path}.ref"))
        value_si, raw_value = _parse_value(model.get("value", node.get("value")), primitive)
        if value_si is None:
            issues.append(_issue("TOPOLOGY_PASSIVE_VALUE_INVALID", f"{primitive.title()} requires one finite positive SI/SPICE value.", path=f"{path}.circuit_model.value"))
        orientation = _text(model.get("orientation") or node.get("orientation") or "series").lower()
        if orientation not in {"series", "shunt"}:
            issues.append(_issue("TOPOLOGY_PASSIVE_ORIENTATION_INVALID", "R/L/C orientation must be series or shunt.", path=f"{path}.orientation"))
        elif orientation == "series" and (len(power_in.get(node_id, [])) != 1 or len(power_out.get(node_id, [])) != 1):
            issues.append(_issue("TOPOLOGY_SERIES_PATH_INVALID", "A series R/L/C element requires exactly one incoming and one outgoing power edge.", path=path))
        elif orientation == "shunt" and (len(power_in.get(node_id, [])) + len(power_out.get(node_id, [])) != 1 or not returns.get(node_id)):
            issues.append(_issue("TOPOLOGY_SHUNT_PATH_INVALID", "A shunt R/L/C element requires one power connection and one return/ground edge.", path=path))
        elements.append({
            "id": node_id,
            "reference": reference or node_id,
            "primitive": primitive,
            "orientation": orientation,
            "value": {"raw": raw_value, "si": value_si},
            "terminals": terminals,
            "source": "explicit_pin_to_pin_model",
        })

    if len(elements) > MAX_ELEMENTS:
        issues.append(_issue("TOPOLOGY_ELEMENT_COUNT_INVALID", f"At most {MAX_ELEMENTS} supported R/L/C elements may be handed off.", path="nodes"))
    if unsupported_models:
        warnings.append(_issue(
            "TOPOLOGY_MODELS_NOT_EXECUTED",
            f"{len(unsupported_models)} behavioral or device model(s) were excluded from the passive handoff and will not be executed.",
            severity="warning", path="nodes",
        ))
    return {
        "contract": TOPOLOGY_CIRCUIT_VALIDATION_CONTRACT,
        "valid": not issues,
        "can_handoff": not issues and bool(elements),
        "can_execute": False,
        "issues": issues,
        "warnings": warnings,
        "counts": {
            "nodes": len(node_by_id), "edges": len(edges), "passive_elements": len(elements),
            "unsupported_models": len(unsupported_models),
        },
        "supported_elements": elements,
        "unsupported_models": unsupported_models,
        "execution_status": "not_executed",
        "execution_reason": "This bridge only produces a reviewed topology handoff. A compatible solver or explicit SPICE workspace must execute it.",
    }


def bridge_topology_to_analysis_spec(topology: Dict[str, Any], design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    """Attach a validated passive power-path handoff to ``AnalysisSpec.options``.

    The original spec is copied.  The bridge never changes ``solver_id`` or
    executes ngspice, preventing a visual topology from becoming an implicit
    nonlinear circuit run.
    """
    validation = validate_topology_circuit(topology, design)
    circuit = {
        "contract": TOPOLOGY_CIRCUIT_CONTRACT,
        "domain": "pi",
        "topology_name": _text(topology.get("name")),
        "elements": deepcopy(validation["supported_elements"]),
        "connections": [
            {key: edge.get(key) for key in ("id", "from", "to", "kind", "net")}
            for edge in topology.get("edges", []) if isinstance(edge, dict) and edge.get("kind") in {"power", "return"}
        ],
        "ground_nodes": [
            _text(node.get("id")) for node in topology.get("nodes", [])
            if isinstance(node, dict) and _text(node.get("kind")) == "return"
        ],
        "unsupported_models": deepcopy(validation["unsupported_models"]),
        "execution": {
            "state": "not_executed",
            "implicit_spice_execution": False,
            "reason": validation["execution_reason"],
        },
    }
    analysis_spec = spec.to_dict()
    options = deepcopy(analysis_spec.get("options") or {})
    options["topology_circuit"] = circuit
    options["topology_circuit_validation"] = {
        "contract": validation["contract"],
        "valid": validation["valid"],
        "can_handoff": validation["can_handoff"],
        "can_execute": False,
        "issues": deepcopy(validation["issues"]),
        "warnings": deepcopy(validation["warnings"]),
    }
    analysis_spec["options"] = options
    return {
        "contract": TOPOLOGY_CIRCUIT_CONTRACT,
        "status": "ready" if validation["can_handoff"] else "blocked",
        "validation": validation,
        "analysis_spec": analysis_spec,
        "circuit": circuit,
    }


__all__ = [
    "TOPOLOGY_CIRCUIT_CONTRACT",
    "TOPOLOGY_CIRCUIT_VALIDATION_CONTRACT",
    "TOPOLOGY_CONTRACT",
    "bridge_topology_to_analysis_spec",
    "validate_topology_circuit",
]
