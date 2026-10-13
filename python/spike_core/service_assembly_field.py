# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded assembly field methods; no solver process/executable overrides."""
from .service_helpers import error_response, operation_id


def handle_assembly_field_request(method, params, *, request_id=None):
    from .service_pwm_electrothermal import handle_pwm_electrothermal_request
    response = handle_pwm_electrothermal_request(method, params, request_id=request_id)
    if response is not None:
        return response
    from .service_volume_electrothermal import handle_volume_electrothermal_request
    response = handle_volume_electrothermal_request(method, params, request_id=request_id)
    if response is not None:
        return response
    if method == 'admit_assembly_em_study':
        try:
            if not isinstance(params, dict) or set(params) != {'record'}:
                raise ValueError('ASSEMBLY_EM_FIELDS: exact record required')
            from .assembly_em_study import admit_assembly_em_study
            return {'ok': True, 'result': admit_assembly_em_study(params['record'])}
        except Exception as exc:
            return error_response('SPIKE-BE-IPC-E-0001', str(exc), context={'method': method})
    if method in {'prepare_assembly_em', 'run_assembly_em'}:
        try:
            if not isinstance(params, dict) or set(params) != {'request'}:
                raise ValueError('ASSEMBLY_EM_FIELDS: exact request required')
            from .assembly_em import prepare_assembly_em, run_assembly_em
            if method == 'prepare_assembly_em':
                result = prepare_assembly_em(params['request'])
            else:
                from uuid import uuid4
                from extensions.openems_suite.openems_case_integrity import _state_root
                result = run_assembly_em(params['request'], _state_root() / 'assembly-em-runs' / uuid4().hex)
            return {'ok': True, 'result': result}
        except Exception as exc:
            return error_response('SPIKE-BE-IPC-E-0001', str(exc), context={'method': method})
    methods = {'assign_assembly_thermal_body_power', 'prepare_assembly_field_handoff', 'run_assembly_field_thermal', 'run_assembly_field_transient', 'validate_assembly_thermal_time_refinement', 'derive_assembly_view_factors',
               'export_assembly_field_study', 'import_assembly_field_study', 'run_assembly_electrothermal',
               'evaluate_electrical_heat_source', 'prepare_pcb_electrothermal_geometry', 'solve_fan_system_operating_point', 'run_assembly_airflow'}
    if method not in methods:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError('ASSEMBLY_FIELD_FIELDS: parameters must be an object')
        if method == 'run_assembly_airflow':
            if set(params) != {'request'}:
                raise ValueError('AIRFLOW_FIELDS: exact request required')
            import tempfile
            from pathlib import Path
            from .assembly_airflow import run_assembly_airflow
            with tempfile.TemporaryDirectory(prefix='spike-assembly-airflow-') as directory:
                result = run_assembly_airflow(params['request'], Path(directory) / 'run')
        elif method == 'assign_assembly_thermal_body_power':
            from .assembly_thermal_body_power import assign_assembly_thermal_body_power
            from .assembly_field_geometry import keys
            keys(params, ('request', 'problem', 'occurrence_id', 'power_w', 'expected_request_digest', 'replace_existing'))
            result = assign_assembly_thermal_body_power(**params)
        elif method == 'validate_assembly_thermal_time_refinement':
            if set(params) != {'request', 'problem', 'transient_settings', 'tolerances'}:
                raise ValueError('THERMAL_REFINEMENT_FIELDS: request, problem, transient_settings and tolerances required')
            from .thermal_accuracy import run_assembly_time_refinement
            result = run_assembly_time_refinement(params['request'], params['problem'],
                params['transient_settings'], params['tolerances'])
        elif method == 'run_assembly_field_transient':
            if not {'request', 'problem', 'transient_settings'} <= set(params) or set(params) - {'request', 'problem', 'transient_settings', 'solver'}:
                raise ValueError('ASSEMBLY_TRANSIENT_FIELDS: invalid transient parameters')
            solver = params.get('solver', 'internal')
            if solver == 'internal':
                from .assembly_field_transient import run_assembly_field_transient
                from .worker_progress import emit_worker_progress
                result = run_assembly_field_transient(params['request'], params['problem'], params['transient_settings'],
                    progress_callback=lambda frame: emit_worker_progress(operation_id(request_id), method, frame))
            elif solver == 'calculix':
                from .calculix_transient import run_calculix_field_transient
                result = run_calculix_field_transient(params['request'], params['problem'], params['transient_settings'])
            else:
                raise ValueError('ASSEMBLY_TRANSIENT_SOLVER: choose internal or calculix')
        elif method in {'prepare_assembly_field_handoff', 'derive_assembly_view_factors'}:
            if set(params) != {'request'}:
                raise ValueError('ASSEMBLY_FIELD_FIELDS: only request accepted')
            if method == 'prepare_assembly_field_handoff':
                from .assembly_field_handoff import prepare_assembly_field_handoff
                result = prepare_assembly_field_handoff(params['request'])
            else:
                from .assembly_field_handoff import bounded_json
                from .assembly_view_factors import derive_assembly_view_factors
                bounded_json(params['request'])
                result = derive_assembly_view_factors(params['request'])
                bounded_json(result)
        elif method == 'solve_fan_system_operating_point':
            if set(params) != {'request'}:
                raise ValueError('FAN_SYSTEM_FIELDS: only request accepted')
            from .fan_system_operating_point import solve_fan_system_operating_point
            from .assembly_field_handoff import bounded_json
            bounded_json(params['request'])
            result = solve_fan_system_operating_point(params['request'])
            bounded_json(result)
        elif method == 'prepare_pcb_electrothermal_geometry':
            if set(params) != {'request'}:
                raise ValueError('ELECTROTHERMAL_FIELDS: only request accepted')
            from .pcb_electrothermal_geometry import prepare_pcb_electrothermal_geometry
            from .assembly_field_handoff import bounded_json
            bounded_json(params['request'])
            result = prepare_pcb_electrothermal_geometry(params['request'])
            bounded_json(result)
        elif method == 'run_assembly_electrothermal':
            if set(params) != {'request'}:
                raise ValueError('ELECTROTHERMAL_FIELDS: only request accepted')
            from .assembly_electrothermal import run_assembly_electrothermal
            result = run_assembly_electrothermal(params['request'])
        elif method == 'evaluate_electrical_heat_source':
            if set(params) != {'request','temperature_k'}:
                raise ValueError('ELECTROTHERMAL_FIELDS: source request and temperature required')
            from .electrical_heat_sources import evaluate_electrical_heat_source
            from .assembly_field_handoff import bounded_json
            bounded_json(params)
            result = evaluate_electrical_heat_source(params['request'],params['temperature_k'])
            bounded_json(result)
        elif method == 'run_assembly_field_thermal':
            if set(params) != {'request', 'problem'}:
                raise ValueError('ASSEMBLY_FIELD_FIELDS: request and problem required')
            from .assembly_field_thermal import run_assembly_field_thermal
            result = run_assembly_field_thermal(params['request'], params['problem'])
        elif method == 'export_assembly_field_study':
            if not {'request', 'problem'} <= set(params) or set(params)-{'request', 'problem', 'result', 'include_results', 'transient_settings'}:
                raise ValueError('ASSEMBLY_FIELD_FIELDS: invalid study export')
            from .assembly_field_study import export_assembly_field_study
            result = export_assembly_field_study(**params)
        else:
            if 'record' not in params or set(params)-{'record', 'current_request', 'current_problem'}:
                raise ValueError('ASSEMBLY_FIELD_FIELDS: invalid study import')
            from .assembly_field_study import import_assembly_field_study
            result = import_assembly_field_study(**params)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        return error_response('SPIKE-BE-IPC-E-0001', 'Assembly field request is invalid or unsupported.',
                              operation_id=operation_id(request_id), detail=str(exc),
                              context={'method': method, 'boundary': 'assembly_field'}, error_type=type(exc).__name__)
    return {'ok': True, 'result': result}
