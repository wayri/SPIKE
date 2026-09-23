"""Validated visual SPICE workspace and deterministic netlist composition.

The workspace stores engineering intent separately from ngspice syntax.  It
never searches for model files or expands include directives: every model and
parasitic used for a run is explicit, reviewable, and carried in the project.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Iterable, List

from .contracts import DesignIR
from .spice_netlist_safety import FORBIDDEN_DIRECTIVES, validate_netlist


SPICE_WORKSPACE_CONTRACT = "spike/spice-workspace/v1"
SPICE_WORKSPACE_VALIDATION_CONTRACT = "spike/spice-workspace-validation/v1"
SPICE_NETLIST_PREVIEW_CONTRACT = "spike/spice-netlist-preview/v1"
MAX_MODELS = 1024
MAX_ASSIGNMENTS = 8192
MAX_PARASITICS = 100_000
MAX_MODEL_SOURCE_BYTES = 2 * 1024 * 1024
MAX_VALUE_EXPRESSION_CHARS = 4096
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:+-]{0,127}$")
PIN_IDENTIFIER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:+-]{0,127}$")
MODEL_ANALYSIS_DIRECTIVES = {
    ".ac", ".dc", ".end", ".four", ".noise", ".op", ".plot", ".print",
    ".pz", ".save", ".sens", ".tf", ".tran",
}
PRIMITIVES = {
    "resistor": ("R", 2),
    "capacitor": ("C", 2),
    "inductor": ("L", 2),
    "voltage_source": ("V", 2),
    "current_source": ("I", 2),
    "vccs": ("G", 4),
    "vcvs": ("E", 4),
    "cccs": ("F", 2),
    "ccvs": ("H", 2),
    "diode": ("D", 2),
}


def _issue(code: str, message: str, *, severity: str = "error", path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "path": path}


def _finite(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if positive and number <= 0:
        return None
    if nonnegative and number < 0:
        return None
    return number


def _identifier(value: Any) -> str:
    return str(value or "").strip()


def _safe_instance_name(prefix: str, value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "item"
    return f"{prefix}{token[:80]}"


def _validate_model_source(source: Any, path: str, issues: List[Dict[str, str]]) -> str:
    text = str(source or "")
    if len(text.encode("utf-8")) > MAX_MODEL_SOURCE_BYTES:
        issues.append(_issue("SPICE_MODEL_TOO_LARGE", "Inline model source exceeds 2 MiB.", path=path))
        return ""
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip().lower()
        if not stripped or stripped.startswith("*"):
            continue
        token = stripped.split(maxsplit=1)[0]
        if token in FORBIDDEN_DIRECTIVES or token in MODEL_ANALYSIS_DIRECTIVES:
            issues.append(_issue(
                "SPICE_MODEL_DIRECTIVE_REJECTED",
                f"Model source contains disallowed directive {token} at line {line_number}.",
                path=path,
            ))
    return text.strip()


def _validate_value_expression(value: Any, path: str, issues: List[Dict[str, str]]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > MAX_VALUE_EXPRESSION_CHARS:
        issues.append(_issue("SPICE_VALUE_TOO_LARGE", "Primitive values are limited to 4,096 characters.", path=path))
        return ""
    if any(character in text for character in ("\r", "\n", "\x00")) or text.startswith("."):
        issues.append(_issue("SPICE_VALUE_EXPRESSION_REJECTED", "Primitive values must be a single data expression, not a SPICE directive.", path=path))
        return ""
    return text


def _component_references(design: DesignIR) -> set[str]:
    return {
        str(component.get("reference") or component.get("ref") or "").strip()
        for component in design.components
        if str(component.get("reference") or component.get("ref") or "").strip()
    }


def _pad_index(design: DesignIR) -> Dict[str, Dict[str, Any]]:
    return {
        str(pad.get("id", "")): pad
        for pad in design.pads
        if str(pad.get("id", ""))
    }


def validate_spice_workspace(workspace: Dict[str, Any], design: DesignIR) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if not isinstance(workspace, dict) or workspace.get("contract") != SPICE_WORKSPACE_CONTRACT:
        return {
            "contract": SPICE_WORKSPACE_VALIDATION_CONTRACT,
            "valid": False,
            "can_run": False,
            "issues": [_issue("SPICE_WORKSPACE_CONTRACT_INVALID", f"Expected {SPICE_WORKSPACE_CONTRACT}.")],
            "warnings": [],
            "counts": {"models": 0, "assignments": 0, "parasitics": 0},
        }
    name = _identifier(workspace.get("name"))
    if not name or len(name) > 256:
        issues.append(_issue("SPICE_WORKSPACE_NAME_INVALID", "Workspace name must contain 1 to 256 characters.", path="name"))
    domain = _identifier(workspace.get("domain"))
    if domain not in {"pi", "si"}:
        issues.append(_issue("SPICE_WORKSPACE_DOMAIN_INVALID", "Workspace domain must be pi or si.", path="domain"))
    models = workspace.get("models", [])
    assignments = workspace.get("assignments", [])
    parasitics = workspace.get("parasitics", [])
    analysis = workspace.get("analysis", {})
    if not isinstance(models, list) or len(models) > MAX_MODELS:
        issues.append(_issue("SPICE_MODEL_COUNT_INVALID", f"Models must be an array with at most {MAX_MODELS} entries.", path="models"))
        models = []
    if not isinstance(assignments, list) or len(assignments) > MAX_ASSIGNMENTS:
        issues.append(_issue("SPICE_ASSIGNMENT_COUNT_INVALID", f"Assignments must be an array with at most {MAX_ASSIGNMENTS} entries.", path="assignments"))
        assignments = []
    if not isinstance(parasitics, list) or len(parasitics) > MAX_PARASITICS:
        issues.append(_issue("SPICE_PARASITIC_COUNT_INVALID", f"Parasitics must be an array with at most {MAX_PARASITICS} entries.", path="parasitics"))
        parasitics = []

    model_by_id: Dict[str, Dict[str, Any]] = {}
    for index, model in enumerate(models):
        path = f"models[{index}]"
        if not isinstance(model, dict):
            issues.append(_issue("SPICE_MODEL_INVALID", "Each model must be an object.", path=path))
            continue
        identifier = _identifier(model.get("id"))
        if not IDENTIFIER.fullmatch(identifier):
            issues.append(_issue("SPICE_MODEL_ID_INVALID", "Model IDs must be bounded SPICE-safe identifiers.", path=f"{path}.id"))
            continue
        if identifier in model_by_id:
            issues.append(_issue("SPICE_MODEL_ID_DUPLICATE", f"Duplicate model ID: {identifier}.", path=f"{path}.id"))
            continue
        kind = _identifier(model.get("kind"))
        origin = _identifier(model.get("origin"))
        if origin not in {"built_in", "project", "imported"}:
            issues.append(_issue("SPICE_MODEL_ORIGIN_INVALID", "Model origin must be built_in, project, or imported.", path=f"{path}.origin"))
        pins = model.get("pins", [])
        if not isinstance(pins, list) or not pins or len(pins) > 512 or any(not PIN_IDENTIFIER.fullmatch(_identifier(pin)) for pin in pins):
            issues.append(_issue("SPICE_MODEL_PINS_INVALID", "Models require one or more unique SPICE-safe pin names.", path=f"{path}.pins"))
        elif len({_identifier(pin) for pin in pins}) != len(pins):
            issues.append(_issue("SPICE_MODEL_PINS_DUPLICATE", "Model pin names must be unique.", path=f"{path}.pins"))
        if kind == "primitive":
            primitive = _identifier(model.get("primitive"))
            definition = PRIMITIVES.get(primitive)
            if definition is None:
                issues.append(_issue("SPICE_PRIMITIVE_UNSUPPORTED", f"Unsupported primitive: {primitive or 'missing'}.", path=f"{path}.primitive"))
            elif isinstance(pins, list) and len(pins) != definition[1]:
                issues.append(_issue("SPICE_PRIMITIVE_PIN_COUNT", f"{primitive} requires {definition[1]} pins.", path=f"{path}.pins"))
            value = _validate_value_expression(model.get("value"), f"{path}.value", issues)
            parameters = model.get("parameters", {})
            if parameters is not None and not isinstance(parameters, dict):
                issues.append(_issue("SPICE_PRIMITIVE_PARAMETERS_INVALID", "Primitive parameters must be an object.", path=f"{path}.parameters"))
                parameters = {}
            if primitive not in {"diode"} and not value and not parameters:
                issues.append(_issue("SPICE_PRIMITIVE_VALUE_REQUIRED", f"{primitive or 'Primitive'} requires a value or source expression.", path=f"{path}.value"))
            if primitive in {"cccs", "ccvs"} and not _identifier((parameters or {}).get("control_source_assignment_id")):
                issues.append(_issue(
                    "SPICE_CONTROL_SOURCE_REQUIRED",
                    f"{primitive} requires parameters.control_source_assignment_id.",
                    path=f"{path}.parameters.control_source_assignment_id",
                ))
        elif kind == "subcircuit":
            subcircuit_name = _identifier(model.get("subcircuit_name"))
            source = _validate_model_source(model.get("source"), f"{path}.source", issues)
            if not IDENTIFIER.fullmatch(subcircuit_name):
                issues.append(_issue("SPICE_SUBCIRCUIT_NAME_INVALID", "A SPICE-safe subcircuit name is required.", path=f"{path}.subcircuit_name"))
            elif not re.search(rf"(?im)^\s*\.subckt\s+{re.escape(subcircuit_name)}(?:\s|$)", source):
                issues.append(_issue("SPICE_SUBCIRCUIT_DECLARATION_MISSING", f"Inline source does not declare .subckt {subcircuit_name}.", path=f"{path}.source"))
            if not re.search(r"(?im)^\s*\.ends(?:\s|$)", source):
                issues.append(_issue("SPICE_SUBCIRCUIT_END_MISSING", "Inline subcircuit source requires .ends.", path=f"{path}.source"))
        else:
            issues.append(_issue("SPICE_MODEL_KIND_INVALID", "Model kind must be primitive or subcircuit.", path=f"{path}.kind"))
        model_by_id[identifier] = model

    known_components = _component_references(design)
    pads = _pad_index(design)
    enabled_assignments = 0
    source_assignments = 0
    assignment_ids: set[str] = set()
    assignment_by_id: Dict[str, Dict[str, Any]] = {}
    for index, assignment in enumerate(assignments):
        path = f"assignments[{index}]"
        if not isinstance(assignment, dict):
            issues.append(_issue("SPICE_ASSIGNMENT_INVALID", "Each assignment must be an object.", path=path))
            continue
        assignment_id = _identifier(assignment.get("id"))
        if not IDENTIFIER.fullmatch(assignment_id):
            issues.append(_issue("SPICE_ASSIGNMENT_ID_INVALID", "Assignment IDs must be bounded SPICE-safe identifiers.", path=f"{path}.id"))
        elif assignment_id in assignment_ids:
            issues.append(_issue("SPICE_ASSIGNMENT_ID_DUPLICATE", f"Duplicate assignment ID: {assignment_id}.", path=f"{path}.id"))
        assignment_ids.add(assignment_id)
        if assignment_id and assignment_id not in assignment_by_id:
            assignment_by_id[assignment_id] = assignment
        if assignment.get("enabled", True) is False:
            continue
        enabled_assignments += 1
        reference = _identifier(assignment.get("component_ref"))
        model = model_by_id.get(_identifier(assignment.get("model_id")))
        if reference not in known_components:
            issues.append(_issue("SPICE_COMPONENT_UNKNOWN", f"Component {reference or 'missing'} is not present in the design.", path=f"{path}.component_ref"))
        if model is None:
            issues.append(_issue("SPICE_ASSIGNMENT_MODEL_UNKNOWN", "Assignment references an unknown model.", path=f"{path}.model_id"))
            continue
        if model.get("kind") == "primitive" and model.get("primitive") in {"voltage_source", "current_source"}:
            source_assignments += 1
        bindings = assignment.get("pin_bindings", [])
        if not isinstance(bindings, list):
            issues.append(_issue("SPICE_PIN_BINDINGS_INVALID", "Pin bindings must be an array.", path=f"{path}.pin_bindings"))
            continue
        binding_by_pin = {_identifier(binding.get("model_pin")): binding for binding in bindings if isinstance(binding, dict)}
        for pin in model.get("pins", []):
            binding = binding_by_pin.get(_identifier(pin))
            if not binding:
                issues.append(_issue("SPICE_PIN_UNMAPPED", f"Model pin {pin} is not mapped.", path=f"{path}.pin_bindings"))
                continue
            pad_id = _identifier(binding.get("pad_id"))
            circuit_node = _identifier(binding.get("circuit_node"))
            if pad_id and pad_id not in pads:
                issues.append(_issue("SPICE_PAD_UNKNOWN", f"Pad {pad_id} is not present in the design.", path=f"{path}.pin_bindings"))
            if not circuit_node:
                issues.append(_issue("SPICE_CIRCUIT_NODE_REQUIRED", f"Model pin {pin} requires a circuit node.", path=f"{path}.pin_bindings"))

    for model_index, model in enumerate(models):
        if not isinstance(model, dict) or model.get("kind") != "primitive" or model.get("primitive") not in {"cccs", "ccvs"}:
            continue
        control_id = _identifier((model.get("parameters") or {}).get("control_source_assignment_id"))
        control_assignment = assignment_by_id.get(control_id)
        if control_assignment is None or control_assignment.get("enabled", True) is False:
            issues.append(_issue(
                "SPICE_CONTROL_SOURCE_UNKNOWN",
                f"Current-controlled source model {model.get('id', model_index + 1)} references unavailable assignment {control_id or 'missing'}.",
                path=f"models[{model_index}].parameters.control_source_assignment_id",
            ))
            continue
        control_model = model_by_id.get(_identifier(control_assignment.get("model_id")))
        if not control_model or control_model.get("kind") != "primitive" or control_model.get("primitive") != "voltage_source":
            issues.append(_issue(
                "SPICE_CONTROL_SOURCE_NOT_VOLTAGE_DEFINED",
                "CCCS and CCVS controls must reference an enabled voltage-source assignment so branch current is explicit.",
                path=f"models[{model_index}].parameters.control_source_assignment_id",
            ))

    parasitic_ids: set[str] = set()
    for index, parasitic in enumerate(parasitics):
        path = f"parasitics[{index}]"
        if not isinstance(parasitic, dict) or parasitic.get("enabled", True) is False:
            continue
        parasitic_id = _identifier(parasitic.get("id"))
        if not IDENTIFIER.fullmatch(parasitic_id):
            issues.append(_issue("SPICE_PARASITIC_ID_INVALID", "Parasitic IDs must be bounded SPICE-safe identifiers.", path=f"{path}.id"))
        elif parasitic_id in parasitic_ids:
            issues.append(_issue("SPICE_PARASITIC_ID_DUPLICATE", f"Duplicate parasitic ID: {parasitic_id}.", path=f"{path}.id"))
        parasitic_ids.add(parasitic_id)
        if parasitic.get("endpoint_reviewed") is not True:
            issues.append(_issue(
                "SPICE_PARASITIC_ENDPOINT_REVIEW_REQUIRED",
                "Imported parasitic endpoints must be explicitly mapped and reviewed before execution.",
                path=f"{path}.endpoint_reviewed",
            ))
        start = _identifier(parasitic.get("from_node"))
        stop = _identifier(parasitic.get("to_node"))
        if not start or not stop or start == stop:
            issues.append(_issue("SPICE_PARASITIC_ENDPOINTS_INVALID", "Parasitics require distinct explicit from/to circuit nodes.", path=path))
        values = {
            key: _finite(parasitic.get(key, 0), nonnegative=True)
            for key in ("resistance_ohm", "inductance_h", "capacitance_f", "conductance_s")
        }
        if any(value is None for value in values.values()) or not any(value and value > 0 for value in values.values() if value is not None):
            issues.append(_issue("SPICE_PARASITIC_VALUES_INVALID", "At least one finite positive R, L, C, or G value is required.", path=path))
        if (values.get("capacitance_f") or values.get("conductance_s")) and not _identifier(parasitic.get("reference_node")):
            issues.append(_issue("SPICE_PARASITIC_REFERENCE_REQUIRED", "Capacitance and conductance require an explicit reference node.", path=f"{path}.reference_node"))
        status = _identifier(parasitic.get("model_status")) or "unvalidated"
        if status != "validated":
            warnings.append(_issue(
                "SPICE_PARASITIC_NOT_VALIDATED",
                f"Parasitic {parasitic.get('id', index + 1)} is {status}; the resulting circuit remains model-dependent.",
                severity="warning",
                path=path,
            ))

    if not enabled_assignments:
        issues.append(_issue("SPICE_ASSIGNMENT_REQUIRED", "At least one enabled component/model assignment is required.", path="assignments"))
    if not source_assignments:
        warnings.append(_issue("SPICE_SOURCE_REVIEW_REQUIRED", "No built-in independent source is assigned; verify that an inline subcircuit supplies excitation.", severity="warning", path="assignments"))
    if not _identifier(workspace.get("ground_node")):
        issues.append(_issue("SPICE_GROUND_REQUIRED", "Select an explicit circuit ground/return node.", path="ground_node"))
    if not isinstance(analysis, dict) or analysis.get("mode") not in {"operating_point", "ac", "transient"}:
        issues.append(_issue("SPICE_ANALYSIS_MODE_INVALID", "Analysis mode must be operating_point, ac, or transient.", path="analysis.mode"))
    elif analysis.get("mode") == "ac":
        if _finite(analysis.get("start_hz"), positive=True) is None or _finite(analysis.get("stop_hz"), positive=True) is None:
            issues.append(_issue("SPICE_AC_RANGE_INVALID", "AC analysis requires finite positive start/stop frequencies.", path="analysis"))
        elif float(analysis["stop_hz"]) <= float(analysis["start_hz"]):
            issues.append(_issue("SPICE_AC_RANGE_INVALID", "AC stop frequency must exceed start frequency.", path="analysis"))
        points = _finite(analysis.get("points_per_decade"), positive=True)
        if points is None or points > 10_000:
            issues.append(_issue("SPICE_AC_POINTS_INVALID", "AC points per decade must be between 1 and 10,000.", path="analysis.points_per_decade"))
    elif analysis.get("mode") == "transient":
        step = _finite(analysis.get("time_step_s"), positive=True)
        stop = _finite(analysis.get("stop_time_s"), positive=True)
        if step is None or stop is None or step >= stop:
            issues.append(_issue("SPICE_TRANSIENT_RANGE_INVALID", "Transient analysis requires 0 < time step < stop time.", path="analysis"))
        elif stop / step > 10_000_000:
            issues.append(_issue("SPICE_TRANSIENT_BUDGET_EXCEEDED", "Transient request exceeds ten million nominal time steps.", path="analysis"))

    return {
        "contract": SPICE_WORKSPACE_VALIDATION_CONTRACT,
        "valid": not issues,
        "can_run": not issues,
        "issues": issues,
        "warnings": warnings,
        "counts": {"models": len(models), "assignments": len(assignments), "parasitics": len(parasitics)},
        "model_status": "validated" if not warnings and not issues else "solver_dependent" if not issues else "unsupported",
    }


def _node_aliases(nodes: Iterable[str], ground_node: str) -> Dict[str, str]:
    aliases = {ground_node: "0", "0": "0"}
    for node in sorted({_identifier(value) for value in nodes if _identifier(value)}):
        if node not in aliases:
            aliases[node] = f"n_{hashlib.sha256(node.encode('utf-8')).hexdigest()[:12]}"
    return aliases


def _analysis_directive(analysis: Dict[str, Any]) -> str:
    mode = analysis["mode"]
    if mode == "operating_point":
        return ".op"
    if mode == "ac":
        return f".ac dec {int(float(analysis['points_per_decade']))} {float(analysis['start_hz']):.12g} {float(analysis['stop_hz']):.12g}"
    return f".tran {float(analysis['time_step_s']):.12g} {float(analysis['stop_time_s']):.12g}"


def compose_spice_workspace(workspace: Dict[str, Any], design: DesignIR) -> Dict[str, Any]:
    validation = validate_spice_workspace(workspace, design)
    if not validation["can_run"]:
        return {
            "contract": SPICE_NETLIST_PREVIEW_CONTRACT,
            "status": "blocked",
            "netlist": "",
            "validation": validation,
            "node_aliases": {},
        }
    models = {str(model["id"]): model for model in workspace["models"]}
    assignments = [item for item in workspace["assignments"] if item.get("enabled", True)]
    parasitics = [item for item in workspace["parasitics"] if item.get("enabled", True)]
    nodes = [str(workspace["ground_node"])]
    for assignment in assignments:
        nodes.extend(str(binding["circuit_node"]) for binding in assignment["pin_bindings"])
    for parasitic in parasitics:
        nodes.extend(str(parasitic.get(key, "")) for key in ("from_node", "to_node", "reference_node"))
    aliases = _node_aliases(nodes, str(workspace["ground_node"]))
    lines = ["SPIKE visual SPICE workspace", "* Generated deterministically; edit the workspace, not this preview."]
    element_aliases: Dict[str, str] = {}
    for original, alias in sorted(aliases.items()):
        lines.append(f"* node {alias} = {original}")
    model_sources: List[str] = []
    for model in models.values():
        source = str(model.get("source", "")).strip()
        if source:
            model_sources.append(source)
    lines.extend(model_sources)
    for index, assignment in enumerate(assignments, start=1):
        model = models[str(assignment["model_id"])]
        binding_by_pin = {str(binding["model_pin"]): binding for binding in assignment["pin_bindings"]}
        instance_nodes = [aliases[str(binding_by_pin[str(pin)]["circuit_node"])] for pin in model["pins"]]
        reference = str(assignment["component_ref"])
        if model["kind"] == "subcircuit":
            instance_name = _safe_instance_name("X", reference)
            lines.append(f"{instance_name} {' '.join(instance_nodes)} {model['subcircuit_name']}")
            for key in (str(assignment["id"]), reference):
                if key in element_aliases and element_aliases[key] != instance_name:
                    raise ValueError(f"Ambiguous workspace element alias {key}.")
                element_aliases[key] = instance_name
            continue
        primitive = str(model["primitive"])
        prefix = PRIMITIVES[primitive][0]
        value = str(model.get("value", "")).strip()
        if primitive == "diode":
            value = str(model.get("device_model", model.get("value", "D_DEFAULT"))).strip()
            if not str(model.get("source", "")).strip():
                lines.append(f".model {value} D")
        instance_name = _safe_instance_name(prefix, reference or str(index))
        for key in (str(assignment["id"]), reference):
            if key in element_aliases and element_aliases[key] != instance_name:
                raise ValueError(f"Ambiguous workspace element alias {key}.")
            element_aliases[key] = instance_name
        if primitive in {"cccs", "ccvs"}:
            control_assignment_id = _identifier((model.get("parameters") or {}).get("control_source_assignment_id"))
            control_assignment = next((item for item in assignments if _identifier(item.get("id")) == control_assignment_id), None)
            if control_assignment is None:
                raise ValueError(f"Dependent source {reference} references unavailable assignment {control_assignment_id}.")
            control_reference = _identifier(control_assignment.get("component_ref"))
            control_name = _safe_instance_name("V", control_reference or control_assignment_id)
            lines.append(f"{instance_name} {' '.join(instance_nodes)} {control_name} {value}")
        else:
            lines.append(f"{instance_name} {' '.join(instance_nodes)} {value}")
    for index, parasitic in enumerate(parasitics, start=1):
        token = _safe_instance_name("P", str(parasitic.get("id", index)))
        start = aliases[str(parasitic["from_node"])]
        stop = aliases[str(parasitic["to_node"])]
        reference = aliases.get(str(parasitic.get("reference_node", "")), "0")
        resistance = float(parasitic.get("resistance_ohm", 0) or 0)
        inductance = float(parasitic.get("inductance_h", 0) or 0)
        capacitance = float(parasitic.get("capacitance_f", 0) or 0)
        conductance = float(parasitic.get("conductance_s", 0) or 0)
        cursor = start
        if resistance > 0:
            next_node = f"{token}_r"
            lines.append(f"R{token} {cursor} {next_node} {resistance:.12g}")
            cursor = next_node
        if inductance > 0:
            next_node = stop
            lines.append(f"L{token} {cursor} {next_node} {inductance:.12g}")
            cursor = next_node
        if cursor != stop:
            lines.append(f"R{token}_link {cursor} {stop} 1e-12")
        if capacitance > 0:
            lines.append(f"C{token} {stop} {reference} {capacitance:.12g}")
        if conductance > 0:
            lines.append(f"R{token}_g {stop} {reference} {1.0 / conductance:.12g}")
        lines.append(f"* parasitic {token} source={parasitic.get('source_result_id', 'manual')} status={parasitic.get('model_status', 'unvalidated')}")
    lines.extend([_analysis_directive(workspace["analysis"]), ".end"])
    netlist = validate_netlist("\n".join(lines) + "\n")
    return {
        "contract": SPICE_NETLIST_PREVIEW_CONTRACT,
        "status": "ready",
        "netlist": netlist,
        "validation": validation,
        "node_aliases": aliases,
        "element_aliases": element_aliases,
        "provenance": {
            "composer": "python.spike_core.spice_workspace",
            "workspace_contract": SPICE_WORKSPACE_CONTRACT,
            "explicit_model_count": len(models),
            "assignment_count": len(assignments),
            "parasitic_count": len(parasitics),
            "geometry_parasitics_inferred": False,
        },
    }
