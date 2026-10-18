# SPDX-License-Identifier: Apache-2.0
"""Original mixed resistive/series-inductive boundaries for a fitted wave model.

For each positive L introduce q=sqrt(Z0)*I=a-b in sqrt(W). Then the
algebraic row is (I-D)*a=C*x+q; zero-L rows retain (I-Gamma*D)*a=
Gamma*C*x+c*Vs. Solving the combined rows gives a=Q*z+H*u, z=[x,q],
with u=Vs/sqrt(Z0) for inductors and u=c*Vs for resistors. The inductor
law V+R*I+L*I'=Vs gives q'=(Z0/L)*u-2*(Z0/L)*a+((Z0-R)/L)*q.
All augmented exponential coordinates [z,u,delta_u] have units sqrt(W).
Zero initial states and continuous PWL sources are prescribed explicitly.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm

from . import sparameter_terminated as resistive

prescribed = resistive.prescribed
rational = resistive.rational
REQUEST_CONTRACT = "spike/inductive-network-transient-request/v1"
RESULT_CONTRACT = "spike/inductive-network-transient-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterInductiveError(ValueError):
    """Failure without any successful partial trajectory."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_INDUCTIVE_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterInductiveError(code, message)


def _prepare(request, size, poll):
    rational.sampling._record(request, {"contract", "fit_request", "terminations", "output_times_s"}, "inductive request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported inductive network contract")
    terms = request["terminations"]
    _require(isinstance(terms, list) and 1 <= len(terms) <= 8, "Provide one termination per source port")
    adapted, properties = [], {}
    for term in terms:
        rational.sampling._record(term, {"port_name", "resistance_ohm", "inductance_h", "voltage_points"}, "inductive termination")
        resistance = rational.sampling._number(term["resistance_ohm"], "resistance")
        inductance = rational.sampling._number(term["inductance_h"], "inductance")
        _require(resistance >= 0 and inductance >= 0, "Resistance and inductance must be nonnegative")
        port = term["port_name"]
        _require(isinstance(port, str) and port not in properties, "Invalid or duplicate termination port")
        properties[port] = resistance, inductance
        # R=0 admission gives c=1/sqrt(Z0), exactly the inductive source normalization.
        adapted.append({"port_name": port, "resistance_ohm": 0. if inductance else resistance, "voltage_points": term["voltage_points"]})
    _require(any(v[1] > 0 for v in properties.values()), "At least one strictly positive inductance required")
    admission = {"contract": resistive.REQUEST_CONTRACT, "fit_request": request["fit_request"],
                 "terminations": adapted, "output_times_s": request["output_times_s"]}
    ports, waves, voltages, grid, outputs, gamma, _, _ = resistive._prepare(admission, size, poll)
    resistance = np.array([properties[p][0] for p in ports])
    inductance = np.array([properties[p][1] for p in ports])
    inductive = np.flatnonzero(inductance > 0)
    n, k = len(ports), len(request["fit_request"]["pole_rates_rad_s"])
    count, m = n*k+len(inductive), 2*len(request["fit_request"]["source"]["frequencies_hz"])
    augmented = count+2*n
    _require(count <= 32 and augmented <= 48, "Including inductors, state/augmented limits are 32/48", "resource_limit")
    durations = {b-a for a, b in zip(grid, grid[1:])}
    work = m*(k+1)**2+m*(k+1)*n*n+len(durations)*augmented**3+(len(grid)-1)*(count*count+8*n*count+12*n*n)
    _require(work <= _MAX_WORK, "Aggregate inductive transient work exceeds 100 million", "resource_limit")
    estimate = 6*size+96*(m//2)*n*n+len(outputs)*(1024+2048*n)+262144
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated inductive response exceeds 16 MiB", "resource_limit")
    return ports, waves, voltages, grid, outputs, gamma, resistance, inductance, inductive, work


def _closure(poles, direct, residues, gamma, resistance, inductance, inductive, reference):
    n, memory = len(gamma), len(poles)*len(gamma)
    count = memory+len(inductive)
    cmat = np.hstack((np.hstack(residues), np.zeros((n, len(inductive)))))
    multipliers = gamma.copy(); multipliers[inductive] = 1.
    loop = np.eye(n)-multipliers[:, None]*direct
    state_rhs = multipliers[:, None]*cmat
    input_rhs = np.eye(n); input_rhs[inductive, :] = 0.
    for j, port in enumerate(inductive): state_rhs[port, memory+j] = 1.
    rhs = np.hstack((state_rhs, input_rhs))
    singular = np.linalg.svd(loop, compute_uv=False)
    _require(singular[-1] >= 1e-10*max(1., singular[0]), "Singular or unresolved mixed boundary feedthrough", "ill_conditioned")
    condition = float(singular[0]/singular[-1])
    _require(condition <= 1e10, "Ill-conditioned mixed boundary feedthrough", "ill_conditioned")
    solution = np.linalg.solve(loop, rhs)
    norm = rational._norm
    denominator = norm(loop)*norm(solution)+norm(rhs)
    _require(math.isfinite(denominator) and denominator > 0, "Unrepresentable loop residual scale", "numerical_failure")
    backward = norm(loop@solution-rhs)/denominator
    _require(math.isfinite(backward) and backward <= 1e-10, "Mixed boundary solve residual exceeds tolerance", "numerical_failure")
    qmat, hmat = solution[:, :count], solution[:, count:]
    original, injection, direct_forcing = np.zeros((count, count)), np.zeros((count, n)), np.zeros((count, n))
    original[:memory, :memory] = np.diag(np.repeat(-poles, n))
    injection[:memory] = np.vstack([p*np.eye(n) for p in poles])
    for j, port in enumerate(inductive):
        rate = reference/float(inductance[port])
        damping = (reference-float(resistance[port]))/float(inductance[port])
        _require(math.isfinite(rate) and rate > 0 and math.isfinite(damping), "Unrepresentable inductive coefficients", "numerical_failure")
        _require(reference == resistance[port] or damping != 0, "Inductive damping coefficient underflows", "numerical_failure")
        original[memory+j, memory+j] = damping
        injection[memory+j, port] = -2*rate
        direct_forcing[memory+j, port] = rate
    feedback, driven = injection@qmat, injection@hmat
    # Every row of injection has one nonzero entry: underflow can be identified
    # before adding physically cancelling terms in the actual closed system.
    for row in range(count):
        port = row % n if row < memory else int(inductive[row-memory])
        _require(not np.any((qmat[port] != 0) & (feedback[row] == 0))
                 and not np.any((hmat[port] != 0) & (driven[row] == 0)), "Inductive closure product underflows", "numerical_failure")
    closed, forcing = original+feedback, direct_forcing+driven
    _require(all(np.isfinite(a).all() for a in (closed, forcing, solution)), "Nonfinite inductive closure", "numerical_failure")
    margin = float(-np.max(np.linalg.eigvals(closed).real))
    scale = max(float(np.linalg.norm(a, 2)) for a in (closed, original, feedback))
    _require(math.isfinite(scale) and scale > 0, "Invalid stability construction scale", "numerical_failure")
    relative = margin/scale
    _require(math.isfinite(relative) and margin > 0 and relative > 1e-10, "Connected model is unstable, marginal or unresolved", "unstable_closed_system")
    return cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative


def run_inductive_network_transient(request, *, cancel_check=None):
    """Fit internally, close mixed R/RL boundaries, propagate zero states."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterInductiveError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Inductive network transient cancelled", "cancelled")

    try:
        poll()
        frozen, size = prescribed._snapshot(request)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            ports, waves, voltages, grid, outputs, gamma, resistance, inductance, inductive, work = _prepare(frozen, size, poll)
            poll()
            fit = rational.fit_sparameter_rational(frozen["fit_request"], cancel_check=cancel_check)
            poll()
            poles, direct, residues = prescribed._model(fit, frozen["fit_request"], ports)
            reference = float(frozen["fit_request"]["source"]["reference_impedance_ohm"])
            cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative = _closure(poles, direct, residues, gamma, resistance, inductance, inductive, reference)
            n, memory, root = len(ports), len(poles)*len(ports), math.sqrt(reference)
            count = len(closed); state = np.zeros(count)
            inductive_ports = [ports[i] for i in inductive]
            positions, voltage_positions, transitions, points = [0]*n, [0]*n, {}, []
            output_lookup = dict(zip(outputs, frozen["output_times_s"]))
            max_boundary, max_state = 0., 0.

            def observe(time, normalized, voltage):
                nonlocal max_boundary, max_state
                incident = qmat@state+hmat@normalized
                outgoing = direct@incident+cmat@state
                actual_voltage, current = root*(incident+outgoing), (incident-outgoing)/root
                derivative = closed@state+forcing@normalized
                inductor_current, current_derivative = state[memory:]/root, derivative[memory:]/root
                inductive_drop = np.zeros(n); inductive_drop[inductive] = inductance[inductive]*current_derivative
                resistive_drop = resistance*current
                resistor_power = resistive_drop*current
                inductor_energy = ((inductance[inductive]*inductor_current)*inductor_current)/2
                _require(not np.any((resistance > 0) & (current != 0) & (resistor_power == 0))
                         and not np.any((inductor_current != 0) & (inductor_energy == 0)),
                         "Termination power or energy underflows", "numerical_failure")
                boundary = actual_voltage+resistive_drop+inductive_drop-voltage
                _require(all(np.isfinite(a).all() for a in (state, incident, outgoing, actual_voltage, current, derivative, inductor_current, current_derivative, boundary, resistor_power, inductor_energy)), "Nonfinite inductive trajectory", "numerical_failure")
                norm = rational._norm
                boundary_scale = max(norm(actual_voltage), norm(resistive_drop), norm(inductive_drop), norm(voltage))
                boundary_error = norm(boundary)/boundary_scale if boundary_scale else 0.
                current_scale = max(norm(incident[inductive]), norm(outgoing[inductive]), norm(state[memory:]))
                state_error = norm(incident[inductive]-outgoing[inductive]-state[memory:])/current_scale if current_scale else 0.
                _require(math.isfinite(boundary_error) and boundary_error <= 1e-10 and math.isfinite(state_error) and state_error <= 1e-10,
                         "Inductor current or physical boundary residual exceeds tolerance", "numerical_failure")
                max_boundary, max_state = max(max_boundary, boundary_error), max(max_state, state_error)
                if time in output_lookup:
                    row = {"time_s": output_lookup[time]}
                    for key, array in (("source_voltage_v", voltage), ("incident_wave_sqrt_w", incident), ("outgoing_wave_sqrt_w", outgoing),
                                       ("port_voltage_v", actual_voltage), ("port_current_a", current), ("boundary_residual_v", boundary),
                                       ("termination_resistor_power_w", resistor_power)):
                        row[key+"_by_port"] = dict(zip(ports, array.tolist()))
                    row["inductor_current_a_by_port"] = dict(zip(inductive_ports, inductor_current.tolist()))
                    row["inductor_current_derivative_a_per_s_by_port"] = dict(zip(inductive_ports, current_derivative.tolist()))
                    row["inductor_energy_j_by_port"] = dict(zip(inductive_ports, inductor_energy.tolist()))
                    points.append(row)

            start = prescribed._incident(0., waves, positions)
            observe(0., start, prescribed._incident(0., voltages, voltage_positions))
            for left, right in zip(grid, grid[1:]):
                poll(); duration = right-left
                if duration not in transitions:
                    generator = np.zeros((count+2*n, count+2*n))
                    generator[:count, :count] = duration*closed
                    generator[:count, count:count+n] = duration*forcing
                    generator[count:count+n, count+n:] = np.eye(n)
                    _require(not np.any((closed != 0) & (generator[:count, :count] == 0))
                             and not np.any((forcing != 0) & (generator[:count, count:count+n] == 0)), "Interval coefficients underflow", "numerical_failure")
                    _require(np.isfinite(generator).all() and np.linalg.norm(generator, 2) <= 1e6, "Dimensionless generator exceeds norm limit", "resource_limit")
                    transition = expm(generator)
                    _require(np.isfinite(transition).all(), "Nonfinite inductive exponential", "numerical_failure")
                    transitions[duration] = transition[:count, :count], transition[:count, count:count+n]-transition[:count, count+n:], transition[:count, count+n:]
                    poll()
                end = prescribed._incident(right, waves, positions)
                evolution, start_weight, end_weight = transitions[duration]
                state = evolution@state+start_weight@start+end_weight@end
                observe(right, end, prescribed._incident(right, voltages, voltage_positions))
                start = end
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": rational.sampling._digest(frozen), "fit_result": fit, "terminations": frozen["terminations"],
                      "output_times_s": frozen["output_times_s"], "port_names": ports, "inductive_port_names": inductive_ports,
                      "points": points, "final_state_sqrt_w": state[:memory].reshape(len(poles), n).tolist(),
                      "final_inductor_current_a_by_port": dict(zip(inductive_ports, (state[memory:]/root).tolist())),
                      "diagnostics": {"algebraic_loop_condition": condition, "algebraic_loop_backward_error": backward,
                                      "closed_system_stability_margin_per_s": margin, "closed_system_relative_stability_margin": relative,
                                      "maximum_boundary_relative_residual": max_boundary, "maximum_current_state_relative_residual": max_state,
                                      "interval_count": len(grid)-1, "unique_exponential_count": len(transitions), "estimated_work": work,
                                      "integration_method": "exact_piecewise_linear_augmented_exponential"},
                      "limitations": ["Zero initial fitted-network and inductor states; continuous supplied PWL voltages and finite nonnegative series R/L only",
                                      "At least one positive L; positive-L current states are source-port ordered; zero-L ports use resistive algebraic boundaries",
                                      "Port current is into the fitted network; V+R*I+L*dI/dt=Vs and q=sqrt(Z0)*I; instantaneous waves without RMS conversion",
                                      "Exact PWL exponential propagation of the fitted model, with all augmented coordinates in sqrt(W)",
                                      "Reported R*I^2 and L*I^2/2 are instantaneous supplied-termination power/energy, not integrated heating or physical storage of an arbitrary fitted network",
                                      "Singular feedthrough, unresolved stable margins, marginal modes and unsupported floating-point ranges reject without regularization",
                                      "No nonlinear, capacitive boundary, open/infinite termination or general circuit topology; no source-band extrapolation accuracy claim",
                                      "Synthetic verification and numerical stability do not establish measured passivity, causality or production qualification"]}
            _require(len(rational.sampling._json(result)) <= _MAX_RESULT_BYTES, "Inductive result exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterInductiveError:
        raise
    except (resistive.SParameterTerminatedError, prescribed.SParameterTransientError, rational.SParameterRationalError, rational.sampling.SParameterSamplingError) as error:
        raise SParameterInductiveError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterInductiveError("numerical_failure", f"Inductive numerical failure: {error}") from error
