# SPDX-License-Identifier: Apache-2.0
"""Balanced-flux discrete-gradient exchange for salient/nonlinear magnetic ports.

This is a coupling algorithm, not a constitutive motor or fluid model. The
magnetic port must provide a coherent Hamiltonian and a stable energy difference.
Fluid evaluations are immutable trials; this step never commits a fluid state.
"""
import math
import numpy as np
from scipy.optimize import root
from .propulsion_pod_three_phase import STAR


def symmetric_coordinate_gradient(port, start, end):
    """Symmetrized coordinate increments; three/five-point quadrature at tiny steps.

    The exact difference comes from the port's same constitutive functional.
    Quadrature is a bounded numerical approximation and its chain error is
    checked, never inferred from convergence of the circuit residual alone.
    Coordinates are two balanced flux linkages (Wb turn) and unwrapped radians.
    """
    a, b = np.asarray(start, float), np.asarray(end, float)
    if a.shape != (3,) or b.shape != (3,) or not np.isfinite(np.r_[a, b]).all():
        raise ValueError('Finite two-flux/angle endpoints required')
    def partial(z, j):
        state = port.energy_gradient(z[:2].tolist(), float(z[2]))
        values = np.r_[state['current_coordinates_a'], -state['torque_n_m']]
        if values.shape != (3,) or not np.isfinite(values).all():
            raise ValueError('Invalid magnetic Hamiltonian gradient')
        return float(values[j])
    answer = np.zeros(3)
    indicators = np.zeros(3)
    for order in ((0, 1, 2), (2, 1, 0)):
        z = a.copy()
        for j in order:
            next_z = z.copy(); next_z[j] = b[j]
            delta = b[j] - a[j]
            if delta == 0:
                value = partial(z, j)
            elif abs(delta) > 1e-6 * max(abs(a[j]), abs(b[j]), 1e-9):
                value = float(port.energy_difference(z.tolist(), next_z.tolist())) / delta
            else:
                estimates = []
                for n in (3, 5):
                    points, weights = np.polynomial.legendre.leggauss(n)
                    total = 0.
                    for point, weight in zip(points, weights):
                        sample = z.copy(); sample[j] += .5 * (point + 1) * delta
                        total += weight * partial(sample, j) / 2
                    estimates.append(total)
                value = estimates[1]
                indicators[j] += abs(estimates[1] - estimates[0]) / 2
            answer[j] += value / 2
            z = next_z
    difference = float(port.energy_difference(a.tolist(), b.tolist()))
    chain_error = float(answer @ (b-a) - difference)
    if not np.isfinite(np.r_[answer, indicators, difference, chain_error]).all():
        raise ValueError('Nonfinite magnetic discrete gradient')
    work_scale = max(abs(difference), float(np.sum(np.abs(answer * (b-a)))))
    if abs(chain_error) > 1e-11 + 1e-8 * work_scale:
        raise ValueError('Magnetic discrete-gradient energy chain failed')
    return answer, {'energy_difference_j': difference, 'chain_error_j': chain_error,
                    'gradient_quadrature_indicator': indicators.tolist()}


