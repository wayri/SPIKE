# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded thermal BE transient with quasi-static resistive electrical balance.

Original derivation: R(T)=Rref*(1+alpha*(T-Tref)), P=I**2*R, and
C*(T[n]-T[n-1])/dt + G*(T[n]-Tamb) = P(T[n]). Existing MNA OP and
lumped thermal kernels provide the two solves; this module owns admission,
fixed-point iteration and independently evaluated nodal energy residuals.
Temperatures are kelvin at this boundary (thermal-kernel Celsius conversion
is explicit). This is NOT electrical transient, transistor, CFD, or hardware
qualification. No cooling paths or material values are inferred. A synthetic
shared-sink fixture is not a model of the bare-PCB SAS assembly.

The schema is strict and all fields are required. See the companion tests for
a minimal request. Every resistor needs one temperature/loss mapping; every
circuit element needs a loss-ledger entry. Ideal source absorption is explicitly
external to the thermal domain. Constant supplies only; no C/L or semiconductors.
Iteration can fail near strong feedback; reduce timestep or supply justified
relaxation, never reinterpret failure as a stable thermal result. Temporal
accuracy requires a caller-run refinement study. Independent equations and
synthetic test data were authored here; no third-party implementation used.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import time
from typing import Any, Callable

from .native_mna import run_native_mna, validate_native_mna_request
from .thermal import ThermalScenario
from .thermal_network import estimate_lumped_thermal_network

CONTRACT = "spike/transient-resistive-electrothermal-request/v1"
RESULT_CONTRACT = "spike/transient-resistive-electrothermal-result/v1"
MAX_JSON_BYTES = 8 * 1024 * 1024


class CouplingError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = "TRE_" + code
        super().__init__(message)


def _require(condition, code, message):
    if not condition:
        raise CouplingError(code, message)


def _keys(value, fields, label):
    _require(type(value) is dict and set(value) == set(fields), "FIELDS",
             f"{label} requires exactly: {', '.join(sorted(fields))}.")


def _number(value, label, positive=False):
    _require(type(value) in (int, float), "NUMBER", f"{label} must be numeric.")
    try:
        result = float(value)
    except OverflowError:
        raise CouplingError("NUMBER", f"{label} is unrepresentable.") from None
    _require(math.isfinite(result) and (not positive or result > 0), "NUMBER",
             f"{label} must be finite" + (" and positive." if positive else "."))
    return result


def _text(value, label):
    _require(isinstance(value, str) and 0 < len(value) <= 256 and value.strip() == value,
             "IDENTITY", f"{label} must be a bounded nonblank string.")
    return value


def _list(value, label, maximum, minimum=1):
    _require(type(value) is list and minimum <= len(value) <= maximum, "BOUNDS",
             f"{label} needs {minimum}..{maximum} entries.")
    return value


def _json_bytes(value, code):
    """Bound ordinary JSON encoding without building an unbounded byte copy."""
    size = 0
    for chunk in json.JSONEncoder().iterencode(value):
        size += len(chunk.encode("utf-8"))
        _require(size <= MAX_JSON_BYTES, code, "Serialized payload exceeds 8 MiB.")
    return size


