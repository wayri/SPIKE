# SPDX-License-Identifier: Apache-2.0
"""Explicit reduced circuits coupled by retained assembly connector pin links.

All boards share one MNA solve. Local node '0' is an ordinary board-local node:
only the explicitly selected datum is grounded. A link is a series R/L branch
with optional symmetric pi capacitance to an explicitly supplied reference.
No geometry-derived impedance, common return, mutual coupling or field solution
is inferred. SI here is linear AC transfer, not extracted PCB S parameters.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

from .harness_authoring import validate_harness_connections
from .native_mna import run_native_mna, validate_native_mna_request
from .spider_v2 import AssemblyIRV1
from .multiboard_identity import assembly_physics_digest, canonical_json_digest
from .multiboard_circuit_bonds import compile_electrical_bonds

REQUEST_CONTRACT = "spike/multiboard-circuit-request/v1"
RESULT_CONTRACT = "spike/multiboard-circuit-result/v1"
MAX_ELEMENTS = 4096
MAX_POINTS = 10000
MAX_SAMPLE_VALUES = 2_000_000
NODE_FIELDS = ("positive_node", "negative_node", "control_positive_node", "control_negative_node")


class MultiboardCircuitError(ValueError):
    """An explicit coupled circuit is incomplete or unsupported."""


def _identity(kind: str, *parts: str) -> str:
    return kind + json.dumps(parts, separators=(",", ":"), ensure_ascii=True)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MultiboardCircuitError(f"{name} requires a nonempty trimmed string.")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise MultiboardCircuitError(f"{name} requires a finite nonnegative number.")
    return float(value)


def _fields(raw: Any, allowed: set[str], name: str) -> dict:
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise MultiboardCircuitError(f"{name} has unsupported fields or is not an object.")
    return raw


def compile_multiboard_circuit(raw: dict) -> dict:
    """Compile exact retained link coverage into one bounded native circuit."""
    _fields(raw, {"contract", "assembly", "domain", "board_models", "part_models", "electrical_bond_models", "link_models", "ground", "analysis", "thermal_only_part_ids"}, "request")
    if raw.get("contract") != REQUEST_CONTRACT or raw.get("domain") not in {"pi", "si"}:
        raise MultiboardCircuitError(f"Expected {REQUEST_CONTRACT} and domain pi or si.")
    assembly = AssemblyIRV1.from_dict(raw.get("assembly") or {})
    validate_harness_connections(assembly)
    board_ids = {board.id for board in assembly.boards}
    excluded_parts = [part.id for part in assembly.parts if part.part_type == "subassembly" and not part.model_id]
    from .multiboard_thermal_parts import thermal_only_parts
    thermal_parts = thermal_only_parts(raw, assembly, MultiboardCircuitError)
    part_ids = {part.id for part in assembly.parts} - set(excluded_parts) - set(thermal_parts)
    if not board_ids or len(board_ids) + len(part_ids) < 2:
        raise MultiboardCircuitError("Coupled circuit requires at least two board/part occurrences, including a board.")
    if assembly.rigid_flex_links:
        raise MultiboardCircuitError("Rigid-flex links are not supported by this circuit adapter.")
    models = raw.get("board_models")
    if not isinstance(models, list) or len(models) != len(board_ids):
        raise MultiboardCircuitError("board_models must cover every retained board occurrence exactly once.")
    part_models = raw.get("part_models", [])
    if not isinstance(part_models, list) or len(part_models) != len(part_ids):
        raise MultiboardCircuitError("part_models must cover every electrically participating retained physical part exactly once.")
    models = [("board_id", model) for model in models] + [("part_id", model) for model in part_models]
    if sum(len(model.get("elements", [])) for _, model in models if isinstance(model, dict) and isinstance(model.get("elements"), list)) > MAX_ELEMENTS:
        raise MultiboardCircuitError("Reduced circuit exceeds element budget.")
    elements, node_map, element_map = [], {}, {}
    for owner_field, model in models:
        _fields(model, {owner_field, "elements"}, "occurrence model")
        board = _text(model.get(owner_field), owner_field)
        allowed = board_ids if owner_field == "board_id" else part_ids
        if board not in allowed or board in node_map:
            raise MultiboardCircuitError("Unknown or duplicate occurrence model identity.")
        if not isinstance(model.get("elements"), list) or not model["elements"]:
            raise MultiboardCircuitError("Each board and physical part requires a nonempty reduced circuit.")
        node_kind, element_kind = ("node", "element") if owner_field == "board_id" else ("part-node", "part-element")
        node_map[board], element_map[board] = {}, {}
        for source in model["elements"]:
            if not isinstance(source, dict):
                raise MultiboardCircuitError("Circuit element must be an object.")
            kind = source.get("type")
            type_fields = {
                "resistor": {"resistance_ohm"}, "capacitor": {"capacitance_f"}, "inductor": {"inductance_h"},
                "voltage_source": {"dc_value", "value", "ac_magnitude", "ac_phase_deg"},
                "current_source": {"dc_value", "value", "ac_magnitude", "ac_phase_deg"},
                "vccs": {"control_positive_node", "control_negative_node", "transconductance_s"},
                "vcvs": {"control_positive_node", "control_negative_node", "gain"},
                "cccs": {"control_source_id", "gain"}, "ccvs": {"control_source_id", "transresistance_ohm"},
            }
            if not isinstance(kind, str) or kind not in type_fields:
                raise MultiboardCircuitError("Unsupported reduced circuit element type.")
            if owner_field == "part_id" and kind not in {"resistor", "capacitor", "inductor"}:
                raise MultiboardCircuitError("Physical part models accept passive R/C/L elements only.")
            _fields(source, {"id", "type", "positive_node", "negative_node", *type_fields[kind]}, "circuit element")
            if kind in {"voltage_source", "current_source"}:
                analysis_input = raw.get("analysis")
                mode = analysis_input.get("mode") if isinstance(analysis_input, dict) else None
                if mode == "operating_point" and not {"dc_value", "value"}.intersection(source):
                    raise MultiboardCircuitError("Independent DC sources require an explicit dc_value (zero is allowed).")
                if mode == "ac" and "ac_magnitude" not in source:
                    raise MultiboardCircuitError("Independent AC sources require an explicit ac_magnitude (zero is allowed).")
            element = copy.deepcopy(source)
            local_id = _text(element.get("id"), "element id")
            if local_id in element_map[board]:
                raise MultiboardCircuitError("Duplicate board-local element ID.")
            element["id"] = element_map[board][local_id] = _identity(element_kind, board, local_id)
            for field in NODE_FIELDS:
                if field in element:
                    local = _text(element[field], field)
                    element[field] = node_map[board].setdefault(local, _identity(node_kind, board, local))
            if "control_source_id" in element:
                element["control_source_id"] = _identity("element", board, _text(element["control_source_id"], "control_source_id"))
            elements.append(element)
    if set(node_map) != board_ids | part_ids:
        raise MultiboardCircuitError("Missing board or physical part occurrence model.")

    def reference(value: Any) -> str:
        _fields(value, {"board_id", "part_id", "node"}, "reference")
        fields = set(value) & {"board_id", "part_id"}
        if len(fields) != 1:
            raise MultiboardCircuitError("Reference needs exactly one board_id or part_id.")
        field = next(iter(fields))
        board, local = _text(value.get(field), "reference owner"), _text(value.get("node"), "reference node")
        allowed = board_ids if field == "board_id" else part_ids
        if board not in allowed or local not in node_map[board]:
            raise MultiboardCircuitError("Reference must name an existing board-local or part-local circuit node.")
        return node_map[board][local]

    ground = reference(raw.get("ground"))
    expected = {(h.id, "harness"): (h.endpoint_a, h.endpoint_b, h.pin_map) for h in assembly.harnesses}
    expected.update({(m.id, "mate"): (m.data["endpoint_a"], m.data["endpoint_b"], m.data["pin_map"])
                     for m in assembly.connector_mappings if m.kind == "connector-mate"})
    if not expected and not assembly.electrical_bonds:
        raise MultiboardCircuitError("Coupled circuit requires at least one retained inter-board link or electrical bond.")
    links = raw.get("link_models")
    if not isinstance(links, list) or len(links) != len(expected):
        raise MultiboardCircuitError("link_models must cover every retained harness and mate exactly once.")
    seen, link_map = set(), []
    for model in links:
        _fields(model, {"link_id", "kind", "pins"}, "link model")
        key = (_text(model.get("link_id"), "link_id"), _text(model.get("kind"), "link kind"))
        if key not in expected or key in seen:
            raise MultiboardCircuitError("Unknown or duplicate link model identity.")
        seen.add(key)
        endpoint_a, endpoint_b, pin_map = expected[key]
        ends = [value.split("::" if "::" in value else ":", 1) for value in (endpoint_a, endpoint_b)]
        pins = model.get("pins")
        if not isinstance(pins, list) or len(pins) != len(pin_map) or not 1 <= len(pins) <= 512:
            raise MultiboardCircuitError("Link properties require exact nonempty retained pin coverage.")
        covered = set()
        for pin in pins:
            contact_fields = {"contact_a_resistance_ohm", "contact_b_resistance_ohm", "contact_a_inductance_h", "contact_b_inductance_h"}
            _fields(pin, {"source_pin", "target_pin", "resistance_ohm", "inductance_h", "capacitance_f", "reference", *contact_fields}, "pin properties")
            a, b = _text(pin.get("source_pin"), "source_pin"), _text(pin.get("target_pin"), "target_pin")
            if a not in pin_map or pin_map[a] != b or a in covered:
                raise MultiboardCircuitError("Link property pin mapping differs from the retained graph.")
            covered.add(a)
            terminals = []
            for (board, connector), terminal in zip(ends, (a, b)):
                local = f"{connector}:{terminal}"
                if local not in node_map[board]:
                    raise MultiboardCircuitError(f"Missing explicit board terminal node {board}/{local}.")
                terminals.append(node_map[board][local])
            r = _number(pin.get("resistance_ohm"), "resistance_ohm")
            l = _number(pin.get("inductance_h"), "inductance_h")
            contact_values = {field: _number(pin.get(field, 0), field) for field in contact_fields}
            r += contact_values["contact_a_resistance_ohm"] + contact_values["contact_b_resistance_ohm"]
            l += contact_values["contact_a_inductance_h"] + contact_values["contact_b_inductance_h"]
            c = _number(pin.get("capacitance_f", 0), "capacitance_f")
            prefix = _identity("link", key[1], key[0], a, b)
            p, n = terminals
            ids = []
            for kind, value, field in (("resistor", r, "resistance_ohm"), ("inductor", l, "inductance_h")):
                if not value:
                    continue
                target = _identity("internal", prefix) if kind == "resistor" and l else n
                identifier = prefix + ":" + kind
                elements.append({"id": identifier, "type": kind, "positive_node": p, "negative_node": target, field: value})
                ids.append(identifier)
                p = target
            if not r and not l:
                identifier = prefix + ":ideal"
                elements.append({"id": identifier, "type": "voltage_source", "positive_node": p, "negative_node": n, "dc_value": 0})
                ids.append(identifier)
            if c:
                ref = reference(pin.get("reference"))
                for index, terminal in enumerate(terminals):
                    if terminal == ref:
                        continue  # A capacitor across one identical node stores no energy.
                    identifier = prefix + f":capacitance-{index}"
                    elements.append({"id": identifier, "type": "capacitor", "positive_node": terminal, "negative_node": ref, "capacitance_f": c / 2})
                    ids.append(identifier)
            elif "reference" in pin:
                reference(pin["reference"])
            link_map.append({"link_id": key[0], "kind": key[1], "source_pin": a, "target_pin": b, "element_ids": ids,
                             "series_current_element_id": ids[0], "properties": copy.deepcopy(pin),
                             "total_series_resistance_ohm": r, "total_series_inductance_h": l})
    bond_map = compile_electrical_bonds(raw.get("electrical_bond_models", []), assembly, elements, reference, MultiboardCircuitError)
    analysis = copy.deepcopy(raw.get("analysis"))
    if not isinstance(analysis, dict) or analysis.get("mode") not in {"operating_point", "ac"}:
        raise MultiboardCircuitError("Reduced multiboard execution supports operating_point or ac only.")
    _fields(analysis, {"mode"} if analysis["mode"] == "operating_point" else {"mode", "start_hz", "stop_hz", "points", "scale"}, "analysis")
    if raw["domain"] == "si" and analysis["mode"] != "ac":
        raise MultiboardCircuitError("SI reduced circuit requires AC analysis.")
    points = analysis.get("points", 1) if analysis["mode"] == "ac" else 1
    if isinstance(points, bool) or not isinstance(points, int) or not 1 <= points <= MAX_POINTS:
        raise MultiboardCircuitError("Frequency point budget is 1 through 10000.")
    if len(elements) > MAX_ELEMENTS or points * (len(elements) * 2 + sum(map(len, node_map.values()))) > MAX_SAMPLE_VALUES:
        raise MultiboardCircuitError("Reduced circuit exceeds element or stored sample budget.")
    native = {"contract": "spike/native-mna-request/v1", "elements": elements, "ground_node": ground, "analysis": analysis,
              "resource_limits": {"linear_backend": "scipy-superlu"}}
    validation = validate_native_mna_request(native)
    if not validation["valid"]:
        raise MultiboardCircuitError("Invalid reduced circuit: " + "; ".join(issue["message"] for issue in validation["issues"]))
    return {"native_request": native, "node_map": {key: node_map[key] for key in node_map if key in board_ids},
            "element_map": {key: element_map[key] for key in element_map if key in board_ids}, "links": link_map,
            "part_node_map": {key: node_map[key] for key in node_map if key in part_ids},
            "part_element_map": {key: element_map[key] for key in element_map if key in part_ids},
            "electrical_bonds": bond_map, "excluded_hierarchy_part_ids": excluded_parts,
            **({"excluded_thermal_part_ids": list(thermal_parts)} if thermal_parts else {})}


def run_multiboard_circuit(raw: dict) -> dict:
    """Run a single coupled solve; preserve singular/floating numerical failures."""
    compiled = compile_multiboard_circuit(raw)
    native_request = compiled.pop("native_request")
    native = run_native_mna(native_request)
    if native["status"] == "completed" and raw["analysis"]["mode"] == "operating_point":
        for link in compiled["links"]:
            current = native["data"]["element_current_a"][link["series_current_element_id"]]
            properties = link["properties"]
            losses = {"conductor_loss_w": current ** 2 * properties["resistance_ohm"],
                      "contact_a_loss_w": current ** 2 * properties.get("contact_a_resistance_ohm", 0),
                      "contact_b_loss_w": current ** 2 * properties.get("contact_b_resistance_ohm", 0)}
            link.update(current_a=current, **losses, total_loss_w=sum(losses.values()))
    return {"contract": RESULT_CONTRACT, "status": native["status"], "domain": raw["domain"],
            "model_status": "experimental", "production_qualified": False,
            "coupled_physics": native["status"] == "completed", "coupling_scope": "explicit_linear_reduced_circuit",
            "ground_node": native_request["ground_node"], "analysis": raw["analysis"],
            "assembly_digest": assembly_physics_digest(raw["assembly"]),
            "request_digest": canonical_json_digest(raw),
            **compiled, "native_result": native,
            "limitations": ["Explicit reduced RLC circuits only; PCB geometry is not electrically extracted.",
                            "No mutual inductance/capacitance, distributed delay, radiation, or field coupling.",
                            "Connector capacitance is a symmetric pi shunt to the explicit reference node.",
                            "Physical parts use explicit passive RLC models and retained bond R/L; no implicit chassis ground or geometry extraction.",
                            "SI is linear AC response; eye diagrams and nonlinear drivers are unsupported."]}
