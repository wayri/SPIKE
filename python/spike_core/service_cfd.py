# SPDX-License-Identifier: Apache-2.0
"""Fixed, bounded CFD worker entry points; runtime paths are host configuration."""
from .service_helpers import error_response


METHODS = frozenset({'cfd_capabilities', 'run_native_cfd', 'run_su2_cfd', 'run_su2_cht',
                     'run_native_cht', 'run_coupled_surface_exchange', 'run_enclosure_cht',
                     'run_enclosure_cht_v2'})


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
            from .native_cht import native_cht_capabilities
            result = {'contract': 'spike/cfd-catalog/v1', 'engines': {
                'spike.native_cavity': native_airflow_capabilities(),
                'spike.native_cht': native_cht_capabilities(),
                'spike.enclosure_cht': {'available': True, 'model_status': 'experimental',
                    'geometry': 'supplied_voxel_regions_nested_thermal_tensor_grid',
                    'creeping_obstacles': True, 'inertial_rectangular_fluid_region': True,
                    'local_thermal_refinement': True, 'local_momentum_refinement': False,
                    'turbulence': False, 'rotating_machinery': False, 'production_qualified': False},
                'spike.enclosure_cht_v2': {'available': True, 'model_status': 'experimental',
                    'geometry': 'supplied_stationary_staircase_voxels',
                    'momentum_grid': 'resolved_nested_tensor_planes',
                    'obstacle_inertia': True, 'selected_region_momentum_sizing': True,
                    'confined_patch_amr': False, 'turbulence': False,
                    'rotating_machinery': False, 'production_qualified': False},
                'su2.cavity': su2_airflow_capabilities(),
                'su2.cht': su2_cht_capabilities()},
                'coupling': {'surface_exchange': {
                    'available': True, 'model_status': 'experimental',
                    'quantities': ['heat_flux', 'traction'],
                    'caller_supplied_overlaps': True, 'two_way_fsi': False,
                    'production_qualified': False}},
                'production_qualified': False,
                'assembly_cht_supported': False}
        else:
            if set(params) != {'request'} or not isinstance(params['request'], dict):
                raise ValueError('CFD execution requires exactly one request object.')
            if method == 'run_native_cfd':
                from .native_airflow import run_native_airflow
                result = run_native_airflow(params['request'])
            elif method == 'run_native_cht':
                from .native_cht import run_native_cht
                result = run_native_cht(params['request'])
            elif method == 'run_enclosure_cht':
                from .enclosure_cht import solve_enclosure_cht
                result = solve_enclosure_cht(params['request'])
            elif method == 'run_enclosure_cht_v2':
                from .enclosure_cht_v2 import solve_enclosure_cht_v2
                result = solve_enclosure_cht_v2(params['request'])
            elif method == 'run_coupled_surface_exchange':
                from .coupled_surface_exchange import transfer_coupled_surface_exchange
                result = transfer_coupled_surface_exchange(params['request'])
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
