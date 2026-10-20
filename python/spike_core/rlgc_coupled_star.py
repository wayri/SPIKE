# SPDX-License-Identifier: Apache-2.0
"""Ideal two-conductor star of supplied symmetric coupled-line legs.

For each common-reference physical conductor node, equal voltage and zero
sum inward current give a=J b, J=2/m*ones-I; J.T J=I. Place J on
right leg ports and inject exterior waves on left ports. Reuse the verified
conditioned block solve and actual pair field producers; count leg heat once.
Foundation: Staelin, MIT Electromagnetics and Applications (2011), chapter8
sections8.1.2/8.3.1; independent derivation and oracle in method record.
"""
from __future__ import annotations
import math
import numpy as np
from . import rlgc_coupled_cascade as cascade
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

pair = cascade.pair
REQUEST = "spike/rlgc-coupled-star-request/v1"
RESULT = "spike/rlgc-coupled-star-result/v1"
_MAX_BYTES = 32*1024*1024
_MAX_WORK = 100_000_000


class CoupledStarError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "COUPLED_STAR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise CoupledStarError(code, message)


def _admission_child(leg, excitations, position):
    return cascade._child(leg, [{"frequency_hz": item["frequency_hz"],
        "incident_waves": item["incident_waves"][2*position:2*position+2]+[{"real": 0., "imag": 0.}]*2} for item in excitations])


