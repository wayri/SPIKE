# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original bounded P1 solid thermal transient; see ASSEMBLY_THERMAL_TRANSIENT.md.

Integrating rho*cp*N_i*N_j gives V*rho*cp*(I+11^T)/20 (J/K).
Backward Euler advances M*(T-T_old)/dt + K*T + radiation(T) = f(t).
The consistent matrix is deliberately not replaced by a lumped approximation.
"""
from __future__ import annotations

import copy
import bisect
import math

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg

from .assembly_tetra_radiation import radiation_operator
from .assembly_tetra_thermal_validation import (
    AssemblyTetraThermalError, identifier, keys, number, require, validate_request,
)

SETTINGS_CONTRACT = 'spike/assembly-tetra-transient-settings/v1'
RESULT_CONTRACT = 'spike/assembly-tetra-transient-result/v1'
MAX_STEPS = 10000
MAX_FRAMES = 1001
MAX_FRAME_VALUES = 200000
MAX_SCHEDULE_POINTS = 1001


def validate_transient_settings(data, settings):
    """Admit SI settings and bounded event-aligned grids before assembly."""
    keys(settings, ('contract', 'duration_s', 'time_step_s', 'output_interval_s',
                    'initial_temperature_k', 'material_heat_capacity'), ('power_schedule',))
    require(settings['contract'] == SETTINGS_CONTRACT, 'Invalid transient settings contract.')
    duration, step, output = (number(settings[k], k, positive=True) for k in
                              ('duration_s', 'time_step_s', 'output_interval_s'))
    require(step <= duration and output <= duration, 'Time step/output interval exceeds duration.')
    require(duration / step <= MAX_STEPS and duration / output <= MAX_FRAMES - 1,
            'Transient step or output budget exceeded.')
    n = len(data['xyz'])
    initial = settings['initial_temperature_k']
    if isinstance(initial, list):
        require(len(initial) == n, 'Initial temperature node count mismatch.')
        initial = np.array([number(t, 'initial temperature', nonnegative=True) for t in initial])
    else:
        initial = np.full(n, number(initial, 'initial temperature', nonnegative=True))
    require(all(initial[node] == value for node, value in data['fixed'].items()),
            'Initial temperature must equal each fixed boundary temperature.')
    if data['radiation']:
        require(np.all(initial > 0) and np.all(initial <= 10000),
                'Radiation initial temperature range must be (0, 10000] K.')
    records = settings['material_heat_capacity']
    require(isinstance(records, list) and len(records) == len(data['tensors']),
            'Heat capacity required exactly once per material.')
    capacity = {}
    for record in records:
        keys(record, ('material_id', 'density_kg_m3', 'specific_heat_j_kgk'))
        mid = identifier(record['material_id'])
        require(mid in data['tensors'] and mid not in capacity, 'Unknown or duplicate heat-capacity material.')
        capacity[mid] = (number(record['density_kg_m3'], 'density', positive=True) *
                         number(record['specific_heat_j_kgk'], 'specific heat', positive=True))
        require(math.isfinite(capacity[mid]) and capacity[mid] > 0, 'Unrepresentable volumetric heat capacity.')
    schedule = settings.get('power_schedule', [{'time_s': 0., 'scale': 1.},
                                                {'time_s': duration, 'scale': 1.}])
    require(isinstance(schedule, list) and 2 <= len(schedule) <= MAX_SCHEDULE_POINTS,
            'Power schedule requires 2 to 1001 points.')
    admitted = []
    for record in schedule:
        keys(record, ('time_s', 'scale'))
        t = number(record['time_s'], 'schedule time', nonnegative=True)
        scale = number(record['scale'], 'power scale', nonnegative=True)
        require(t <= duration and (not admitted or t > admitted[-1][0]),
                'Power schedule times must increase within duration.')
        admitted.append((t, scale))
    require(admitted[0][0] == 0 and admitted[-1][0] == duration,
            'Power schedule must span exactly zero through duration.')

    time_tolerance = 16 * np.finfo(float).eps * duration

    def regular(interval):
        return [i * interval for i in range(math.ceil(duration / interval))
                if i * interval < duration - time_tolerance] + [duration]

    outputs = regular(output)
    # Arithmetic such as 3*0.2 and the authored knot 0.6 must represent one
    # event. Snap derived output instants to an adjacent authored source knot.
    knots = [t for t, _ in admitted]
    for i, t in enumerate(outputs):
        position = bisect.bisect_left(knots, t)
        for knot in knots[max(0, position - 1):position + 1]:
            if abs(t - knot) <= time_tolerance:
                outputs[i] = knot
                break
    require(len(outputs) <= MAX_FRAMES and len(outputs) * n <= MAX_FRAME_VALUES,
            'Retained transient frame memory budget exceeded.')
    # Keep canonical output/schedule events exact. Reject indistinguishable
    # authored source knots rather than silently changing their ordering.
    grid = sorted(set(regular(step) + outputs + [t for t, _ in admitted]))
    compact = [grid[0]]
    protected = set(outputs + [t for t, _ in admitted])
    for t in grid[1:]:
        if t - compact[-1] <= time_tolerance:
            require(not (t in protected and compact[-1] in protected),
                    'Transient event times are numerically indistinguishable.')
            if t in protected:
                compact[-1] = t
        else:
            compact.append(t)
    require(len(compact) - 1 <= MAX_STEPS, 'Event-aligned transient step budget exceeded.')
    return {'duration_s': duration, 'time_step_s': step, 'output_interval_s': output,
            'initial': initial, 'capacity': capacity, 'schedule': admitted,
            'output_times': outputs, 'time_grid': compact}


def _assemble(data, capacities, cancel):
    n = len(data['xyz'])
    entries = data['matrix_entry_budget']
    rows, cols = np.empty(entries, dtype=np.int32), np.empty(entries, dtype=np.int32)
    stiffness, mass = np.empty(entries), np.empty(entries)
    used = 0
    source, boundary = np.zeros(n), np.zeros(n)

    def block(nodes, matrix, capacity=None):
        nonlocal used
        require(np.isfinite(matrix).all(), 'Nonfinite transient stiffness.')
        if capacity is not None:
            require(np.isfinite(capacity).all(), 'Nonfinite transient capacity.')
        count = len(nodes) ** 2
        require(used + count <= entries, 'Sparse matrix entry budget exceeded.')
        rows[used:used + count] = np.repeat(nodes, len(nodes))
        cols[used:used + count] = np.tile(nodes, len(nodes))
        stiffness[used:used + count] = matrix.ravel()
        mass[used:used + count] = 0. if capacity is None else capacity.ravel()
        used += count

    for cell, (volume, gradients) in zip(data['cells'], data['geometry']):
        cancel()
        nodes = cell['vertices']
        block(nodes, volume * gradients @ data['tensors'][cell['material_id']] @ gradients.T,
              volume * capacities[cell['material_id']] * (np.eye(4) + np.ones((4, 4))) / 20)
        source[nodes] += volume * data['sources'].get(cell['id'], 0.) / 4
    face_mass = (np.eye(3) + np.ones((3, 3))) / 12
    for face, area, h, ambient in data['convection']:
        block(face, h * area * face_mass)
        boundary[list(face)] += h * area * ambient / 3
    for face, area, flux in data['fluxes']:
        boundary[list(face)] += area * flux / 3
    for _, left, right, area, h in data['contacts']:
        local = area * h * face_mass
        block(left + right, np.block([[local, -local], [-local, local]]))
    require(np.isfinite(source).all() and np.isfinite(boundary).all(), 'Nonfinite transient load.')
    k = coo_matrix((stiffness[:used], (rows[:used], cols[:used])), shape=(n, n)).tocsr()
    m = coo_matrix((mass[:used], (rows[:used], cols[:used])), shape=(n, n)).tocsr()
    m.eliminate_zeros()
    require(np.all(m.diagonal() > 0), 'Nonpositive heat capacity.')
    return k, m, source, boundary


def _step(k, m, old, dt, load, data, free, cancel):
    """Solve increments; avoid subtracting two large M*T/dt load vectors."""
    operator = k + m / dt
    temperature = old.copy()
    iterations = 0
    scale = max(float(np.linalg.norm(load[free])), float(np.linalg.norm((k @ old)[free])), 1e-30)
    radiation = data['radiation']
    for newton in range(81):
        cancel()
        power, tangent = radiation_operator(temperature, radiation)
        storage = m @ ((temperature - old) / dt)
        residual = storage + k @ temperature + power - load
        scale = max(scale, float(np.linalg.norm(power[free])), float(np.linalg.norm(storage[free])))
        norm = float(np.linalg.norm(residual[free]))
        # Arithmetic floor covers subtracting nearby Kelvin values in dT/dt.
        floor = 32 * np.finfo(float).eps * float(np.linalg.norm(
            np.abs(operator[free]) @ np.abs(temperature)))
        if norm <= 1e-10 * scale + floor:
            return temperature, power, residual, newton, iterations, float(norm / max(scale, floor / 1e-10))
        require(newton < 80, 'Bounded transient Newton iteration did not converge.')
        a = (operator + tangent)[free][:, free]
        diagonal = a.diagonal()
        require(np.isfinite(diagonal).all() and np.all(diagonal > 0), 'Nonpositive transient tangent.')
        scaling = 1 / np.sqrt(diagonal)

        def count(_):
            nonlocal iterations
            iterations += 1
            cancel()

        delta, info = cg(diags(scaling) @ a @ diags(scaling), -scaling * residual[free],
                         rtol=1e-12, atol=0, maxiter=min(100000, max(1000, 20 * len(free))), callback=count)
        require(info == 0 and np.isfinite(delta).all(), 'Bounded transient CG did not converge.')
        delta *= scaling
        accepted = False
        for backtrack in range(30):
            cancel()
            alpha = 0.5 ** backtrack
            trial = temperature.copy()
            trial[free] += alpha * delta
            if np.any(trial < 0) or (radiation and (np.any(trial <= 0) or np.any(trial > 10000))):
                continue
            heat, _ = radiation_operator(trial, radiation)
            trial_residual = m @ ((trial - old) / dt) + k @ trial + heat - load
            if np.linalg.norm(trial_residual[free]) <= (1 - 1e-4 * alpha) * norm + floor:
                temperature = trial
                accepted = True
                break
        require(accepted, 'Transient Newton line search failed or temperature range exceeded.')


def run_assembly_tetra_transient(request, transient, *, progress_callback=None, cancel_check=None):
    """Return real solved frames, or raise; callbacks never imply completion.

    progress_callback(frame) receives an independent frame at each retained
    time. cancel_check() returning true aborts without returning a partial result.
    """
    def cancel():
        require(cancel_check is None or not cancel_check(), 'Transient thermal solve cancelled.')

    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            cancel()
            data = validate_request(request)
            settings = validate_transient_settings(data, transient)
            cancel()
            return _run(data, settings, progress_callback, cancel)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        raise AssemblyTetraThermalError('Transient input or operator is numerically unrepresentable.') from exc


def _run(data, settings, progress, cancel):
    k, m, source, boundary = _assemble(data, settings['capacity'], cancel)
    temperature = settings['initial'].copy()
    initial = temperature.copy()
    fixed = np.array(sorted(data['fixed']), dtype=int)
    free = np.array([i for i in range(len(temperature)) if i not in data['fixed']], dtype=int)
    frames = []
    totals = {key: 0. for key in ('source_j', 'prescribed_flux_inward_j', 'temperature_reaction_inward_j',
                                  'convection_outward_j', 'radiation_outward_j')}
    balance = None
    total_cg, total_newton, max_residual, max_relative = 0, 0, 0., 0.
    accumulated_tolerance = 0.

    def emit(t):
        frame = {'time_s': float(t), 'node_temperatures_k': temperature.tolist(),
                 'minimum_k': float(np.min(temperature)), 'maximum_k': float(np.max(temperature)),
                 'stored_energy_change_j': float(np.sum(m @ (temperature - initial))),
                 'heat_balance': copy.deepcopy(balance)}
        frames.append(frame)
        if progress is not None:
            progress(copy.deepcopy(frame))
        cancel()

    emit(0.)
    outputs = set(settings['output_times'])
    schedule_times, schedule_scales = zip(*settings['schedule'])
    times = settings['time_grid']
    for old_time, time in zip(times, times[1:]):
        cancel()
        dt = time - old_time
        scale = float(np.interp(time, schedule_times, schedule_scales))
        load = boundary + source * scale
        old = temperature
        temperature, radiation, reactions, newton, cg_count, relative = _step(
            k, m, old, dt, load, data, free, cancel)
        require(np.isfinite(temperature).all(), 'Nonfinite transient temperature.')
        total_cg += cg_count
        total_newton += newton
        max_residual = max(max_residual, float(np.max(np.abs(reactions[free]), initial=0)))
        max_relative = max(max_relative, relative)
        balance = {'source_w': float(np.sum(source)) * scale,
                   'prescribed_flux_inward_w': sum(a * q for _, a, q in data['fluxes']),
                   'temperature_reaction_inward_w': float(np.sum(reactions[fixed])),
                   'convection_outward_w': sum(a * h * (float(np.mean(temperature[list(f)])) - ambient)
                                                for f, a, h, ambient in data['convection']),
                   'radiation_outward_w': float(np.sum(radiation)),
                   'storage_rate_w': float(np.sum(m @ ((temperature - old) / dt)))}
        imbalance = (balance['source_w'] + balance['prescribed_flux_inward_w'] +
                     balance['temperature_reaction_inward_w'] - balance['convection_outward_w'] -
                     balance['radiation_outward_w'] - balance['storage_rate_w'])
        tolerance = 1e-8 * max(sum(abs(v) for v in balance.values()), 1e-30)
        tolerance += 128 * np.finfo(float).eps * float(np.sum(
            np.abs(k + m / dt) @ np.abs(temperature)))
        require(abs(imbalance) <= tolerance, 'Transient global heat balance tolerance exceeded.')
        balance.update(imbalance_w=float(imbalance), acceptance_tolerance_w=float(tolerance))
        accumulated_tolerance += tolerance * dt
        for key in totals:
            totals[key] += balance[key[:-1] + 'w'] * dt
        if time in outputs:
            emit(time)
    stored = float(np.sum(m @ (temperature - initial)))
    energy_error = (totals['source_j'] + totals['prescribed_flux_inward_j'] +
                    totals['temperature_reaction_inward_j'] - totals['convection_outward_j'] -
                    totals['radiation_outward_j'] - stored)
    require(math.isfinite(energy_error) and abs(energy_error) <= accumulated_tolerance,
            'Transient integrated energy balance tolerance exceeded.')
    fluxes = [{'cell_id': cell['id'], 'volume_m3': volume,
               'heat_flux_w_m2': (-data['tensors'][cell['material_id']] @
                                  (gradients.T @ temperature[cell['vertices']])).tolist()}
              for cell, (volume, gradients) in zip(data['cells'], data['geometry'])]
    contacts = []
    for sid, left, right, area, h in data['contacts']:
        jump = float(np.mean(temperature[list(left)] - temperature[list(right)]))
        contacts.append({'id': sid, 'left_to_right_heat_w': area * h * jump,
                         'mean_temperature_jump_k': jump})
    return {'contract': RESULT_CONTRACT, 'status': 'experimental', 'model_status': 'experimental',
            'production_qualified': False, 'mode': 'transient', 'temperature_units': 'K',
            'node_temperatures_k': temperature.tolist(), 'cell_heat_flux_w_m2': fluxes,
            'contacts': contacts, 'reactions_w': {str(i): float(reactions[i]) for i in fixed},
            'frames': frames, 'heat_balance': balance,
            'energy_balance': {**totals, 'stored_energy_change_j': stored,
                               'imbalance_j': float(energy_error), 'acceptance_tolerance_j': float(accumulated_tolerance)},
            'diagnostics': {'method': 'backward_euler', 'capacity_matrix': 'consistent_P1',
                            'cg_iterations': total_cg, 'newton_iterations': total_newton,
                            'free_relative_residual': max_relative, 'free_max_residual_w': max_residual,
                            'max_element_jacobian_condition': data['max_condition'],
                            'temporal_convergence_verified': False},
            'boundary_evidence': {'omitted_faces_are_adiabatic': True,
                                  'omitted_adiabatic_faces': [list(f) for f in data['omitted']],
                                  'heat_flux_sign': 'positive_inward'},
            'resources': {'nodes': len(temperature), 'tetrahedra': len(data['cells']),
                          'matrix_nonzeros': int(k.nnz), 'capacity_nonzeros': int(m.nnz),
                          'steps': len(times) - 1, 'frames': len(frames),
                          'limits': {'steps': MAX_STEPS, 'frames': MAX_FRAMES, 'frame_values': MAX_FRAME_VALUES}},
            'limitations': ['experimental P1 transient solid conduction with constant material properties',
                            'backward Euler is first order; time-step and mesh convergence require separate studies',
                            'prescribed fixed boundaries and ambient radiation; no airflow or enclosure radiosity',
                            'piecewise-linear source scale sampled at step endpoints',
                            'consistent capacity is not positivity preserving on arbitrary meshes; negative Kelvin rejected',
                            'no temperature-dependent properties, phase change or production qualification']}
