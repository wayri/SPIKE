# SPDX-License-Identifier: Apache-2.0
"""Physical R/L/C endpoints around an unchanged supplied coupled star.

Independently derived two-level closure: star S=E.T B (I-CB)^-1 E,
then (I-diag(Gamma)S)a=d for physical Is=Iline+jwCV and
Vs=V+(R+jwL)Is. Existing direct solves implement both closures without
forming inverses; W/J/var stay separate. See RLGC_LOADED_STAR.md.
Foundation: Staelin, MIT Electromagnetics and Applications (2011),
chapter8 sections8.1.2/8.1.4/8.3.1; original composition and tests.
"""
from __future__ import annotations
import math
import numpy as np

from . import rlgc_coupled_star as star
from . import rlgc_reactive_pair as reactive
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

cascade = star.cascade
pair = star.pair
REQUEST = "spike/rlgc-loaded-star-request/v1"
RESULT = "spike/rlgc-loaded-star-result/v1"
_MAX_BYTES = 32*1024*1024


class LoadedStarError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "LOADED_STAR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise LoadedStarError(code, message)


def _view(raw):
    return {"contract": reactive.REQUEST, "pair": raw["legs"][0]["pair"],
            "terminations": raw["terminations"], "sources": raw["sources"]}


def _star_request(raw, incidents=None):
    return {"contract": star.REQUEST, "legs": raw["legs"], "excitations": [
        {"frequency_hz": source["frequency_hz"], "incident_waves": [pair._pair(v) for v in
            (np.zeros(2*len(raw["legs"]), complex) if incidents is None else incidents[k])]}
        for k, source in enumerate(raw["sources"])]}


def _prepare(raw, poll):
    cascade.bound._record(raw, {"contract", "legs", "terminations", "sources"}, "loaded star")
    _require(raw["contract"] == REQUEST, "Unsupported loaded star contract")
    _require(isinstance(raw["legs"], list) and 2 <= len(raw["legs"]) <= 8, "Supply 2..8 coupled legs", "resource_limit")
    sources = raw["sources"]
    _require(isinstance(sources, list) and 1 <= len(sources) <= 1024, "Supply 1..1024 source samples", "resource_limit")
    count = 2*len(raw["legs"])
    for source in sources:
        cascade.bound._record(source, {"frequency_hz", "voltage_v"}, "physical source sample")
        _require(isinstance(source["voltage_v"], list) and len(source["voltage_v"]) == count, "Supply a voltage for every ordered physical port")
        for v in source["voltage_v"]: pair._complex(v)
    terms = raw["terminations"]
    _require(isinstance(terms, list) and len(terms) == count, "Supply one explicit termination per physical port")
    names, ports = set(), set()
    for term in terms:
        poll()
        cascade.bound._record(term, {"id", "port", "resistance_ohm", "inductance_h", "capacitance_f"}, "physical RLC termination")
        name, port = term["id"], term["port"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80 and name not in names, "Unique bounded terminal IDs required")
        _require(type(port) is int and 0 <= port < count and port not in ports, "Assign every integer physical port exactly once")
        names.add(name); ports.add(port)
        for key, low, high in (("resistance_ohm", 1e-6, 1e12), ("inductance_h", 0., 1e3), ("capacitance_f", 0., 1.)):
            v = term[key]
            _require(type(v) in (int, float) and math.isfinite(v) and low <= v <= high, key+" outside finite supported range")
    terms = sorted(terms, key=lambda t: t["port"])
    star._prepare(_star_request(raw), poll)
    return terms


def _feedback(scattering, source, resistance, inductance, capacitance, omega, reference):
    impedance = resistance+1j*omega*inductance
    admittance = 1/impedance
    total = admittance+1j*omega*capacitance
    denominator = 1+reference*total
    gamma = (1-reference*total)/denominator
    drive = np.sqrt(reference)*(admittance*source)/denominator
    system = np.eye(len(source))-gamma[:, None]*scattering
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= 1e8, "Endpoint feedback condition exceeds 1e8", "ill_conditioned")
    incident = np.linalg.solve(system, drive)
    residual = float(np.linalg.norm(system@incident-drive))
    scale = float(np.linalg.norm(system)*np.linalg.norm(incident)+np.linalg.norm(drive))
    _require(np.isfinite(incident).all() and math.isfinite(residual) and residual <= 1e-10*scale,
             "Endpoint feedback residual failed", "numerical_failure")
    return incident, condition, residual


def _bare(raw, poll, cancel_check):
    networks = []
    for leg in raw["legs"]:
        poll()
        networks.append(cascade.bound._bare_network({"pair": leg["pair"], "sources": raw["sources"]}, poll, cancel_check))
    connection, injection = star._connection(len(networks))
    solutions = []
    for index in range(len(raw["sources"])):
        poll(); solutions.append(cascade._solve([network[index] for network in networks], connection, injection))
    return networks, solutions


