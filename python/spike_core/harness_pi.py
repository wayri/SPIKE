# SPDX-License-Identifier: MIT
"""Explicit-terminal, bounded DC operating points for authored harness circuits.

This adapter composes existing circuit kernels; it does not extract board fields.
Positive current enters each element at its positive/from terminal. Current loads
draw their specified amperes from positive to negative, including the return wire.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .harness import compile_harness, terminal_key, validate_harness
from .native_mna import run_native_mna

REQUEST_CONTRACT = "spike/harness-pi-request/v1"
RESULT_CONTRACT = "spike/harness-pi-result/v1"
MAX_ELEMENTS = 4096
MAX_NODES = 1024
MAX_BYTES = 8 * 1024 * 1024


def compile_harness_pi(raw):
    """Validate explicit endpoint bindings and construct a DC native MNA job."""
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_BYTES:
        raise ValueError("Harness PI request exceeds 8 MiB.")
    path = Path(__file__).resolve().parents[2] / "schemas/harness-pi-request-v1.schema.json"
    error = next(Draft202012Validator(json.loads(path.read_text(encoding="utf-8"))).iter_errors(raw), None)
    if error:
        raise ValueError(f"Invalid harness PI request at {list(error.path)}: {error.message}")
    harness = validate_harness(raw["harness"])
    if sum(len(c["pins"]) for c in harness["connectors"]) + len(harness["splices"]) > MAX_NODES:
        raise ValueError("Harness PI terminal inventory exceeds node limit.")
    if len(harness["wires"]) > MAX_ELEMENTS:
        raise ValueError("Harness PI wire inventory exceeds element limit.")
    inventory = {terminal_key({"connector": c["id"], "pin": p["id"]})
                 for c in harness["connectors"] for p in c["pins"]}
    inventory.update(terminal_key({"splice": s["id"]}) for s in harness["splices"])

    def bind(endpoint):
        key = terminal_key(endpoint)
        if key not in inventory:
            raise ValueError("Harness PI endpoint references an unknown connector pin or splice.")
        return key

    ground = bind(raw["ground"])
    fragment = compile_harness(harness)
    elements = []
    for original in fragment["elements"]:
        element = dict(original)
        if element["type"] == "capacitor":
            continue  # Open circuit in a time-invariant DC operating point.
        if element["type"] == "conductance":
            element["type"] = "resistor"
            element["resistance_ohm"] = 1 / element.pop("conductance_to_reference_s")
        elements.append(element)
    ids = set()
    bindings = []
    for category, rows in (("contact", raw.get("contacts", [])), ("terminal", raw["terminals"])):
        for row in rows:
            identity = (category, row["id"])
            if identity in ids:
                raise ValueError(f"Duplicate {category} ID: {row['id']}")
            ids.add(identity)
            p = bind(row["from"] if category == "contact" else row["positive"])
            n = bind(row["to"] if category == "contact" else row["negative"])
            if p == n:
                raise ValueError("Harness PI positive and negative endpoints must be distinct.")
            element = {"id": json.dumps(identity, separators=(",", ":")), "positive_node": p, "negative_node": n}
            if category == "contact":
                element.update(type="resistor", resistance_ohm=row["resistance_ohm"])
            else:
                element.update(type="voltage_source" if row["type"] == "voltage_source" else "current_source", dc_value=row["value"])
            elements.append(element)
            bindings.append({"kind": category, "id": row["id"], "element_id": element["id"], "positive_node": p, "negative_node": n})
    if not any(e["type"] == "voltage_source" for e in elements):
        raise ValueError("Harness PI requires an explicit voltage source.")
    nodes = {e[key] for e in elements for key in ("positive_node", "negative_node")}
    limits = raw.get("resource_limits", {})
    if len(elements) > limits.get("maximum_elements", MAX_ELEMENTS) or len(nodes) > limits.get("maximum_nodes", MAX_NODES):
        raise ValueError("Harness PI element or node resource limit exceeded.")
    # A current source imposes current, not a DC voltage reference. Excluding it
    # detects absent returns even when the drawn topological graph appears closed.
    adjacent = {n: set() for n in nodes}
    for element in elements:
        if element["type"] != "current_source":
            p, n = element["positive_node"], element["negative_node"]
            adjacent[p].add(n)
            adjacent[n].add(p)
    seen, pending = set(), [ground]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(adjacent.get(node, set()) - seen)
    if ground not in nodes or nodes - seen:
        raise ValueError("Harness PI has a floating circuit or missing explicit conductive return to ground.")
    return {"request_digest": hashlib.sha256(encoded).hexdigest(), "harness_digest": fragment["harness_digest"],
            "bindings": bindings, "native_request": {"contract": "spike/native-mna-request/v1", "ground_node": ground,
            "analysis": {"mode": "operating_point"}, "elements": elements,
            "resource_limits": {"linear_backend": "scipy-superlu", "memory_limit_gb": 2}}}


def run_harness_pi(raw, *, cancel_check=None):
    """Run a DC point, retaining kernel failures and exact circuit provenance."""
    if cancel_check and cancel_check():
        raise ValueError("Harness PI execution cancelled.")
    compiled = compile_harness_pi(raw)
    if cancel_check and cancel_check():
        raise ValueError("Harness PI execution cancelled.")
    native = run_native_mna(compiled["native_request"])
    if cancel_check and cancel_check():
        raise ValueError("Harness PI execution cancelled; result discarded.")
    result = {"contract": RESULT_CONTRACT, "status": native["status"], "model_status": "experimental",
              "production_qualified": False, "request_digest": compiled["request_digest"],
              "harness_digest": compiled["harness_digest"], "native_result": native,
              "limitations": ["Lumped linear DC only; no PCB copper, board field coupling, connector heating or SI qualification.",
                              "Contact resistance is explicit per mated pin pair; dimensions do not determine contact resistance.",
                              "Capacitors are open and inductors have zero DC drop; SI metadata is retained in the input, not solved."]}
    if native["status"] != "completed":
        return result
    data = native["data"]
    voltage = dict(data["node_voltage_v"])
    voltage[compiled["native_request"]["ground_node"]] = 0.0
    result["node_voltages_v"] = voltage
    result["connections"] = [{**binding, "voltage_v": voltage[binding["positive_node"]] - voltage[binding["negative_node"]],
                              "current_a": data["element_current_a"][binding["element_id"]],
                              "power_w": data["element_power_w"][binding["element_id"]]} for binding in compiled["bindings"]]
    result["wires"] = [{"wire_id": e["wire_id"], "resistance_ohm": e["resistance_ohm"],
                        "current_a": data["element_current_a"][e["id"]], "loss_w": data["element_power_w"][e["id"]]}
                       for e in compiled["native_request"]["elements"] if "wire_id" in e]
    result["total_wire_loss_w"] = sum(w["loss_w"] for w in result["wires"])
    result["total_contact_loss_w"] = sum(c["power_w"] for c in result["connections"] if c["kind"] == "contact")
    return result