def _prepare(request):
    _keys(request, ("contract", "circuit", "thermal", "loss_mappings", "loss_ledger", "time", "iteration"), "request")
    _require(request["contract"] == CONTRACT, "CONTRACT", "Unsupported contract.")
    circuit = request["circuit"]
    _keys(circuit, ("contract", "request_id", "ground_node", "analysis", "elements"), "circuit")
    _require(circuit["analysis"] == {"mode": "operating_point"}, "ELECTRICAL_SCOPE", "Only quasi-static OP is supported.")
    _text(circuit["request_id"], "request_id")
    _text(circuit["ground_node"], "ground_node")
    elements, resistors = {}, {}
    for element in _list(circuit["elements"], "elements", 64):
        _require(type(element) is dict, "FIELDS", "Element must be a dictionary.")
        kind = element.get("type")
        _require(kind in ("resistor", "voltage_source", "current_source"), "ELECTRICAL_SCOPE", "Only resistors and constant ideal sources are supported.")
        parameter = "resistance_ohm" if kind == "resistor" else "dc_value"
        _keys(element, ("id", "type", "positive_node", "negative_node", parameter), "element")
        identifier = _text(element["id"], "element id")
        _require(identifier not in elements, "IDENTITY", "Duplicate element ID.")
        for key in ("positive_node", "negative_node"):
            _text(element[key], key)
        _number(element[parameter], parameter, kind == "resistor")
        elements[identifier] = element
        if kind == "resistor":
            resistors[identifier] = element
    _require(bool(resistors), "MAPPING", "At least one dissipative resistor is required.")
    _require(validate_native_mna_request(circuit).get("valid"), "ELECTRICAL_INPUT", "Native MNA rejected the circuit.")
    thermal = request["thermal"]
    _keys(thermal, ("ambient_temperature_k", "nodes", "links"), "thermal")
    ambient = _number(thermal["ambient_temperature_k"], "ambient_temperature_k", True)
    nodes = {}
    for node in _list(thermal["nodes"], "thermal nodes", 32):
        _keys(node, ("id", "capacitance_j_per_k", "initial_temperature_k", "minimum_temperature_k", "maximum_temperature_k"), "thermal node")
        identifier = _text(node["id"], "thermal node ID")
        _require(identifier != "ambient" and identifier not in nodes, "IDENTITY", "Duplicate/reserved thermal node ID.")
        for key in set(node) - {"id"}:
            _number(node[key], key, True)
        _require(node["minimum_temperature_k"] <= node["initial_temperature_k"] <= node["maximum_temperature_k"]
                 and node["minimum_temperature_k"] < node["maximum_temperature_k"], "TEMPERATURE_RANGE", "Initial temperature must lie inside a finite validity range.")
        nodes[identifier] = node
    seen = set()
    for link in _list(thermal["links"], "thermal links", 256):
        _keys(link, ("id", "from_id", "to_id", "resistance_k_per_w"), "thermal link")
        identifier = _text(link["id"], "link ID")
        _require(identifier not in seen, "IDENTITY", "Duplicate thermal link ID.")
        seen.add(identifier)
        for key in ("from_id", "to_id"):
            _text(link[key], key)
            _require(link[key] in nodes or link[key] == "ambient", "THERMAL_INPUT", "Unknown thermal endpoint.")
        _require(link["from_id"] != link["to_id"], "THERMAL_INPUT", "Thermal self-link is unsupported.")
        _number(link["resistance_k_per_w"], "thermal resistance", True)
    bindings = {}
    for binding in _list(request["loss_mappings"], "loss_mappings", 64, minimum=0):
        _keys(binding, ("element_id", "thermal_node_id", "reference_temperature_k", "temperature_coefficient_per_k"), "loss mapping")
        identifier = _text(binding["element_id"], "mapped element")
        nid = _text(binding["thermal_node_id"], "mapped thermal node")
        _require(identifier in resistors and identifier not in bindings and nid in nodes, "MAPPING", "Mapping must uniquely bind a resistor to an existing thermal node.")
        reference = _number(binding["reference_temperature_k"], "reference temperature", True)
        alpha = _number(binding["temperature_coefficient_per_k"], "temperature coefficient")
        for temperature in (nodes[nid]["minimum_temperature_k"], nodes[nid]["maximum_temperature_k"]):
            factor = 1 + alpha * (temperature - reference)
            _require(math.isfinite(factor) and factor > 0, "RESISTANCE_RANGE", "R(T) must remain positive throughout declared validity.")
        bindings[identifier] = binding
    _require(set(bindings) == set(resistors), "MAPPING", "Every resistor requires a loss/temperature mapping.")
    ledger_ids = set()
    for item in _list(request["loss_ledger"], "loss ledger", 64, minimum=0):
        _keys(item, ("element_id", "disposition", "reason"), "loss ledger entry")
        identifier = _text(item["element_id"], "ledger element")
        _text(item["reason"], "ledger reason")
        expected = "joule_heat" if identifier in resistors else "external_ideal_source"
        _require(identifier in elements and identifier not in ledger_ids and item["disposition"] == expected,
                 "LEDGER", "Ledger must explicitly classify every resistor/source once.")
        ledger_ids.add(identifier)
    _require(ledger_ids == set(elements), "LEDGER", "Loss ledger is incomplete.")
    timing, options = request["time"], request["iteration"]
    _keys(timing, ("stop_time_s", "maximum_time_step_s"), "time")
    end = _number(timing["stop_time_s"], "stop time", True)
    maximum_dt = _number(timing["maximum_time_step_s"], "maximum timestep", True)
    ratio = end / maximum_dt
    _require(math.isfinite(ratio) and ratio <= 5000, "BOUNDS", "At most 5000 thermal steps are supported.")
    steps = max(1, math.ceil(ratio))
    _keys(options, ("max_iterations", "relaxation", "temperature_tolerance_k", "power_tolerance_w", "balance_tolerance_w", "electrical_relative_tolerance", "time_limit_s"), "iteration")
    _require(type(options["max_iterations"]) is int and 1 <= options["max_iterations"] <= 100, "BOUNDS", "Iterations must be 1..100.")
    _require(steps * options["max_iterations"] <= 100000, "BOUNDS", "Step/iteration product exceeds 100000.")
    for key in set(options) - {"max_iterations"}:
        _number(options[key], key, True)
    _require(options["relaxation"] <= 1 and options["time_limit_s"] <= 120, "BOUNDS", "Relaxation must be <=1 and time limit <=120 s.")
    return circuit, nodes, bindings, ambient, steps, end / steps


