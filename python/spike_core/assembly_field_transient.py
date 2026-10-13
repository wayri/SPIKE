# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Retained occurrence binding and admission for experimental thermal history."""
import copy
import math

import numpy as np

from .assembly_field_handoff import bounded_json
from .assembly_field_thermal import bind_assembly_field_thermal
from .assembly_tetra_thermal_validation import keys, number, require, validate_request
from .assembly_tetra_transient import (
    RESULT_CONTRACT, run_assembly_tetra_transient, validate_transient_settings,
)
from .multiboard_identity import canonical_json_digest

FIELD_RESULT_CONTRACT = 'spike/assembly-field-transient-result/v1'


def _bind_canonical(request, problem):
    """Admit raw input, then bind the same AssemblyIR defaults as native saves.

    Only assembly serialization defaults and saved reduced-study output are
    normalized. Mesh, source, material, boundary and placement identities keep
    their existing exact digest checks.
    """
    admitted = bind_assembly_field_thermal(request, problem)
    from .multiboard_study import physical_assembly
    assembly = physical_assembly(request['assembly'])
    if assembly == request['assembly']:
        return admitted
    canonical = copy.deepcopy(request)
    canonical['assembly'] = assembly
    return bind_assembly_field_thermal(canonical, problem)


def remap_field_transient_settings(request, handoff, settings):
    """Expand authored physical material capacities to occurrence materials."""
    require(isinstance(settings, dict), 'Transient settings object required.')
    records = settings.get('material_heat_capacity')
    require(isinstance(records, list) and len(records) == len(request['materials']),
            'Heat capacity required exactly once per authored material.')
    physical = {m['id'] for m in request['materials']}
    capacities = {}
    for record in records:
        keys(record, ('material_id', 'density_kg_m3', 'specific_heat_j_kgk'))
        mid = record['material_id']
        require(isinstance(mid, str) and mid in physical and mid not in capacities,
                'Unknown or duplicate authored heat-capacity material.')
        capacities[mid] = record
    remapped = copy.deepcopy(settings)
    remapped['material_heat_capacity'] = []
    traces = {t['occurrence_id']: t for t in handoff['source_traceability']}
    for body in request['bodies']:
        trace = traces[body['occurrence_id']]
        for local, physical_id in body['material_map'].items():
            remapped['material_heat_capacity'].append({**capacities[physical_id],
                                                       'material_id': trace['material_map'][local]})
    return remapped


def validate_field_transient_settings(request, problem, settings):
    """Validate geometry, occurrence problem and capacity/time setup without solving."""
    bounded_json(settings)
    handoff, tetra, _, _ = _bind_canonical(request, problem)
    remapped = remap_field_transient_settings(request, handoff, settings)
    validate_transient_settings(validate_request(tetra), remapped)
    return remapped


def _occurrences(temperatures, traces):
    output = {}
    for trace in traces:
        start, stop = trace['vertex_range']
        samples = temperatures[start:stop]
        output[trace['occurrence_id']] = {'minimum_k': min(samples), 'maximum_k': max(samples),
                                          'vertex_range': [start, stop]}
    return output


def run_assembly_field_transient(request, problem, transient, *, progress_callback=None, cancel_check=None):
    bounded_json(transient)
    require(cancel_check is None or not cancel_check(), 'Transient thermal solve cancelled.')
    handoff, tetra, assigned, contacts = _bind_canonical(request, problem)
    remapped = remap_field_transient_settings(request, handoff, transient)
    field = run_assembly_tetra_transient(tetra, remapped, progress_callback=progress_callback,
                                         cancel_check=cancel_check)
    result = {'contract': FIELD_RESULT_CONTRACT, 'mode': 'transient', 'model_status': 'experimental',
              'production_qualified': False, 'assembly_digest': handoff['assembly_digest'],
              'request_digest': handoff['request_digest'], 'handoff_digest': handoff['handoff_digest'],
              'problem_digest': canonical_json_digest(problem), 'transient_digest': canonical_json_digest(transient),
              'transient_settings': copy.deepcopy(transient), 'field_result': field,
              'occurrence_temperatures': _occurrences(field['node_temperatures_k'], handoff['source_traceability']),
              'source_traceability': handoff['source_traceability'],
              'adiabatic_face_ids': [f['id'] for f in handoff['boundary_faces'] if f['id'] not in assigned | contacts],
              'limitations': field['limitations'] + [
                  'retained tetrahedral geometry only; no automatic PCB or STEP fidelity qualification']}
    result['result_digest'] = canonical_json_digest(result)
    bounded_json(result)
    return result


def _close(actual, expected, label, atol=1e-8):
    require(math.isclose(number(actual, label), expected, rel_tol=1e-10, abs_tol=atol),
            f'Transient result inconsistent {label}.')


