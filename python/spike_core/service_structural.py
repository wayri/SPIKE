# SPDX-License-Identifier: Apache-2.0
"""Lazy worker boundary for bounded original structural solvers."""
from .service_helpers import error_response


def handle_structural_request(method, params, *, request_id=None):
    if method not in {'run_assembly_tetra_structural', 'run_assembly_thermomechanical'}:
        return None
    try:
        if not isinstance(params, dict) or set(params) != {'request'}:
            raise ValueError('STRUCTURAL_FIELDS: exact request required')
        if method == 'run_assembly_tetra_structural':
            from .assembly_tetra_structural import run_assembly_tetra_structural
            result = run_assembly_tetra_structural(params['request'])
        else:
            from .assembly_thermomechanical import run_assembly_thermomechanical
            result = run_assembly_thermomechanical(params['request'])
        return {'ok': True, 'result': result}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', str(exc), context={'method': method})
