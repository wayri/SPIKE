# SPDX-License-Identifier: Apache-2.0
"""Fixed, bounded CFD worker entry points; runtime paths are host configuration."""
from .service_helpers import error_response


METHODS = frozenset({'cfd_capabilities', 'run_native_cfd', 'run_su2_cfd', 'run_su2_cht'})


def handle_cfd_request(method, params):
    if method not in METHODS:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError('CFD parameters must be an object.')
        if method == 'cfd_capabilities':
            if params:
                raise ValueError('CFD capabilities accepts no parameters.')
            from .native_airflow import native_airflow_capabilities
            from .su2_airflow import su2_airflow_capabilities
            from .su2_cht import su2_cht_capabilities
            result = {'contract': 'spike/cfd-catalog/v1', 'engines': {
                'spike.native_cavity': native_airflow_capabilities(),
                'su2.cavity': su2_airflow_capabilities(),
                'su2.cht': su2_cht_capabilities()},
                'production_qualified': False,
                'assembly_cht_supported': False}
        else:
            if set(params) != {'request'} or not isinstance(params['request'], dict):
                raise ValueError('CFD execution requires exactly one request object.')
            if method == 'run_native_cfd':
                from .native_airflow import run_native_airflow
                result = run_native_airflow(params['request'])
            elif method == 'run_su2_cfd':
                from .su2_airflow import run_su2_airflow
                result = run_su2_airflow(params['request'])
            else:
                from .su2_cht import run_su2_cht
                result = run_su2_cht(params['request'])
        return {'ok': True, 'result': result}
    except (ValueError, TypeError, KeyError, ArithmeticError, OSError, RuntimeError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'CFD operation failed.',
                              detail=str(exc), context={'method': method},
                              error_type=type(exc).__name__)
