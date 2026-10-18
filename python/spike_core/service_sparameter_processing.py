# SPDX-License-Identifier: Apache-2.0
"""Owned-worker boundary for explicit sampled network transformations."""
from .service_helpers import error_response


def handle_sparameter_processing_request(method, params):
    if method not in ('deembed_two_port', 'resample_sparameter_network', 'fit_sparameter_rational',
                      'run_rational_network_transient', 'run_terminated_network_transient',
                      'run_inductive_network_transient', 'run_capacitive_network_transient'):
        return None
    try:
        if not isinstance(params, dict) or set(params) != {'request'}:
            raise ValueError('Exactly one network transformation request is required')
        if method == 'run_capacitive_network_transient':
            from .sparameter_capacitive_terminated import run_capacitive_network_transient
            result = run_capacitive_network_transient(params['request'])
        elif method == 'run_inductive_network_transient':
            from .sparameter_inductive_terminated import run_inductive_network_transient
            result = run_inductive_network_transient(params['request'])
        elif method == 'run_terminated_network_transient':
            from .sparameter_terminated import run_terminated_network_transient
            result = run_terminated_network_transient(params['request'])
        elif method == 'run_rational_network_transient':
            from .sparameter_transient import run_rational_network_transient
            result = run_rational_network_transient(params['request'])
        elif method == 'fit_sparameter_rational':
            from .sparameter_rational import fit_sparameter_rational
            result = fit_sparameter_rational(params['request'])
        elif method == 'resample_sparameter_network':
            from .sparameter_sampling import resample_sparameter_network
            result = resample_sparameter_network(params['request'])
        else:
            from .sparameter_deembedding import deembed_two_port
            result = deembed_two_port(params['request'])
        return {'ok': True, 'result': result}
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'Sampled network transformation failed admission or numerical checks.',
                              detail=str(exc), context={'method': method,
                              'network_code': getattr(exc, 'code', 'NETWORK_INVALID_REQUEST')},
                              error_type=type(exc).__name__)