def energy_port_step(port, fluid_trial, thermal, flux_coordinates, angle, speed,
                     temperature_k, duty, bus_v, dt, inertia, damping, maximum_speed,
                     maximum_thermal_iterations=40, temperature_tolerance_k=1e-8):
    """Solve circuit, Hamiltonian motor, shaft and thermal feedback in one step.

    Resistance heating uses E*x_DG rather than averaging endpoint currents. The
    supplied port includes all magnetic/end-turn storage. `fluid_trial(omega)`
    must be pure and return torque_nm and power_w at the common midpoint. This
    interface admits quasi-steady loads; an unsteady fluid participant needs its
    own transactional state/energy contract, not a stateless substitution.
    """
    q0 = np.asarray(flux_coordinates, float)
    T0 = np.asarray(temperature_k, float); d = np.asarray(duty, float)
    scalars = (angle, speed, bus_v, dt, inertia, damping, maximum_speed)
    if q0.shape != (2,) or T0.shape != (11,) or d.shape != (3,) or not np.isfinite(np.r_[q0,T0,d]).all():
        raise ValueError('Expected two flux coordinates, eleven temperatures and three duties')
    if not all(math.isfinite(x) for x in scalars) or dt <= 0 or inertia <= 0 or bus_v <= 0 or damping < 0:
        raise ValueError('Invalid passive time/drive/shaft inputs')
    if not 0 <= speed < maximum_speed or np.any(d < 0) or np.any(d > 1):
        raise ValueError('Duty or initial shaft speed outside envelope')
    voltage = bus_v*d
    start = np.r_[q0, angle]
    flux_scale = max(float(np.linalg.norm(q0)), dt*bus_v, 1e-8)
    speed_scale = max(speed, 1.)
    torque_scale = inertia*speed_scale/dt
    T1 = T0.copy(); guess = np.r_[q0/flux_scale, speed/speed_scale]
    for iteration in range(maximum_thermal_iterations):
        r = thermal.resistances(((T0+T1)/2).tolist(), d.tolist())
        resistance = np.asarray(r['winding_resistance_ohm']) + r['leg_resistance_ohm']
        def trial(y):
            q1 = y[:2]*flux_scale; w1 = float(y[2]*speed_scale)
            wm = (speed+w1)/2; theta1 = angle+dt*wm
            dg, chain = symmetric_coordinate_gradient(port, start, np.r_[q1,theta1])
            current = STAR@dg[:2]; torque = -float(dg[2])
            limit=getattr(port,'max_current_a',None)
            if limit is not None and (not math.isfinite(limit) or limit<=0 or max(abs(current))>limit):
                raise ValueError('Discrete-gradient work current exceeds the magnetic port envelope')
            fluid = fluid_trial(wm)
            if not isinstance(fluid, dict) or not all(k in fluid for k in ('torque_nm','power_w')):
                raise ValueError('Fluid trial omitted load/power')
            Q, P = float(fluid['torque_nm']), float(fluid['power_w'])
            if not math.isfinite(Q+P) or abs(P-Q*wm) > 1e-10+1e-9*abs(P):
                raise ValueError('Fluid midpoint shaft-work identity failed')
            circuit = (q1-q0)/dt-STAR.T@(voltage-resistance*current)
            shaft = inertia*(w1-speed)/dt-torque+Q+damping*wm
            return np.r_[circuit/bus_v, shaft/torque_scale], q1,w1,theta1,current,torque,fluid,chain
        solution = root(lambda y: trial(y)[0], guess, method='hybr', options={'xtol':1e-10,'maxfev':120})
        residual,q1,w1,theta1,current,torque,fluid,chain = trial(solution.x)
        if not solution.success and np.linalg.norm(residual, np.inf) > 1e-9:
            raise ValueError('Coupled salient/nonlinear solve failed: '+str(solution.message))
        if np.linalg.norm(residual, np.inf) > 1e-9 or not 0 <= w1 <= maximum_speed:
            raise ValueError('Coupled residual or shaft envelope failed')
        wm = (speed+w1)/2
        heat = thermal.midpoint_step(T0.tolist(), current.tolist(), d.tolist(), dt,
                                     bearing_heat_w=damping*wm*wm)
        updated = np.asarray(heat['temperature_k'])
        if np.max(np.abs(updated-T1)) <= temperature_tolerance_k:
            break
        T1 = updated; guess = solution.x
    else:
        raise ValueError('Salient/nonlinear electrothermal fixed point failed')
    actual = thermal.resistances(heat['midpoint_temperature_k'],d.tolist())
    actual_R = np.asarray(actual['winding_resistance_ohm'])+actual['leg_resistance_ohm']
    circuit = (q1-q0)/dt-STAR.T@(voltage-actual_R*current)
    shaft = inertia*(w1-speed)/dt-torque+fluid['torque_nm']+damping*wm
    if np.linalg.norm(circuit,np.inf)>1e-8 or abs(shaft)>1e-9:
        raise ValueError('Accepted midpoint resistance invalidated circuit/shaft residual')
    source = dt*float(voltage@current); fluid_work = dt*fluid['power_w']
    storage = chain['energy_difference_j']+.5*inertia*(w1*w1-speed*speed)
    defect = source-fluid_work-storage-heat['storage_j']-heat['ambient_heat_j']
    if abs(defect)>1e-9+1e-7*max(abs(source),abs(storage),abs(heat['storage_j'])):
        raise ValueError('Whole salient/nonlinear energy balance failed')
    endpoint = port.energy_gradient(q1.tolist(),theta1)
    return {'flux_coordinates_wb_turn':q1.tolist(),'angle_rad':theta1,'speed_rad_s':w1,
            'currents_a':(STAR@np.asarray(endpoint['current_coordinates_a'])).tolist(),
            'work_currents_a':current.tolist(),'temperature_k':heat['temperature_k'],
            'field_torque_dg_n_m':torque,'fluid':fluid,'thermal':heat,
            'temperature_iterations':iteration+1,'projected_kvl_residual_v':circuit.tolist(),
            'shaft_residual_n_m':shaft,'magnetic_chain':chain,
            'energy':{'dc_source_work_j':source,'fluid_shaft_work_j':fluid_work,
                      'magnetic_and_kinetic_storage_change_j':storage,
                      'thermal_storage_change_j':heat['storage_j'],
                      'ambient_heat_j':heat['ambient_heat_j'],'defect_j':defect}}
