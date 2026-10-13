# SPDX-License-Identifier: Apache-2.0
"""Bounded original transient CalculiX adapter; no upstream source is included."""
from __future__ import annotations

import copy
import hashlib
import math
import re

import numpy as np

from .assembly_field_handoff import bounded_json
from .assembly_tetra_thermal_validation import validate_request
from .calculix_deck import compile_calculix_deck
from .calculix_runtime import run_calculix_deck
from .calculix_thermal import _bind_canonical, _field_from_temperatures
from .multiboard_identity import canonical_json_digest

LIMITATIONS = [
    'Experimental external DC3D4 transient solid thermal adapter; not production qualified.',
    'Constant positive density, specific heat and conductivity; no phase change or airflow.',
    'Prescribed ambient convection/radiation and explicit congruent contact faces only.',
    'Unspecified exterior faces are adiabatic; temperatures use Kelvin and geometry uses SI.',
    'Fixed backward time increments require a separate timestep and mesh convergence study.',
    'CalculiX is separately installed; no upstream solver or fixture is redistributed.',
]


def compile_calculix_transient_deck(request, settings):
    """Reuse steady geometry cards with capacity and one fixed increment per step."""
    from .assembly_tetra_transient import validate_transient_settings
    data = validate_request(request)
    admitted = validate_transient_settings(data, settings)
    steps = len(admitted['time_grid']) - 1
    if steps * len(data['xyz']) > 500000:
        raise ValueError('CALCULIX_TRANSIENT_LIMIT: increment-node history budget exceeded.')
    compiled = compile_calculix_deck(request, require_steady_sink=False)
    base, remainder = compiled['deck'].split('*INITIAL CONDITIONS,TYPE=TEMPERATURE\n', 1)
    lines = base.splitlines()
    # Insert heat storage in the same MATERIAL block as its conductivity.
    capacities = {row['material_id']: row for row in settings['material_heat_capacity']}
    for mid, name in compiled['material_map'].items():
        index = lines.index(f'*MATERIAL,NAME={name}') + 1
        row = capacities[mid]
        lines[index:index] = ['*DENSITY', format(row['density_kg_m3'], '.17g'),
                              '*SPECIFIC HEAT', format(row['specific_heat_j_kgk'], '.17g')]
    lines[1] = 'SPIKE original transient thermal SI deck'
    lines += ['*INITIAL CONDITIONS,TYPE=TEMPERATURE']
    lines += [f'{i},{t:.17g}' for i, t in enumerate(admitted['initial'], 1)]
    # The shared compiler is authoritative for all face/element load mappings.
    load_lines = remainder.split('*NODE PRINT,', 1)[0].splitlines()[4:]
    estimated_bytes = (len(compiled['deck']) + 64*len(data['xyz']) +
                       steps*(256 + sum(len(line)+40 for line in load_lines)))
    if estimated_bytes > 8*1024**2:
        raise ValueError('CALCULIX_TRANSIENT_LIMIT: expanded input deck budget exceeded.')
    schedule = np.asarray(admitted['schedule'], dtype=float)
    for start, stop in zip(admitted['time_grid'], admitted['time_grid'][1:]):
        dt = stop - start
        # CalculiX reads each HEAT TRANSFER numeric field in a 20-character
        # buffer. 17-digit scientific notation can exceed it at PWM scales.
        # Preserve already-admitted ordinary increments and their deck hashes;
        # use twelve significant digits only for an overlong field (<=5e-12
        # relative rounding error). No stale evidence needs reinterpretation.
        increment = format(dt, '.17g')
        if len(increment) > 20:
            increment = format(dt, '.12g')
        lines += ['*STEP,INC=1', '*HEAT TRANSFER,DIRECT,SOLVER=ITERATIVE CHOLESKY', f'{increment},{increment}']
        scale = float(np.interp(stop, schedule[:, 0], schedule[:, 1]))
        in_flux = False
        for line in load_lines:
            if line.startswith('*'):
                in_flux = line == '*DFLUX'
            if in_flux and not line.startswith('*'):
                parts = line.split(',')
                if parts[1] == 'BF':
                    parts[-1] = format(float(parts[-1]) * scale, '.17g')
                line = ','.join(parts)
            lines.append(line)
        lines += ['*NODE PRINT,NSET=NALL,FREQUENCY=1', 'NT', '*END STEP']
    compiled.update(deck='\n'.join(lines) + '\n', transient_settings_digest=canonical_json_digest(settings),
                    time_grid=admitted['time_grid'], output_times=admitted['output_times'])
    return compiled


