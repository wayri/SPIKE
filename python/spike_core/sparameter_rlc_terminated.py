# SPDX-License-Identifier: Apache-2.0
"""Original unified series-R/L source and shunt-C fitted-network boundary.

State z=[x,q,v], q=sqrt(Z0)*Isource on L ports, v=V/sqrt(Z0) on C ports.
C rows impose a+b=v, L-only rows a-b=q, and pure-R rows a-Gamma*b=c*Vs.
With b=D*a+Cm*x one conditioned solve gives a=Q*z+H*u. Dynamic-port
u=Vs/sqrt(Z0); pure-R u=c*Vs. For simultaneous L/C, q'=(Z0/L)(u-v)
-(R/L)q and v'=(q+v-2a)/(Z0*C). L-only and C-only rows use the
corresponding eliminated-voltage/current laws. Continuous PWL inputs are
propagated through [z,u,delta_u] in sqrt(W) by a dimensionless exponential.
KVL/KCL use source current, distinguished from fitted-network current.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm

from . import sparameter_terminated as resistive

prescribed = resistive.prescribed
rational = resistive.rational
REQUEST_CONTRACT = "spike/rlc-network-transient-request/v1"
RESULT_CONTRACT = "spike/rlc-network-transient-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterRlcError(ValueError):
    """Failure without any successful partial trajectory."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_RLC_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterRlcError(code, message)


