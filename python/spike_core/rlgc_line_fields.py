# SPDX-License-Identifier: Apache-2.0
"""Driven RMS fields and conservative distributed loss for sampled RLGC lines.

Independently derived from dV/dx=-(R+j*w*L)I, dI/dx=-(G+j*w*C)V:
V=F*exp(-gamma*x)+B*exp(-gamma*(ell-x)); I is their difference/Zc.
The right terminal's current into the line is -I(ell). With RMS phasors,
d Re(V*conj(I))/dx=-R*|I|^2-G*|V|^2. The exact length integrals use the
positive eigenvalues H+J and H-J of the two-wave overlap matrix; short-line
series retain H-J without subtracting nearly equal numbers. No probe mesh
sets the integrated loss, and no heat/residual redistribution is performed.

Foundation: Staelin, Electromagnetics and Applications (2011), MIT OCW,
chapter 8 section 8.3.1, equations 8.3.3--8.3.16. Original implementation,
not adapted from external code. L/C storage is the assumed nondispersive
distributed circuit storage; arbitrary sampled R/G do not certify causality.
"""
from __future__ import annotations

import math

import numpy as np

from .rlgc_line_network import RLGCLineNetworkError, _prepare as _prepare_line, build_rlgc_line_network
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST_CONTRACT = "spike/rlgc-line-fields-request/v1"
RESULT_CONTRACT = "spike/rlgc-line-fields-result/v1"
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_CONDITION = 1e8
_SOLVE_TOLERANCE = 1e-10
_BOUNDARY_TOLERANCE = 1e-9
_POWER_TOLERANCE = 1e-10


