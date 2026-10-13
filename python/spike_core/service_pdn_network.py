# SPDX-License-Identifier: Apache-2.0
"""Owned-worker boundary for explicitly modeled AC PDN/filter studies."""
from .service_helpers import error_response


def handle_pdn_network_request(method, params):
    methods = {'evaluate_pdn_network', 'validate_pdn_network', 'normalize_pdn_shunt_capacitance',
               'pdn_capacitor_elements', 'review_series_capacitor_leg', 'extract_pdn_electrostatic'}
    if method not in methods:
        return None
    try:
        fields = {'request', 'expected_context_digest'} if method == 'pdn_capacitor_elements' else {'request'}
        if not isinstance(params, dict) or set(params) != fields:
            raise ValueError('PDN_FIELDS: exactly one request is required')
        if method == 'extract_pdn_electrostatic':
            from .pdn_electrostatic import extract_pdn_electrostatic
            from .pdn_shunt_capacitance import pdn_capacitor_elements
            result = extract_pdn_electrostatic(params['request'])
            reference = result['reference_electrode']['node']
            source = {'kind': 'supplied_maxwell_matrix', 'model': result['model'],
                      'model_status': 'experimental', 'provenance': {'source': result['input_digest']},
                      'context_digest': result['context_digest'], 'nodes': result['nodes'], 'matrix_f': result['matrix_f'],
                      'return_boundary': {'mode': 'explicit', 'node': reference, 'net': reference},
                      'mesh': {'status': 'accepted', 'digest': result['mesh_digest']}}
            result['pdn_elements'] = pdn_capacitor_elements(source, expected_context_digest=result['context_digest'])
            for item in result['pdn_elements']:
                item['provenance'] = {'kind': 'extracted', 'source_id': result['input_digest']}
        elif method == 'review_series_capacitor_leg':
            from .pdn_series_capacitors import review_series_capacitor_leg
            result = review_series_capacitor_leg(params['request'])
        elif method == 'pdn_capacitor_elements':
            from .pdn_shunt_capacitance import pdn_capacitor_elements
            result = {'contract': 'spike/pdn-capacitor-elements/v1', 'elements': pdn_capacitor_elements(
                params['request'], expected_context_digest=params['expected_context_digest'])}
        elif method == 'normalize_pdn_shunt_capacitance':
            from .pdn_shunt_capacitance import normalize_shunt_capacitance
            result = normalize_shunt_capacitance(params['request'])
        else:
            from .pdn_network import evaluate_pdn_network, validate_pdn_network
            result = (evaluate_pdn_network if method == 'evaluate_pdn_network' else validate_pdn_network)(params['request'])
        return {'ok': True, 'result': result}
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'PDN model is invalid, unsupported or failed numerical admission.',
            detail=str(exc), context={'method': method, 'pdn_code': getattr(exc, 'code', 'PDN_INVALID_REQUEST')},
            error_type=type(exc).__name__)
