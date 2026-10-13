# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original solution-specific BE time refinement; no qualification promotion.

Compare identical retained space/time samples from dt, dt/2 and dt/4.
Absolute Kelvin differences and rise above the initial field set acceptance.
Event clipping can defeat refinement and is reported rather than concealed.
"""
import copy
import math

import numpy as np

from .assembly_tetra_thermal_validation import keys, number, require, validate_request
from .assembly_tetra_transient import validate_transient_settings
from .multiboard_identity import canonical_json_digest

CONTRACT = 'spike/thermal-time-refinement/v1'


def run_time_refinement(request, settings, tolerances, *, runner, tetra_request,
                        problem=None, cancel_check=None):
    """Runner(settings) returns a completed, already admitted thermal history."""
    keys(tolerances, ('absolute_k', 'relative_rise'))
    absolute = number(tolerances['absolute_k'], 'absolute tolerance', positive=True)
    relative = number(tolerances['relative_rise'], 'relative tolerance', nonnegative=True)
    require(relative <= 1, 'Relative tolerance must be at most one.')
    base_step = number(settings['time_step_s'], 'time step', positive=True)
    runs, grids, results, setups = [], [], [], []
    data = validate_request(tetra_request)
    handoff = None
    if problem is not None:
        from .assembly_field_transient import _bind_canonical
        handoff, _, _, _ = _bind_canonical(request, problem)
    # Preflight every grid before spending time on any solve.
    for divisor in (1, 2, 4):
        require(cancel_check is None or not cancel_check(), 'Thermal refinement cancelled.')
        setup = copy.deepcopy(settings)
        setup['time_step_s'] = base_step / divisor
        # Runner and tetra settings can have different occurrence material IDs.
        if problem is not None:
            from .assembly_field_transient import remap_field_transient_settings
            admitted = remap_field_transient_settings(request, handoff, setup)
        else:
            admitted = setup
        grid = validate_transient_settings(data, admitted)['time_grid']
        grids.append(grid)
        setups.append(setup)
    for setup in setups:
        require(cancel_check is None or not cancel_check(), 'Thermal refinement cancelled.')
        result = runner(setup)
        field = result.get('field_result', result)
        frames = field['frames']
        times = [frame['time_s'] for frame in frames]
        values = np.array([frame['node_temperatures_k'] for frame in frames])
        require(values.ndim == 2 and np.isfinite(values).all(), 'Invalid refinement history.')
        balance = field['energy_balance']
        require(math.isfinite(balance['imbalance_j']) and
                abs(balance['imbalance_j']) <= balance['acceptance_tolerance_j'],
                'Refinement run failed energy conservation.')
        if runs:
            require(times == runs[0]['times'] and values.shape == runs[0]['values'].shape,
                    'Refinement samples differ in time or space.')
        runs.append({'times': times, 'values': values})
        results.append(result)
    require(cancel_check is None or not cancel_check(), 'Thermal refinement cancelled.')
    changes = [b['values'] - a['values'] for a, b in zip(runs, runs[1:])]
    maxima = [float(np.max(np.abs(delta))) for delta in changes]
    rise = float(np.max(np.abs(runs[-1]['values'] - runs[-1]['values'][0])))
    threshold = absolute + relative * rise
    independent = len(grids[0]) < len(grids[1]) < len(grids[2])
    noise = 128 * np.finfo(float).eps * max(1., float(np.max(np.abs(runs[-1]['values']))))
    uniform = all(np.allclose(np.diff(grid), settings['time_step_s'] / divisor,
                             rtol=1e-12, atol=0) for grid, divisor in zip(grids, (1, 2, 4)))
    significant = (np.abs(changes[0]) > noise) | (np.abs(changes[1]) > noise)
    same_direction = bool(np.any(significant) and np.all(
        changes[0][significant] * changes[1][significant] > 0))
    norms = [float(np.linalg.norm(delta)) for delta in changes]
    order = (math.log2(norms[0] / norms[1]) if uniform and same_direction and
             noise < maxima[1] < maxima[0] and norms[1] > 0 else None)
    status = ('event_grid_limited' if not independent else
              'within_requested_change' if maxima[1] <= threshold else 'refinement_required')
    evidence = {'contract': CONTRACT, 'status': status, 'production_qualified': False,
                'request_digest': canonical_json_digest(request),
                'settings_digest': canonical_json_digest(settings),
                'problem_digest': None if problem is None else canonical_json_digest(problem),
                'tolerances': copy.deepcopy(tolerances), 'acceptance_threshold_k': threshold,
                'fine_temperature_change_from_initial_k': rise,
                'coarse_to_medium_max_change_k': maxima[0], 'medium_to_fine_max_change_k': maxima[1],
                'medium_to_fine_rms_change_k': float(np.sqrt(np.mean(changes[1] ** 2))),
                'independent_time_refinement': independent, 'uniform_halved_grids': uniform,
                'same_direction_changes': same_direction, 'empirical_l2_order': order,
                'runs': [{'time_step_s': settings['time_step_s'] / divisor,
                          'steps': len(grid) - 1, 'full_record_sha256': canonical_json_digest(result),
                          'energy_balance': copy.deepcopy(result.get('field_result', result)['energy_balance'])}
                         for divisor, grid, result in zip((1, 2, 4), grids, results)],
                'limitations': ['solution-specific temporal change, not an error bound or hardware validation',
                                'mesh, source, material, boundary and fluid-model accuracy are not assessed',
                                'empirical order requires uniform halving and same-direction resolved changes']}
    evidence['evidence_digest'] = canonical_json_digest(evidence)
    return {'evidence': evidence, 'fine_result': results[-1]}


def run_assembly_time_refinement(request, problem, settings, tolerances, *, cancel_check=None):
    from .assembly_field_transient import _bind_canonical, run_assembly_field_transient
    from .assembly_field_handoff import bounded_json
    bounded_json({'request': request, 'problem': problem, 'settings': settings, 'tolerances': tolerances})
    _, tetra, _, _ = _bind_canonical(request, problem)
    output = run_time_refinement(request, settings, tolerances, problem=problem, tetra_request=tetra,
        cancel_check=cancel_check,
        runner=lambda setup: run_assembly_field_transient(request, problem, setup, cancel_check=cancel_check))
    bounded_json(output)
    return output
