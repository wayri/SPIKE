# SPDX-License-Identifier: Apache-2.0
"""Sampled physical Thevenin boundaries around a supplied coupled pair.

With RMS waves and inward current, V+R*I=Vs gives a=Gamma*b+d.
For b=S*a, solve (I-Gamma*S)*a=d; no inverse or regularization.
Signed source work Re(Vs*conj(I)) splits into R*|I|^2 and line input.
The unchanged coupled-pair fields retain their own distributed loss once.
Foundation: Staelin, MIT OCW Electromagnetics and Applications (2011),
chapter8 sections8.1.1-8.1.2; see method record and independent oracle.
"""
from __future__ import annotations

import math
import numpy as np

from . import rlgc_coupled_pair as pair
from .rlgc_line_network import RLGCLineNetworkError, build_rlgc_line_network
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST = "spike/rlgc-terminated-pair-request/v1"
RESULT = "spike/rlgc-terminated-pair-result/v1"
_MAX_BYTES = 32*1024*1024
_MAX_CONDITION = 1e8


class TerminatedPairError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "TERMINATED_PAIR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise TerminatedPairError(code, message)


def _record(raw, fields, label):
    _require(isinstance(raw, dict) and set(raw) == set(fields), "Invalid "+label+" fields")


def _pair_request(raw, incident=None):
    return {"contract": pair.REQUEST, **raw["pair"], "excitations": [
        {"frequency_hz": source["frequency_hz"], "incident_waves": [pair._pair(v) for v in
         (np.zeros(4, complex) if incident is None else incident[index])]}
        for index, source in enumerate(raw["sources"])]}


def _prepare(raw, poll):
    _record(raw, {"contract", "pair", "terminations", "sources"}, "terminated pair")
    _require(raw["contract"] == REQUEST, "Unsupported terminated pair contract")
    _record(raw["pair"], {"conductor_ids", "modes", "probes"}, "pair model")
    sources = raw["sources"]
    _require(isinstance(sources, list) and 1 <= len(sources) <= 1024, "Provide 1..1024 source samples", "resource_limit")
    for source in sources:
        _record(source, {"frequency_hz", "voltage_v"}, "source sample")
        _require(isinstance(source["voltage_v"], list) and len(source["voltage_v"]) == 4, "Supply all four physical source voltages")
        for value in source["voltage_v"]:
            pair._complex(value)
    pair._prepare(_pair_request(raw), poll)
    terms = raw["terminations"]
    _require(isinstance(terms, list) and len(terms) == 4, "Supply four explicit port terminations")
    indexed, names = {}, set()
    for term in terms:
        _record(term, {"id", "port", "resistance_ohm"}, "termination")
        name, port, resistance = term["id"], term["port"], term["resistance_ohm"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80 and name not in names, "Unique bounded termination IDs required")
        _require(type(port) is int and 0 <= port < 4 and port not in indexed, "Unique integer ports0..3 required")
        _require(type(resistance) in (int, float) and math.isfinite(resistance) and 1e-6 <= resistance <= 1e12, "Termination resistance must be finite in1e-6..1e12ohm")
        indexed[port] = term; names.add(name)
    return [indexed[port] for port in range(4)]


def _bare_network(raw, poll, cancel_check):
    leaves = []
    for mode in ("even", "odd"):
        poll()
        leaves.append(build_rlgc_line_network(raw["pair"]["modes"][mode], cancel_check=cancel_check)["network"])
    matrices = []
    for index in range(len(raw["sources"])):
        poll()
        modal = np.zeros((4, 4), complex)
        for j, leaf in enumerate(leaves):
            modal[2*j:2*j+2, 2*j:2*j+2] = pair._decode(leaf["s_parameters"][index])
        matrices.append(pair._T@modal@pair._T.T)
    return matrices


def _feedback(scattering, source, resistance, reference):
    # Normalize before adding R+Zref, retaining extreme admitted references.
    scale = np.maximum(resistance, reference)
    r, z = resistance/scale, reference/scale
    gamma = (r-z)/(r+z)
    drive = ((np.sqrt(reference)/scale)/(r+z))*source
    system = np.eye(4)-gamma[:, None]*scattering
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= _MAX_CONDITION, "Physical termination feedback exceeds condition1e8", "ill_conditioned")
    incident = np.linalg.solve(system, drive)
    residual = float(np.linalg.norm(system@incident-drive))
    normalization = float(np.linalg.norm(system)*np.linalg.norm(incident)+np.linalg.norm(drive))
    _require(np.isfinite(incident).all() and math.isfinite(residual) and residual <= 1e-10*normalization,
             "Physical termination feedback residual failed", "numerical_failure")
    return incident, condition, residual


def _same_scalar(actual, expected):
    _require(type(actual) in (int, float) and math.isfinite(actual)
             and abs(actual-expected) <= 1e-10*max(abs(actual), abs(expected)), "Child scalar observable differs from modal constituents", "invalid_result")