def _balance(balance):
    keys(balance, ('source_w', 'prescribed_flux_inward_w', 'temperature_reaction_inward_w',
                   'convection_outward_w', 'radiation_outward_w', 'storage_rate_w',
                   'imbalance_w', 'acceptance_tolerance_w'))
    for value in balance.values():
        number(value, 'heat balance')
    tolerance = number(balance['acceptance_tolerance_w'], 'balance tolerance', nonnegative=True)
    computed = (balance['source_w'] + balance['prescribed_flux_inward_w'] +
                balance['temperature_reaction_inward_w'] - balance['convection_outward_w'] -
                balance['radiation_outward_w'] - balance['storage_rate_w'])
    require(abs(balance['imbalance_w']) <= tolerance and abs(computed - balance['imbalance_w']) <= tolerance,
            'Transient heat balance failed.')


def verify_assembly_field_transient_result(request, problem, result):
    """Validate retained identity, shape and reported invariants, not authenticity."""
    bounded_json(result)
    keys(result, ('contract', 'mode', 'model_status', 'production_qualified', 'assembly_digest',
                  'request_digest', 'handoff_digest', 'problem_digest', 'transient_digest', 'transient_settings',
                  'field_result', 'occurrence_temperatures', 'source_traceability', 'adiabatic_face_ids',
                  'limitations', 'result_digest'))
    require(result['contract'] == FIELD_RESULT_CONTRACT and result['mode'] == 'transient' and
            result['model_status'] == 'experimental' and result['production_qualified'] is False,
            'Invalid transient result contract/status.')
    require(result['result_digest'] == canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'}),
            'Transient result digest mismatch.')
    handoff, tetra, assigned, contacts = _bind_canonical(request, problem)
    for key in ('assembly_digest', 'request_digest', 'handoff_digest'):
        require(result[key] == handoff[key], 'Transient result stale geometry/material identity.')
    require(result['problem_digest'] == canonical_json_digest(problem), 'Transient result stale problem.')
    require(result['transient_digest'] == canonical_json_digest(result['transient_settings']),
            'Transient settings digest mismatch.')
    data = validate_request(tetra)
    settings = validate_transient_settings(data, remap_field_transient_settings(
        request, handoff, result['transient_settings']))
    field = result['field_result']
    keys(field, ('contract', 'status', 'model_status', 'production_qualified', 'mode', 'temperature_units',
                 'node_temperatures_k', 'cell_heat_flux_w_m2', 'contacts', 'reactions_w', 'frames',
                 'heat_balance', 'energy_balance', 'diagnostics', 'boundary_evidence', 'resources', 'limitations'))
    require(field['contract'] == RESULT_CONTRACT and field['status'] == field['model_status'] == 'experimental' and
            field['production_qualified'] is False and field['mode'] == 'transient' and field['temperature_units'] == 'K',
            'Invalid transient field status or units.')
    frames = field['frames']
    require(isinstance(frames, list) and len(frames) == len(settings['output_times']),
            'Transient frame count mismatch.')
    weights = np.zeros(len(data['xyz']))
    for cell, (volume, _) in zip(data['cells'], data['geometry']):
        weights[cell['vertices']] += volume * settings['capacity'][cell['material_id']] / 4
    for index, (frame, time) in enumerate(zip(frames, settings['output_times'])):
        keys(frame, ('time_s', 'node_temperatures_k', 'minimum_k', 'maximum_k', 'stored_energy_change_j', 'heat_balance'))
        require(number(frame['time_s'], 'frame time') == time, 'Transient frame time mismatch.')
        values = frame['node_temperatures_k']
        require(isinstance(values, list) and len(values) == len(weights), 'Transient node count mismatch.')
        values = np.array([number(t, 'temperature', nonnegative=True) for t in values])
        require(all(values[i] == t for i, t in data['fixed'].items()), 'Changed fixed transient temperature.')
        if data['radiation']:
            require(np.all(values > 0) and np.all(values <= 10000), 'Invalid transient radiation temperature.')
        _close(frame['minimum_k'], float(values.min()), 'frame minimum')
        _close(frame['maximum_k'], float(values.max()), 'frame maximum')
        _close(frame['stored_energy_change_j'], float(weights @ (values - settings['initial'])), 'stored energy')
        if index == 0:
            require(values.tolist() == settings['initial'].tolist() and frame['heat_balance'] is None,
                    'Initial transient frame changed.')
        else:
            _balance(frame['heat_balance'])
    require(field['node_temperatures_k'] == frames[-1]['node_temperatures_k'] and
            field['heat_balance'] == frames[-1]['heat_balance'], 'Transient final frame mismatch.')
    require(result['source_traceability'] == handoff['source_traceability'], 'Transient source ownership changed.')
    require(result['occurrence_temperatures'] == _occurrences(field['node_temperatures_k'], handoff['source_traceability']),
            'Transient occurrence temperatures changed.')
    require(result['adiabatic_face_ids'] == [f['id'] for f in handoff['boundary_faces']
                                           if f['id'] not in assigned | contacts], 'Transient adiabatic faces changed.')
    energy = field['energy_balance']
    keys(energy, ('source_j', 'prescribed_flux_inward_j', 'temperature_reaction_inward_j', 'convection_outward_j',
                  'radiation_outward_j', 'stored_energy_change_j', 'imbalance_j', 'acceptance_tolerance_j'))
    for value in energy.values():
        number(value, 'energy balance')
    tolerance = number(energy['acceptance_tolerance_j'], 'energy tolerance', nonnegative=True)
    computed = (energy['source_j'] + energy['prescribed_flux_inward_j'] + energy['temperature_reaction_inward_j'] -
                energy['convection_outward_j'] - energy['radiation_outward_j'] - energy['stored_energy_change_j'])
    require(abs(energy['imbalance_j']) <= tolerance and abs(computed - energy['imbalance_j']) <= tolerance,
            'Transient integrated energy balance failed.')
    _close(energy['stored_energy_change_j'], frames[-1]['stored_energy_change_j'], 'final stored energy')
    _verify_final_fields(field, data, settings)
    return copy.deepcopy(result)