def parse_calculix_temperature_history(text, count, expected_times):
    """Admit every increment in order; reject missing, repeated or partial tables."""
    blocks, current, current_time = [], None, None
    header = re.compile(r'temperatures(?:\s*\(.*?\))?\s+for\s+set\s+NALL\s+and\s+time\s+(\S+)', re.I)
    for line in text.splitlines():
        match = header.search(line)
        if match:
            if current is not None:
                blocks.append((current_time, current))
            current_time = float(match.group(1).replace('D', 'E').replace('d', 'e'))
            current = {}
            continue
        if current is None or not line.strip():
            continue
        if re.match(r'\s*(?:S T E P|INCREMENT)\s+\d+\s*$', line):
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[0].isdigit():
            raise ValueError('CALCULIX_OUTPUT: unexpected transient NT row.')
        node = int(parts[0])
        value = float(parts[1].replace('D', 'E').replace('d', 'e'))
        if node in current or not 1 <= node <= count or not math.isfinite(value) or value < 0:
            raise ValueError('CALCULIX_OUTPUT: invalid transient nodal temperature.')
        current[node] = value
    if current is not None:
        blocks.append((current_time, current))
    if len(blocks) != len(expected_times):
        raise ValueError('CALCULIX_INCOMPLETE: transient increment history is incomplete.')
    frames = []
    for (time_s, nodes), expected in zip(blocks, expected_times):
        if not math.isfinite(time_s) or not math.isclose(time_s, expected, rel_tol=2e-6, abs_tol=1e-10):
            raise ValueError('CALCULIX_INCOMPLETE: transient increment time mismatch.')
        if len(nodes) != count:
            raise ValueError('CALCULIX_INCOMPLETE: transient temperature mesh coverage is incomplete.')
        frames.append({'time_s': expected, 'node_temperatures_k': [nodes[i] for i in range(1, count+1)]})
    return frames


def run_calculix_transient(request, settings, engine_options=None, *, cancel_check=None):
    """Execute an admitted solid transient and return final field plus retained frames."""
    from .assembly_tetra_transient import validate_transient_settings
    data = validate_request(request)
    admitted = validate_transient_settings(data, settings)
    compiled = compile_calculix_transient_deck(request, settings)
    execution = run_calculix_deck(compiled, engine_options, cancel_check=cancel_check,
        temperature_parser=lambda text, count: parse_calculix_temperature_history(text, count, compiled['time_grid'][1:]),
        completed_step_time=admitted['duration_s'])
    history = execution.pop('node_temperatures_k')
    all_frames = [{'time_s': 0., 'node_temperatures_k': admitted['initial'].tolist()}, *history]
    frames = []
    for frame in all_frames:
        _check_frame(data, frame['node_temperatures_k'])
        if any(math.isclose(frame['time_s'], t, rel_tol=1e-12, abs_tol=1e-12) for t in admitted['output_times']):
            frames.append({**frame, 'minimum_k': min(frame['node_temperatures_k']),
                           'maximum_k': max(frame['node_temperatures_k'])})
    field = _field_from_temperatures(request, history[-1]['node_temperatures_k'])
    field.update(contract='spike/calculix-transient-field/v1', mode='transient',
                 frames=frames,
                 transient_settings=copy.deepcopy(settings), execution=execution)
    field['diagnostics']['convergence_source'] = 'CalculiX successful completion and every requested increment NT coverage'
    field['diagnostics']['temporal_convergence_verified'] = False
    return field