def _same_vector(actual, expected, evaluation_scale=0.):
    _require(math.isfinite(evaluation_scale) and evaluation_scale >= 0 and np.isfinite(actual).all()
             and np.linalg.norm(actual-expected) <= 1e-9*max(np.linalg.norm(actual), np.linalg.norm(expected))
             + 64*np.finfo(float).eps*evaluation_scale, "Child field differs from modal constituents", "invalid_result")


def _bind(child, expected, scattering, poll):
    _require(child.get("contract") == pair.RESULT and child.get("production_qualified") is False
             and child.get("model_status") == "experimental" and _json(child.get("source_request")) == _json(expected)
             and child.get("input_digest") == _digest(expected), "Coupled child provenance differs", "invalid_result")
    grid = [source["frequency_hz"] for source in expected["excitations"]]
    reference = expected["modes"]["even"]["reference_impedance_ohm"]
    network = child["network"]
    names = [name+":"+end for end in ("left", "right") for name in expected["conductor_ids"]]
    _require(network["port_names"] == names and network["reference_impedance_ohm"] == reference
             and network["frequencies_hz"] == grid and len(network["s_parameters"]) == len(grid)
             and len(child["points"]) == len(grid), "Coupled child coverage differs", "invalid_result")
    modes = [child["modes"][mode] for mode in ("even", "odd")]
    for j, mode in enumerate(("even", "odd")):
        pair._bind(modes[j], pair._child(expected, mode, j))
    for index, point in enumerate(child["points"]):
        poll()
        _require(point["frequency_hz"] == grid[index] and [p["port"] for p in point["boundary_values"]] == list(range(4))
                 and [(p["id"], p["fractional_position"]) for p in point["probe_values"]]
                 == [(p["id"], p["fractional_position"]) for p in expected["probes"]], "Coupled field identity differs", "invalid_result")
        _require(np.array_equal(pair._decode(network["s_parameters"][index]), scattering[index]), "Bare and driven network differ", "invalid_result")
        modal_network = pair._T.T@scattering[index]@pair._T
        for j, mode in enumerate(modes):
            _same_vector(pair._decode(mode["network"]["s_parameters"][index]), modal_network[2*j:2*j+2, 2*j:2*j+2])
        for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w"):
            _same_scalar(point["power_balance"][key], sum(mode["points"][index]["power_balance"][key] for mode in modes))
        for end_index, end in enumerate(("left", "right")):
            incident = np.array([pair._complex(v) for v in expected["excitations"][index]["incident_waves"]])
            outgoing = scattering[index]@incident
            ends = slice(2*end_index, 2*end_index+2)
            # V/I may cancel at a standing-wave node. Compare the two evaluation
            # paths against their wave operands, not the nearly zero difference.
            wave_scale = np.linalg.norm(incident[ends])+np.linalg.norm(outgoing[ends])
            for key in ("voltage_v", "current_into_line_a"):
                modal = np.array([pair._complex(mode["points"][index]["boundary_values"][end][key]) for mode in modes])
                actual = np.array([pair._complex(row[key]) for row in point["boundary_values"][2*end_index:2*end_index+2]])
                scale = np.sqrt(reference)*wave_scale if key == "voltage_v" else wave_scale/np.sqrt(reference)
                _same_vector(actual, pair._Q@modal, scale)
        for p, probe in enumerate(point["probe_values"]):
            poll()
            voltage, current, densities = pair._observables(modes, index, p)
            for key, values in (("voltage_v", voltage), ("current_left_to_right_a", current)):
                _same_vector(np.array([pair._complex(c[key]) for c in probe["conductors"]]), values)
            for key, value in densities.items():
                _same_scalar(probe["pair"][key], value)
            _same_scalar(probe["pair"]["transported_power_w"], float(np.vdot(current, voltage).real))
            for j, conductor in enumerate(probe["conductors"]):
                _require(conductor["id"] == expected["conductor_ids"][j], "Child conductor identity differs", "invalid_result")
                _same_scalar(conductor["transported_power_w"], float(np.real(voltage[j]*np.conj(current[j]))))


