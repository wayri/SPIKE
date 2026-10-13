# SPDX-License-Identifier: Apache-2.0
"""Occurrence-bound external thermal orchestration and saved-result admission."""
from __future__ import annotations

import copy
import hashlib
import math

import numpy as np

from .assembly_field_handoff import bounded_json
from .assembly_field_thermal import bind_assembly_field_thermal
from .assembly_tetra_thermal_validation import validate_request
from .calculix_deck import compile_calculix_deck
from .calculix_runtime import probe_calculix_runtime, run_calculix_deck
from .multiboard_identity import canonical_json_digest

LIMITATIONS = [
    'Experimental external steady DC3D4 solid thermal adapter; not production qualified.',
    'Prescribed ambient convection and diffuse gray radiation only; no solved airflow or cavity radiosity.',
    'Constant symmetric positive conductivity; no transient or temperature-dependent material properties.',
    'Only explicitly retained congruent coincident thermal contacts with supplied conductance are supported.',
    'Thermal contact uses fixed geometry and zero clearance; no mechanical displacement or contact-pressure prediction.',
    'Unspecified exterior faces are adiabatic. Heat flux is derived from returned nodal temperatures.',
    'CalculiX is separately installed under its upstream license; no solver runtime is redistributed.',
]


def _bind_canonical(request, problem):
    # Preserve admission of raw input, then use the project persistence boundary's
    # canonical AssemblyIR defaults for stable saved-result identity.
    bind_assembly_field_thermal(request, problem)
    from .multiboard_study import physical_assembly
    canonical = copy.deepcopy(request)
    canonical['assembly'] = physical_assembly(request['assembly'])
    return bind_assembly_field_thermal(canonical, problem)


def prepare_calculix_thermal(request, problem):
    handoff, tetra, assigned, contact_faces = _bind_canonical(request, problem)
    compiled = compile_calculix_deck(tetra)
    runtime = probe_calculix_runtime()
    return {'contract': 'spike/calculix-thermal-case/v1',
            'status': 'ready_to_run' if runtime['available'] else 'unavailable',
            'model_status': 'experimental', 'production_qualified': False,
            'runtime': runtime, **compiled,
            **{k: handoff[k] for k in ('assembly_digest', 'request_digest', 'handoff_digest', 'source_traceability')},
            'problem_digest': canonical_json_digest(problem),
            'adiabatic_face_ids': [f['id'] for f in handoff['boundary_faces'] if f['id'] not in assigned | contact_faces],
            'limitations': list(LIMITATIONS)}


def _field_from_temperatures(tetra, temperatures):
    data = validate_request(tetra)
    if not isinstance(temperatures, list) or len(temperatures) != len(data['xyz']) or any(
        type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in temperatures):
        raise ValueError('CALCULIX_RESULT: invalid temperature coverage or physical range.')
    values = np.asarray(temperatures, dtype=float)
    # .dat NT output uses finite decimal precision. Check prescribed values
    # against a conservative 6-significant-digit roundtrip allowance.
    for node, temperature in data['fixed'].items():
        if not math.isclose(values[node], temperature, rel_tol=2e-6, abs_tol=2e-6):
            raise ValueError('CALCULIX_RESULT: prescribed nodal temperature was not satisfied.')
    fluxes = []
    for cell, (volume, gradients) in zip(data['cells'], data['geometry']):
        flux = -data['tensors'][cell['material_id']] @ gradients.T @ values[cell['vertices']]
        if not np.isfinite(flux).all():
            raise ValueError('CALCULIX_RESULT: nonfinite derived heat flux.')
        fluxes.append({'cell_id': cell['id'], 'heat_flux_w_m2': flux.tolist(), 'volume_m3': volume})
    return {'contract': 'spike/calculix-thermal-field/v1', 'status': 'experimental',
            'model_status': 'experimental', 'production_qualified': False,
            'mode': 'steady_state', 'temperature_units': 'K',
            'node_temperatures_k': list(temperatures), 'cell_heat_flux_w_m2': fluxes,
            'contacts': [{'id': cid, 'left_to_right_heat_w': float(area*h*np.mean(values[list(left)]-values[list(right)])),
                          'mean_temperature_jump_k': float(np.mean(values[list(left)]-values[list(right)]))}
                         for cid, left, right, area, h in data['contacts']],
            'resources': {'nodes': len(values), 'tetrahedra': len(fluxes)},
            'boundary_evidence': {'omitted_faces_are_adiabatic': True, 'heat_flux_sign': 'positive_inward'},
            'diagnostics': {'prescribed_temperatures_checked': True,
                            'heat_flux_source': 'Fourier gradient of CalculiX NT output',
                            'global_heat_balance': 'not_reported',
                            'convergence_source': 'CalculiX successful completion and final step NT coverage'}}