def _check_frame(data, values):
    if (not isinstance(values, list) or len(values) != len(data['xyz']) or
            any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values)):
        raise ValueError('CALCULIX_RESULT: invalid transient temperature coverage or range.')
    if any(not math.isclose(values[i], t, rel_tol=2e-6, abs_tol=2e-6) for i, t in data['fixed'].items()):
        raise ValueError('CALCULIX_RESULT: transient prescribed temperature differs.')


def _field_envelope(request, problem, settings, field, compiled):
    from .assembly_field_transient import _occurrences
    handoff, _, assigned, contacts = _bind_canonical(request, problem)
    result = {'contract': 'spike/calculix-field-transient-result/v1', 'mode': 'transient',
              'model_status': 'experimental', 'production_qualified': False, 'solver_id': 'external.calculix',
              **{k: handoff[k] for k in ('assembly_digest', 'request_digest', 'handoff_digest', 'source_traceability')},
              'problem_digest': canonical_json_digest(problem),
              'transient_digest': canonical_json_digest(settings), 'transient_settings': copy.deepcopy(settings),
              'field_result': field,
              'occurrence_temperatures': _occurrences(field['node_temperatures_k'], handoff['source_traceability']),
              'adiabatic_face_ids': [f['id'] for f in handoff['boundary_faces'] if f['id'] not in assigned | contacts],
              'limitations': list(LIMITATIONS),
              'deck_identity': {k: compiled[k] for k in ('tetra_request_digest', 'transient_settings_digest',
                  'node_map', 'element_map', 'material_map', 'boundary_map', 'contact_map')}}
    result['result_digest'] = canonical_json_digest(result)
    bounded_json(result)
    return result


def run_calculix_field_transient(request, problem, settings, engine_options=None, *, cancel_check=None):
    """Preserve retained occurrence/material identity across the external execution."""
    from .assembly_field_transient import remap_field_transient_settings
    bounded_json(settings)
    handoff, tetra, _, _ = _bind_canonical(request, problem)
    remapped = remap_field_transient_settings(request, handoff, settings)
    field = run_calculix_transient(tetra, remapped, engine_options, cancel_check=cancel_check)
    return _field_envelope(request, problem, settings, field, compile_calculix_transient_deck(tetra, remapped))


def verify_calculix_field_transient_result(request, problem, result):
    """Check history integrity and binding offline; artifact hashes are not authenticity."""
    from .assembly_field_transient import remap_field_transient_settings
    from .assembly_tetra_transient import validate_transient_settings
    bounded_json(result)
    if not isinstance(result, dict) or result.get('contract') != 'spike/calculix-field-transient-result/v1':
        raise ValueError('CALCULIX_RESULT: unsupported transient result contract.')
    if result.get('result_digest') != canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'}):
        raise ValueError('CALCULIX_RESULT_DIGEST: saved transient result was changed.')
    handoff, tetra, _, _ = _bind_canonical(request, problem)
    settings = result.get('transient_settings')
    remapped = remap_field_transient_settings(request, handoff, settings)
    data = validate_request(tetra)
    admitted = validate_transient_settings(data, remapped)
    compiled = compile_calculix_transient_deck(tetra, remapped)
    field = result.get('field_result', {})
    frames = field.get('frames')
    if not isinstance(frames, list) or len(frames) != len(admitted['output_times']):
        raise ValueError('CALCULIX_RESULT: missing transient history frames.')
    for frame, time_s in zip(frames, admitted['output_times']):
        if not isinstance(frame, dict) or frame.get('time_s') != time_s:
            raise ValueError('CALCULIX_RESULT: saved transient frame times differ.')
        values = frame.get('node_temperatures_k')
        _check_frame(data, values)
        if frame != {'time_s': time_s, 'node_temperatures_k': values,
                      'minimum_k': min(values), 'maximum_k': max(values)}:
            raise ValueError('CALCULIX_RESULT: transient frame extrema differ.')
    if frames[0]['node_temperatures_k'] != admitted['initial'].tolist():
        raise ValueError('CALCULIX_RESULT: transient initial conditions differ.')
    execution = field.get('execution', {})
    if (execution.get('input_sha256') != hashlib.sha256(compiled['deck'].encode('ascii')).hexdigest()
            or execution.get('exit_code') != 0 or execution.get('solver_reported_finished') is not True
            or execution.get('completed_step_time') != admitted['duration_s']):
        raise ValueError('CALCULIX_RESULT: missing completed transient execution evidence.')
    for key in ('output_sha256', 'log_sha256'):
        value = execution.get(key)
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('CALCULIX_RESULT: invalid transient execution artifact digest.')
    expected = _field_from_temperatures(tetra, frames[-1]['node_temperatures_k'])
    expected.update(contract='spike/calculix-transient-field/v1', mode='transient', frames=frames,
                    transient_settings=remapped, execution=execution)
    expected['diagnostics']['convergence_source'] = 'CalculiX successful completion and every requested increment NT coverage'
    expected['diagnostics']['temporal_convergence_verified'] = False
    if field != expected:
        raise ValueError('CALCULIX_RESULT: saved transient field derivation differs.')
    if result != _field_envelope(request, problem, settings, expected, compiled):
        raise ValueError('CALCULIX_STALE: geometry, problem, transient settings or result metadata differs.')
    return copy.deepcopy(result)