def _verify_final_fields(field, data, settings):
    values = np.array(field['node_temperatures_k'])
    fluxes = field['cell_heat_flux_w_m2']
    require(isinstance(fluxes, list) and len(fluxes) == len(data['cells']), 'Transient cell flux count mismatch.')
    for item, cell, (volume, gradients) in zip(fluxes, data['cells'], data['geometry']):
        keys(item, ('cell_id', 'volume_m3', 'heat_flux_w_m2'))
        require(item['cell_id'] == cell['id'], 'Transient cell identity changed.')
        _close(item['volume_m3'], volume, 'cell volume', atol=0)
        flux = item['heat_flux_w_m2']
        require(isinstance(flux, list) and len(flux) == 3, 'Transient flux vector required.')
        expected = -data['tensors'][cell['material_id']] @ (gradients.T @ values[cell['vertices']])
        for actual, reference in zip(flux, expected):
            _close(actual, reference, 'cell heat flux')
    require(isinstance(field['contacts'], list) and len(field['contacts']) == len(data['contacts']),
            'Transient contact count changed.')
    for record, (sid, left, right, area, h) in zip(field['contacts'], data['contacts']):
        keys(record, ('id', 'left_to_right_heat_w', 'mean_temperature_jump_k'))
        require(record['id'] == sid, 'Transient contact identity changed.')
        jump = float(np.mean(values[list(left)] - values[list(right)]))
        _close(record['mean_temperature_jump_k'], jump, 'contact jump')
        _close(record['left_to_right_heat_w'], area * h * jump, 'contact flow')
    require(isinstance(field['reactions_w'], dict) and set(field['reactions_w']) == {str(i) for i in data['fixed']},
            'Transient reaction node identities changed.')
    for value in field['reactions_w'].values():
        number(value, 'reaction')
    resources = field['resources']
    require(isinstance(resources, dict), 'Transient resources object required.')
    for key, expected in [('nodes', len(values)), ('tetrahedra', len(data['cells'])),
                          ('steps', len(settings['time_grid']) - 1), ('frames', len(settings['output_times']))]:
        require(type(resources.get(key)) is int and resources[key] == expected, 'Transient resource count changed.')
    diagnostic = field['diagnostics']
    keys(diagnostic, ('method', 'capacity_matrix', 'cg_iterations', 'newton_iterations', 'free_relative_residual',
                      'free_max_residual_w', 'max_element_jacobian_condition', 'temporal_convergence_verified'))
    require(diagnostic['method'] == 'backward_euler' and diagnostic['capacity_matrix'] == 'consistent_P1' and
            diagnostic['temporal_convergence_verified'] is False, 'Unsupported transient method/convergence claim.')
    for key in ('cg_iterations', 'newton_iterations'):
        require(type(diagnostic[key]) is int and diagnostic[key] >= 0, 'Invalid transient iteration count.')
    for key in ('free_relative_residual', 'free_max_residual_w', 'max_element_jacobian_condition'):
        number(diagnostic[key], key, nonnegative=True)
    require(diagnostic['free_relative_residual'] <= 1e-8, 'Transient residual exceeded.')
