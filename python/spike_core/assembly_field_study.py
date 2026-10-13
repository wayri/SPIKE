# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Offline field-study snapshots with explicit integrity and stale admission."""
import copy

from .assembly_field_geometry import keys
from .assembly_field_handoff import bounded_json, prepare_assembly_field_handoff
from .assembly_field_thermal import verify_assembly_field_result
from .multiboard_identity import canonical_json_digest


def export_assembly_field_study(request, problem, result=None, *, include_results=True, transient_settings=None):
    prepare_assembly_field_handoff(request)
    bounded_json(problem)
    if transient_settings is not None:
        from .assembly_field_transient import validate_field_transient_settings
        validate_field_transient_settings(request, problem, transient_settings)
    if result is not None and result.get('mode') == 'transient':
        recorded = result.get('transient_settings')
        if transient_settings is None:
            transient_settings = recorded
        if recorded != transient_settings:
            raise ValueError('ASSEMBLY_FIELD_STALE: transient result settings differ from setup')
    if type(include_results) is not bool:
        raise ValueError('ASSEMBLY_FIELD_STUDY: include_results must be boolean')
    if result is not None:
        result = verify_assembly_field_result(request, problem, result)
        if include_results and result.get('contract') in ('spike/calculix-thermal-result/v1', 'spike/calculix-field-transient-result/v1', 'spike/assembly-field-transient-result/v1'):
            from .multiboard_study import physical_assembly
            request = copy.deepcopy(request)
            request['assembly'] = physical_assembly(request['assembly'])
            result = verify_assembly_field_result(request, problem, result)
    record = {'contract': 'spike/assembly-field-study-file/v1', 'request': copy.deepcopy(request),
              'problem': copy.deepcopy(problem), 'result': result if include_results else None}
    if transient_settings is not None:
        record['transient_settings'] = copy.deepcopy(transient_settings)
    record['file_digest'] = canonical_json_digest(record)
    bounded_json(record)
    return record


def import_assembly_field_study(record, *, current_request=None, current_problem=None):
    bounded_json(record)
    keys(record, ('contract', 'request', 'problem', 'result', 'file_digest'), ('transient_settings',))
    content = {k: v for k, v in record.items() if k != 'file_digest'}
    if record['contract'] != 'spike/assembly-field-study-file/v1' or canonical_json_digest(content) != record['file_digest']:
        raise ValueError('ASSEMBLY_FIELD_STUDY_DIGEST: altered or unsupported study')
    prepare_assembly_field_handoff(record['request'])
    if 'transient_settings' in record:
        from .assembly_field_transient import validate_field_transient_settings
        validate_field_transient_settings(record['request'], record['problem'], record['transient_settings'])
    if isinstance(record['result'], dict) and record['result'].get('mode') == 'transient' and record['result'].get('transient_settings') != record.get('transient_settings'):
        raise ValueError('ASSEMBLY_FIELD_STALE: transient result settings differ from setup')
    if current_request is not None:
        current_comparison, saved_comparison = current_request, record['request']
        if isinstance(record['result'], dict) and record['result'].get('contract') in ('spike/calculix-thermal-result/v1', 'spike/calculix-field-transient-result/v1', 'spike/assembly-field-transient-result/v1'):
            from .multiboard_study import physical_assembly
            # CalculiX results bind canonical AssemblyIR defaults. Compare both
            # spellings at that same boundary, while retaining all mesh fields.
            prepare_assembly_field_handoff(current_request)
            current_comparison, saved_comparison = copy.deepcopy(current_request), copy.deepcopy(record['request'])
            current_comparison['assembly'] = physical_assembly(current_request['assembly'])
            saved_comparison['assembly'] = physical_assembly(record['request']['assembly'])
        if canonical_json_digest(current_comparison) != canonical_json_digest(saved_comparison):
            raise ValueError('ASSEMBLY_FIELD_STALE: active assembly field request differs')
    if current_problem is not None and canonical_json_digest(current_problem) != canonical_json_digest(record['problem']):
        raise ValueError('ASSEMBLY_FIELD_STALE: active field problem differs')
    admitted = copy.deepcopy(record)
    if record['result'] is not None:
        admitted['result'] = verify_assembly_field_result(record['request'], record['problem'], record['result'])
        if admitted['result'] != record['result']:
            admitted['file_digest'] = canonical_json_digest({k: v for k, v in admitted.items() if k != 'file_digest'})
    return admitted