def compare_thermal_transient_results(request, problem, internal, external, *,
                                      absolute_tolerance_k, relative_tolerance):
    """Compare verified identical geometry/time histories; relative error is on rise."""
    from .assembly_field_transient import verify_assembly_field_transient_result
    verify_assembly_field_transient_result(request, problem, internal)
    verify_calculix_field_transient_result(request, problem, external)
    if internal['transient_settings'] != external['transient_settings']:
        raise ValueError('CALCULIX_COMPARISON: transient settings and timestep must match.')
    return compare_transient_fields(internal['field_result'], external['field_result'],
        absolute_tolerance_k=absolute_tolerance_k, relative_tolerance=relative_tolerance)


def compare_transient_fields(internal, external, *, absolute_tolerance_k, relative_tolerance):
    """Nodal comparison primitive for already admitted benchmark fixture fields."""
    from .assembly_tetra_thermal_validation import number
    absolute_tolerance_k = number(absolute_tolerance_k, 'absolute comparison tolerance', nonnegative=True)
    relative_tolerance = number(relative_tolerance, 'relative comparison tolerance', nonnegative=True)
    left, right = internal['frames'], external['frames']
    if [f['time_s'] for f in left] != [f['time_s'] for f in right]:
        raise ValueError('CALCULIX_COMPARISON: retained times must match exactly.')
    a = np.asarray([f['node_temperatures_k'] for f in left], dtype=float)
    b = np.asarray([f['node_temperatures_k'] for f in right], dtype=float)
    if a.shape != b.shape or a.ndim != 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('CALCULIX_COMPARISON: complete finite node histories required.')
    if not np.array_equal(a[0], b[0]):
        raise ValueError('CALCULIX_COMPARISON: initial nodal temperatures must match.')
    error = np.abs(a-b)
    excursion = np.abs(b-b[0])
    tolerances = absolute_tolerance_k + relative_tolerance * excursion
    worst = np.unravel_index(int(np.argmax(error)), error.shape)
    return {'contract': 'spike/thermal-transient-comparison/v1',
            'passed': bool(np.all(error <= tolerances)), 'nodes': int(a.shape[1]), 'frames': int(a.shape[0]),
            'maximum_absolute_error_k': float(error.max()), 'rms_error_k': float(np.sqrt(np.mean(error**2))),
            'worst_time_s': left[worst[0]]['time_s'], 'worst_node_index': int(worst[1]),
            'absolute_tolerance_k': absolute_tolerance_k, 'relative_tolerance': relative_tolerance,
            'relative_basis': 'per-node absolute temperature change from initial state in CalculiX',
            'limitation': 'Cross-engine agreement is numerical evidence, not measured physical accuracy or Fang parity.'}
