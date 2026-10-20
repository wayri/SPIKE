# SPDX-License-Identifier: Apache-2.0
"""Physical R/L/C endpoints around an unchanged supplied coupled cascade.

Independently derived two-level closure: cascade S=E.T B (I-PB)^-1 E,
then (I-diag(Gamma)S)a=d for physical Is=Iline+jwCV and
Vs=V+(R+jwL)Is. Existing direct solves implement both closures without
forming inverses; W/J/var stay separate. See RLGC_LOADED_CASCADE.md.
Foundation: Staelin, MIT Electromagnetics and Applications (2011),
chapter8 sections8.1.2/8.1.4/8.3.1; original composition and tests.
"""
from __future__ import annotations
import numpy as np

from . import rlgc_coupled_cascade as cascade
from . import rlgc_reactive_pair as reactive
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

pair = cascade.pair
REQUEST = "spike/rlgc-loaded-cascade-request/v1"
RESULT = "spike/rlgc-loaded-cascade-result/v1"
_MAX_BYTES = 32*1024*1024


class LoadedCascadeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "LOADED_CASCADE_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise LoadedCascadeError(code, message)


def _view(raw):
    return {"contract": reactive.REQUEST, "pair": raw["sections"][0]["pair"],
            "terminations": raw["terminations"], "sources": raw["sources"]}


def _cascade_request(raw, incidents=None):
    return {"contract": cascade.REQUEST, "sections": raw["sections"], "excitations": [
        {"frequency_hz": source["frequency_hz"], "incident_waves": [pair._pair(v) for v in
            (np.zeros(4, complex) if incidents is None else incidents[k])]}
        for k, source in enumerate(raw["sources"])]}


def _prepare(raw, poll):
    cascade.bound._record(raw, {"contract", "sections", "terminations", "sources"}, "loaded cascade")
    _require(raw["contract"] == REQUEST, "Unsupported loaded cascade contract")
    _require(isinstance(raw["sections"], list) and 1 <= len(raw["sections"]) <= 8, "Supply1..8 coupled sections", "resource_limit")
    terms = reactive._prepare(_view(raw), poll)
    cascade._prepare(_cascade_request(raw), poll)
    return terms


def _bare(raw, poll, cancel_check):
    networks = []
    for section in raw["sections"]:
        poll()
        networks.append(cascade.bound._bare_network({"pair": section["pair"], "sources": raw["sources"]}, poll, cancel_check))
    connection, injection = cascade._connection(len(networks))
    solutions = []
    for index in range(len(raw["sources"])):
        poll(); solutions.append(cascade._solve([network[index] for network in networks], connection, injection))
    return networks, solutions


def _bind(child, expected, networks, solutions, poll):
    _require(child.get("contract") == cascade.RESULT and child.get("production_qualified") is False
             and child.get("model_status") == "experimental" and _json(child.get("source_request")) == _json(expected)
             and child.get("input_digest") == _digest(expected), "Cascade child provenance differs", "invalid_result")
    sections, points = child["sections"], child["points"]
    _require([s["id"] for s in sections] == [s["id"] for s in expected["sections"]]
             and len(points) == len(solutions), "Cascade section/sample coverage differs", "invalid_result")
    reference = expected["sections"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
    names = expected["sections"][0]["pair"]["conductor_ids"]
    network = {"id": "coupled-cascade-"+_digest(expected)[:20],
        "port_names": [name+":"+end for end in ("left", "right") for name in names],
        "reference_impedance_ohm": reference, "frequencies_hz": [e["frequency_hz"] for e in expected["excitations"]],
        "s_parameters": [[[pair._pair(v) for v in row] for row in solution[0]] for solution in solutions]}
    _require(_json(child["network"]) == _json(network), "Cascade network identity/values differ", "invalid_result")
    for k, (section, model) in enumerate(zip(sections, expected["sections"])):
        poll(); drives = []
        for excitation, solution in zip(expected["excitations"], solutions):
            local = solution[1]@np.array([pair._complex(v) for v in excitation["incident_waves"]])
            drives.append({"frequency_hz": excitation["frequency_hz"], "incident_waves": [pair._pair(v) for v in local[4*k:4*k+4]]})
        cascade.bound._bind(section["result"], cascade._child(model, drives), networks[k], poll)
    children = [s["result"] for s in sections]
    for index, solution in enumerate(solutions):
        poll()
        canonical = cascade._ledger(expected, children, index, solution[0], reference, solution)
        _require(_json(points[index]) == _json(canonical), "Cascade boundary/junction/section heat ledger differs", "invalid_result")


def run_rlgc_loaded_cascade(request, *, cancel_check=None):
    """Return physical terminals, complete section fields and explicit W/J/var."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise LoadedCascadeError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Loaded cascade cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); terms = _prepare(raw, poll)
        count, samples = len(raw["sections"]), len(raw["sources"])
        probes = sum(len(s["pair"]["probes"]) for s in raw["sections"])
        _require(6*size+samples*(16384+20480*count+4096*probes)+524288 <= _MAX_BYTES,
                 "Estimated loaded cascade result exceeds32MiB", "resource_limit")
        _require(samples*((4*count)**3+256*count+64*probes) <= cascade._MAX_WORK,
                 "Combined connection work exceeds bound", "resource_limit")
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            networks, connections = _bare(raw, poll, cancel_check)
            reference = raw["sections"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
            r, l, c = (np.array([t[key] for t in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
            solutions = []
            for connection, source in zip(connections, raw["sources"]):
                poll()
                solutions.append(reactive._feedback(connection[0], np.array([pair._complex(v) for v in source["voltage_v"]]),
                                                   r, l, c, 2*np.pi*source["frequency_hz"], reference))
            expected = _cascade_request(raw, [s[0] for s in solutions])
            child = cascade.run_rlgc_coupled_cascade(expected, cancel_check=cancel_check)
            _bind(child, expected, networks, connections, poll)
            pair._size(child, _MAX_BYTES-size)
            points = []
            for index, solution in enumerate(solutions):
                poll()
                points.append(reactive._point(_view(raw), terms, child, index, connections[index][0], solution))
        result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
            "source_request": raw, "input_digest": _digest(raw), "cascade_result": child, "points": points,
            "limitations": ["Physical seriesR/L and node-shuntC source/load closure around supplied symmetric coupled sections only.",
                "R1e-6..1e12ohm,L0..1e3H,C0..1F; positive finite R, ideal fixed L/C; no ideal open/short, nonlinear/lossy reactive or general terminal topology.",
                "Terminal resistor and section conductor/dielectric heat W counted once; mean stored J and reactive var are separate, with signed source VA.",
                "No geometry/contact extraction, physical discontinuity parasitics, thermal-cell ownership, causal/transient/DC or measured/board qualification.",
                "Independent positive-frequency RMS steady cases, no automatic frequency summation or transient thermal input; inherited section/probe/condition/byte/work bounds apply."]}
        pair._size(result, _MAX_BYTES); poll()
        return result
    except LoadedCascadeError:
        raise
    except (cascade.CoupledCascadeError, reactive.ReactivePairError, cascade.bound.TerminatedPairError,
            pair.CoupledPairError, cascade.bound.RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("COUPLED_CASCADE_", "REACTIVE_PAIR_", "TERMINATED_PAIR_", "COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise LoadedCascadeError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise LoadedCascadeError("numerical_failure", str(error)) from error