def _bind(child, expected, networks, solutions, poll):
    _require(child.get("contract") == star.RESULT and child.get("production_qualified") is False
             and child.get("model_status") == "experimental" and _json(child.get("source_request")) == _json(expected)
             and child.get("input_digest") == _digest(expected), "Star child provenance differs", "invalid_result")
    legs, points = child["legs"], child["points"]
    _require([s["id"] for s in legs] == [s["id"] for s in expected["legs"]]
             and len(points) == len(solutions), "Star leg/sample coverage differs", "invalid_result")
    reference = expected["legs"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
    names = expected["legs"][0]["pair"]["conductor_ids"]
    network = {"id": "coupled-star-"+_digest(expected)[:20],
        "port_names": [_json([leg["id"], name]).decode("utf-8") for leg in expected["legs"] for name in names],
        "reference_impedance_ohm": reference, "frequencies_hz": [e["frequency_hz"] for e in expected["excitations"]],
        "s_parameters": [[[pair._pair(v) for v in row] for row in solution[0]] for solution in solutions]}
    _require(_json(child["network"]) == _json(network), "Star network identity/values differ", "invalid_result")
    for k, (leg, model) in enumerate(zip(legs, expected["legs"])):
        poll(); drives = []
        for excitation, solution in zip(expected["excitations"], solutions):
            local = solution[1]@np.array([pair._complex(v) for v in excitation["incident_waves"]])
            drives.append({"frequency_hz": excitation["frequency_hz"], "incident_waves": [pair._pair(v) for v in local[4*k:4*k+4]]})
        cascade.bound._bind(leg["result"], cascade._child(model, drives), networks[k], poll)
    children = [s["result"] for s in legs]
    for index, solution in enumerate(solutions):
        poll()
        canonical = star._point(expected, children, index, solution, reference)
        _require(_json(points[index]) == _json(canonical), "Star boundary/junction/leg heat ledger differs", "invalid_result")


def run_rlgc_loaded_star(request, *, cancel_check=None):
    """Return physical terminals, complete leg fields and explicit W/J/var."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise LoadedStarError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Loaded star cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); terms = _prepare(raw, poll)
        count, samples = len(raw["legs"]), len(raw["sources"])
        probes = sum(len(s["pair"]["probes"]) for s in raw["legs"])
        _require(6*size+samples*(16384+20480*count+4096*probes)+524288 <= _MAX_BYTES,
                 "Estimated loaded star result exceeds32MiB", "resource_limit")
        _require(samples*((4*count)**3+256*count+64*probes) <= cascade._MAX_WORK,
                 "Combined connection work exceeds bound", "resource_limit")
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            networks, connections = _bare(raw, poll, cancel_check)
            reference = raw["legs"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
            r, l, c = (np.array([t[key] for t in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
            solutions = []
            for connection, source in zip(connections, raw["sources"]):
                poll()
                solutions.append(_feedback(connection[0], np.array([pair._complex(v) for v in source["voltage_v"]]),
                                                   r, l, c, 2*np.pi*source["frequency_hz"], reference))
            expected = _star_request(raw, [s[0] for s in solutions])
            child = star.run_rlgc_coupled_star(expected, cancel_check=cancel_check)
            _bind(child, expected, networks, connections, poll)
            pair._size(child, _MAX_BYTES-size)
            points = []
            for index, solution in enumerate(solutions):
                poll()
                points.append(reactive._point(_view(raw), terms, child, index, connections[index][0], solution))
        result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
            "source_request": raw, "input_digest": _digest(raw), "star_result": child, "points": points,
            "limitations": ["Physical seriesR/L and node-shuntC source/load closure around supplied symmetric coupled legs only.",
                "R1e-6..1e12ohm,L0..1e3H,C0..1F; positive finite R, ideal fixed L/C; no ideal open/short, nonlinear/lossy reactive or general terminal topology.",
                "Terminal resistor and leg conductor/dielectric heat W counted once; mean stored J and reactive var are separate, with signed source VA.",
                "No geometry/contact extraction, physical discontinuity parasitics, thermal-cell ownership, causal/transient/DC or measured/board qualification.",
                "2..8 uniform coupled legs, 4..16 physical endpoints and exact common grid/reference; independent RMS cases, no frequency summation or transient heat history; inherited bounds apply."]}
        pair._size(result, _MAX_BYTES); poll()
        return result
    except LoadedStarError:
        raise
    except (star.CoupledStarError, cascade.CoupledCascadeError, reactive.ReactivePairError, cascade.bound.TerminatedPairError,
            pair.CoupledPairError, cascade.bound.RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("COUPLED_STAR_", "COUPLED_CASCADE_", "REACTIVE_PAIR_", "TERMINATED_PAIR_", "COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise LoadedStarError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise LoadedStarError("numerical_failure", str(error)) from error
