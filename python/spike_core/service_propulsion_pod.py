# SPDX-License-Identifier: Apache-2.0
"""Fixed worker routes for the experimental coupled propulsion benchmark."""
import copy
from .service_helpers import error_response

def handle_propulsion_pod_request(method, params):
    from .service_propulsion_pod_geometry import handle_geometry_pod_request
    geometry=handle_geometry_pod_request(method,params)
    if geometry is not None:return geometry
    if method not in {'propulsion_pod_capabilities', 'validate_propulsion_pod', 'run_propulsion_pod',
                      'propulsion_pod_three_phase_capabilities', 'validate_propulsion_pod_three_phase',
                      'run_propulsion_pod_three_phase'}:
        return None
    try:
        if 'three_phase' in method:
            from .propulsion_pod_three_phase_run import (
                DEFAULT_REQUEST as THREE_DEFAULT, REQUEST as THREE_REQUEST, RESULT as THREE_RESULT,
                validate_three_phase_request, run_three_phase_pod)
            if method == 'propulsion_pod_three_phase_capabilities':
                if params != {}:
                    raise ValueError('Capabilities accepts no parameters')
                return {'ok': True, 'result': {'request_contract': THREE_REQUEST,
                    'result_contract': THREE_RESULT, 'default_request': copy.deepcopy(THREE_DEFAULT),
                    'model_status': 'experimental', 'production_qualified': False,
                    'field': 'synthetic three-phase P1 FEM with floating star neutral',
                    'thermal': 'eleven-node reciprocal thermal network with resistance feedback',
                    'propeller': 'hover BEM; not blade-resolved CFD',
                    'real_motor_characterization': False, 'compiles_builtin_controller_on_run': True}}
            if not isinstance(params, dict) or set(params) != {'request'}:
                raise ValueError('Exactly one request object is required')
            if method == 'validate_propulsion_pod_three_phase':
                clean, steps, stride, frames = validate_three_phase_request(params['request'])
                return {'ok': True, 'result': {'valid': True, 'request': clean, 'steps': steps,
                    'controller_stride': stride, 'field_stride': frames}}
            return {'ok': True, 'result': run_three_phase_pod(params['request'])}
        from .propulsion_pod import DEFAULT_REQUEST, REQUEST, RESULT, validate_request, run_propulsion_pod
        if method == 'propulsion_pod_capabilities':
            if params != {}:
                raise ValueError('Capabilities accepts no parameters')
            return {'ok': True, 'result': {'request_contract': REQUEST, 'result_contract': RESULT,
                'model_status': 'experimental', 'production_qualified': False, 'default_request': copy.deepcopy(DEFAULT_REQUEST),
                'controller': 'fixed built-in original C source through optional SPIKES Studio runtime/compiler',
                'field': 'two-phase synthetic linear P1 finite-element reference',
                'propeller': 'geometry-based no-swirl hover BEM; not blade-resolved CFD',
                'compiles_builtin_controller_on_run': True}}
        if not isinstance(params, dict) or set(params) != {'request'}:
            raise ValueError('Exactly one request object is required')
        if method == 'validate_propulsion_pod':
            clean, steps, stride, frame_stride = validate_request(params['request'])
            return {'ok': True, 'result': {'valid': True, 'request': clean, 'steps': steps,
                                          'controller_stride': stride, 'field_stride': frame_stride}}
        return {'ok': True, 'result': run_propulsion_pod(params['request'])}
    except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError, OSError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'Coupled propulsion benchmark failed.',
                              detail=str(exc), context={'method': method}, error_type=type(exc).__name__)