def run_transient_resistive_electrothermal(request: Any, *, cancel_check: Callable[[], bool] | None = None) -> dict:
    """Return completed approximate samples, or coded failure with no samples.

    Numerical tolerances are supplied by the caller, never hardware limits.
    The budget is checked between bounded kernel calls, not a process watchdog.
    """
    result = {"contract": RESULT_CONTRACT, "status": "blocked", "model_status": "approximate",
              "samples": [], "history": [], "issues": [], "qualification": {"hardware_pass": False, "production_qualified": False},
              "limitations": ["Thermal transient with quasi-static resistor/source OP, not electrical transient.",
                              "No semiconductor, L/C, switching, airflow, board spreading, or inferred cooling.",
                              "All ideal sources are external to the thermal domain; their internal losses are not modeled.",
                              "Caller-supplied cooling and parameter validity are not physically verified."]}
    started = time.monotonic()
    try:
        _json_bytes(request, "INPUT_BYTES")
        circuit, nodes, bindings, ambient, steps, dt = _prepare(request)
        options = request["iteration"]
        original = deepcopy(circuit)
        result["input_sha256"] = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

        def check():
            if cancel_check is not None and cancel_check():
                raise CouplingError("CANCELLED", "Execution cancelled.")
            _require(time.monotonic() - started <= options["time_limit_s"], "TIMEOUT", "Wall-time budget exhausted.")

        def temperatures(values):
            _require(type(values) is dict and set(values) == set(nodes), "NUMERICAL_FAILURE", "Thermal result must contain exactly the declared nodes.")
            for nid, value in values.items():
                _require(math.isfinite(value) and nodes[nid]["minimum_temperature_k"] <= value <= nodes[nid]["maximum_temperature_k"],
                         "TEMPERATURE_RANGE", f"{nid} leaves its declared temperature range.")

        def electrical(values):
            check()
            temperatures(values)
            query = deepcopy(original)
            resistances = {}
            for element in query["elements"]:
                if element["id"] in bindings:
                    binding = bindings[element["id"]]
                    resistance = element["resistance_ohm"] * (1 + binding["temperature_coefficient_per_k"] * (values[binding["thermal_node_id"]] - binding["reference_temperature_k"]))
                    _require(math.isfinite(resistance) and resistance > 0, "RESISTANCE_RANGE", "Nonpositive/nonfinite R(T).")
                    element["resistance_ohm"] = resistance
                    resistances[element["id"]] = resistance
            solved = run_native_mna(query)
            _require(type(solved) is dict, "NUMERICAL_FAILURE", "Malformed electrical result.")
            _require(solved.get("status") == "completed", "ELECTRICAL_SOLVE", "Electrical OP did not complete.")
            data = solved["data"]
            expected_fields = {"node_voltage_v", "branch_current_a", "element_current_a", "element_power_w"}
            _require(type(data) is dict and set(data) == expected_fields, "NUMERICAL_FAILURE", "Missing/unexpected electrical result fields.")
            expected_ids = {element["id"] for element in query["elements"]}
            for key in ("element_current_a", "element_power_w"):
                _require(type(data[key]) is dict and set(data[key]) == expected_ids, "NUMERICAL_FAILURE", "Electrical result element coverage is incomplete.")
            for collection in data.values():
                _require(type(collection) is dict, "NUMERICAL_FAILURE", "Malformed electrical result collection.")
                _require(all(math.isfinite(value) for value in collection.values()), "NONFINITE", "Nonfinite electrical result.")
            residual = solved["diagnostics"]["relative_residual_max"]
            _require(math.isfinite(residual) and residual <= options["electrical_relative_tolerance"], "ELECTRICAL_RESIDUAL", "Electrical residual exceeds tolerance.")
            power = {nid: 0.0 for nid in nodes}
            for identifier, binding in bindings.items():
                p = data["element_power_w"][identifier]
                _require(p >= 0, "POWER", "Negative resistor heating is unsupported.")
                power[binding["thermal_node_id"]] += p
            balance = math.fsum(data["element_power_w"].values())
            _require(abs(balance) <= options["balance_tolerance_w"], "ELECTRICAL_BALANCE", "Electrical source/loss conservation failed.")
            return power, {**data, "resistance_ohm": resistances, "power_balance_w": balance}

        def thermal(previous, powers):
            check()
            scenario = ThermalScenario(mode="transient", ambient_temperature_c=ambient - 273.15,
                thermal_elements=[{"id": nid, "power_w": powers[nid], "thermal_capacitance_j_per_c": node["capacitance_j_per_k"],
                                   "initial_temperature_c": previous[nid] - 273.15} for nid, node in nodes.items()],
                thermal_links=[{"id": link["id"], "from_id": link["from_id"], "to_id": link["to_id"],
                                "resistance_c_per_w": link["resistance_k_per_w"]} for link in request["thermal"]["links"]],
                run={"end_time_s": dt, "write_interval_s": dt})
            solved = estimate_lumped_thermal_network(scenario)
            _require(type(solved) is dict, "NUMERICAL_FAILURE", "Malformed thermal result.")
            _require(solved.get("status") == "completed", "THERMAL_SOLVE", "Thermal network rejected input or failed; check explicit ambient paths.")
            returned = solved["transient"][-1]["temperatures_c"]
            _require(type(returned) is dict and set(returned) == set(nodes), "NUMERICAL_FAILURE", "Thermal result node coverage is incomplete or unexpected.")
            values = {nid: value + 273.15 for nid, value in returned.items()}
            temperatures(values)
            return values

        def balance(previous, values, power):
            residuals = {nid: nodes[nid]["capacitance_j_per_k"] * (values[nid] - previous[nid]) / dt - power[nid] for nid in nodes}
            boundary_power = 0.0
            for link in request["thermal"]["links"]:
                left, right = link["from_id"], link["to_id"]
                flux = (values.get(left, ambient) - values.get(right, ambient)) / link["resistance_k_per_w"]
                if left != "ambient": residuals[left] += flux
                if right != "ambient": residuals[right] -= flux
                if right == "ambient": boundary_power += flux
                if left == "ambient": boundary_power -= flux
            storage = math.fsum(nodes[nid]["capacitance_j_per_k"] * (values[nid] - previous[nid]) / dt for nid in nodes)
            global_error = storage + boundary_power - math.fsum(power.values())
            all_values = [*residuals.values(), global_error, storage, boundary_power]
            _require(all(math.isfinite(v) for v in all_values), "NONFINITE", "Nonfinite energy balance.")
            return max(abs(v) for v in residuals.values()), global_error, storage, boundary_power

        previous = {nid: node["initial_temperature_k"] for nid, node in nodes.items()}
        initial_power, initial_electrical = electrical(previous)
        samples = [{"time_s": 0.0, "temperature_k": dict(previous), "node_power_w": initial_power, "electrical": initial_electrical}]
        retained_bytes = _json_bytes(samples, "RESULT_BYTES")
        for step in range(1, steps + 1):
            guess = dict(previous)
            for iteration in range(1, options["max_iterations"] + 1):
                powers, _ = electrical(guess)
                mapped = thermal(previous, powers)
                final_power, final_electrical = electrical(mapped)
                temperature_error = max(abs(mapped[nid] - guess[nid]) for nid in nodes)
                power_error = max(abs(final_power[nid] - powers[nid]) for nid in nodes)
                local_error, global_error, storage, boundary = balance(previous, mapped, final_power)
                record = {"step": step, "iteration": iteration, "temperature_residual_k": temperature_error,
                          "power_residual_w": power_error, "nodal_balance_residual_w": local_error, "global_balance_residual_w": global_error}
                if (temperature_error <= options["temperature_tolerance_k"] and power_error <= options["power_tolerance_w"]
                        and local_error <= options["balance_tolerance_w"] and abs(global_error) <= options["balance_tolerance_w"]):
                    result["history"].append(record)
                    samples.append({"time_s": step * dt, "temperature_k": mapped, "node_power_w": final_power,
                                    "electrical": final_electrical, "stored_energy_rate_w": storage, "ambient_heat_flow_w": boundary})
                    retained_bytes += _json_bytes(samples[-1], "RESULT_BYTES") + _json_bytes(record, "RESULT_BYTES") + 4
                    _require(retained_bytes <= MAX_JSON_BYTES, "RESULT_BYTES", "Retained result exceeds 8 MiB.")
                    previous = mapped
                    break
                guess = {nid: guess[nid] + options["relaxation"] * (mapped[nid] - guess[nid]) for nid in nodes}
            else:
                result["history"].append(record)
                raise CouplingError("NONCONVERGENCE", f"Unrelaxed coupled residual failed at step {step}.")
        check()
        result.update(status="completed", samples=samples, loss_ledger=deepcopy(request["loss_ledger"]),
                      time_step_s=dt, steps=steps, method="backward_euler_thermal_quasistatic_resistive_mna")
        _json_bytes(result, "RESULT_BYTES")
    except CouplingError as error:
        result["status"] = "cancelled" if error.code == "TRE_CANCELLED" else "blocked"
        result["samples"] = []
        if error.code == "TRE_RESULT_BYTES":
            result["history"] = []
            for key in ("loss_ledger", "time_step_s", "steps", "method"):
                result.pop(key, None)
        result["issues"] = [{"code": error.code, "message": str(error), "severity": "error"}]
    except (ValueError, ArithmeticError, KeyError, TypeError, AttributeError, IndexError) as error:
        result["status"] = "blocked"
        result["samples"] = []
        result["issues"] = [{"code": "TRE_NUMERICAL_FAILURE", "message": str(error), "severity": "error"}]
    return result
