# SPDX-License-Identifier: Apache-2.0
"""Lazy, bounded worker admission for circuit-to-volume co-simulation."""
from .service_helpers import error_response, operation_id


def handle_volume_electrothermal_request(method, params, *, request_id=None):
    methods = {'prepare_multiboard_volume_electrothermal', 'run_multiboard_volume_electrothermal',
               'verify_multiboard_volume_electrothermal_result', 'prepare_assembly_thermal_contact_model',
               'describe_volume_electrothermal_bindings', 'discover_assembly_thermal_links',
               'autolink_assembly_thermal_contacts'}
    if method not in methods:
        return None
    try:
        from .assembly_field_handoff import bounded_json
        bounded_json(params)
        required = ({'request', 'problem', 'contact_ids'} if method == 'autolink_assembly_thermal_contacts' else
                    {'request', 'problem'} if method == 'discover_assembly_thermal_links' else
                    {'geometry', 'circuit'} if method == 'describe_volume_electrothermal_bindings' else
                    {'request', 'problem', 'contact_id', 'thermal_resistance_k_per_w'}
                    if method == 'prepare_assembly_thermal_contact_model' else
                    {'request', 'result'} if method == 'verify_multiboard_volume_electrothermal_result' else {'request'})
        if not isinstance(params, dict) or set(params) != required:
            raise ValueError('VOLUME_COUPLING_FIELDS: exact method parameters required')
        if method in {'discover_assembly_thermal_links', 'autolink_assembly_thermal_contacts'}:
            from . import assembly_thermal_autolink
            result = getattr(assembly_thermal_autolink, method)(**params)
        elif method == 'describe_volume_electrothermal_bindings':
            from .multiboard_circuit import compile_multiboard_circuit
            from .assembly_field_handoff import prepare_assembly_field_handoff
            from .multiboard_identity import assembly_physics_digest
            if assembly_physics_digest(params['geometry']['assembly']) != assembly_physics_digest(params['circuit']['assembly']):
                raise ValueError('VOLUME_COUPLING_STALE: circuit and volume assembly differ')
            compiled = compile_multiboard_circuit(params['circuit'])
            handoff = prepare_assembly_field_handoff(params['geometry'])
            result = {'resistors': [{'element_id': e['id'], 'resistance_ohm': e['resistance_ohm']}
                                   for e in compiled['native_request']['elements'] if e['type'] == 'resistor'],
                      'occurrences': [{'occurrence_id': t['occurrence_id'], 'cell_ids': list(t['cell_map'])}
                                      for t in handoff['source_traceability']],
                      'assembly_digest': assembly_physics_digest(params['geometry']['assembly']),
                      'status': 'identities_only', 'production_qualified': False}
        elif method == 'prepare_assembly_thermal_contact_model':
            from .assembly_thermal_contact_model import prepare_assembly_thermal_contact_model
            result = prepare_assembly_thermal_contact_model(**params)
        else:
            from . import multiboard_volume_electrothermal as coupling
            result = getattr(coupling, method)(**params)
        bounded_json(result)
        return {'ok': True, 'result': result}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'Electrothermal setup is invalid or unsupported.',
                              operation_id=operation_id(request_id), detail=str(exc),
                              context={'method': method, 'boundary': 'volume_electrothermal'}, error_type=type(exc).__name__)
