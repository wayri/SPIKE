# SPDX-License-Identifier: Apache-2.0
"""Supplied symmetric coupled pair through unchanged scalar modal solvers.

Original derivation: Q=1/sqrt(2)*[[1,1],[1,-1]] gives V=Q*Vm, I=Q*Im.
R,L,G,C=Q*diag(even,odd)*Q.T, so dV/dx=-(R+jwL)I and
dI/dx=-(G+jwC)V. The real orthogonal map preserves complex power,
quadratic storage and dissipative loss. Modal heat is counted exactly once;
no per-conductor ownership of mutual terms or thermal mesh is inferred.
Foundation: Steer, Microwave and RF Design II, sections5.3/5.5 (online
author-attributed text, reviewed2026-10-20); see method record.
"""
from __future__ import annotations

import math
import numpy as np

from .rlgc_line_fields import RLGCLineFieldsError, _prepare as _prepare_fields, run_rlgc_line_fields
from .rlgc_line_network import RLGCLineNetworkError
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST = "spike/rlgc-coupled-pair-request/v1"
RESULT = "spike/rlgc-coupled-pair-result/v1"
_Q = np.array([[1., 1.], [1., -1.]])/np.sqrt(2.)
_T = np.array([[1., 0., 1., 0.], [1., 0., -1., 0.],
               [0., 1., 0., 1.], [0., 1., 0., -1.]])/np.sqrt(2.)
_MAX_BYTES = 32*1024*1024


class CoupledPairError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "COUPLED_PAIR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise CoupledPairError(code, message)


def _record(value, fields, label):
    _require(isinstance(value, dict) and set(value) == set(fields), "Invalid "+label+" fields")


def _complex(value):
    _record(value, {"real", "imag"}, "complex scalar")
    _require(all(type(v) in (int, float) and math.isfinite(v) for v in value.values()), "Nonfinite/non-numeric complex scalar")
    return complex(value["real"], value["imag"])


def _pair(value):
    _require(np.isfinite(value), "Nonfinite phasor", "numerical_failure")
    return {"real": float(value.real), "imag": float(value.imag)}


def _matrix(values):
    return (_Q*np.asarray(values))@_Q.T


def _decode(matrix):
    return np.array([[_complex(value) for value in row] for row in matrix])


def _size(value, budget):
    # Stream instead of allocating an aggregate JSON string.
    import json
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
        size += len(chunk.encode())
        _require(size <= budget, "Coupled pair response exceeds 32 MiB budget", "resource_limit")
    return size


def _child(raw, mode, index):
    excitations = []
    for item in raw["excitations"]:
        waves = _T.T@np.array([_complex(value) for value in item["incident_waves"]])
        excitations.append({"frequency_hz": item["frequency_hz"],
            "incident_left": _pair(waves[2*index]), "incident_right": _pair(waves[2*index+1])})
    return {"contract": "spike/rlgc-line-fields-request/v1", "line_request": raw["modes"][mode],
            "probes": raw["probes"], "excitations": excitations}


def _prepare(raw, poll):
    _record(raw, {"contract", "conductor_ids", "modes", "excitations", "probes"}, "coupled pair")
    _require(raw["contract"] == REQUEST, "Unsupported coupled pair contract")
    ids = raw["conductor_ids"]
    _require(isinstance(ids, list) and len(ids) == 2 and all(isinstance(v, str) and v.strip() and len(v) <= 64 for v in ids)
             and len(set(ids)) == 2, "Provide two unique bounded conductor identifiers")
    _record(raw["modes"], {"even", "odd"}, "modes")
    drives = raw["excitations"]
    _require(isinstance(drives, list) and 1 <= len(drives) <= 1024, "Provide 1..1024 coherent excitation samples", "resource_limit")
    for item in drives:
        _record(item, {"frequency_hz", "incident_waves"}, "excitation")
        _require(isinstance(item["incident_waves"], list) and len(item["incident_waves"]) == 4, "Provide four ordered port waves")
    children = [_child(raw, mode, index) for index, mode in enumerate(("even", "odd"))]
    for child in children:
        _prepare_fields(child, poll)
    even, odd = (raw["modes"][mode] for mode in ("even", "odd"))
    for key in ("length_m", "reference_impedance_ohm"):
        _require(even[key] == odd[key], "Modal "+key+" must agree exactly")
    _require([s["frequency_hz"] for s in even["samples"]] == [s["frequency_hz"] for s in odd["samples"]], "Modal grids must agree exactly")
    _require(even["inductance_h_per_m"] >= odd["inductance_h_per_m"] and even["capacitance_f_per_m"] <= odd["capacitance_f_per_m"],
             "Co-directed pair requires Le>=Lo and Maxwell Ce<=Co")
    _require(all(e["conductance_s_per_m"] <= o["conductance_s_per_m"] for e, o in zip(even["samples"], odd["samples"])), "Maxwell conductance requires Ge<=Go")
    return children


