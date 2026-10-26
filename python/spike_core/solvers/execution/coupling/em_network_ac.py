# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Sample-exact AC circuit boundaries around declared passive power-wave data.

Solve waves directly, avoiding singular S->Z/Y conversions for ideal throughs.
This does not fit/extrapolate samples or infer EM-body loss as heat.
"""
import hashlib
import json
import math

import numpy as np

from ...signal_integrity.networks.sparameter_sampling import REQUEST_CONTRACT as SAMPLING_CONTRACT, resample_sparameter_network

REQUEST_CONTRACT = "spike/em-network-ac-request/v1"
RESULT_CONTRACT = "spike/em-network-ac-result/v1"
WAVE_CONVENTION = "rms_power_waves_common_positive_real_reference"


def _require(condition, message):
    if not condition:
        raise ValueError("EM_NETWORK_AC: " + message)


def _digest(raw):
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _pair(raw):
    _require(isinstance(raw, list) and len(raw) == 2 and all(
        type(x) in (int, float) and math.isfinite(x) and abs(x) <= 1e100 for x in raw),
        "Finite bounded [real, imaginary] pair required")
    return complex(*raw)


def _pairs(values):
    return [[float(x.real), float(x.imag)] for x in values]


def solve_em_network_ac(request, *, cancel_check=None):
    """Every port has V+Zseries*I=Vs; I flows into the EM network, V/Vs are RMS.

    Positive-real series impedances may include supplied reactive components.
    Their R*abs(I)^2 is explicit circuit heat; net EM-port power is unclassified.
    """
    _require(cancel_check is None or callable(cancel_check), "Cancellation check must be callable")
    encoded = json.dumps(request, sort_keys=True, allow_nan=False)
    _require(len(encoded.encode()) <= 8*1024**2, "Request exceeds 8 MiB")
    raw = json.loads(encoded)
    _require(isinstance(raw, dict) and set(raw) == {"contract", "source", "wave_convention", "boundaries"}
             and raw["contract"] == REQUEST_CONTRACT and raw["wave_convention"] == WAVE_CONVENTION,
             "Exact contract and explicit RMS power-wave declaration required")

    def poll():
        _require(cancel_check is None or not cancel_check(), "CANCELLED")

    poll()
    source = raw["source"]
    _require(isinstance(source, dict) and isinstance(source.get("frequencies_hz"), list)
             and 1 <= len(source["frequencies_hz"]) <= 512, "Source requires 1..512 exact samples")
    admitted = resample_sparameter_network({"contract": SAMPLING_CONTRACT,
        "source": source, "target_frequencies_hz": source["frequencies_hz"],
        "dc_policy": {"mode": "require_source"}}, cancel_check=cancel_check)
    ports, z0 = source["port_names"], source["reference_impedance_ohm"]
    _require(1e-6 <= z0 <= 1e9, "Reference outside bounded real impedance range")
    samples = raw["boundaries"]
    _require(isinstance(samples, list) and len(samples) == len(source["frequencies_hz"]),
             "One explicit boundary record per source frequency required")
    root, results = math.sqrt(z0), []
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for index, (frequency, matrix, boundary) in enumerate(zip(
                source["frequencies_hz"], source["s_parameters"], samples)):
            poll()
            _require(isinstance(boundary, dict) and set(boundary) == set(ports),
                     "Every named port must have exactly one boundary")
            for item in boundary.values():
                _require(isinstance(item, dict) and set(item) == {"voltage_v", "impedance_ohm"},
                         "Exact source voltage/series impedance fields required")
            vs = np.array([_pair(boundary[p]["voltage_v"]) for p in ports])
            zs = np.array([_pair(boundary[p]["impedance_ohm"]) for p in ports])
            _require(np.all(zs.real >= 0), "Active series resistance unsupported")
            s = np.array([[complex(pair["real"], pair["imag"]) for pair in row] for row in matrix])
            smax = admitted["diagnostics"][index]["smax"]
            _require(smax <= 1+1e-10, "Passive-network workflow rejects nonpassive sample")
            reflection = (zs-z0)/(zs+z0)
            rhs = root*vs/(zs+z0)
            system = np.eye(len(ports))-reflection[:, None]*s
            condition = float(np.linalg.cond(system))
            _require(math.isfinite(condition) and condition <= 1e10, "Singular/ill-conditioned circuit connection")
            a = np.linalg.solve(system, rhs); b = s@a
            residual_scale = np.linalg.norm(system)*np.linalg.norm(a)+np.linalg.norm(rhs)
            residual = np.linalg.norm(system@a-rhs)
            _require(residual <= 1e-10*residual_scale, "Wave solve residual failed")
            voltage, current = root*(a+b), (a-b)/root
            port_power = (voltage*current.conjugate()).real
            resistor_power = zs.real*np.abs(current)**2
            source_power = (vs*current.conjugate()).real
            incoming = math.fsum(float(abs(x)**2) for x in a)
            outgoing = math.fsum(float(abs(x)**2) for x in b)
            net = math.fsum(float(x) for x in port_power)
            source_total = math.fsum(float(x) for x in source_power)
            series_total = math.fsum(float(x) for x in resistor_power)
            scale = max(incoming+outgoing, abs(source_total)+series_total,
                        float(np.linalg.norm(voltage)*np.linalg.norm(current)), np.finfo(float).tiny)
            error = max(abs(net-(incoming-outgoing)), abs(source_total-series_total-net))
            _require(math.isfinite(scale) and error <= 1e-10*scale, "AC circuit power balance failed")
            _require(np.linalg.norm(voltage+zs*current-vs) <= 1e-10*max(
                np.linalg.norm(voltage)+np.linalg.norm(zs*current)+np.linalg.norm(vs), np.finfo(float).tiny),
                "Physical voltage/current boundary residual failed")
            # A strongly excited port must not hide cancellation at a weak port.
            boundary_error = np.abs(voltage+zs*current-vs)
            boundary_scale = np.maximum(np.abs(voltage)+np.abs(zs*current)+np.abs(vs), np.finfo(float).tiny)
            _require(np.all(boundary_error <= 1e-10*boundary_scale),
                     "Per-port physical voltage/current boundary residual failed")
            results.append({"frequency_hz": frequency, "voltage_rms_v": _pairs(voltage),
                "current_into_network_rms_a": _pairs(current), "series_resistor_power_w": resistor_power.tolist(),
                "port_real_power_w": port_power.tolist(), "unclassified_network_power_w": net,
                "source_real_power_w": source_total, "incident_power_w": incoming, "outgoing_power_w": outgoing,
                "connection_condition": condition, "power_balance_error_w": error,
                "maximum_relative_boundary_error": float(np.max(boundary_error/boundary_scale)),
                "power_balance_tolerance_w": 1e-10*scale, "source_smax": smax})
    result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
        "input_digest": _digest(raw), "source_digest": _digest(source), "ports": ports,
        "wave_convention": WAVE_CONVENTION, "samples": results,
        "limitations": ["Exact supplied frequencies only; no causality/fit/transient or source-accuracy qualification",
                        "Port power deficit includes radiation and other unclassified mechanisms; not automatic EM heat",
                        "Circuit RMS amplitudes assume the declared common-real-reference power-wave convention"]}
    _require(len(json.dumps(result, allow_nan=False).encode()) <= 16*1024**2, "Result exceeds 16 MiB")
    poll()
    return result
