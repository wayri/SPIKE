# SPDX-License-Identifier: Apache-2.0
"""Ideal physical connections of supplied symmetric coupled-line sections.

Independent derivation: common-reference V continuity and opposing inward
currents give a_left=b_right, a_right=b_left at each conductor connection.
With block section scattering B, connection permutation P and exterior
injection E, solve (I-PB)X=E; exterior S=E.T B X. No chain inverse is used.
Foundation: Staelin, MIT Electromagnetics and Applications (2011), chapter8
sections8.1.2 and8.3.1; original derivation/verification in method record.
"""
from __future__ import annotations
import math
import numpy as np

from . import rlgc_terminated_pair as bound
from .sparameter_sampling import SParameterSamplingError, _digest, _snapshot

pair = bound.pair
REQUEST = "spike/rlgc-coupled-cascade-request/v1"
RESULT = "spike/rlgc-coupled-cascade-result/v1"
_MAX_BYTES = 32*1024*1024
_MAX_WORK = 100_000_000


class CoupledCascadeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "COUPLED_CASCADE_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise CoupledCascadeError(code, message)


def _child(section, drives):
    return {"contract": pair.REQUEST, **section["pair"], "excitations": drives}


def _prepare(raw, poll):
    bound._record(raw, {"contract", "sections", "excitations"}, "coupled cascade")
    _require(raw["contract"] == REQUEST, "Unsupported coupled cascade contract")
    sections = raw["sections"]
    _require(isinstance(sections, list) and 1 <= len(sections) <= 8, "Supply1..8 sections", "resource_limit")
    ids, first = set(), None
    for section in sections:
        poll()
        bound._record(section, {"id", "pair"}, "coupled section")
        name = section["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80 and name not in ids, "Unique bounded section IDs required")
        ids.add(name)
        bound._record(section["pair"], {"conductor_ids", "modes", "probes"}, "section pair")
        child = _child(section, raw["excitations"])
        pair._prepare(child, poll)
        signature = (child["conductor_ids"], child["modes"]["even"]["reference_impedance_ohm"],
                     [s["frequency_hz"] for s in child["modes"]["even"]["samples"]])
        if first is None:
            first = signature
        _require(signature == first, "Exact conductor order, grid and common real reference required across sections")


def _connection(count):
    connection = np.zeros((4*count, 4*count))
    injection = np.zeros((4*count, 4))
    injection[:2, :2] = np.eye(2)
    injection[-2:, 2:] = np.eye(2)
    for k in range(count-1):
        for conductor in range(2):
            left, right = 4*k+2+conductor, 4*(k+1)+conductor
            connection[left, right] = connection[right, left] = 1.
    return connection, injection


def _solve(blocks, connection, injection):
    block = np.zeros_like(connection, dtype=complex)
    for k, matrix in enumerate(blocks):
        _require(np.shape(matrix) == (4, 4) and np.isfinite(matrix).all(), "Nonfinite or malformed section network", "invalid_result")
        block[4*k:4*k+4, 4*k:4*k+4] = matrix
    system = np.eye(len(block))-connection@block
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= 1e8, "Connection condition exceeds1e8", "ill_conditioned")
    response = np.linalg.solve(system, injection)
    residual = float(np.linalg.norm(system@response-injection))
    scale = float(np.linalg.norm(system)*np.linalg.norm(response)+np.linalg.norm(injection))
    _require(np.isfinite(response).all() and math.isfinite(residual) and residual <= 1e-10*scale,
             "Connection residual failed", "numerical_failure")
    scattering = injection.T@block@response
    _require(np.isfinite(scattering).all() and np.linalg.svd(scattering, compute_uv=False)[0] <= 1+1e-9
             and np.max(abs(scattering-scattering.T)) <= 1e-9, "Cascade passivity/reciprocity failed", "numerical_failure")
    return scattering, response, condition, residual