def _bind(child, request):
    _require(child.get("contract") == "spike/rlgc-line-fields-result/v1" and _json(child.get("source_request")) == _json(request)
             and child.get("input_digest") == _digest(request) and child.get("production_qualified") is False
             and child.get("model_status") == "experimental", "Child provenance differs", "invalid_result")
    grid = [s["frequency_hz"] for s in request["line_request"]["samples"]]
    network = child["network"]
    _require(network["port_names"] == ["left", "right"] and network["frequencies_hz"] == grid
             and network["reference_impedance_ohm"] == request["line_request"]["reference_impedance_ohm"]
             and len(network["s_parameters"]) == len(grid) and len(child["points"]) == len(grid), "Child network coverage differs", "invalid_result")
    for frequency, point in zip(grid, child["points"]):
        _require(point["frequency_hz"] == frequency and [(p["id"], p["fractional_position"]) for p in point["probe_values"]]
                 == [(p["id"], p["fractional_position"]) for p in request["probes"]], "Child probe/frequency identity differs", "invalid_result")


def _observables(children, index, probe_index):
    points = [c["points"][index]["probe_values"][probe_index] for c in children]
    voltage = _Q@np.array([_complex(p["voltage_v"]) for p in points])
    current = _Q@np.array([_complex(p["current_left_to_right_a"]) for p in points])
    return voltage, current, {key: sum(p[key] for p in points) for key in (
        "electric_energy_j_per_m", "magnetic_energy_j_per_m", "conductor_loss_w_per_m", "dielectric_loss_w_per_m", "total_loss_w_per_m")}


def _point(raw, children, index, scattering, poll):
    excitation = raw["excitations"][index]
    incident = np.array([_complex(v) for v in excitation["incident_waves"]])
    outgoing = scattering@incident
    reference = raw["modes"]["even"]["reference_impedance_ohm"]
    voltage = np.sqrt(reference)*(incident+outgoing)
    inward = (incident-outgoing)/np.sqrt(reference)
    boundary = []
    for end_index, end in enumerate(("left", "right")):
        for key, actual in (("voltage_v", voltage), ("current_into_line_a", inward)):
            modal = np.array([_complex(c["points"][index]["boundary_values"][end][key]) for c in children])
            expected = _Q@modal
            scale = max(np.linalg.norm(actual), np.linalg.norm(expected))
            _require(np.linalg.norm(actual[2*end_index:2*end_index+2]-expected) <= 1e-9*scale, "Physical boundary differs from child waves", "numerical_failure")
        for conductor in range(2):
            port = 2*end_index+conductor
            boundary.append({"port": port, "voltage_v": _pair(voltage[port]), "current_into_line_a": _pair(inward[port]),
                             "input_power_w": float(np.real(voltage[port]*np.conj(inward[port])))})
    records = []
    for probe_index, probe in enumerate(raw["probes"]):
        poll()
        v, i, densities = _observables(children, index, probe_index)
        records.append({**probe, "conductors": [{"id": name, "voltage_v": _pair(v[j]), "current_left_to_right_a": _pair(i[j]),
            "transported_power_w": float(np.real(v[j]*np.conj(i[j])))} for j, name in enumerate(raw["conductor_ids"])],
            "pair": {**densities, "transported_power_w": float(np.vdot(i, v).real)}})
    losses = {key: sum(c["points"][index]["power_balance"][key] for c in children) for key in ("conductor_loss_w", "dielectric_loss_w", "total_loss_w")}
    net_input = sum(p["input_power_w"] for p in boundary)
    incident_power = float(np.vdot(incident, incident).real)
    residual = net_input-losses["total_loss_w"]
    wave_residual = net_input-(incident_power-float(np.vdot(outgoing, outgoing).real))
    scale = max(incident_power, abs(net_input), losses["total_loss_w"])
    _require(all(math.isfinite(v) for v in (*losses.values(), net_input, residual, wave_residual))
             and abs(residual) <= 1e-10*scale and abs(wave_residual) <= 1e-10*scale, "Pair power balance failed", "numerical_failure")
    return {"frequency_hz": excitation["frequency_hz"], "boundary_values": boundary, "probe_values": records,
            "power_balance": {**losses, "net_input_w": net_input, "residual_w": residual, "wave_residual_w": wave_residual}}