def _prepare(raw, poll):
    cascade.bound._record(raw, {"contract", "legs", "excitations"}, "coupled star")
    _require(raw["contract"] == REQUEST, "Unsupported coupled star contract")
    legs, drives = raw["legs"], raw["excitations"]
    _require(isinstance(legs, list) and 2 <= len(legs) <= 8, "Supply2..8 coupled legs", "resource_limit")
    _require(isinstance(drives, list) and 1 <= len(drives) <= 1024, "Supply1..1024 samples", "resource_limit")
    for drive in drives:
        cascade.bound._record(drive, {"frequency_hz", "incident_waves"}, "star excitation")
        _require(isinstance(drive["incident_waves"], list) and len(drive["incident_waves"]) == 2*len(legs), "Supply two physical waves per ordered leg")
        for value in drive["incident_waves"]:
            pair._complex(value)
    ids, first = set(), None
    for k, leg in enumerate(legs):
        poll(); cascade.bound._record(leg, {"id", "pair"}, "star leg")
        name = leg["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80 and name not in ids, "Unique bounded leg IDs required")
        ids.add(name)
        cascade.bound._record(leg["pair"], {"conductor_ids", "modes", "probes"}, "leg pair")
        child = _admission_child(leg, drives, k); pair._prepare(child, poll)
        signature = (child["conductor_ids"], child["modes"]["even"]["reference_impedance_ohm"],
                     [s["frequency_hz"] for s in child["modes"]["even"]["samples"]])
        if first is None: first = signature
        _require(signature == first, "Exact common conductor order, grid and real reference required")


def _connection(count):
    connection, injection = np.zeros((4*count, 4*count)), np.zeros((4*count, 2*count))
    junction = 2./count*np.ones((count, count))-np.eye(count)
    for k in range(count):
        injection[4*k:4*k+2, 2*k:2*k+2] = np.eye(2)
    for conductor in range(2):
        indices = np.arange(count)*4+2+conductor
        connection[np.ix_(indices, indices)] = junction
    return connection, injection


def _point(raw, children, index, solution, reference):
    incident = np.array([pair._complex(v) for v in raw["excitations"][index]["incident_waves"]])
    outgoing = solution[0]@incident
    voltage, current = np.sqrt(reference)*(incident+outgoing), (incident-outgoing)/np.sqrt(reference)
    external = [row for child in children for row in child["points"][index]["boundary_values"][:2]]
    for key, expected in (("voltage_v", voltage), ("current_into_line_a", current)):
        actual = np.array([pair._complex(row[key]) for row in external])
        _require(np.linalg.norm(actual-expected) <= 1e-9*max(np.linalg.norm(actual), np.linalg.norm(expected)), "Exterior and leg fields differ", "invalid_result")
    input_power = float(np.vdot(current, voltage).real)
    incident_power = float(np.vdot(incident, incident).real)
    losses = {key: sum(child["points"][index]["power_balance"][key] for child in children)
              for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w")}
    residual = input_power-losses["total_loss_w"]
    scale = max(incident_power, abs(input_power), losses["total_loss_w"])
    _require(all(math.isfinite(v) for v in (*losses.values(), input_power, residual)) and abs(residual) <= 1e-10*scale,
             "Star input/heat balance failed", "numerical_failure")
    ends = [child["points"][index]["boundary_values"][2:] for child in children]
    voltages = np.array([[pair._complex(t["voltage_v"]) for t in rows] for rows in ends])
    currents = np.array([[pair._complex(t["current_into_line_a"]) for t in rows] for rows in ends])
    junctions = []
    for j, name in enumerate(raw["legs"][0]["pair"]["conductor_ids"]):
        v, i = voltages[:, j], currents[:, j]
        vres, ires = v-v[0], np.sum(i)
        pres = float(np.vdot(i, v).real)
        _require(np.isfinite(vres).all() and np.isfinite(ires) and math.isfinite(pres)
                 and np.linalg.norm(vres) <= 1e-9*max(np.linalg.norm(v), np.sqrt(reference)*np.linalg.norm(incident))
                 and abs(ires) <= 1e-9*max(float(np.sum(abs(i))), np.linalg.norm(incident)/np.sqrt(reference))
                 and abs(pres) <= 1e-10*max(incident_power, float(np.sum(abs(v*np.conj(i))))),
                 "Physical conductor node V/KCL/power failed", "numerical_failure")
        junctions.append({"conductor_id": name, "voltage_v": pair._pair(v[0]),
                          "voltage_residual_v": [pair._pair(z) for z in vres], "current_residual_a": pair._pair(ires), "power_residual_w": pres})
    ids = raw["legs"][0]["pair"]["conductor_ids"]
    return {"frequency_hz": raw["excitations"][index]["frequency_hz"],
        "boundary_values": [{"port": k, "leg_id": raw["legs"][k//2]["id"], "conductor_id": ids[k%2],
            "voltage_v": pair._pair(voltage[k]), "current_into_line_a": pair._pair(current[k]),
            "input_power_w": float(np.real(voltage[k]*np.conj(current[k])))} for k in range(len(voltage))],
        "junctions": junctions, "connection_condition": solution[2], "connection_residual": solution[3],
        "power_balance": {**losses, "net_input_w": input_power, "residual_w": residual}}


def run_rlgc_coupled_star(request, *, cancel_check=None):
    """Return a 2m-port ideal coupled star, actual leg fields and owned heat."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise CoupledStarError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Coupled star cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); _prepare(raw, poll)
        count, samples = len(raw["legs"]), len(raw["excitations"])
        probes = sum(len(leg["pair"]["probes"]) for leg in raw["legs"])
        _require(5*size+samples*(4096+20480*count+4096*probes+256*count**2)+262144 <= _MAX_BYTES,
                 "Estimated coupled star result exceeds32MiB", "resource_limit")
        _require(samples*((4*count)**3+256*count+64*probes) <= _MAX_WORK, "Combined star work exceeds bound", "resource_limit")
        networks = []
        for leg in raw["legs"]:
            poll(); networks.append(cascade.bound._bare_network({"pair": leg["pair"], "sources": raw["excitations"]}, poll, cancel_check))
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            connection, injection = _connection(count)
            solutions, drives = [], [[] for _ in raw["legs"]]
            for index, excitation in enumerate(raw["excitations"]):
                poll(); solution = cascade._solve([n[index] for n in networks], connection, injection); solutions.append(solution)
                local = solution[1]@np.array([pair._complex(v) for v in excitation["incident_waves"]])
                for k in range(count):
                    drives[k].append({"frequency_hz": excitation["frequency_hz"], "incident_waves": [pair._pair(z) for z in local[4*k:4*k+4]]})
            children, retained = [], size
            for leg, drive, network in zip(raw["legs"], drives, networks):
                poll(); expected = cascade._child(leg, drive)
                child = pair.run_rlgc_coupled_pair(expected, cancel_check=cancel_check)
                cascade.bound._bind(child, expected, network, poll)
                retained += pair._size(child, _MAX_BYTES-retained); children.append(child)
            reference = raw["legs"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
            points = []
            for index, solution in enumerate(solutions):
                poll(); points.append(_point(raw, children, index, solution, reference))
            digest = _digest(raw)
            result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
                "source_request": raw, "input_digest": digest,
                "network": {"id": "coupled-star-"+digest[:20],
                    "port_names": [_json([leg["id"], name]).decode("utf-8") for leg in raw["legs"] for name in leg["pair"]["conductor_ids"]],
                    "reference_impedance_ohm": reference, "frequencies_hz": [p["frequency_hz"] for p in points],
                    "s_parameters": [[[pair._pair(z) for z in row] for row in solution[0]] for solution in solutions]},
                "legs": [{"id": leg["id"], "result": child} for leg, child in zip(raw["legs"], children)], "points": points,
                "limitations": ["2..8 uniform supplied symmetric coupled legs; left ends are exterior physical ports, right ends tie two separate ideal conductor nodes in exact common conductor order.",
                    "Exact common positive frequency grid and real reference; RMS exterior waves ordered leg then conductor, collision-free JSON pair port labels.",
                    "Ideal nodes conserve V/current/power, with no junction energy, heat, contact or geometric parasitic extraction.",
                    "Each leg owns integrated pair-level conductor/dielectric heat W once; mutual terms have no inferred conductor or thermal-cell ownership.",
                    "No arbitrary graphs/asymmetric media, physical RLC terminal closure, DC/transient/causal, radiation, thermal feedback, measurements or board qualification.",
                    "1..1024 samples,1..32 probes per leg subject to8MiB input,32MiB output,100million connection-work units and condition<=1e8."]}
        pair._size(result, _MAX_BYTES); poll(); return result
    except CoupledStarError: raise
    except (cascade.CoupledCascadeError, cascade.bound.TerminatedPairError, pair.CoupledPairError,
            cascade.bound.RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("COUPLED_CASCADE_", "TERMINATED_PAIR_", "COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise CoupledStarError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise CoupledStarError("numerical_failure", str(error)) from error
