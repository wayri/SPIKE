# SPDX-License-Identifier: Apache-2.0
"""Exact prescribed-PWL wave response of the supplied-real-pole fitted model.

For x'=-p*x+p*a and a linear incident wave over h, integration gives
x1=q*x0+(w-phi)*a0+phi*a1, q=exp(-p*h), w=1-q, phi=1-w/(p*h).
Small-z series avoid cancellation in phi; larger z uses w/z-q for the
start weight, avoiding cancellation for a ramp ending at zero. Overflowed
z uses the equivalent inverse factors for the surviving start contribution.
This propagates the fitted model without a numerical timestep approximation.
Each pole state is a vector of incident-port waves. b=D*a+sum R_k*x_k.
With real instantaneous power-normalized waves, V=sqrt(R0)*(a+b) and
I=(a-b)/sqrt(R0), positive into the network. No RMS conversion is implied.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import sparameter_rational as rational

REQUEST_CONTRACT = "spike/rational-network-transient-request/v1"
RESULT_CONTRACT = "spike/rational-network-transient-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_INTERVALS = 20000
_MAX_WORK = 100_000_000


class SParameterTransientError(ValueError):
    """Invalid or failed fitted-model transient returns no partial trajectory."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_TRANSIENT_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterTransientError(code, message)


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(request):
            size += len(chunk.encode("utf-8"))
            _require(size <= _MAX_REQUEST_BYTES, "Transient request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except SParameterTransientError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise SParameterTransientError("invalid_request", f"Invalid finite JSON: {error}") from error


def _times(values, name):
    for value in values:
        _require(rational.sampling._number(value, name) >= 0, "Times must be nonnegative")
    _require(all(b > a for a, b in zip(values, values[1:])), f"{name} must increase strictly")
    converted = [float(value) for value in values]
    _require(all(b > a for a, b in zip(converted, converted[1:])),
             f"{name} collapses under floating-point representation", "numerical_failure")
    return converted


def _prepare(request, size, poll):
    rational.sampling._record(request, {"contract", "fit_request", "incident_waves", "output_times_s"}, "transient request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported rational network transient contract")
    fit_request = request["fit_request"]
    fit_size = len(rational.sampling._json(fit_request))
    source, frequencies, poles, _, _ = rational._prepare(fit_request, fit_size, poll)
    ports = source["port_names"]
    raw_waves = request["incident_waves"]
    _require(isinstance(raw_waves, list) and len(raw_waves) == len(ports), "Exactly one incident waveform per source port required")
    by_port, union, horizon = {}, {0}, None
    for wave in raw_waves:
        rational.sampling._record(wave, {"port_name", "points"}, "incident waveform")
        port = wave["port_name"]
        _require(isinstance(port, str) and port in ports and port not in by_port, "Unknown or duplicate waveform port")
        points = wave["points"]
        _require(isinstance(points, list) and 2 <= len(points) <= 1024, "Waveforms require 2..1024 points", "resource_limit")
        for point in points:
            rational.sampling._record(point, {"time_s", "value_sqrt_w"}, "wave point")
        raw_times = [point["time_s"] for point in points]
        times = _times(raw_times, "waveform times")
        _require(raw_times[0] == 0 and raw_times[-1] > 0, "Waveforms must start exactly at zero and end at a positive horizon")
        _require(horizon is None or raw_times[-1] == horizon, "Waveforms must share an exact common final time; no extension")
        horizon = raw_times[-1]
        amplitudes = [rational.sampling._number(point["value_sqrt_w"], "incident wave") for point in points]
        by_port[port] = (times, amplitudes)
        union.update(raw_times)
    raw_outputs = request["output_times_s"]
    _require(isinstance(raw_outputs, list) and 1 <= len(raw_outputs) <= 4096, "Provide 1..4096 output times", "resource_limit")
    outputs = _times(raw_outputs, "output times")
    _require(raw_outputs[-1] <= horizon, "Output times exceed the explicitly supplied horizon")
    union.update(raw_outputs)
    grid = _times(sorted(union), "union of knots and outputs")
    intervals = len(grid) - 1
    _require(intervals <= _MAX_INTERVALS, "Union exceeds 20000 intervals", "resource_limit")
    n, k, m = len(ports), len(poles), 2 * len(frequencies)
    work = m * (k+1)**2 + m * (k+1) * n*n + 16 * intervals * k*n + len(outputs) * (k+1) * n*n
    _require(work <= _MAX_WORK, "Aggregate fit and propagation work exceeds 100 million units", "resource_limit")
    fit_estimate = 3 * fit_size + 96 * len(frequencies) * n*n + 64 * (k+1) * n*n + 65536
    names_size = sum(len(rational.sampling._json(port)) for port in ports)
    estimate = 3 * size + fit_estimate + len(outputs) * (512 + 4 * names_size + 256 * n) + 131072
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated transient response exceeds 16 MiB", "resource_limit")
    return ports, [by_port[p] for p in ports], grid, outputs, work


def _model(fit, request, ports):
    source = request["source"]
    _require(isinstance(fit, dict) and fit.get("contract") == rational.RESULT_CONTRACT
             and fit.get("model_status") == "experimental" and fit.get("production_qualified") is False
             and fit.get("input_digest") == rational.sampling._digest(request)
             and fit.get("pole_rates_rad_s") == request["pole_rates_rad_s"], "Fitted model identity mismatch", "numerical_failure")
    binding = fit.get("source")
    _require(isinstance(binding, dict) and binding.get("network") == source
             and binding.get("input_digest") == rational.sampling._digest(source), "Fitted source binding mismatch", "numerical_failure")
    model = fit.get("model")
    _require(isinstance(model, dict) and set(model) == {"direct", "residues", "realization", "stability", "causality"}
             and model["realization"] == "x_k_prime=-p_k*x_k+p_k*a; b=D*a+sum(R_k*x_k)"
             and model["stability"] == "strictly_stable_supplied_real_poles"
             and model["causality"] == "proper_real_rational_by_construction", "Unsupported returned model realization", "numerical_failure")
    poles = np.array(request["pole_rates_rad_s"], dtype=float)
    residues = model["residues"]
    _require(isinstance(residues, list) and len(residues) == len(poles), "Invalid returned residue count", "numerical_failure")
    matrices = [model["direct"]] + residues
    for matrix in matrices:
        _require(isinstance(matrix, list) and len(matrix) == len(ports)
                 and all(isinstance(row, list) and len(row) == len(ports)
                         and all(type(v) in (int, float) for v in row) for row in matrix),
                 "Invalid returned real coefficient dimensions", "numerical_failure")
    coefficients = np.asarray(matrices, dtype=float)
    _require(np.isfinite(coefficients).all(), "Nonfinite returned coefficients", "numerical_failure")
    return poles, coefficients[0], coefficients[1:]


def _incident(time, waves, positions):
    result = []
    for port, (times, values) in enumerate(waves):
        index = positions[port]
        while index + 1 < len(times) and time >= times[index + 1]:
            index += 1
        positions[port] = index
        if time == times[index]:
            result.append(values[index])
        else:
            weight = (time - times[index]) / (times[index + 1] - times[index])
            _require(math.isfinite(weight) and 0 < weight < 1, "Unrepresentable interior waveform fraction", "numerical_failure")
            result.append((1-weight) * values[index] + weight * values[index + 1])
    return np.array(result)


def _advance(state, poles, interval, start, end):
    next_state = np.empty_like(state)
    for index, raw_pole in enumerate(poles):
        pole = float(raw_pole)
        z = pole * interval
        _require(z > 0, "Positive pole-time product underflows to zero", "numerical_failure")
        if math.isinf(z):
            inverse = (1 / pole) / interval
            # Both factors exceed one if their positive product overflows.
            # Scale a0 before division so a representable a0/z is not lost
            # when the inverse product itself underflows.
            next_state[index] = (start / pole) / interval + (1-inverse) * end
            continue
        q, w = math.exp(-z), -math.expm1(-z)
        if z < .01:
            v = z * (.5 + z * (-1/6 + z * (1/24 + z * (-1/120 + z * (1/720 + z * (-1/5040 + z/40320))))))
            _require(v > 0, "Ramp weight underflows supported precision", "numerical_failure")
            u = w - v
        else:
            inverse_weight = w / z
            u, v = inverse_weight - q, 1 - inverse_weight
        _require(u >= 0 and v >= 0, "Invalid exponential endpoint weights", "numerical_failure")
        next_state[index] = q * state[index] + u * start + v * end
    _require(np.isfinite(next_state).all(), "Nonfinite propagated state", "numerical_failure")
    return next_state


def _observe(time, incident, state, direct, residues, root_reference, ports):
    outgoing = direct @ incident + np.einsum("kij,kj->i", residues, state)
    voltage, current = root_reference * (incident + outgoing), (incident - outgoing) / root_reference
    _require(all(np.isfinite(array).all() for array in (incident, outgoing, voltage, current)),
             "Nonfinite output waves, voltage or current", "numerical_failure")
    return {"time_s": time, "incident_wave_sqrt_w_by_port": dict(zip(ports, incident.tolist())),
            "outgoing_wave_sqrt_w_by_port": dict(zip(ports, outgoing.tolist())),
            "port_voltage_v_by_port": dict(zip(ports, voltage.tolist())),
            "port_current_a_by_port": dict(zip(ports, current.tolist()))}


def run_rational_network_transient(request, *, cancel_check=None):
    """Fit internally, then propagate zero states through every PWL interval."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterTransientError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Rational network transient cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            ports, waves, grid, outputs, work = _prepare(frozen, size, poll)
            poll()
            fit = rational.fit_sparameter_rational(frozen["fit_request"], cancel_check=cancel_check)
            poll()
            poles, direct, residues = _model(fit, frozen["fit_request"], ports)
            state = np.zeros((len(poles), len(ports)))
            root_reference = math.sqrt(frozen["fit_request"]["source"]["reference_impedance_ohm"])
            positions, points = [0] * len(ports), []
            output_lookup = dict(zip(outputs, frozen["output_times_s"]))
            start = _incident(0., waves, positions)
            if 0. in output_lookup:
                points.append(_observe(output_lookup[0.], start, state, direct, residues, root_reference, ports))
            for left, right in zip(grid, grid[1:]):
                poll()
                end = _incident(right, waves, positions)
                state = _advance(state, poles, right-left, start, end)
                if right in output_lookup:
                    points.append(_observe(output_lookup[right], end, state, direct, residues, root_reference, ports))
                start = end
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": rational.sampling._digest(frozen), "fit_result": fit,
                      "incident_waves": frozen["incident_waves"], "output_times_s": frozen["output_times_s"],
                      "port_names": ports, "points": points, "final_state_sqrt_w": state.tolist(),
                      "diagnostics": {"integration_method": "exact_piecewise_linear_exponential", "interval_count": len(grid)-1,
                                      "estimated_work": work},
                      "limitations": ["Zero initial states and prescribed continuous PWL incident power waves; nonzero initial input gives direct feedthrough at 0+",
                                      "Inputs have units sqrt(W); voltage/current are instantaneous real wave quantities with current into the network, without RMS conversion",
                                      "Exact interval propagation of the fitted supplied-real-pole model only; fast corners may contain frequencies outside its evidenced fit band",
                                      "No general load termination or closed-loop interconnection; zero incident wave means a matched incoming boundary",
                                      "Floating-point time or weight collapse is rejected; no timestep refinement or hidden extrapolation",
                                      "Fit and transient remain experimental, without measured or production qualification"]}
            _require(len(rational.sampling._json(result)) <= _MAX_RESULT_BYTES, "Transient response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterTransientError:
        raise
    except rational.SParameterRationalError as error:
        raise SParameterTransientError(error.code.removeprefix("SPARAMETER_RATIONAL_"), str(error)) from error
    except rational.sampling.SParameterSamplingError as error:
        raise SParameterTransientError(error.code.removeprefix("SPARAMETER_SAMPLING_"), str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterTransientError("numerical_failure", f"Transient numerical failure: {error}") from error
