# SPDX-License-Identifier: Apache-2.0
"""Experimental actual sampled-C / reciprocal P1 FEM / hover-BEM coupled loop.

Two-phase synthetic linear machine, averaged ideal voltage drive and no-swirl
quasi-steady hover propeller. This is not VESC firmware or blade-resolved CFD.
See the independently authored PROPULSION_POD_* derivations before changing
the electrical, PM-source, shaft or fluid work accounting.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import time
import numpy as np
from scipy.optimize import brentq

from .propulsion_pod_field import FieldMotor, validate_field_spec
from .propulsion_pod_propeller import evaluate_propeller
from .propulsion_pod_controller import create_controller, SOURCE_SHA256

REQUEST = 'spike/propulsion-pod-request/v1'
RESULT = 'spike/propulsion-pod-result/v1'
DEFAULT_REQUEST = {
    'contract': REQUEST, 'field_motor': {},
    'propeller': {'contract': 'spike/hover-bem-propeller/v1', 'blade_count': 2,
        'radial_stations_m': [.03, .15], 'chord_m': [.018, .012], 'twist_rad': [.18, .12],
        'density_kg_m3': 1.225, 'dynamic_viscosity_pa_s': 1.81e-5, 'speed_of_sound_m_s': 343.,
        'polar': {'lift_slope_per_rad': 6., 'drag_coefficient': .012, 'alpha_valid_rad': [0., .2],
                  'reynolds_valid': [0., 2e6], 'source': 'Illustrative attached linear polar; not measured'},
        'radial_cells': 32, 'relative_tolerance': 1e-10, 'max_iterations': 80},
    'drive': {'resistance_ohm': [.5, .5], 'end_turn_inductance_h': [.0002, .0002],
              'dc_bus_v': 12., 'current_limit_a': 4., 'speed_kp_a_s_per_rad': .06,
              'speed_ki_a_per_rad': .5, 'current_gain_ohm': .25},
    'shaft': {'inertia_kg_m2': 5e-6, 'damping_n_m_s': 1e-6,
              'initial_speed_rad_s': 0., 'initial_angle_rad': .2},
    'transient': {'duration_s': .25, 'time_step_s': .0001, 'controller_period_s': .0005,
                  'field_output_interval_s': .01, 'target_speed_rad_s': 100.,
                  'maximum_speed_rad_s': 500., 'wall_budget_s': 120.},
}

def _number(value, label, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{label} must be finite in [{lower}, {upper}]')
    return float(value)

def _keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label} has unexpected or missing fields')

def _ratio(a, b, label):
    ratio = a/b
    if not math.isfinite(ratio) or ratio < 1 or abs(ratio-round(ratio)) > 1e-8:
        raise ValueError(f'{label} must be an integer multiple of time_step_s')
    return round(ratio)

def validate_request(request):
    _keys(request, DEFAULT_REQUEST, 'request')
    if request['contract'] != REQUEST:
        raise ValueError('Unsupported propulsion-pod request contract')
    clean = copy.deepcopy(request)
    if not isinstance(clean['field_motor'], dict):
        raise ValueError('field_motor must be an object')
    clean['field_motor'] = validate_field_spec(clean['field_motor'])
    for name in ('drive', 'shaft', 'transient'):
        _keys(clean[name], DEFAULT_REQUEST[name], name)
    drive, shaft, transient = clean['drive'], clean['shaft'], clean['transient']
    for key, upper in [('resistance_ohm', 100.), ('end_turn_inductance_h', 1.)]:
        values = drive[key]
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError(f'{key} requires two phase values')
        drive[key] = [_number(v, key, 1e-8 if key == 'resistance_ohm' else 0., upper) for v in values]
    for key, low, high in [('dc_bus_v', .001, 100.), ('current_limit_a', .001, 100.),
                          ('speed_kp_a_s_per_rad', 0., 10.), ('speed_ki_a_per_rad', 0., 100.),
                          ('current_gain_ohm', 0., 100.)]:
        drive[key] = _number(drive[key], key, low, high)
    for key, low, high in [('inertia_kg_m2', 1e-9, 100.), ('damping_n_m_s', 0., 100.),
                          ('initial_speed_rad_s', 0., 10000.), ('initial_angle_rad', -1e6, 1e6)]:
        shaft[key] = _number(shaft[key], key, low, high)
    for key, low, high in [('duration_s', 1e-5, 10.), ('time_step_s', 1e-6, .01),
                          ('controller_period_s', 1e-6, .1), ('field_output_interval_s', 1e-6, 10.),
                          ('target_speed_rad_s', 0., 10000.), ('maximum_speed_rad_s', .01, 10000.),
                          ('wall_budget_s', 1., 600.)]:
        transient[key] = _number(transient[key], key, low, high)
    steps = _ratio(transient['duration_s'], transient['time_step_s'], 'duration_s')
    stride = _ratio(transient['controller_period_s'], transient['time_step_s'], 'controller_period_s')
    frame_stride = _ratio(transient['field_output_interval_s'], transient['time_step_s'], 'field_output_interval_s')
    if steps > 20000 or math.ceil(steps/frame_stride)+1 > 101:
        raise ValueError('Pod capture exceeds 20000 accepted steps or 101 field frames')
    if transient['maximum_speed_rad_s']*transient['time_step_s'] > .1:
        raise ValueError('Maximum rotor angle per step exceeds 0.1 rad; refine the time step')
    if shaft['initial_speed_rad_s'] >= transient['maximum_speed_rad_s']:
        raise ValueError('Initial speed must be below maximum_speed_rad_s')
    # Admit every polar/geometry bound before compiling or running a controller.
    evaluate_propeller(clean['propeller'], 0.)
    evaluate_propeller(clean['propeller'], transient['maximum_speed_rad_s'])
    return clean, steps, stride, frame_stride

def _sinc(x):
    return float(np.sinc(x/math.pi))

def angular_secants(motor, theta0, theta1):
    """Exact stable harmonic divided differences, including PM self potential."""
    delta, middle = theta1-theta0, .5*(theta1+theta0)
    terms = motor.coupling_terms(middle)
    return (np.asarray(terms['dpsi_dangle_wb_turn_per_rad'])*_sinc(.5*delta),
            terms['dpm_source_potential_dangle_j_per_rad']*_sinc(delta))

def coupled_step(motor, propeller, currents, angle, speed, voltage, dt, resistance,
                 end_turn_l, inertia, damping, maximum_speed):
    """One implicitly accepted conservative circuit/field/shaft/propeller step.

    No input state is mutated. The C controller is held across this step and
    is never advanced during root trials. Negative/reversing speed is outside
    the admitted hover model and fails rather than being silently clamped.
    """
    i0, v = np.asarray(currents, float), np.asarray(voltage, float)
    R = np.asarray(resistance, float)
    L = np.asarray(motor.inductance_h)+np.diag(end_turn_l)
    lhs = L/dt+np.diag(R/2)
    old = (L/dt-np.diag(R/2))@i0+v

    def trial(w1):
        wbar = .5*(speed+w1)
        theta1 = angle+dt*wbar
        dpsi, dC = angular_secants(motor, angle, theta1)
        delta_flux_pm = dt*wbar*dpsi
        i1 = np.linalg.solve(lhs, old-delta_flux_pm/dt)
        ibar = .5*(i0+i1)
        torque = float(ibar@dpsi+dC)
        fluid = evaluate_propeller(propeller, wbar)
        residual = inertia*(w1-speed)/dt-torque+damping*wbar+fluid['torque_nm']
        return residual, i1, theta1, torque, dpsi, fluid

    low, high = trial(0.)[0], trial(maximum_speed)[0]
    if abs(low) < 1e-13:
        next_speed = 0.
    elif low >= 0 or high <= 0:
        raise ValueError('Coupled shaft root not bracketed in admitted nonnegative speed range; no step accepted')
    else:
        next_speed = brentq(lambda w: trial(w)[0], 0., maximum_speed, xtol=1e-12, rtol=1e-12, maxiter=60)
    mechanical_residual, i1, theta1, torque, dpsi, fluid = trial(next_speed)
    ibar, wbar = .5*(i0+i1), .5*(speed+next_speed)
    electric_residual = L@(i1-i0)/dt+wbar*dpsi+R*ibar-v
    if np.max(np.abs(i1)) > motor.spec['max_current_a']:
        raise ValueError('Phase current exceeded the admitted field envelope; no step accepted')
    if abs(mechanical_residual) > 1e-10 or np.max(np.abs(electric_residual)) > 1e-9:
        raise ValueError('Individual physical coupled residual gate failed; no step accepted')
    state0, state1 = motor.evaluate(i0.tolist(), angle), motor.evaluate(i1.tolist(), theta1)
    delta_u = state1['magnetic_energy_j']-state0['magnetic_energy_j'] + .5*(i1@np.diag(end_turn_l)@i1-i0@np.diag(end_turn_l)@i0)
    delta_k = .5*inertia*(next_speed**2-speed**2)
    source_work = dt*float(v@ibar)
    copper = dt*float(R@(ibar*ibar))
    damping_work = dt*damping*wbar*wbar
    shaft_work = dt*fluid['power_w']
    defect = source_work-copper-damping_work-shaft_work-delta_u-delta_k
    tolerance = 1e-10+1e-8*max(abs(source_work), abs(delta_u), abs(delta_k))
    if abs(defect) > tolerance:
        raise ValueError('Coupled electrical/field/shaft/fluid energy gate failed; no step accepted')
    return {'currents_a': i1.tolist(), 'angle_rad': theta1, 'speed_rad_s': next_speed,
        'torque_dg_n_m': torque, 'propeller_midpoint': fluid,
        'back_emf_midpoint_v': (wbar*dpsi).tolist(),
        'residuals': {'circuit_v': electric_residual.tolist(), 'shaft_n_m': mechanical_residual},
        'energy': {'source_work_j': source_work, 'copper_heat_j': copper,
                   'shaft_damping_heat_j': damping_work, 'propeller_shaft_work_j': shaft_work,
                   'magnetic_energy_change_j': float(delta_u), 'kinetic_energy_change_j': delta_k,
                   'defect_j': float(defect), 'tolerance_j': tolerance}}

def run_propulsion_pod(request):
    clean, steps, stride, frame_stride = validate_request(request)
    started = time.monotonic()
    motor = FieldMotor(clean['field_motor'])
    drive, shaft, settings = clean['drive'], clean['shaft'], clean['transient']
    dt = settings['time_step_s']
    currents, angle, speed = [0., 0.], shaft['initial_angle_rad'], shaft['initial_speed_rad_s']
    voltage = [0., 0.]
    history, frames, events = [], [], []
    totals = {key: 0. for key in ('source_work_j', 'copper_heat_j', 'shaft_damping_heat_j',
                                  'propeller_shaft_work_j', 'magnetic_energy_change_j', 'kinetic_energy_change_j', 'defect_j')}
    maximum_defect = maximum_circuit_residual = maximum_shaft_residual = 0.
    controller = create_controller(settings['controller_period_s'], drive['dc_bus_v']/2)
    executable_digest = controller.manifest.executable_sha256
    field_mesh = None
    try:
        for index in range(steps+1):
            if time.monotonic()-started > settings['wall_budget_s']:
                raise ValueError('Coupled pod wall budget exceeded; incomplete result refused')
            t = index*dt
            state = motor.evaluate(currents, angle)
            prop = evaluate_propeller(clean['propeller'], speed)
            if index < steps and index % stride == 0:
                derivative = state['angular_derivatives']['dflux_dangle_wb_turn_per_rad']
                sensor = {'target_rad_s': settings['target_speed_rad_s'], 'speed_rad_s': speed,
                    'current_a': currents[0], 'current_b': currents[1], 'dpsi_a': derivative[0], 'dpsi_b': derivative[1],
                    'resistance_a': drive['resistance_ohm'][0], 'resistance_b': drive['resistance_ohm'][1],
                    'voltage_limit_v': drive['dc_bus_v']/2, 'current_limit_a': drive['current_limit_a'],
                    'kp': drive['speed_kp_a_s_per_rad'], 'ki': drive['speed_ki_a_per_rad'],
                    'current_gain': drive['current_gain_ohm']}
                before_state, before_tick = dict(controller.state), controller.tick
                try:
                    output = controller.step(sensor, t, settings['controller_period_s'])
                    voltage = [output['VphaseA'], output['VphaseB']]
                except Exception:
                    controller.state, controller.tick = before_state, before_tick
                    raise
                events.append({'time_s': t, 'sensors': sensor, 'phase_voltage_v': list(voltage),
                               'controller_state': dict(controller.state)})
            history.append({'time_s': t, 'currents_a': list(currents), 'angle_rad': angle, 'speed_rad_s': speed,
                'phase_voltage_v': list(voltage), 'flux_linkage_wb_turn': state['flux_linkage_wb_turn'],
                'torque_n_m': state['torque_n_m'], 'propeller_torque_n_m': prop['torque_nm'],
                'thrust_n': prop['thrust_n'], 'propeller_power_w': prop['power_w'],
                'magnetic_energy_j': state['magnetic_energy_j']+.5*float(np.asarray(currents)@np.diag(drive['end_turn_inductance_h'])@np.asarray(currents)),
                'kinetic_energy_j': .5*shaft['inertia_kg_m2']*speed*speed})
            if index % frame_stride == 0 or index == steps:
                field = motor.evaluate(currents, angle, include_field=True)['field']
                if field_mesh is None:
                    field_mesh = {key: field[key] for key in ('nodes_m', 'triangles', 'region_ids')}
                frames.append({'time_s': t, 'angle_rad': angle, 'speed_rad_s': speed, 'currents_a': list(currents),
                    'element_b_t': field['element_b_t'], 'potential_a_wb_per_m': field['potential_a_wb_per_m'],
                    'current_density_a_per_m2': field['current_density_a_per_m2'], 'radial_airflow': prop['radial_airflow']})
            if index == steps:
                break
            accepted = coupled_step(motor, clean['propeller'], currents, angle, speed, voltage, dt,
                drive['resistance_ohm'], drive['end_turn_inductance_h'], shaft['inertia_kg_m2'],
                shaft['damping_n_m_s'], settings['maximum_speed_rad_s'])
            currents, angle, speed = accepted['currents_a'], accepted['angle_rad'], accepted['speed_rad_s']
            for key in totals:
                totals[key] += accepted['energy'][key]
            maximum_defect = max(maximum_defect, abs(accepted['energy']['defect_j']))
            maximum_circuit_residual = max(maximum_circuit_residual, *map(abs, accepted['residuals']['circuit_v']))
            maximum_shaft_residual = max(maximum_shaft_residual, abs(accepted['residuals']['shaft_n_m']))
    finally:
        controller.close()
    result = {'contract': RESULT, 'status': 'completed', 'model_status': 'experimental', 'production_qualified': False,
        'request_sha256': hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'request': clean, 'accepted_steps': steps, 'controller_ticks': len(events),
        'history': history, 'controller_events': events, 'field_mesh': field_mesh, 'frames': frames,
        'energy': {**totals, 'maximum_step_defect_j': maximum_defect,
                   'maximum_circuit_residual_v': maximum_circuit_residual, 'maximum_shaft_residual_n_m': maximum_shaft_residual,
                   'numerical_dissipation_j': 0., 'method': 'implicit midpoint and exact harmonic discrete-gradient work'},
        'provenance': {'controller': 'actual SPIKES persistent compiled C controller',
            'controller_source_sha256': SOURCE_SHA256, 'controller_executable_sha256': executable_digest,
            'field_basis': motor.diagnostics, 'field_spec_sha256': motor.spec_sha256,
            'duration_wall_s': time.monotonic()-started},
        'limitations': ['Synthetic two-phase fixed-mesh linear recoil PM benchmark; not the VESC three-phase motor or firmware.',
            'Ideal averaged voltage drive, explicit supplied winding resistance and end-turn inductance; no transistor switching losses. current_limit_a bounds the controller current request, not actual current or a safety clamp.',
            'Quasi-steady no-swirl attached-flow hover BEM and computed annular inflow; not blade-resolved CFD or enclosure/wall flow.',
            'No coupled board/motor temperature, saturation, hysteresis, eddy losses, dynamic inflow or full drone flight.',
            'Requires optional source SPIKES Studio runtime and local C compiler; not yet a qualified frozen release.',
            'Numerical benchmark verification does not establish real motor/propeller or manufactured-board accuracy; human numerical review required.']}
    if len(json.dumps(result, allow_nan=False).encode()) > 14*1024*1024:
        raise ValueError('Coupled result exceeds 14 MiB transport budget; reduce saved fields or duration')
    return result