def run_calculix_thermal(request, problem, engine_options=None, *, cancel_check=None):
    prepared = prepare_calculix_thermal(request, problem)
    _, tetra, _, _ = bind_assembly_field_thermal(request, problem)
    execution = run_calculix_deck(prepared, engine_options, cancel_check=cancel_check)
    field = _field_from_temperatures(tetra, execution.pop('node_temperatures_k'))
    occurrences = {}
    for trace in prepared['source_traceability']:
        start, stop = trace['vertex_range']
        samples = field['node_temperatures_k'][start:stop]
        occurrences[trace['occurrence_id']] = {'minimum_k': min(samples), 'maximum_k': max(samples),
                                               'vertex_range': [start, stop]}
    result = {'contract': 'spike/calculix-thermal-result/v1', 'model_status': 'experimental',
              'production_qualified': False, 'solver_id': 'external.calculix',
              **{k: prepared[k] for k in ('assembly_digest', 'request_digest', 'handoff_digest',
                  'problem_digest', 'source_traceability', 'adiabatic_face_ids', 'limitations')},
              'field_result': field, 'occurrence_temperatures': occurrences, 'execution': execution,
              'deck_identity': {k: prepared[k] for k in ('tetra_request_digest', 'node_map', 'element_map',
                                                        'material_map', 'boundary_map', 'contact_map')}}
    result['result_digest'] = canonical_json_digest(result)
    bounded_json(result)
    return result


def verify_calculix_thermal_result(request, problem, result):
    """Check integrity, geometry binding and derived values; not authenticity."""
    bounded_json(result)
    if not isinstance(result, dict) or result.get('contract') != 'spike/calculix-thermal-result/v1':
        raise ValueError('CALCULIX_RESULT: unsupported saved result contract.')
    if result.get('result_digest') != canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'}):
        raise ValueError('CALCULIX_RESULT_DIGEST: saved result was changed.')
    handoff, tetra, assigned, contact_faces = _bind_canonical(request, problem)
    compiled = compile_calculix_deck(tetra)
    for key in ('assembly_digest', 'request_digest', 'handoff_digest', 'source_traceability'):
        if result.get(key) != handoff[key]:
            raise ValueError('CALCULIX_STALE: retained geometry or material binding changed.')
    if result.get('problem_digest') != canonical_json_digest(problem):
        raise ValueError('CALCULIX_STALE: thermal boundary or heat-source problem changed.')
    if result.get('model_status') != 'experimental' or result.get('production_qualified') is not False or result.get('solver_id') != 'external.calculix':
        raise ValueError('CALCULIX_RESULT: invalid solver qualification claim.')
    expected_field = _field_from_temperatures(tetra, result.get('field_result', {}).get('node_temperatures_k'))
    if result.get('field_result') != expected_field:
        raise ValueError('CALCULIX_RESULT: saved fields differ from returned temperature derivation.')
    expected_occurrences = {}
    for trace in handoff['source_traceability']:
        start, stop = trace['vertex_range']
        samples = expected_field['node_temperatures_k'][start:stop]
        expected_occurrences[trace['occurrence_id']] = {'minimum_k': min(samples), 'maximum_k': max(samples),
                                                       'vertex_range': [start, stop]}
    if result.get('occurrence_temperatures') != expected_occurrences:
        raise ValueError('CALCULIX_RESULT: occurrence field ownership mismatch.')
    expected_identity = {k: compiled[k] for k in ('tetra_request_digest', 'node_map', 'element_map', 'material_map', 'boundary_map', 'contact_map')}
    if result.get('deck_identity') != expected_identity:
        raise ValueError('CALCULIX_RESULT: solver node/element/material/boundary identity changed.')
    execution = result.get('execution', {})
    if execution.get('input_sha256') != hashlib.sha256(compiled['deck'].encode('ascii')).hexdigest() or execution.get('exit_code') != 0 or execution.get('solver_reported_finished') is not True or execution.get('completed_step_time') != 1:
        raise ValueError('CALCULIX_RESULT: missing completed execution evidence.')
    for key in ('output_sha256', 'log_sha256'):
        digest = execution.get(key)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('CALCULIX_RESULT: malformed execution artifact digest.')
    if result.get('adiabatic_face_ids') != [f['id'] for f in handoff['boundary_faces'] if f['id'] not in assigned | contact_faces] or result.get('limitations') != LIMITATIONS:
        raise ValueError('CALCULIX_RESULT: missing boundary/limitation evidence.')
    return copy.deepcopy(result)
