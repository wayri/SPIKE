# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Presentation admission for retained thermal field results, not authenticity."""
import math

from .assembly_field_geometry import keys, number


def validate_thermal_result_shape(result, handoff):
    keys(result, ('contract', 'model_status', 'production_qualified', 'assembly_digest', 'request_digest',
                  'handoff_digest', 'problem_digest', 'field_result', 'occurrence_temperatures',
                  'source_traceability', 'adiabatic_face_ids', 'limitations', 'result_digest'))
    field = result['field_result']
    keys(field, ('contract', 'status', 'model_status', 'production_qualified', 'mode', 'temperature_units',
                 'node_temperatures_k', 'cell_heat_flux_w_m2', 'contacts', 'reactions_w', 'heat_balance',
                 'diagnostics', 'boundary_evidence', 'resources', 'limitations'))
    if (field['contract'] != 'spike/assembly-tetra-thermal-result/v1' or field['status'] != 'experimental' or
        field['model_status'] != 'experimental' or field['production_qualified'] is not False or
        field['mode'] != 'steady_state' or field['temperature_units'] != 'K'):
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid nested solver status, units or contract')
    temperatures = field['node_temperatures_k']
    if not isinstance(temperatures, list) or len(temperatures) != handoff['mesh']['counts']['vertices']:
        raise ValueError('ASSEMBLY_FIELD_RESULT: node count differs from bound mesh')
    if any(number(t) < -1e-8 for t in temperatures):
        raise ValueError('ASSEMBLY_FIELD_RESULT: below absolute zero temperature')
    expected_cells = {c['id'] for c in handoff['mesh']['cells']}
    fluxes = field['cell_heat_flux_w_m2']
    if not isinstance(fluxes, list) or len(fluxes) != len(expected_cells):
        raise ValueError('ASSEMBLY_FIELD_RESULT: cell count differs from bound mesh')
    returned = set()
    for cell in fluxes:
        keys(cell, ('cell_id', 'heat_flux_w_m2', 'volume_m3'))
        if cell['cell_id'] not in expected_cells or cell['cell_id'] in returned:
            raise ValueError('ASSEMBLY_FIELD_RESULT: unknown or duplicate field cell')
        returned.add(cell['cell_id'])
        vector = cell['heat_flux_w_m2']
        if not isinstance(vector, list) or len(vector) != 3:
            raise ValueError('ASSEMBLY_FIELD_RESULT: heat flux must be a 3-vector')
        for value in vector:
            number(value)
        number(cell['volume_m3'], positive=True)
    expected_occurrences = {t['occurrence_id']: t for t in handoff['source_traceability']}
    if not isinstance(result['occurrence_temperatures'], dict) or set(result['occurrence_temperatures']) != set(expected_occurrences):
        raise ValueError('ASSEMBLY_FIELD_RESULT: occurrence count differs from bound mesh')
    for oid, trace in expected_occurrences.items():
        item = result['occurrence_temperatures'][oid]
        keys(item, ('minimum_k', 'maximum_k', 'vertex_range'))
        start, stop = trace['vertex_range']
        if item['vertex_range'] != trace['vertex_range']:
            raise ValueError('ASSEMBLY_FIELD_RESULT: changed vertex ownership')
        for key, value in [('minimum_k', min(temperatures[start:stop])), ('maximum_k', max(temperatures[start:stop]))]:
            if not math.isclose(number(item[key]), value, abs_tol=1e-8, rel_tol=1e-12):
                raise ValueError('ASSEMBLY_FIELD_RESULT: occurrence temperature disagrees with nodal values')
    if result['source_traceability'] != handoff['source_traceability']:
        raise ValueError('ASSEMBLY_FIELD_RESULT: changed source traceability')
    keys(field['heat_balance'], ('source_w', 'prescribed_flux_inward_w', 'temperature_reaction_inward_w',
                                'convection_outward_w', 'imbalance_w', 'acceptance_tolerance_w'), ('radiation_outward_w',))
    for value in field['heat_balance'].values():
        number(value)
    balance = field['heat_balance']
    if balance['acceptance_tolerance_w'] < 0 or abs(balance['imbalance_w']) > balance['acceptance_tolerance_w']:
        raise ValueError('ASSEMBLY_FIELD_RESULT: reported heat conservation failed')
    calculated = balance['source_w']+balance['prescribed_flux_inward_w']+balance['temperature_reaction_inward_w']-balance['convection_outward_w']-balance.get('radiation_outward_w', 0)
    if abs(calculated-balance['imbalance_w']) > balance['acceptance_tolerance_w']:
        raise ValueError('ASSEMBLY_FIELD_RESULT: inconsistent heat balance')
    if not isinstance(field['resources'], dict) or any(type(field['resources'].get(k)) is not int or field['resources'][k] != v
            for k, v in [('nodes', len(temperatures)), ('tetrahedra', len(expected_cells))]):
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid resource counts')
    diagnostics = field['diagnostics']
    keys(diagnostics, ('free_relative_residual', 'free_max_residual_w', 'reciprocity_max_error_w_k',
                       'positive_energy_check', 'volume_gradient_energy_w_k', 'contact_jump_energy_w_k',
                       'cg_iterations', 'max_element_jacobian_condition'), ('newton_iterations',))
    if diagnostics['positive_energy_check'] is not True or type(diagnostics['cg_iterations']) is not int or diagnostics['cg_iterations'] < 0:
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid numerical diagnostics')
    for key, value in diagnostics.items():
        if key not in ('positive_energy_check', 'cg_iterations') and number(value) < 0:
            raise ValueError('ASSEMBLY_FIELD_RESULT: negative numerical diagnostic')
    if 'newton_iterations' in diagnostics and (type(diagnostics['newton_iterations']) is not int or not 0 <= diagnostics['newton_iterations'] <= 80):
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid Newton diagnostics')
    if diagnostics['free_relative_residual'] > 1e-8:
        raise ValueError('ASSEMBLY_FIELD_RESULT: excessive reported residual')
    if not isinstance(field['contacts'], list) or len(field['contacts']) > 10000:
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid contact output')
    for item in field['contacts']:
        keys(item, ('id', 'left_to_right_heat_w', 'mean_temperature_jump_k'))
        number(item['left_to_right_heat_w'])
        number(item['mean_temperature_jump_k'])
    if not isinstance(field['reactions_w'], dict):
        raise ValueError('ASSEMBLY_FIELD_RESULT: invalid temperature reactions')
    for key, value in field['reactions_w'].items():
        if not isinstance(key, str) or not key.isdecimal() or not 0 <= int(key) < len(temperatures):
            raise ValueError('ASSEMBLY_FIELD_RESULT: reaction outside mesh')
        number(value)
    valid_faces = {f['id'] for f in handoff['boundary_faces']}
    if not isinstance(result['adiabatic_face_ids'], list) or any(not isinstance(fid, str) or fid not in valid_faces for fid in result['adiabatic_face_ids']):
        raise ValueError('ASSEMBLY_FIELD_RESULT: adiabatic face outside mesh')
