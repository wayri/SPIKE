# SPDX-License-Identifier: Apache-2.0
"""Owned-worker boundary for explicit sampled network transformations."""
from .service_helpers import error_response


def handle_sparameter_processing_request(method, params):
    if method not in ('run_rlgc_loaded_star', 'run_rlgc_coupled_star', 'run_rlgc_loaded_cascade', 'run_rlgc_coupled_cascade', 'run_rlgc_reactive_pair', 'run_rlgc_terminated_pair', 'run_rlgc_coupled_pair', 'run_si_candidate_study', 'deembed_two_port', 'resample_sparameter_network', 'fit_sparameter_rational',
                      'run_rational_network_transient', 'run_terminated_network_transient',
                      'run_inductive_network_transient', 'run_capacitive_network_transient',
                      'run_rlc_network_transient', 'run_initialized_rlc_network_transient',
                      'run_rlc_energy_ledger', 'run_multi_aggressor_crosstalk',
                      'run_crosstalk_timing_corners', 'run_network_reflectometry',
                      'run_lossless_line_transient', 'run_distortionless_line_transient', 'build_rlgc_line_network', 'run_rlgc_line_fields', 'run_rlgc_line_cascade', 'run_rlgc_line_junction'):
        return None
    try:
        if not isinstance(params, dict) or set(params) != {'request'}:
            raise ValueError('Exactly one network transformation request is required')
        if method == 'run_rlgc_loaded_star':
            from .rlgc_loaded_star import run_rlgc_loaded_star
            result = run_rlgc_loaded_star(params['request'])
        elif method == 'run_rlgc_coupled_star':
            from .rlgc_coupled_star import run_rlgc_coupled_star
            result = run_rlgc_coupled_star(params['request'])
        elif method == 'run_rlgc_loaded_cascade':
            from .rlgc_loaded_cascade import run_rlgc_loaded_cascade
            result = run_rlgc_loaded_cascade(params['request'])
        elif method == 'run_rlgc_coupled_cascade':
            from .rlgc_coupled_cascade import run_rlgc_coupled_cascade
            result = run_rlgc_coupled_cascade(params['request'])
        elif method == 'run_rlgc_reactive_pair':
            from .rlgc_reactive_pair import run_rlgc_reactive_pair
            result = run_rlgc_reactive_pair(params['request'])
        elif method == 'run_rlgc_terminated_pair':
            from .rlgc_terminated_pair import run_rlgc_terminated_pair
            result = run_rlgc_terminated_pair(params['request'])
        elif method == 'run_rlgc_coupled_pair':
            from .rlgc_coupled_pair import run_rlgc_coupled_pair
            result = run_rlgc_coupled_pair(params['request'])
        elif method == 'run_si_candidate_study':
            from .si_candidate_study import run_si_candidate_study
            result = run_si_candidate_study(params['request'])
        elif method == 'run_rlgc_line_junction':
            from .rlgc_line_junction import run_rlgc_line_junction
            result = run_rlgc_line_junction(params['request'])
        elif method == 'run_rlgc_line_cascade':
            from .rlgc_line_cascade import run_rlgc_line_cascade
            result = run_rlgc_line_cascade(params['request'])
        elif method == 'run_rlgc_line_fields':
            from .rlgc_line_fields import run_rlgc_line_fields
            result = run_rlgc_line_fields(params['request'])
        elif method == 'build_rlgc_line_network':
            from .rlgc_line_network import build_rlgc_line_network
            result = build_rlgc_line_network(params['request'])
        elif method == 'run_distortionless_line_transient':
            from .distortionless_line_transient import run_distortionless_line_transient
            result = run_distortionless_line_transient(params['request'])
        elif method == 'run_lossless_line_transient':
            from .lossless_line_transient import run_lossless_line_transient
            result = run_lossless_line_transient(params['request'])
        elif method == 'run_network_reflectometry':
            from .sparameter_reflectometry import run_network_reflectometry
            result = run_network_reflectometry(params['request'])
        elif method == 'run_crosstalk_timing_corners':
            from .sparameter_crosstalk_timing import run_crosstalk_timing_corners
            result = run_crosstalk_timing_corners(params['request'])
        elif method == 'run_multi_aggressor_crosstalk':
            from .sparameter_multi_aggressor import run_multi_aggressor_crosstalk
            result = run_multi_aggressor_crosstalk(params['request'])
        elif method == 'run_rlc_energy_ledger':
            from .sparameter_rlc_energy import run_rlc_energy_ledger
            result = run_rlc_energy_ledger(params['request'])
        elif method == 'run_initialized_rlc_network_transient':
            from .sparameter_rlc_initial import run_initialized_rlc_network_transient
            result = run_initialized_rlc_network_transient(params['request'])
        elif method == 'run_rlc_network_transient':
            from .sparameter_rlc_terminated import run_rlc_network_transient
            result = run_rlc_network_transient(params['request'])
        elif method == 'run_capacitive_network_transient':
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