def _ledger(raw, terms, child, index, incident, scattering, condition, solve_residual):
    reference = raw["pair"]["modes"]["even"]["reference_impedance_ohm"]
    source = np.array([pair._complex(v) for v in raw["sources"][index]["voltage_v"]])
    resistance = np.array([term["resistance_ohm"] for term in terms])
    outgoing = scattering@incident
    voltage = np.sqrt(reference)*(incident+outgoing)
    current = (incident-outgoing)/np.sqrt(reference)
    kvl = voltage+resistance*current-source
    scale = max(np.linalg.norm(voltage), np.linalg.norm(resistance*current), np.linalg.norm(source))
    _require(np.linalg.norm(kvl) <= 1e-9*scale, "Physical source KVL failed", "numerical_failure")
    point = child["points"][index]
    measured = np.array([[pair._complex(p["voltage_v"]), pair._complex(p["current_into_line_a"])] for p in point["boundary_values"]])
    for actual, expected in ((measured[:, 0], voltage), (measured[:, 1], current)):
        _require(np.linalg.norm(actual-expected) <= 1e-9*max(np.linalg.norm(actual), np.linalg.norm(expected)), "Driven child boundary differs", "invalid_result")
    source_power = np.real(source*np.conj(current))
    heat = resistance*np.real(current*np.conj(current))
    input_power = np.real(voltage*np.conj(current))
    line = point["power_balance"]
    _require(all(math.isfinite(line[key]) and line[key] >= 0 for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w")), "Invalid child line heat", "invalid_result")
    line_heat = line["conductor_loss_w"]+line["dielectric_loss_w"]
    work, terminal_heat = float(np.sum(source_power)), float(np.sum(heat))
    source_residual = work-terminal_heat-line_heat
    input_residual = float(np.sum(input_power))-line_heat
    budget_scale = max(float(np.sum(np.abs(source)*np.abs(current))), float(np.vdot(incident, incident).real), terminal_heat, line_heat)
    _require(np.isfinite(source_power).all() and np.isfinite(heat).all()
             and abs(source_residual) <= 1e-10*budget_scale and abs(input_residual) <= 1e-10*budget_scale
             and abs(line["total_loss_w"]-line_heat) <= 1e-10*budget_scale, "Source/resistor/line power balance failed", "numerical_failure")
    terminals = [{**term, "source_voltage_v": pair._pair(source[j]), "voltage_v": pair._pair(voltage[j]),
        "current_into_line_a": pair._pair(current[j]), "source_power_w": float(source_power[j]),
        "resistor_heat_w": float(heat[j]), "line_input_power_w": float(input_power[j]), "kvl_residual_v": pair._pair(kvl[j])}
        for j, term in enumerate(terms)]
    return {"frequency_hz": raw["sources"][index]["frequency_hz"], "terminals": terminals,
        "feedback_condition": condition, "feedback_residual": solve_residual,
        "power_balance": {"source_power_w": work, "terminal_resistor_heat_w": terminal_heat,
            "line_conductor_heat_w": line["conductor_loss_w"], "line_dielectric_heat_w": line["dielectric_loss_w"],
            "total_heat_w": terminal_heat+line_heat, "source_residual_w": source_residual, "line_residual_w": input_residual}}


def run_rlgc_terminated_pair(request, *, cancel_check=None):
    """Apply explicit physical source/load boundaries and retain owned heat once."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise TerminatedPairError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Terminated pair cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); terms = _prepare(raw, poll)
        count = len(raw["sources"])
        _require(4*size+count*(16384+4096*len(raw["pair"]["probes"]))+262144 <= _MAX_BYTES,
                 "Estimated terminated-pair result exceeds32MiB", "resource_limit")
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            scattering = _bare_network(raw, poll, cancel_check)
            reference = raw["pair"]["modes"]["even"]["reference_impedance_ohm"]
            resistance = np.array([term["resistance_ohm"] for term in terms])
            solutions = []
            for matrix, source in zip(scattering, raw["sources"]):
                poll()
                solutions.append(_feedback(matrix, np.array([pair._complex(v) for v in source["voltage_v"]]), resistance, reference))
            expected = _pair_request(raw, [solution[0] for solution in solutions])
            child = pair.run_rlgc_coupled_pair(expected, cancel_check=cancel_check)
            _bind(child, expected, scattering, poll)
            pair._size(child, _MAX_BYTES-size)
            points = []
            for index, (incident, condition, residual) in enumerate(solutions):
                poll()
                points.append(_ledger(raw, terms, child, index, incident, scattering[index], condition, residual))
        result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
            "source_request": raw, "input_digest": _digest(raw), "pair_result": child, "points": points,
            "limitations": ["Sampled RMS sources with explicit constant positive physical-port resistances1e-6..1e12ohm; zero source defines a load.",
                "Line fields retain supplied uniform symmetric modal-model limits; no DC, reactive/nonlinear/infinite/zero resistance, time-domain or causal qualification.",
                "Signed source power, per-terminal resistor heat and pair-level distributed line heat are separate; nested modal/line views must not be summed twice.",
                "Terminal IDs identify lumped heat only; no physical contact, thermal mesh, material feedback, geometry extraction or measured accuracy is inferred.",
                "Conditioned solve1e8, raw feedback/KVL and power checks; no inverse, clipping, regularization or hidden loss reassignment."]}
        pair._size(result, _MAX_BYTES); poll()
        return result
    except TerminatedPairError:
        raise
    except (pair.CoupledPairError, RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise TerminatedPairError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise TerminatedPairError("numerical_failure", str(error)) from error