def _ledger(raw, children, index, matrix, reference, solution):
    incident = np.array([pair._complex(v) for v in raw["excitations"][index]["incident_waves"]])
    outgoing = matrix@incident
    voltage = np.sqrt(reference)*(incident+outgoing)
    current = (incident-outgoing)/np.sqrt(reference)
    boundary = children[0]["points"][index]["boundary_values"][:2]+children[-1]["points"][index]["boundary_values"][2:]
    for key, expected in (("voltage_v", voltage), ("current_into_line_a", current)):
        actual = np.array([pair._complex(t[key]) for t in boundary])
        _require(np.linalg.norm(actual-expected) <= 1e-9*max(np.linalg.norm(actual), np.linalg.norm(expected)),
                 "Exterior field differs from section fields", "invalid_result")
    power = float(np.vdot(current, voltage).real)
    incident_power = float(np.vdot(incident, incident).real)
    losses = {key: sum(child["points"][index]["power_balance"][key] for child in children)
              for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w")}
    residual = power-losses["total_loss_w"]
    scale = max(incident_power, abs(power), losses["total_loss_w"])
    _require(all(math.isfinite(v) for v in (*losses.values(), power, residual)) and abs(residual) <= 1e-10*scale,
             "Global cascade heat balance failed", "numerical_failure")
    junctions = []
    for k in range(len(children)-1):
        left = children[k]["points"][index]["boundary_values"][2:]
        right = children[k+1]["points"][index]["boundary_values"][:2]
        vl, vr = (np.array([pair._complex(t["voltage_v"]) for t in rows]) for rows in (left, right))
        il, ir = (np.array([pair._complex(t["current_into_line_a"]) for t in rows]) for rows in (left, right))
        vres, ires = vl-vr, il+ir
        pres = float(np.vdot(il, vl).real+np.vdot(ir, vr).real)
        local_scale = max(incident_power, float(np.linalg.norm(vl)*np.linalg.norm(il)), float(np.linalg.norm(vr)*np.linalg.norm(ir)))
        _require(np.isfinite(vres).all() and np.isfinite(ires).all() and math.isfinite(pres)
                 and np.linalg.norm(vres) <= 1e-9*max(np.linalg.norm(vl), np.linalg.norm(vr), np.sqrt(reference*incident_power))
                 and np.linalg.norm(ires) <= 1e-9*max(np.linalg.norm(il), np.linalg.norm(ir), np.sqrt(incident_power/reference))
                 and abs(pres) <= 1e-10*local_scale, "Interface continuity failed", "numerical_failure")
        junctions.append({"left_section_id": raw["sections"][k]["id"], "right_section_id": raw["sections"][k+1]["id"],
                          "voltage_residual_v": [pair._pair(v) for v in vres], "current_residual_a": [pair._pair(v) for v in ires],
                          "power_residual_w": pres})
    return {"frequency_hz": raw["excitations"][index]["frequency_hz"],
            "boundary_values": [{"port": j, "voltage_v": pair._pair(voltage[j]), "current_into_line_a": pair._pair(current[j]),
                                 "input_power_w": float(np.real(voltage[j]*np.conj(current[j])))} for j in range(4)],
            "junctions": junctions, "connection_condition": solution[2], "connection_residual": solution[3],
            "power_balance": {**losses, "net_input_w": power, "residual_w": residual}}


def run_rlgc_coupled_cascade(request, *, cancel_check=None):
    """Return four-port S, actual section fields and separately owned heat W."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise CoupledCascadeError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Coupled cascade cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); _prepare(raw, poll)
        count, samples = len(raw["sections"]), len(raw["excitations"])
        probes = sum(len(section["pair"]["probes"]) for section in raw["sections"])
        _require(5*size+samples*(4096+16384*count+4096*probes)+262144 <= _MAX_BYTES,
                 "Estimated cascade result exceeds32MiB", "resource_limit")
        _require(samples*((4*count)**3+256*count+64*probes) <= _MAX_WORK, "Combined connection work exceeds bound", "resource_limit")
        networks = []
        for section in raw["sections"]:
            poll()
            networks.append(bound._bare_network({"pair": section["pair"], "sources": raw["excitations"]}, poll, cancel_check))
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            connection, injection = _connection(count)
            solutions, drives = [], [[] for _ in raw["sections"]]
            for index, excitation in enumerate(raw["excitations"]):
                poll()
                solution = _solve([network[index] for network in networks], connection, injection)
                solutions.append(solution)
                local = solution[1]@np.array([pair._complex(v) for v in excitation["incident_waves"]])
                for k in range(count):
                    drives[k].append({"frequency_hz": excitation["frequency_hz"],
                                      "incident_waves": [pair._pair(v) for v in local[4*k:4*k+4]]})
            children, retained = [], size
            for section, local, network in zip(raw["sections"], drives, networks):
                poll(); expected = _child(section, local)
                child = pair.run_rlgc_coupled_pair(expected, cancel_check=cancel_check)
                bound._bind(child, expected, network, poll)
                retained += pair._size(child, _MAX_BYTES-retained)
                children.append(child)
            points = []
            reference = raw["sections"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
            for index, solution in enumerate(solutions):
                poll(); points.append(_ledger(raw, children, index, solution[0], reference, solution))
            digest = _digest(raw)
            ids = raw["sections"][0]["pair"]["conductor_ids"]
            result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
                "source_request": raw, "input_digest": digest,
                "network": {"id": "coupled-cascade-"+digest[:20], "port_names": [name+":"+end for end in ("left", "right") for name in ids],
                    "reference_impedance_ohm": reference, "frequencies_hz": [p["frequency_hz"] for p in points],
                    "s_parameters": [[[pair._pair(v) for v in row] for row in solution[0]] for solution in solutions]},
                "sections": [{"id": section["id"], "result": child} for section, child in zip(raw["sections"], children)], "points": points,
                "limitations": ["Ordered supplied symmetric co-directed coupled sections, exact common positive grids/real reference/conductor order; no arbitrary matrix basis or branching.",
                    "Ideal zero-length interfaces conserve V/I/power; no bend, via, launch or return-path parasitic extraction.",
                    "Each section owns pair-level integrated conductor/dielectric heat W once; mutual terms have no inferred conductor or thermal-cell ownership.",
                    "RMS sampled steady fields; no causal/transient/DC, geometry/material extraction, thermal deposition, measurements or board qualification.",
                    "1..8 sections,1..1024 samples,1..32 probes per section subject to8MiB input,32MiB output and100million connection-work units; condition<=1e8."]}
        pair._size(result, _MAX_BYTES); poll()
        return result
    except CoupledCascadeError:
        raise
    except (bound.TerminatedPairError, pair.CoupledPairError, bound.RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("TERMINATED_PAIR_", "COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise CoupledCascadeError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise CoupledCascadeError("numerical_failure", str(error)) from error
