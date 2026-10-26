# SPDX-License-Identifier: Apache-2.0
"""Original series-R source with shunt-C boundary around a fitted wave model.

For positive C introduce v=V/sqrt(Z0)=a+b in sqrt(W). The algebraic row
is (I+D)*a=v-Cmodel*x; zero-C rows retain (I-Gamma*D)*a=Gamma*Cmodel*x+c*Vs.
Solving gives a=Q*z+H*u, z=[x,v], with u=Vs/sqrt(Z0) on capacitive rows.
KCL (Vs-V)/R=Inet+C*V' gives v'=alpha*u+(beta-alpha)*v-2*beta*a,
alpha=1/(R*C), beta=1/(Z0*C). All augmented coordinates [z,u,delta_u]
have units sqrt(W). Zero initial states and continuous PWL sources are explicit.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm

from . import sparameter_terminated as resistive

prescribed = resistive.prescribed
rational = resistive.rational
REQUEST_CONTRACT = "spike/capacitive-network-transient-request/v1"
RESULT_CONTRACT = "spike/capacitive-network-transient-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterCapacitiveError(ValueError):
    """Failure without any successful partial trajectory."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_CAPACITIVE_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterCapacitiveError(code, message)


def _prepare(request, size, poll):
    rational.sampling._record(request, {"contract", "fit_request", "terminations", "output_times_s"}, "capacitive request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported capacitive network contract")
    terms = request["terminations"]
    _require(isinstance(terms, list) and 1 <= len(terms) <= 8, "Provide one termination per source port")
    adapted, properties = [], {}
    for term in terms:
        rational.sampling._record(term, {"port_name", "resistance_ohm", "capacitance_f", "voltage_points"}, "capacitive termination")
        resistance = rational.sampling._number(term["resistance_ohm"], "resistance")
        capacitance = rational.sampling._number(term["capacitance_f"], "capacitance")
        _require(resistance >= 0 and capacitance >= 0, "Resistance and capacitance must be nonnegative")
        _require(capacitance == 0 or resistance > 0, "Positive shunt capacitance requires strictly positive source resistance")
        port = term["port_name"]
        _require(isinstance(port, str) and port not in properties, "Invalid or duplicate termination port")
        properties[port] = resistance, capacitance
        # R=0 admission gives c=1/sqrt(Z0), exactly the capacitive source normalization.
        adapted.append({"port_name": port, "resistance_ohm": 0. if capacitance else resistance, "voltage_points": term["voltage_points"]})
    _require(any(v[1] > 0 for v in properties.values()), "At least one strictly positive capacitance required")
    admission = {"contract": resistive.REQUEST_CONTRACT, "fit_request": request["fit_request"],
                 "terminations": adapted, "output_times_s": request["output_times_s"]}
    ports, waves, voltages, grid, outputs, gamma, _, _ = resistive._prepare(admission, size, poll)
    resistance = np.array([properties[p][0] for p in ports])
    capacitance = np.array([properties[p][1] for p in ports])
    capacitive = np.flatnonzero(capacitance > 0)
    n, k = len(ports), len(request["fit_request"]["pole_rates_rad_s"])
    count, m = n*k+len(capacitive), 2*len(request["fit_request"]["source"]["frequencies_hz"])
    augmented = count+2*n
    _require(count <= 32 and augmented <= 48, "Including capacitors, state/augmented limits are 32/48", "resource_limit")
    durations = {b-a for a, b in zip(grid, grid[1:])}
    work = m*(k+1)**2+m*(k+1)*n*n+len(durations)*augmented**3+(len(grid)-1)*(count*count+8*n*count+12*n*n)
    _require(work <= _MAX_WORK, "Aggregate capacitive transient work exceeds 100 million", "resource_limit")
    estimate = 6*size+96*(m//2)*n*n+len(outputs)*(1024+2048*n)+262144
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated capacitive response exceeds 16 MiB", "resource_limit")
    return ports, waves, voltages, grid, outputs, gamma, resistance, capacitance, capacitive, work


def _closure(poles, direct, residues, gamma, resistance, capacitance, capacitive, reference):
    n, memory = len(gamma), len(poles)*len(gamma)
    count = memory+len(capacitive)
    cmat = np.hstack((np.hstack(residues), np.zeros((n, len(capacitive)))))
    multipliers = gamma.copy(); multipliers[capacitive] = -1.
    loop = np.eye(n)-multipliers[:, None]*direct
    state_rhs = multipliers[:, None]*cmat
    input_rhs = np.eye(n); input_rhs[capacitive, :] = 0.
    for j, port in enumerate(capacitive): state_rhs[port, memory+j] = 1.
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
    for j, port in enumerate(capacitive):
        beta = (1/reference)/float(capacitance[port])
        alpha = (1/float(resistance[port]))/float(capacitance[port])
        _require(math.isfinite(beta) and beta > 0 and math.isfinite(alpha) and alpha > 0,
                 "Unrepresentable capacitive coefficients", "numerical_failure")
        original[memory+j, memory+j] = beta-alpha
        injection[memory+j, port] = -2*beta
        direct_forcing[memory+j, port] = alpha
    feedback, driven = injection@qmat, injection@hmat
    # Every row of injection has one nonzero entry: underflow can be identified
    # before adding physically cancelling terms in the actual closed system.
    for row in range(count):
        port = row % n if row < memory else int(capacitive[row-memory])
        _require(not np.any((qmat[port] != 0) & (feedback[row] == 0))
                 and not np.any((hmat[port] != 0) & (driven[row] == 0)), "Capacitive closure product underflows", "numerical_failure")
    closed, forcing = original+feedback, direct_forcing+driven
    _require(all(np.isfinite(a).all() for a in (closed, forcing, solution)), "Nonfinite capacitive closure", "numerical_failure")
    margin = float(-np.max(np.linalg.eigvals(closed).real))
    scale = max(float(np.linalg.norm(a, 2)) for a in (closed, original, feedback))
    _require(math.isfinite(scale) and scale > 0, "Invalid stability construction scale", "numerical_failure")
    relative = margin/scale
    _require(math.isfinite(relative) and margin > 0 and relative > 1e-10, "Connected model is unstable, marginal or unresolved", "unstable_closed_system")
    return cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative


def run_capacitive_network_transient(request, *, cancel_check=None):
    """Fit internally, close mixed R/shunt-C boundaries, propagate zero states."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterCapacitiveError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Capacitive network transient cancelled", "cancelled")

    try:
        poll()
        frozen, size = prescribed._snapshot(request)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            ports, waves, voltages, grid, outputs, gamma, resistance, capacitance, capacitive, work = _prepare(frozen, size, poll)
            poll()
            fit = rational.fit_sparameter_rational(frozen["fit_request"], cancel_check=cancel_check)
            poll()
            poles, direct, residues = prescribed._model(fit, frozen["fit_request"], ports)
            reference = float(frozen["fit_request"]["source"]["reference_impedance_ohm"])
            cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative = _closure(poles, direct, residues, gamma, resistance, capacitance, capacitive, reference)
            n, memory, root = len(ports), len(poles)*len(ports), math.sqrt(reference)
            count = len(closed); state = np.zeros(count)
            capacitive_ports = [ports[i] for i in capacitive]
            positions, voltage_positions, transitions, points = [0]*n, [0]*n, {}, []
            output_lookup = dict(zip(outputs, frozen["output_times_s"]))
            max_boundary, max_state = 0., 0.

            def observe(time, normalized, voltage):
                nonlocal max_boundary, max_state
                incident = qmat@state+hmat@normalized
                outgoing = direct@incident+cmat@state
                actual_voltage, current = root*(incident+outgoing), (incident-outgoing)/root
                derivative = closed@state+forcing@normalized
                capacitor_voltage, voltage_derivative = root*state[memory:], root*derivative[memory:]
                capacitor_current = np.zeros(n); capacitor_current[capacitive] = capacitance[capacitive]*voltage_derivative
                source_current = current.copy()
                finite_resistance = resistance > 0
                voltage_drop = voltage[finite_resistance]-actual_voltage[finite_resistance]
                source_current[finite_resistance] = voltage_drop/resistance[finite_resistance]
                _require(not np.any((voltage_drop != 0) & (source_current[finite_resistance] == 0))
                         and not np.any((voltage_derivative != 0) & (capacitor_current[capacitive] == 0)),
                         "Boundary current underflows", "numerical_failure")
                resistor_power = (resistance*source_current)*source_current
                capacitor_energy = ((capacitance[capacitive]*capacitor_voltage)*capacitor_voltage)/2
                _require(not np.any(finite_resistance & (source_current != 0) & (resistor_power == 0))
                         and not np.any((capacitor_voltage != 0) & (capacitor_energy == 0)),
                         "Termination power or energy underflows", "numerical_failure")
                boundary = current+capacitor_current-source_current
                _require(all(np.isfinite(a).all() for a in (state, incident, outgoing, actual_voltage, current, derivative, capacitor_voltage, voltage_derivative, source_current, boundary, resistor_power, capacitor_energy)), "Nonfinite capacitive trajectory", "numerical_failure")
                norm = rational._norm
                boundary_scale = max(norm(current), norm(capacitor_current), norm(source_current))
                boundary_error = norm(boundary)/boundary_scale if boundary_scale else 0.
                voltage_scale = max(norm(incident[capacitive]), norm(outgoing[capacitive]), norm(state[memory:]))
                state_error = norm(incident[capacitive]+outgoing[capacitive]-state[memory:])/voltage_scale if voltage_scale else 0.
                # Also verify ideal R=C=0 voltage rows; KCL there defines Isource.
                algebraic_rhs = normalized.copy(); algebraic_rhs[capacitive] = state[memory:]
                algebraic_scale = max(norm(incident), norm(gamma*outgoing), norm(algebraic_rhs))
                algebraic_error = norm(incident-gamma*outgoing-algebraic_rhs)/algebraic_scale if algebraic_scale else 0.
                boundary_error = max(boundary_error, algebraic_error)
                _require(math.isfinite(boundary_error) and boundary_error <= 1e-10 and math.isfinite(state_error) and state_error <= 1e-10,
                         "Capacitor voltage or physical/algebraic boundary residual exceeds tolerance", "numerical_failure")
                max_boundary, max_state = max(max_boundary, boundary_error), max(max_state, state_error)
                if time in output_lookup:
                    row = {"time_s": output_lookup[time]}
                    for key, array in (("source_voltage_v", voltage), ("incident_wave_sqrt_w", incident), ("outgoing_wave_sqrt_w", outgoing),
                                       ("port_voltage_v", actual_voltage), ("port_current_a", current), ("boundary_residual_a", boundary),
                                       ("source_current_a", source_current),
                                       ("termination_resistor_power_w", resistor_power)):
                        row[key+"_by_port"] = dict(zip(ports, array.tolist()))
                    row["capacitor_voltage_v_by_port"] = dict(zip(capacitive_ports, capacitor_voltage.tolist()))
                    row["capacitor_voltage_derivative_v_per_s_by_port"] = dict(zip(capacitive_ports, voltage_derivative.tolist()))
                    row["capacitor_energy_j_by_port"] = dict(zip(capacitive_ports, capacitor_energy.tolist()))
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
                    _require(np.isfinite(transition).all(), "Nonfinite capacitive exponential", "numerical_failure")
                    transitions[duration] = transition[:count, :count], transition[:count, count:count+n]-transition[:count, count+n:], transition[:count, count+n:]
                    poll()
                end = prescribed._incident(right, waves, positions)
                evolution, start_weight, end_weight = transitions[duration]
                state = evolution@state+start_weight@start+end_weight@end
                observe(right, end, prescribed._incident(right, voltages, voltage_positions))
                start = end
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": rational.sampling._digest(frozen), "fit_result": fit, "terminations": frozen["terminations"],
                      "output_times_s": frozen["output_times_s"], "port_names": ports, "capacitive_port_names": capacitive_ports,
                      "points": points, "final_state_sqrt_w": state[:memory].reshape(len(poles), n).tolist(),
                      "final_capacitor_voltage_v_by_port": dict(zip(capacitive_ports, (root*state[memory:]).tolist())),
                      "diagnostics": {"algebraic_loop_condition": condition, "algebraic_loop_backward_error": backward,
                                      "closed_system_stability_margin_per_s": margin, "closed_system_relative_stability_margin": relative,
                                      "maximum_boundary_relative_residual": max_boundary, "maximum_voltage_state_relative_residual": max_state,
                                      "interval_count": len(grid)-1, "unique_exponential_count": len(transitions), "estimated_work": work,
                                      "integration_method": "exact_piecewise_linear_augmented_exponential"},
                      "limitations": ["Zero initial fitted-network and capacitor states; continuous PWL voltages with series source resistance and shunt capacitance",
                                      "Positive C requires positive finite R; zero-C ports use resistive algebraic boundaries, including ideal voltage sources at zero R",
                                      "Current into network satisfies Inet+C*dV/dt=Isource; Isource=(Vs-V)/R for positive R and Isource=Inet for zero R/C",
                                      "Boundary diagnostic checks physical KCL and mixed wave algebra; zero R/C ideal voltage equality is checked separately from its defining source-current KCL",
                                      "Capacitor voltage states are source-port ordered; V=sqrt(Z0)*v; instantaneous power waves without RMS conversion",
                                      "Exact PWL exponential propagation of the fitted model, with all augmented coordinates in sqrt(W)",
                                      "Reported R*Isource^2 and C*V^2/2 are instantaneous supplied-termination power/energy, not integrated heating or physical storage of an arbitrary fitted network",
                                      "Singular feedthrough, unresolved stable margins, marginal modes and unsupported floating-point ranges reject without regularization",
                                      "No nonlinear, inductive boundary, open/infinite termination or general circuit topology; no source-band extrapolation accuracy claim",
                                      "Synthetic verification and numerical stability do not establish measured passivity, causality or production qualification"]}
            _require(len(rational.sampling._json(result)) <= _MAX_RESULT_BYTES, "Capacitive result exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterCapacitiveError:
        raise
    except (resistive.SParameterTerminatedError, prescribed.SParameterTransientError, rational.SParameterRationalError, rational.sampling.SParameterSamplingError) as error:
        raise SParameterCapacitiveError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterCapacitiveError("numerical_failure", f"Capacitive numerical failure: {error}") from error
