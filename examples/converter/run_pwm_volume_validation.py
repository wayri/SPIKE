"""Original switched-ODE and separately installed CalculiX correlation fixtures.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from python.spike_core.pwm_electrothermal import DEFAULTS
from python.spike_core.pwm_volume_electrothermal import REQUEST, run_pwm_volume_electrothermal
from python.spike_core.calculix_transient import run_calculix_transient
from python.spike_core.assembly_tetra_transient import run_assembly_tetra_transient
from tests.python.test_assembly_tetra_thermal import cube, request
from tests.python.test_calculix_transient import sine_case


def uniform_case(*, cycles=80, step=1e-6, window=1):
    """Original unit-volume insulated solid, total capacity 0.01 J/K.

    All six tetrahedra have equal volume; every dissipative device distributes
    its energy uniformly. This is a mathematical fixture, not a PCB material.
    """
    thermal = request(cube())
    thermal['boundaries'] = []
    fractions = [{'cell_id': cell['id'], 'weight': 1/6}
                 for cell in thermal['mesh']['cells']]
    return {'contract': REQUEST, 'parameters': {'cycles': cycles, 'maximum_step_s': step},
            'thermal': {'request': thermal, 'initial_temperature_k': 300.,
                        'material_heat_capacity': [{'material_id': 'k', 'density_kg_m3': .01,
                                                   'specific_heat_j_kgk': 1.}],
                        'device_cell_fractions': {name: copy.deepcopy(fractions)
                                                 for name in ('Rw', 'SH', 'SL', 'Load')}},
            'coupling': {'cycles_per_window': window, 'temperature_tolerance_k': 1e-9,
                         'relative_energy_tolerance': 1e-9}}


def switched_reference(parameters, step=1e-7, capacity=.01):
    """Independent continuous switched ODE integrated with event-aligned RK4.

    KCL eliminates the switch node. State is i_L [A], v_C [V], temperature
    rise [K]; sampled PI integral is updated once at each cycle start. All
    four physical passive losses enter dT/dt, never numerical BE dissipation.
    """
    p = {**DEFAULTS, **parameters}
    vin, ron, roff = (p[k] for k in ('input_voltage_v', 'switch_on_resistance_ohm',
                                    'switch_off_resistance_ohm'))
    period = 1/p['switching_frequency_hz']
    state, integral, history = (0., 0., 0.), 0., []

    def derivative(y, high):
        current, voltage, rise = y
        gh, gl = (1/ron, 1/roff) if high else (1/roff, 1/ron)
        sw = (vin*gh-current)/(gh+gl)
        rw = p['winding_resistance_ohm']*(1+p['temperature_coefficient_per_k']*rise)
        heat = rw*current**2 + voltage**2/p['load_resistance_ohm']
        heat += gh*(vin-sw)**2 + gl*sw**2
        return ((sw-rw*current-voltage)/p['inductance_h'],
                (current-voltage/p['load_resistance_ohm'])/p['capacitance_f'], heat/capacity)

    def shifted(y, dy, dt):
        return tuple(a+dt*b for a, b in zip(y, dy))

    for cycle in range(p['cycles']):
        error = p['target_voltage_v']-state[1]
        duty = min(.95, max(.05, p['target_voltage_v']/vin +
                           p['controller_kp_per_v']*error + p['controller_ki_per_v_s']*integral))
        integral += period*error
        for high, duration in ((True, duty*period), (False, (1-duty)*period)):
            steps = math.ceil(duration/step)
            dt = duration/steps
            for _ in range(steps):
                a = derivative(state, high)
                b = derivative(shifted(state, a, dt/2), high)
                c = derivative(shifted(state, b, dt/2), high)
                d = derivative(shifted(state, c, dt), high)
                state = tuple(y+dt*(v+2*w+2*x+z)/6 for y, v, w, x, z in zip(state, a, b, c, d))
        history.append({'time_s': (cycle+1)*period, 'inductor_current_a': state[0],
                        'output_voltage_v': state[1], 'temperature_k': 300+state[2]})
    return history


def assert_uniform_conservation(result, capacity=.01):
    if result['status'] != 'completed' or len(result['frames']) != len(result['windows'])+1:
        raise AssertionError('complete committed temperature history required')
    accumulated = 0.
    maximum = 0.
    for window, frame in zip(result['windows'], result['frames'][1:]):
        accumulated += sum(window['device_energies_j'].values())
        error = float(np.max(np.abs(np.asarray(frame['node_temperatures_k'])-(300+accumulated/capacity))))
        maximum = max(maximum, error)
    if maximum > 2e-8:
        raise AssertionError(f'uniform energy-to-temperature oracle failed: {maximum} K')
    return maximum


def correlate_uniform_calculix(raw, result):
    """Replay accepted per-window physical energy in one actual CCX history.

    Only right-endpoint powers are sampled by each backward Euler step. This
    is an independent solid-field transfer check, not an independent circuit.
    """
    thermal = copy.deepcopy(raw['thermal']['request'])
    thermal['heat_sources_w_m3'] = {c['id']: 1. for c in thermal['mesh']['cells']}
    times = [w['completed_cycles']/result['parameters']['switching_frequency_hz'] for w in result['windows']]
    intervals = np.diff([0., *times])
    powers = [float(sum(w['device_energies_j'].values())/dt) for w, dt in zip(result['windows'], intervals)]
    if not np.allclose(intervals, intervals[0], rtol=0, atol=1e-14):
        raise ValueError('correlation fixture requires complete equal-duration windows')
    settings = {'contract': 'spike/assembly-tetra-transient-settings/v1',
                'duration_s': times[-1], 'time_step_s': float(intervals[0]),
                'output_interval_s': float(intervals[0]), 'initial_temperature_k': 300.,
                'material_heat_capacity': copy.deepcopy(raw['thermal']['material_heat_capacity']),
                'power_schedule': [{'time_s': 0., 'scale': powers[0]}] +
                                  [{'time_s': t, 'scale': q} for t, q in zip(times, powers)]}
    external = run_calculix_transient(thermal, settings)
    if len(external['frames']) != len(result['frames']):
        raise AssertionError('CalculiX history coverage mismatch')
    maximum = max(float(np.max(np.abs(np.asarray(left['node_temperatures_k'])-
                                     np.asarray(right['node_temperatures_k']))))
                  for left, right in zip(result['frames'], external['frames']))
    if maximum > 6e-5:
        raise AssertionError(f'CalculiX uniform temperature history differs by {maximum} K')
    return {'maximum_temperature_difference_k': maximum, 'gate_k': 6e-5,
            'external_history': external}


def nonuniform_capacity_distinction():
    """Assert both different capacity rules, never waive a cross-solver mismatch."""
    raw, settings = sine_case(2, .2)
    settings['output_interval_s'] = .2
    points = np.array(raw['mesh']['vertices'])
    n = len(points)
    stiffness, consistent, centroid = (np.zeros((n, n)) for _ in range(3))
    for cell in raw['mesh']['cells']:
        nodes = cell['vertices']
        xyz = points[nodes]
        volume = abs(np.linalg.det((xyz[1:]-xyz[0]).T))/6
        gradient = np.linalg.inv(np.column_stack((np.ones(4), xyz)))[1:].T
        ix = np.ix_(nodes, nodes)
        stiffness[ix] += 2*volume*gradient@gradient.T
        consistent[ix] += 6*volume*(np.eye(4)+np.ones((4, 4)))/20
        centroid[ix] += 6*volume*np.ones((4, 4))/16
    free = np.flatnonzero((points[:, 0] != 0) & (points[:, 0] != 1))
    initial = np.array(settings['initial_temperature_k'])-300
    def oracle(mass):
        return np.linalg.solve((mass/.2+stiffness)[np.ix_(free, free)],
                               (mass@initial/.2)[free])+300
    external = run_calculix_transient(raw, settings)
    internal = run_assembly_tetra_transient(raw, settings)
    ccx = np.array(external['node_temperatures_k'])[free]
    spike = np.array(internal['node_temperatures_k'])[free]
    ccx_error = float(np.max(np.abs(ccx-oracle(centroid))))
    spike_error = float(np.max(np.abs(spike-oracle(consistent))))
    difference = float(np.max(np.abs(ccx-spike)))
    if ccx_error > 6e-5 or spike_error > 1e-8 or difference < .05:
        raise AssertionError(f'capacity distinction: CCX={ccx_error}, SPIKE={spike_error}, difference={difference}')
    return {'calculix_centroid_oracle_error_k': ccx_error,
            'spike_consistent_oracle_error_k': spike_error,
            'cross_solver_difference_k': difference,
            'cross_solver_agreement': False, 'reason': 'DC3D4 centroid vs exact P1 capacity quadrature',
            'external_history': external, 'internal_history': internal}


def retained_board_package_replay(directory):
    """New prepared-step execution and fresh CCX on existing retained geometry.

    This reuses SPIKE's original OCC-meshed two-board/STEP package fixture.
    No remeshing or source-package modification is required.
    """
    from python.spike_core.assembly_field_transient import _bind_canonical, remap_field_transient_settings
    from python.spike_core.calculix_transient import run_calculix_field_transient, verify_calculix_field_transient_result
    from python.spike_core.assembly_tetra_thermal_validation import validate_request
    from python.spike_core.retained_thermal_step import prepare_retained_thermal_step
    names = ('geometry', 'problem', 'settings', 'spike')
    inputs = {name: json.loads((directory/(name+'.json')).read_text()) for name in names}
    geometry, problem, settings = (inputs[name] for name in names[:3])
    external = run_calculix_field_transient(geometry, problem, settings)
    verify_calculix_field_transient_result(geometry, problem, external)
    handoff, tetra, _, _ = _bind_canonical(geometry, problem)
    remapped = remap_field_transient_settings(geometry, handoff, settings)
    data = validate_request(tetra)
    loads = [(cell['id'], volume*tetra.get('heat_sources_w_m3', {}).get(cell['id'], 0.))
             for cell, (volume, _) in zip(data['cells'], data['geometry'])]
    power = sum(value for _, value in loads)
    if power <= 0:
        raise AssertionError('retained fixture has no positive package power')
    fractions = [{'cell_id': cell, 'weight': value/power} for cell, value in loads if value > 0]
    tetra['heat_sources_w_m3'] = {}
    prepared = prepare_retained_thermal_step(tetra, remapped['material_heat_capacity'], {'package-source': fractions})
    temperature = [settings['initial_temperature_k']]*prepared.node_count
    frames = [{'time_s': 0., 'node_temperatures_k': temperature}]
    dt, duration, output = (settings[k] for k in ('time_step_s', 'duration_s', 'output_interval_s'))
    ledgers = []
    for step in range(round(duration/dt)):
        result = prepared.advance(temperature, dt, {'package-source': power*dt})
        temperature = result['node_temperatures_k']
        ledgers.append(result['energy_balance'])
        time = (step+1)*dt
        if math.isclose(time/output, round(time/output), abs_tol=1e-10):
            frames.append({'time_s': time, 'node_temperatures_k': temperature})
    errors = {}
    for name, existing in (('saved_spike', inputs['spike']), ('fresh_calculix', external)):
        expected = existing['field_result']['frames']
        if len(expected) != len(frames):
            raise AssertionError('retained output frame coverage differs')
        maximum = 0.
        for left, right in zip(frames, expected):
            if abs(left['time_s']-right['time_s']) > 1e-12:
                raise AssertionError('retained frame time mismatch')
            difference = np.abs(np.array(left['node_temperatures_k'])-right['node_temperatures_k'])
            maximum = max(maximum, float(np.max(difference)))
            gate = 1e-8 if name == 'saved_spike' else .05+.05*max(abs(t-300) for t in right['node_temperatures_k'])
            if float(np.max(difference)) > gate:
                raise AssertionError(f'{name} retained history differs: {maximum} K, gate {gate} K')
        errors[name+'_maximum_difference_k'] = maximum
    return {'status': 'fresh_ccx_retained_replay_passed', 'fresh_calculix_execution': True,
            'source_sha256': {name+'.json': hashlib.sha256((directory/(name+'.json')).read_bytes()).hexdigest() for name in names},
            'source_directory': str(directory.resolve()), 'nodes': prepared.node_count,
            'tetrahedra': len(tetra['mesh']['cells']), 'package_power_w': power,
            'occurrences': [trace['occurrence_id'] for trace in handoff['source_traceability']],
            'source_traceability': handoff['source_traceability'], 'frames': frames,
            'energy_ledgers': ledgers, 'external_result': external,
            'gates': {'saved_spike_k': 1e-8, 'fresh_calculix_absolute_k': .05,
                      'fresh_calculix_relative_temperature_rise': .05}, **errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--retained-directory', type=Path,
                        default=ROOT/'.local/transient-thermal-validation')
    args = parser.parse_args()
    from python.spikes.native_abi import load_native_library
    library = load_native_library(args.library.resolve())
    reference = switched_reference({'cycles': 80})
    fine_reference = switched_reference({'cycles': 80}, step=5e-8)
    reference_error = max(abs(reference[-1][k]-fine_reference[-1][k])
                          for k in ('inductor_current_a', 'output_voltage_v', 'temperature_k'))
    if reference_error > 1e-7:
        raise AssertionError('independent RK4 reference is not step-converged')
    results, errors, component_errors = [], [], []
    for step in (2e-6, 1e-6, .5e-6):
        raw = uniform_case(step=step)
        result = run_pwm_volume_electrothermal(raw, library=library)
        assert_uniform_conservation(result)
        end = result['windows'][-1]['electrical_cycles'][-1]
        expected = fine_reference[-1]
        error = math.sqrt((end['output_voltage_v']-expected['output_voltage_v'])**2 +
                          (end['inductor_current_a']-expected['inductor_current_a'])**2 +
                          (result['frames'][-1]['node_temperatures_k'][0]-expected['temperature_k'])**2)
        results.append({'request': raw, 'result': result})
        errors.append(error)
        component_errors.append({'inductor_current_a': abs(end['inductor_current_a']-expected['inductor_current_a']),
                                 'output_voltage_v': abs(end['output_voltage_v']-expected['output_voltage_v']),
                                 'temperature_k': abs(result['frames'][-1]['node_temperatures_k'][0]-expected['temperature_k'])})
    if not errors[0] > 1.5*errors[1] > 1.5**2*errors[2] or errors[-1] > .05:
        raise AssertionError(f'electrical/ODE refinement failed: {errors}')
    component_gates = {'inductor_current_a': .005, 'output_voltage_v': .002, 'temperature_k': .005}
    for name, gate in component_gates.items():
        values = [row[name] for row in component_errors]
        if not values[0] > 1.5*values[1] > 1.5**2*values[2] or values[-1] > gate:
            raise AssertionError(f'{name} physical-unit refinement failed: {values}')
    correlation = correlate_uniform_calculix(results[-1]['request'], results[-1]['result'])
    distinction = nonuniform_capacity_distinction()
    retained = retained_board_package_replay(args.retained_directory)
    window_results = []
    for window in (8, 4, 2, 1):
        raw = uniform_case(step=2.5e-7, window=window)
        result = run_pwm_volume_electrothermal(raw, library=library)
        assert_uniform_conservation(result)
        window_results.append({'request': raw, 'result': result})
    def endpoint(result):
        last = result['windows'][-1]['electrical_cycles'][-1]
        return np.array([last['inductor_current_a'], last['output_voltage_v'],
                         result['frames'][-1]['node_temperatures_k'][0]])
    target = endpoint(window_results[-1]['result'])
    window_errors = [float(np.linalg.norm(endpoint(row['result'])-target)) for row in window_results[:-1]]
    if not window_errors[0] > 2*window_errors[1] > 4*window_errors[2] or window_errors[0] > .01:
        raise AssertionError(f'thermal-window refinement failed: {window_errors}')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    def retain(name, value):
        data = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
        (args.output_dir/name).write_bytes(data)
        artifacts[name] = hashlib.sha256(data).hexdigest()
    for index, result in enumerate(results):
        retain(f'coupled-{index}.json', result)
    for index, result in enumerate(window_results):
        retain(f'window-refinement-{index}.json', result)
    retain('calculix-uniform.json', correlation)
    retain('calculix-nonuniform.json', distinction)
    retain('retained-board-package-replay.json', retained)
    retain('switched-reference.json', fine_reference)
    report = {'status': 'bounded_reference_checks_passed', 'production_qualified': False,
              'electrical_refinement_state_errors': errors, 'rk4_reference_refinement_error': reference_error,
              'electrical_refinement_component_errors': component_errors, 'finest_component_error_gates': component_gates,
              'window_refinement_state_errors_relative_to_one_cycle': window_errors,
              'calculix_uniform_maximum_difference_k': correlation['maximum_temperature_difference_k'],
              'nonuniform_cross_solver_agreement': False,
              'nonuniform_cross_solver_difference_k': distinction['cross_solver_difference_k'],
              'retained_board_package_replay': {k: retained[k] for k in ('status', 'fresh_calculix_execution',
                   'nodes', 'tetrahedra', 'saved_spike_maximum_difference_k', 'fresh_calculix_maximum_difference_k')},
              'native_library_sha256': hashlib.sha256(library.path.read_bytes()).hexdigest(),
              'calculix_executable_sha256': correlation['external_history']['execution']['runtime']['executable_sha256'],
              'artifacts': dict(artifacts),
              'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
                  'python/spike_core/pwm_volume_electrothermal.py',
                  'python/spike_core/retained_thermal_step.py',
                  'python/spike_core/calculix_transient.py',
                  'examples/converter/run_pwm_volume_validation.py')},
              'limits': ['synthetic uniform solid, not a representative PCB or measured hardware',
                         'nonuniform cross-solver capacity matrices intentionally differ',
                         'no semiconductor switching-loss or airflow qualification']}
    retain('evidence.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