def _prepare(request, size, poll):
    rational.sampling._record(request, {"contract", "fit_request", "terminations", "output_times_s"}, "RLC request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported RLC network contract")
    terms = request["terminations"]
    _require(isinstance(terms, list) and 1 <= len(terms) <= 8, "Provide one termination per source port")
    adapted, properties = [], {}
    for term in terms:
        rational.sampling._record(term, {"port_name", "resistance_ohm", "inductance_h", "capacitance_f", "voltage_points"}, "RLC termination")
        resistance = rational.sampling._number(term["resistance_ohm"], "resistance")
        inductance = rational.sampling._number(term["inductance_h"], "inductance")
        capacitance = rational.sampling._number(term["capacitance_f"], "capacitance")
        _require(resistance >= 0 and inductance >= 0 and capacitance >= 0, "R/L/C must be nonnegative")
        _require(capacitance == 0 or inductance > 0 or resistance > 0, "C-only boundary requires strictly positive resistance")
        port = term["port_name"]
        _require(isinstance(port, str) and port not in properties, "Invalid or duplicate termination port")
        properties[port] = resistance, inductance, capacitance
        # R=0 admission gives the dynamic-port normalization u=Vs/sqrt(Z0).
        adapted.append({"port_name": port, "resistance_ohm": 0. if inductance or capacitance else resistance, "voltage_points": term["voltage_points"]})
    _require(any(v[1] > 0 for v in properties.values()) and any(v[2] > 0 for v in properties.values()), "At least one positive L and one positive C required")
    admission = {"contract": resistive.REQUEST_CONTRACT, "fit_request": request["fit_request"],
                 "terminations": adapted, "output_times_s": request["output_times_s"]}
    ports, waves, voltages, grid, outputs, gamma, _, _ = resistive._prepare(admission, size, poll)
    resistance = np.array([properties[p][0] for p in ports])
    inductance = np.array([properties[p][1] for p in ports])
    capacitance = np.array([properties[p][2] for p in ports])
    inductive = np.flatnonzero(inductance > 0)
    capacitive = np.flatnonzero(capacitance > 0)
    n, k = len(ports), len(request["fit_request"]["pole_rates_rad_s"])
    count, m = n*k+len(inductive)+len(capacitive), 2*len(request["fit_request"]["source"]["frequencies_hz"])
    augmented = count+2*n
    _require(count <= 32 and augmented <= 48, "Including L and C, state/augmented limits are 32/48", "resource_limit")
    durations = {b-a for a, b in zip(grid, grid[1:])}
    work = m*(k+1)**2+m*(k+1)*n*n+len(durations)*augmented**3+(len(grid)-1)*(count*count+12*n*count+16*n*n)
    _require(work <= _MAX_WORK, "Aggregate RLC transient work exceeds 100 million", "resource_limit")
    estimate = 6*size+96*(m//2)*n*n+len(outputs)*(1024+3072*n)+262144
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated RLC response exceeds 16 MiB", "resource_limit")
    return ports, waves, voltages, grid, outputs, gamma, resistance, inductance, capacitance, inductive, capacitive, work


def _closure(poles, direct, residues, gamma, resistance, inductance, capacitance, inductive, capacitive, reference):
    n, memory = len(gamma), len(poles)*len(gamma)
    count = memory+len(inductive)+len(capacitive)
    qindices = {int(port): memory+j for j, port in enumerate(inductive)}
    vindices = {int(port): memory+len(inductive)+j for j, port in enumerate(capacitive)}
    cmat = np.hstack((np.hstack(residues), np.zeros((n, len(inductive)+len(capacitive)))))
    multipliers = gamma.copy(); multipliers[inductive] = 1.; multipliers[capacitive] = -1.
    loop = np.eye(n)-multipliers[:, None]*direct
    state_rhs = multipliers[:, None]*cmat
    input_rhs = np.eye(n); input_rhs[inductive, :] = 0.; input_rhs[capacitive, :] = 0.
    for port in range(n):
        if port in vindices: state_rhs[port, vindices[port]] = 1.
        elif port in qindices: state_rhs[port, qindices[port]] = 1.
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
    for port, index in qindices.items():
        rate = reference/float(inductance[port])
        damping = float(resistance[port])/float(inductance[port])
        _require(math.isfinite(rate) and rate > 0 and math.isfinite(damping)
                 and (resistance[port] == 0 or damping > 0), "Unrepresentable inductive coefficients", "numerical_failure")
        direct_forcing[index, port] = rate
        if port in vindices:
            original[index, index] = -damping
            original[index, vindices[port]] = -rate
        else:
            original[index, index] = (reference-float(resistance[port]))/float(inductance[port])
            _require(reference == resistance[port] or original[index, index] != 0, "Inductive coefficient underflows", "numerical_failure")
            injection[index, port] = -2*rate
    for port, index in vindices.items():
        beta = (1/reference)/float(capacitance[port])
        _require(math.isfinite(beta) and beta > 0, "Unrepresentable capacitive coefficient", "numerical_failure")
        injection[index, port] = -2*beta
        if port in qindices:
            original[index, index] = beta
            original[index, qindices[port]] = beta
        else:
            alpha = (1/float(resistance[port]))/float(capacitance[port])
            _require(math.isfinite(alpha) and alpha > 0, "Unrepresentable RC coefficient", "numerical_failure")
            original[index, index] = beta-alpha
            direct_forcing[index, port] = alpha
    feedback, driven = injection@qmat, injection@hmat
    # Every nonzero injection row has one entry: underflow can be identified
    # before adding physically cancelling terms in the actual closed system.
    for row in range(count):
        nonzero = np.flatnonzero(injection[row])
        if not len(nonzero): continue
        port = int(nonzero[0])
        _require(not np.any((qmat[port] != 0) & (feedback[row] == 0))
                 and not np.any((hmat[port] != 0) & (driven[row] == 0)), "RLC closure product underflows", "numerical_failure")
    closed, forcing = original+feedback, direct_forcing+driven
    _require(all(np.isfinite(a).all() for a in (closed, forcing, solution)), "Nonfinite RLC closure", "numerical_failure")
    margin = float(-np.max(np.linalg.eigvals(closed).real))
    scale = max(float(np.linalg.norm(a, 2)) for a in (closed, original, feedback))
    _require(math.isfinite(scale) and scale > 0, "Invalid stability construction scale", "numerical_failure")
    relative = margin/scale
    _require(math.isfinite(relative) and margin > 0 and relative > 1e-10, "Connected model is unstable, marginal or unresolved", "unstable_closed_system")
    return cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative


def run_rlc_network_transient(request, *, cancel_check=None):
    """Fit internally, close series-R/L and shunt-C boundaries, propagate zero states."""
    return _run(request, cancel_check=cancel_check)


def _run(request, *, cancel_check=None, initial_state=None, interval_observer=None):
    """Shared propagation; optional normalized states are private to v2 admission."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    _require(interval_observer is None or callable(interval_observer), "interval_observer must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterRlcError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "RLC network transient cancelled", "cancelled")

    try:
        poll()
        frozen, size = prescribed._snapshot(request)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            ports, waves, voltages, grid, outputs, gamma, resistance, inductance, capacitance, inductive, capacitive, work = _prepare(frozen, size, poll)
            poll()
            fit = rational.fit_sparameter_rational(frozen["fit_request"], cancel_check=cancel_check)
            poll()
            poles, direct, residues = prescribed._model(fit, frozen["fit_request"], ports)
            reference = float(frozen["fit_request"]["source"]["reference_impedance_ohm"])
            cmat, qmat, hmat, closed, forcing, condition, backward, margin, relative = _closure(poles, direct, residues, gamma, resistance, inductance, capacitance, inductive, capacitive, reference)
            n, memory, root = len(ports), len(poles)*len(ports), math.sqrt(reference)
            count = len(closed)
            state = np.zeros(count) if initial_state is None else np.array(initial_state, dtype=float, copy=True)
            _require(state.shape == (count,) and np.isfinite(state).all(), "Invalid normalized initial state", "invalid_request")
            qslice, vslice = slice(memory, memory+len(inductive)), slice(memory+len(inductive), count)
            inductive_ports = [ports[i] for i in inductive]
            capacitive_ports = [ports[i] for i in capacitive]
            positions, voltage_positions, transitions, points = [0]*n, [0]*n, {}, []
            output_lookup = dict(zip(outputs, frozen["output_times_s"]))
            max_boundary, max_current_state, max_voltage_state = 0., 0., 0.
            observer_context = {"closed": closed, "forcing": forcing, "qmat": qmat, "hmat": hmat, "direct": direct, "cmat": cmat,
                                "ports": tuple(ports), "reference": reference, "resistance": resistance, "inductance": inductance,
                                "capacitance": capacitance, "inductive": inductive, "capacitive": capacitive,
                                "network_states": memory, "grid": tuple(grid), "estimated_work": work, "output_count": len(outputs),
                                "fit_frequency_count": len(frozen["fit_request"]["source"]["frequencies_hz"])} if interval_observer is not None else None

            def observe(time, normalized, voltage):
                nonlocal max_boundary, max_current_state, max_voltage_state
                incident = qmat@state+hmat@normalized
                outgoing = direct@incident+cmat@state
                actual_voltage, current = root*(incident+outgoing), (incident-outgoing)/root
                derivative = closed@state+forcing@normalized
                inductor_current, current_derivative = state[qslice]/root, derivative[qslice]/root
                capacitor_voltage, voltage_derivative = root*state[vslice], root*derivative[vslice]
                capacitor_current = np.zeros(n); capacitor_current[capacitive] = capacitance[capacitive]*voltage_derivative
                source_current = current.copy()
                algebraic_resistance = (resistance > 0) & (inductance == 0)
                voltage_drop = voltage[algebraic_resistance]-actual_voltage[algebraic_resistance]
                source_current[algebraic_resistance] = voltage_drop/resistance[algebraic_resistance]
                source_current[inductive] = inductor_current
                _require(not np.any((voltage_drop != 0) & (source_current[algebraic_resistance] == 0))
                         and not np.any((voltage_derivative != 0) & (capacitor_current[capacitive] == 0)),
                         "Boundary current underflows", "numerical_failure")
                resistor_power = (resistance*source_current)*source_current
                capacitor_energy = ((capacitance[capacitive]*capacitor_voltage)*capacitor_voltage)/2
                inductor_energy = ((inductance[inductive]*inductor_current)*inductor_current)/2
                _require(not np.any((resistance > 0) & (source_current != 0) & (resistor_power == 0))
                         and not np.any((capacitor_voltage != 0) & (capacitor_energy == 0))
                         and not np.any((inductor_current != 0) & (inductor_energy == 0)),
                         "Termination power or energy underflows", "numerical_failure")
                boundary_current = current+capacitor_current-source_current
                resistive_drop = resistance*source_current
                inductive_drop = np.zeros(n); inductive_drop[inductive] = inductance[inductive]*current_derivative
                _require(not np.any((current_derivative != 0) & (inductive_drop[inductive] == 0)), "Inductive voltage underflows", "numerical_failure")
                boundary_voltage = voltage-actual_voltage-resistive_drop-inductive_drop
                _require(all(np.isfinite(a).all() for a in (state, incident, outgoing, actual_voltage, current, derivative, capacitor_voltage, voltage_derivative,
                         source_current, boundary_current, boundary_voltage, resistor_power, capacitor_energy, inductor_energy, current_derivative)), "Nonfinite RLC trajectory", "numerical_failure")
                norm = rational._norm
                current_scale = max(norm(current), norm(capacitor_current), norm(source_current))
                voltage_scale = max(norm(voltage), norm(actual_voltage), norm(resistive_drop), norm(inductive_drop))
                current_error = norm(boundary_current)/current_scale if current_scale else 0.
                voltage_error = norm(boundary_voltage)/voltage_scale if voltage_scale else 0.
                vscale = max(norm(incident[capacitive]), norm(outgoing[capacitive]), norm(state[vslice]))
                voltage_state_error = norm(incident[capacitive]+outgoing[capacitive]-state[vslice])/vscale if vscale else 0.
                qscale = max(norm(incident[inductive]), norm(outgoing[inductive]), norm(state[qslice]), norm(root*capacitor_current[inductive]))
                current_state_error = norm(root*(current[inductive]+capacitor_current[inductive])-state[qslice])/qscale if qscale else 0.
                # Mixed algebraic residual also verifies zero-R ideal-voltage rows.
                multipliers = gamma.copy(); multipliers[inductive] = 1.; multipliers[capacitive] = -1.
                algebraic_rhs = normalized.copy(); algebraic_rhs[inductive] = state[qslice]; algebraic_rhs[capacitive] = state[vslice]
                algebraic_scale = max(norm(incident), norm(multipliers*outgoing), norm(algebraic_rhs))
                algebraic_error = norm(incident-multipliers*outgoing-algebraic_rhs)/algebraic_scale if algebraic_scale else 0.
                boundary_error = max(current_error, voltage_error, algebraic_error)
                _require(all(math.isfinite(e) and e <= 1e-10 for e in (boundary_error, current_state_error, voltage_state_error)),
                         "RLC state or physical/algebraic boundary residual exceeds tolerance", "numerical_failure")
                max_boundary = max(max_boundary, boundary_error)
                max_current_state, max_voltage_state = max(max_current_state, current_state_error), max(max_voltage_state, voltage_state_error)
                if time in output_lookup:
                    row = {"time_s": output_lookup[time]}
                    for key, array in (("source_voltage_v", voltage), ("incident_wave_sqrt_w", incident), ("outgoing_wave_sqrt_w", outgoing),
                                       ("port_voltage_v", actual_voltage), ("port_current_a", current), ("boundary_residual_a", boundary_current),
                                       ("boundary_residual_v", boundary_voltage),
                                       ("source_current_a", source_current),
                                       ("termination_resistor_power_w", resistor_power)):
                        row[key+"_by_port"] = dict(zip(ports, array.tolist()))
                    row["capacitor_voltage_v_by_port"] = dict(zip(capacitive_ports, capacitor_voltage.tolist()))
                    row["capacitor_voltage_derivative_v_per_s_by_port"] = dict(zip(capacitive_ports, voltage_derivative.tolist()))
                    row["capacitor_energy_j_by_port"] = dict(zip(capacitive_ports, capacitor_energy.tolist()))
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
                    _require(np.isfinite(transition).all(), "Nonfinite RLC exponential", "numerical_failure")
                    transitions[duration] = transition[:count, :count], transition[:count, count:count+n]-transition[:count, count+n:], transition[:count, count+n:]
                    poll()
                end = prescribed._incident(right, waves, positions)
                evolution, start_weight, end_weight = transitions[duration]
                previous_state = state.copy() if interval_observer is not None else None
                state = evolution@state+start_weight@start+end_weight@end
                observe(right, end, prescribed._incident(right, voltages, voltage_positions))
                if interval_observer is not None:
                    context = {key: value.copy() if isinstance(value, np.ndarray) else value for key, value in observer_context.items()}
                    interval_observer(context, left, right, previous_state, state.copy(), start.copy(), end.copy())
                start = end
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": rational.sampling._digest(frozen), "fit_result": fit, "terminations": frozen["terminations"],
                      "output_times_s": frozen["output_times_s"], "port_names": ports, "capacitive_port_names": capacitive_ports, "inductive_port_names": inductive_ports,
                      "points": points, "final_state_sqrt_w": state[:memory].reshape(len(poles), n).tolist(),
                      "final_capacitor_voltage_v_by_port": dict(zip(capacitive_ports, (root*state[vslice]).tolist())),
                      "final_inductor_current_a_by_port": dict(zip(inductive_ports, (state[qslice]/root).tolist())),
                      "diagnostics": {"algebraic_loop_condition": condition, "algebraic_loop_backward_error": backward,
                                      "closed_system_stability_margin_per_s": margin, "closed_system_relative_stability_margin": relative,
                                      "maximum_boundary_relative_residual": max_boundary, "maximum_voltage_state_relative_residual": max_voltage_state,
                                      "maximum_current_state_relative_residual": max_current_state,
                                      "interval_count": len(grid)-1, "unique_exponential_count": len(transitions), "estimated_work": work,
                                      "integration_method": "exact_piecewise_linear_augmented_exponential"},
                      "limitations": ["Zero initial fitted-network, inductor and capacitor states; continuous PWL voltages, series source R/L and port-shunt C",
                                      "At least one positive L and C; C-only ports require positive R; zero-L/C ports use resistive algebra including zero-R ideal voltage sources",
                                      "Inet+C*dV/dt=Isource and Vs=V+R*Isource+L*dIsource/dt; network and source currents are distinct when C is present",
                                      "Boundary diagnostic independently normalizes KVL in volts, KCL in amperes and mixed wave algebra; no mixed-unit norm",
                                      "Inductor and capacitor state blocks are independently source-port ordered, q=sqrt(Z0)*Isource, v=V/sqrt(Z0); no RMS conversion",
                                      "Exact PWL exponential propagation of the fitted model, with all augmented coordinates in sqrt(W)",
                                      "Reported R*Isource^2, L*Isource^2/2 and C*V^2/2 describe supplied terminations, not integrated heating or arbitrary fitted-network storage",
                                      "Singular feedthrough, unresolved stable margins, marginal modes and unsupported floating-point ranges reject without regularization",
                                      "No nonlinear, open/infinite termination or general circuit topology; no source-band extrapolation accuracy claim",
                                      "Synthetic verification and numerical stability do not establish measured passivity, causality or production qualification"]}
            _require(len(rational.sampling._json(result)) <= _MAX_RESULT_BYTES, "RLC result exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterRlcError:
        raise
    except (resistive.SParameterTerminatedError, prescribed.SParameterTransientError, rational.SParameterRationalError, rational.sampling.SParameterSamplingError) as error:
        raise SParameterRlcError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterRlcError("numerical_failure", f"RLC numerical failure: {error}") from error
