# SPDX-License-Identifier: Apache-2.0
"""Finite resistive Thevenin boundaries around an internally fitted wave model.

With current into the network, V+Rt*I=Vs gives a=Gamma*b+u,
u=c*Vs. Substituting b=D*a+C*x gives M*a=Gamma*C*x+u.
Solving M yields a=Q*x+H*u and x'=(A0+P*Q)*x+P*H*u.
The augmented exponential advances [x,u,delta_u], all in sqrt(W), over
each continuous PWL interval. It is exact for the admitted fitted model,
subject to floating-point arithmetic, without a numerical time step.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm

from . import sparameter_transient as prescribed

rational = prescribed.rational
REQUEST_CONTRACT = "spike/terminated-network-transient-request/v1"
RESULT_CONTRACT = "spike/terminated-network-transient-result/v1"
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_WORK = 100_000_000


class SParameterTerminatedError(ValueError):
    """Admission or computation failure, with no partial successful trajectory."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_TERMINATED_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterTerminatedError(code, message)


def _prepare(request, size, poll):
    rational.sampling._record(request, {"contract", "fit_request", "terminations", "output_times_s"}, "terminated request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported terminated network contract")
    source, frequencies, poles, _, _ = rational._prepare(request["fit_request"], len(rational.sampling._json(request["fit_request"])), poll)
    ports, reference = source["port_names"], source["reference_impedance_ohm"]
    n, k = len(ports), len(poles)
    states, augmented = n*k, n*(k+2)
    _require(states <= 32 and augmented <= 48, "Dynamic/augmented state limit is 32/48", "resource_limit")
    terms = request["terminations"]
    _require(isinstance(terms, list) and len(terms) == n, "Exactly one termination per source port required")
    outputs = request["output_times_s"]
    _require(isinstance(outputs, list) and 1 <= len(outputs) <= 1024, "Provide 1..1024 output times", "resource_limit")
    by_port, adapted, root = {}, [], math.sqrt(reference)
    for term in terms:
        rational.sampling._record(term, {"port_name", "resistance_ohm", "voltage_points"}, "termination")
        port = term["port_name"]
        _require(isinstance(port, str) and port in ports and port not in by_port, "Unknown or duplicate termination port")
        resistance = rational.sampling._number(term["resistance_ohm"], "termination resistance")
        _require(resistance >= 0, "Termination resistance must be nonnegative")
        scale = max(resistance, reference)
        r, z = resistance/scale, reference/scale
        gamma, c = (r-z)/(r+z), (z/(r+z))/root
        _require(math.isfinite(c) and c > 0, "Unrepresentable source normalization", "numerical_failure")
        points = term["voltage_points"]
        _require(isinstance(points, list) and 2 <= len(points) <= 1024, "Voltage waveforms require 2..1024 points", "resource_limit")
        converted, values = [], []
        for point in points:
            rational.sampling._record(point, {"time_s", "voltage_v"}, "voltage point")
            voltage = rational.sampling._number(point["voltage_v"], "source voltage")
            value = c*voltage
            _require(math.isfinite(value) and (voltage == 0 or value != 0), "Unrepresentable normalized source voltage", "numerical_failure")
            converted.append({"time_s": point["time_s"], "value_sqrt_w": value})
            values.append(voltage)
        by_port[port] = (gamma, c, ([float(p["time_s"]) for p in points], values))
        adapted.append({"port_name": port, "points": converted})
    admission = {"contract": prescribed.REQUEST_CONTRACT, "fit_request": request["fit_request"],
                 "incident_waves": adapted, "output_times_s": outputs}
    _, waves, grid, outputs, _ = prescribed._prepare(admission, size, poll)
    intervals = len(grid)-1
    durations = set(b-a for a, b in zip(grid, grid[1:]))
    _require(intervals <= 1024 and len(durations) <= 128, "At most 1024 intervals and 128 distinct durations supported", "resource_limit")
    m = 2*len(frequencies)
    work = m*(k+1)**2 + m*(k+1)*n*n + len(durations)*augmented**3 + intervals*(states*states+6*n*states+8*n*n)
    _require(work <= _MAX_WORK, "Aggregate fit/exponential/propagation work exceeds 100 million", "resource_limit")
    estimate = 6*size + 96*len(frequencies)*n*n + len(outputs)*(1024+1024*n) + 262144
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated terminated response exceeds 16 MiB", "resource_limit")
    return ports, waves, [by_port[p][2] for p in ports], grid, outputs, np.array([by_port[p][0] for p in ports]), np.array([by_port[p][1] for p in ports]), work