def run_rlgc_coupled_pair(request, *, cancel_check=None):
    """Return coherent physical-conductor fields and pair-owned distributed loss."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise CoupledPairError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Coupled pair cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request)
        requests = _prepare(raw, poll)
        count, probes = len(raw["excitations"]), len(raw["probes"])
        _require(3*size+count*(8192+4096*probes)+131072 <= _MAX_BYTES, "Estimated pair result exceeds 32 MiB", "resource_limit")
        children, retained = [], size
        for child_request in requests:
            poll()
            child = run_rlgc_line_fields(child_request, cancel_check=cancel_check)
            _bind(child, child_request)
            retained += _size(child, _MAX_BYTES-retained)
            children.append(child)
        matrices, points = [], []
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            for index in range(count):
                poll()
                modal = np.zeros((4, 4), complex)
                for j, child in enumerate(children):
                    matrix = _decode(child["network"]["s_parameters"][index])
                    _require(matrix.shape == (2, 2), "Child matrix shape differs", "invalid_result")
                    modal[2*j:2*j+2, 2*j:2*j+2] = matrix
                scattering = _T@modal@_T.T
                _require(np.linalg.svd(scattering, compute_uv=False)[0] <= 1+1e-9
                         and np.max(abs(scattering-scattering.T)) <= 1e-10, "Pair passivity/reciprocity failed", "numerical_failure")
                matrices.append([[_pair(value) for value in row] for row in scattering])
                points.append(_point(raw, children, index, scattering, poll))
        digest = _digest(raw)
        output = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
            "source_request": raw, "input_digest": digest,
            "network": {"id": "coupled-pair-"+digest[:20], "port_names": [name+":"+end for end in ("left", "right") for name in raw["conductor_ids"]],
                "reference_impedance_ohm": raw["modes"]["even"]["reference_impedance_ohm"],
                "frequencies_hz": [p["frequency_hz"] for p in points], "s_parameters": matrices},
            "modes": dict(zip(("even", "odd"), children)), "points": points,
            "limitations": ["Supplied uniform co-directed symmetric pair with fixed orthonormal even/odd basis; no arbitrary asymmetric or noncommuting matrix model.",
                "Common real port reference and RMS waves in sqrt(W); port order first/second left, first/second right.",
                "Circuit V/I and pair storage/loss only; modal mutual-term heat has no inferred conductor, cell, volume or thermal-mesh ownership.",
                "No geometry/material extraction, DC fields, interpolated/transient/causal qualification, radiation, thermal feedback or measured validation.",
                "Scalar propagation/conditioning limits retained; no singular-value clipping, loss redistribution or physical qualification."]}
        _size(output, _MAX_BYTES); poll()
        return output
    except CoupledPairError:
        raise
    except (RLGCLineFieldsError, RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("RLGC_LINE_FIELDS_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise CoupledPairError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise CoupledPairError("numerical_failure", str(error)) from error