class RLGCLineFieldsError(ValueError):
    """Reject malformed, unrepresentable or nonconservative sweeps atomically."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "RLGC_LINE_FIELDS_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise RLGCLineFieldsError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _number(value, name):
    _require(type(value) in (int, float), f"{name} must be a finite nonboolean scalar")
    try:
        result = float(value)
    except OverflowError as error:
        raise RLGCLineFieldsError("invalid_request", f"Unrepresentable {name}") from error
    _require(math.isfinite(result), f"Nonfinite {name}")
    return np.float64(result)


def _complex(value, name):
    _record(value, {"real", "imag"}, name)
    return np.complex128(complex(_number(value["real"], name), _number(value["imag"], name)))


def _pair(value):
    _require(np.isfinite(value), "Nonfinite field phasor", "numerical_failure")
    return {"real": float(value.real), "imag": float(value.imag)}


def _squared(value):
    return value.real * value.real + value.imag * value.imag


def _prepare(request, poll):
    _record(request, {"contract", "line_request", "excitations", "probes"}, "RLGC fields request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported RLGC fields contract")
    _prepare_line(request["line_request"], poll)
    samples = request["line_request"]["samples"]
    _require(samples[0]["frequency_hz"] > 0, "Driven RMS fields require strictly positive frequencies")
    excitations = request["excitations"]
    _require(isinstance(excitations, list) and len(excitations) == len(samples), "Excitations must exactly cover the line sample grid")
    for index, (sample, excitation) in enumerate(zip(samples, excitations)):
        if index % 64 == 0:
            poll()
        _record(excitation, {"frequency_hz", "incident_left", "incident_right"}, "excitation")
        _number(excitation["frequency_hz"], "excitation frequency")
        _require(excitation["frequency_hz"] == sample["frequency_hz"], "Excitation and line frequency grids must agree exactly")
        _complex(excitation["incident_left"], "incident_left")
        _complex(excitation["incident_right"], "incident_right")
    probes = request["probes"]
    _require(isinstance(probes, list) and 1 <= len(probes) <= 32, "Provide 1..32 probes", "resource_limit")
    names = []
    for probe in probes:
        _record(probe, {"id", "fractional_position"}, "probe")
        name = probe["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80, "Probe id must contain 1..80 characters")
        names.append(name)
        _require(0 <= _number(probe["fractional_position"], "probe position") <= 1, "Probe fraction must lie in [0,1]")
    _require(len(set(names)) == len(names), "Probe ids must be unique")


def _propagation(line, sample):
    length, reference = np.float64(line["length_m"]), np.float64(line["reference_impedance_ohm"])
    omega = 2 * np.pi * np.float64(sample["frequency_hz"])
    a = np.complex128(complex(sample["resistance_ohm_per_m"], omega * line["inductance_h_per_m"])) * length / reference
    b = np.complex128(complex(sample["conductance_s_per_m"], omega * line["capacitance_f_per_m"])) * length * reference
    p, q = np.sqrt(a), np.sqrt(b)
    alpha = a.real * (q.real / (p.real + p.imag)) + b.real * (p.imag / (q.real + q.imag))
    beta = p.real * q.imag + p.imag * q.real
    u, impedance = np.complex128(complex(alpha, beta)), reference * (p / q)
    _require(np.isfinite(u) and np.isfinite(impedance) and impedance.real > 0,
             "Unrepresentable propagation or characteristic impedance", "numerical_failure")
    return u, impedance


def _wave_amplitudes(u, impedance, reference, incident):
    normalized = impedance / reference
    reflection = (normalized - 1) / (normalized + 1)
    coefficient = 2 * np.sqrt(reference) * normalized / (normalized + 1)
    coupling = reflection * np.exp(-u)
    system = np.array([[1, coupling], [coupling, 1]], dtype=complex)
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= _MAX_CONDITION,
             "Endpoint wave solve exceeds condition limit 1e8", "ill_conditioned")
    rhs = coefficient * incident
    waves = np.linalg.solve(system, rhs)
    residual = np.linalg.norm(system @ waves - rhs)
    scale = np.linalg.norm(system) * np.linalg.norm(waves) + np.linalg.norm(rhs)
    _require(np.isfinite(waves).all() and residual <= _SOLVE_TOLERANCE * scale,
             "Endpoint wave solve residual exceeds 1e-10", "numerical_failure")
    return waves


def _fields(waves, u, impedance, fraction):
    forward = waves[0] * np.exp(-u * fraction)
    backward = waves[1] * np.exp(-u * (1 - fraction))
    voltage, current = forward + backward, (forward - backward) / impedance
    _require(np.isfinite(voltage) and np.isfinite(current), "Nonfinite interior fields", "numerical_failure")
    return voltage, current


def _even_remainder(value, alternating):
    """sinh(x)/x-1 or 1-sin(x)/x, through x^12 for |x|<0.1."""
    if value == 0:
        return np.float64(0)
    square = value * value
    term = square / 6
    total = term
    for order in range(2, 7):
        term *= square / ((2 * order) * (2 * order + 1))
        total += (-term if alternating and order % 2 == 0 else term)
    return total


def _integrated_losses(waves, u, impedance, length, resistance, conductance):
    alpha, beta = u.real, u.imag
    h = length if alpha == 0 else length * (-np.expm1(-2 * alpha) / (2 * alpha))
    sinc = np.float64(1) if beta == 0 else np.sin(beta) / beta
    j = length * np.exp(-alpha) * sinc
    sinh_remainder = (_even_remainder(alpha, False) if alpha < .1 else np.sinh(alpha) / alpha - 1)
    sinc_remainder = (_even_remainder(beta, True) if beta < .1 else 1 - sinc)
    minus = length * np.exp(-alpha) * (sinh_remainder + sinc_remainder)
    plus = h + j
    _require(plus >= 0 and minus >= 0 and np.isfinite(plus) and np.isfinite(minus),
             "Invalid integrated overlap weights", "numerical_failure")
    sum_squared, difference_squared = _squared(waves[0] + waves[1]), _squared(waves[0] - waves[1])
    voltage_integral = .5 * (sum_squared * plus + difference_squared * minus)
    current_integral = .5 * (difference_squared * plus + sum_squared * minus) / _squared(impedance)
    conductor, dielectric = resistance * current_integral, conductance * voltage_integral
    _require(np.isfinite(conductor) and np.isfinite(dielectric) and conductor >= 0 and dielectric >= 0,
             "Nonfinite or negative integrated loss", "numerical_failure")
    return conductor, dielectric


def _point(line, sample, excitation, probes, scattering, poll):
    reference, length = np.float64(line["reference_impedance_ohm"]), np.float64(line["length_m"])
    resistance, conductance = np.float64(sample["resistance_ohm_per_m"]), np.float64(sample["conductance_s_per_m"])
    incident = np.array([_complex(excitation["incident_left"], "left wave"), _complex(excitation["incident_right"], "right wave")])
    u, impedance = _propagation(line, sample)
    waves = _wave_amplitudes(u, impedance, reference, incident)
    boundary, measured = {}, []
    for name, fraction, sign in (("left", 0., 1), ("right", 1., -1)):
        voltage, current = _fields(waves, u, impedance, fraction)
        inward = sign * current
        power = np.real(voltage * np.conj(inward))
        boundary[name] = {"voltage_v": _pair(voltage), "current_into_line_a": _pair(inward), "input_power_w": float(power)}
        measured.append([voltage / np.sqrt(reference), inward * np.sqrt(reference)])
    outgoing = scattering @ incident
    expected = np.column_stack([incident + outgoing, incident - outgoing])
    _require(np.linalg.norm(np.array(measured) - expected) <= _BOUNDARY_TOLERANCE * max(np.linalg.norm(expected), np.linalg.norm(incident)),
             "Driven fields disagree with sampled network boundary waves", "numerical_failure")
    conductor, dielectric = _integrated_losses(waves, u, impedance, length, resistance, conductance)
    net_input = np.float64(boundary["left"]["input_power_w"]) + np.float64(boundary["right"]["input_power_w"])
    total, incident_power = conductor + dielectric, sum(_squared(value) for value in incident)
    residual = net_input - total
    tolerance = _POWER_TOLERANCE * max(incident_power, total, abs(net_input))
    _require(np.isfinite(net_input) and np.isfinite(residual) and abs(residual) <= tolerance and net_input >= -tolerance,
             "Integrated loss fails the relative 1e-10 power balance", "numerical_failure")
    records = []
    for probe in probes:
        poll()
        voltage, current = _fields(waves, u, impedance, np.float64(probe["fractional_position"]))
        voltage_squared, current_squared = _squared(voltage), _squared(current)
        local_conductor, local_dielectric = resistance * current_squared, conductance * voltage_squared
        record = {"id": probe["id"], "fractional_position": probe["fractional_position"],
                  "voltage_v": _pair(voltage), "current_left_to_right_a": _pair(current),
                  "transported_power_w": float(np.real(voltage * np.conj(current))),
                  "electric_energy_j_per_m": float(np.float64(.5) * line["capacitance_f_per_m"] * voltage_squared),
                  "magnetic_energy_j_per_m": float(np.float64(.5) * line["inductance_h_per_m"] * current_squared),
                  "conductor_loss_w_per_m": float(local_conductor), "dielectric_loss_w_per_m": float(local_dielectric),
                  "total_loss_w_per_m": float(local_conductor + local_dielectric)}
        _require(all(math.isfinite(value) for value in record.values() if isinstance(value, float)), "Nonfinite probe observable", "numerical_failure")
        records.append(record)
    return {"frequency_hz": sample["frequency_hz"], "boundary_values": boundary, "probe_values": records,
            "power_balance": {"net_input_w": float(net_input), "conductor_loss_w": float(conductor),
                              "dielectric_loss_w": float(dielectric), "total_loss_w": float(total), "residual_w": float(residual)}}


def run_rlgc_line_fields(request, *, cancel_check=None):
    """Return RMS steady-state fields, storage densities and exact length losses."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise RLGCLineFieldsError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "RLGC fields calculation cancelled", "cancelled")

    try:
        poll()
        _prepare(request, poll)
        frozen, size = _snapshot(request)
        _prepare(frozen, poll)
        line, probes = frozen["line_request"], frozen["probes"]
        estimate = 3 * size + len(line["samples"]) * (2048 + 1024 * len(probes)) + 65536
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated RLGC fields response exceeds 16 MiB", "resource_limit")
        network = build_rlgc_line_network(line, cancel_check=cancel_check)["network"]
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            points = []
            for sample, excitation, record in zip(line["samples"], frozen["excitations"], network["s_parameters"]):
                poll()
                scattering = np.array([[complex(value["real"], value["imag"]) for value in row] for row in record])
                points.append(_point(line, sample, excitation, probes, scattering, poll))
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": _digest(frozen), "source_request": frozen, "network": network, "points": points,
                      "diagnostics": {"sample_count": len(points), "probe_count": len(probes),
                                      "maximum_power_balance_residual_w": max(abs(point["power_balance"]["residual_w"]) for point in points)},
                      "limitations": [
                          "RMS phasor fields at strictly positive supplied frequencies; incident waves have units sqrt(W)",
                          "Uniform uncoupled scalar effective line with constant positive L/C and supplied sampled nonnegative R/G",
                          "Time-average circuit storage densities are C|V|^2/2 and L|I|^2/2; no dispersive-material energy model",
                          "Signed terminal powers enter the line; interior current and transported power point left-to-right",
                          "Analytic length-integrated R|I|^2 and G|V|^2 losses; probe positions do not discretize the loss integral",
                          "No DC fields, interpolation, transient/causal qualification, thermal solve, geometry extraction or coupled conductors",
                          "S03 propagation bounds retained: 350 nepers and 1e6 radians; endpoint condition at most 1e8",
                          "At most 1024 samples and 32 probes, subject to conservative 16 MiB response preflight; finite input at most 8 MiB",
                          "Relative power balance tolerance 1e-10 against incident/total/net power scale; raw residual is retained",
                          "Floating-point underflow, overflow and failed invariants reject without clipping or residual redistribution",
                          "Synthetic verification only; experimental and not production qualified",
                      ]}
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "RLGC fields response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except RLGCLineFieldsError:
        raise
    except (RLGCLineNetworkError, SParameterSamplingError) as error:
        prefix = "RLGC_LINE_NETWORK_" if isinstance(error, RLGCLineNetworkError) else "SPARAMETER_SAMPLING_"
        raise RLGCLineFieldsError(error.code.removeprefix(prefix), str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise RLGCLineFieldsError("numerical_failure", f"RLGC fields numerical failure: {error}") from error