def _closure(poles, direct, residues, gamma):
    n = len(gamma)
    cmat = np.hstack(residues)
    pmat = np.vstack([p*np.eye(n) for p in poles])
    original = np.diag(np.repeat(-poles, n))
    loop = np.eye(n)-gamma[:, None]*direct
    singular = np.linalg.svd(loop, compute_uv=False)
    _require(singular[-1] >= 1e-10*max(1., singular[0]), "Singular or unresolved algebraic boundary loop", "ill_conditioned")
    condition = float(singular[0]/singular[-1])
    _require(condition <= 1e10, "Ill-conditioned algebraic boundary loop", "ill_conditioned")
    rhs = np.hstack((gamma[:, None]*cmat, np.eye(n)))
    solution = np.linalg.solve(loop, rhs)
    norm = rational._norm
    denominator = norm(loop)*norm(solution)+norm(rhs)
    _require(math.isfinite(denominator) and denominator > 0, "Unrepresentable algebraic residual scale", "numerical_failure")
    backward = norm(loop@solution-rhs)/denominator
    _require(math.isfinite(backward) and backward <= 1e-10, "Algebraic loop backward error exceeds tolerance", "numerical_failure")
    qmat, hmat = solution[:, :len(original)], solution[:, len(original):]
    feedback = pmat@qmat
    closed, forcing = original+feedback, pmat@hmat
    _require(not np.any((np.tile(hmat, (len(poles), 1)) != 0) & (forcing == 0)),
             "Closed-system forcing underflows supported precision", "numerical_failure")
    _require(all(np.isfinite(a).all() for a in (closed, forcing, solution)), "Nonfinite closed system", "numerical_failure")
    eigenvalues = np.linalg.eigvals(closed)
    margin = float(-np.max(eigenvalues.real))
    # The original construction scale detects unresolved cancellation in A0+PQ.
    scale = max(float(np.linalg.norm(a, 2)) for a in (closed, original, feedback))
    _require(math.isfinite(scale) and scale > 0, "Unrepresentable stability construction scale", "numerical_failure")
    relative = margin/scale
    _require(math.isfinite(relative) and margin > 0 and relative > 1e-10,
             "Closed system is unstable, marginal or numerically unresolved", "unstable_closed_system")
    return cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative


def run_terminated_network_transient(request, *, cancel_check=None):
    """Fit the source and solve finite resistive boundaries from zero states."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterTerminatedError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Terminated transient cancelled", "cancelled")

    try:
        poll()
        frozen, size = prescribed._snapshot(request)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            ports, waves, voltage_waves, grid, outputs, gamma, coefficients, work = _prepare(frozen, size, poll)
            poll()
            fit = rational.fit_sparameter_rational(frozen["fit_request"], cancel_check=cancel_check)
            poll()
            poles, direct, residues = prescribed._model(fit, frozen["fit_request"], ports)
            cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative = _closure(poles, direct, residues, gamma)
            n, count = len(ports), len(closed)
            root = math.sqrt(frozen["fit_request"]["source"]["reference_impedance_ohm"])
            state, transitions = np.zeros(count), {}
            positions, voltage_positions = [0]*n, [0]*n
            points, maximum_residual = [], 0.
            output_lookup = dict(zip(outputs, frozen["output_times_s"]))

            def observe(time, normalized, voltage):
                nonlocal maximum_residual
                incident = qmat@state+hmat@normalized
                outgoing = direct@incident+cmat@state
                port_voltage, current = root*(incident+outgoing), (incident-outgoing)/root
                _require(all(np.isfinite(a).all() for a in (state, normalized, voltage, incident, outgoing, port_voltage, current)), "Nonfinite trajectory", "numerical_failure")
                rhs = coefficients*voltage
                scale = max(rational._norm(incident), rational._norm(gamma*outgoing), rational._norm(rhs))
                residual = rational._norm(incident-gamma*outgoing-rhs)/scale if scale else 0.
                _require(math.isfinite(residual) and residual <= 1e-10, "Boundary wave residual exceeds tolerance", "numerical_failure")
                maximum_residual = max(maximum_residual, residual)
                if time in output_lookup:
                    row = {"time_s": output_lookup[time]}
                    for name, values in (("source_voltage_v", voltage), ("incident_wave_sqrt_w", incident),
                                         ("outgoing_wave_sqrt_w", outgoing), ("port_voltage_v", port_voltage), ("port_current_a", current)):
                        row[name+"_by_port"] = dict(zip(ports, values.tolist()))
                    points.append(row)

            start = prescribed._incident(0., waves, positions)
            observe(0., start, prescribed._incident(0., voltage_waves, voltage_positions))
            for left, right in zip(grid, grid[1:]):
                poll()
                duration = right-left
                if duration not in transitions:
                    generator = np.zeros((count+2*n, count+2*n))
                    generator[:count, :count], generator[:count, count:count+n] = duration*closed, duration*forcing
                    _require(not np.any((closed != 0) & (generator[:count, :count] == 0))
                             and not np.any((forcing != 0) & (generator[:count, count:count+n] == 0)),
                             "Time-system coefficients underflow supported precision", "numerical_failure")
                    generator[count:count+n, count+n:] = np.eye(n)
                    _require(np.isfinite(generator).all() and np.linalg.norm(generator, 2) <= 1e6,
                             "Dimensionless exponential generator exceeds supported norm", "resource_limit")
                    _require(np.any(generator[:count, :count] != 0), "Time-system product underflows", "numerical_failure")
                    transition = expm(generator)
                    _require(np.isfinite(transition).all(), "Nonfinite matrix exponential", "numerical_failure")
                    transitions[duration] = (transition[:count, :count], transition[:count, count:count+n]-transition[:count, count+n:], transition[:count, count+n:])
                    poll()
                end = prescribed._incident(right, waves, positions)
                evolution, start_weight, end_weight = transitions[duration]
                state = evolution@state+start_weight@start+end_weight@end
                observe(right, end, prescribed._incident(right, voltage_waves, voltage_positions))
                start = end
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": rational.sampling._digest(frozen), "fit_result": fit,
                      "terminations": frozen["terminations"], "output_times_s": frozen["output_times_s"], "port_names": ports,
                      "points": points, "final_state_sqrt_w": state.reshape(len(poles), n).tolist(),
                      "diagnostics": {"reflection_coefficients_by_port": dict(zip(ports, gamma.tolist())),
                                      "algebraic_loop_condition": condition, "algebraic_loop_backward_error": backward,
                                      "closed_system_stability_margin_per_s": margin, "closed_system_relative_stability_margin": relative,
                                      "maximum_boundary_relative_residual": maximum_residual, "interval_count": len(grid)-1,
                                      "unique_exponential_count": len(transitions), "estimated_work": work,
                                      "integration_method": "exact_piecewise_linear_augmented_exponential"},
                      "limitations": ["Zero initial fitted-model states; finite nonnegative resistive Thevenin terminations only",
                                      "Real instantaneous power waves in sqrt(W); port current is into the modeled network; no RMS conversion",
                                      "Exact continuous PWL propagation uses normalized forcing u=c*Vs and a dimensionless augmented exponential",
                                      "Algebraic loop inverse gain and conditioning are bounded; stability margin is relative to the original closed-system construction scale",
                                      "Numerical closed-system stability admission does not establish measured stability, source causality or physical passivity",
                                      "No open/infinite, reactive or nonlinear terminations; no accuracy claim outside the source fit band",
                                      "Floating-point time/normalization collapse and oversized generators are rejected; experimental and not production qualified"]}
            _require(len(rational.sampling._json(result)) <= _MAX_RESULT_BYTES, "Response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterTerminatedError:
        raise
    except (prescribed.SParameterTransientError, rational.SParameterRationalError, rational.sampling.SParameterSamplingError) as error:
        raise SParameterTerminatedError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterTerminatedError("numerical_failure", f"Terminated transient numerical failure: {error}") from error
