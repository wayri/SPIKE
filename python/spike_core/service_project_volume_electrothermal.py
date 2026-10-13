# SPDX-License-Identifier: Apache-2.0
"""Retain admitted co-simulation setup/results with the original assembly."""
import copy
from collections.abc import Mapping

from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_project_assembly_field import _open_current_project, _assembly_identity, AssemblyFieldStudyStale
from .multiboard_identity import canonical_json_digest
from .service_helpers import error_response, operation_id

STUDY_KEY = 'assembly_volume_electrothermal'


def _admit(record, assembly):
    from .multiboard_volume_electrothermal import (
        prepare_multiboard_volume_electrothermal, verify_multiboard_volume_electrothermal_result)
    if not isinstance(record, dict) or set(record) != {'request', 'result'}:
        raise ProjectPackageError('VOLUME_COUPLING_RECORD: request and nullable result required')
    prepared = prepare_multiboard_volume_electrothermal(record['request'])
    _, current_digest = _assembly_identity(assembly)
    _, saved_digest = _assembly_identity(record['request']['geometry']['assembly'])
    if current_digest != saved_digest:
        raise AssemblyFieldStudyStale('Saved electrothermal results belong to different assembly geometry, links or placement; rerun.')
    result = None if record['result'] is None else verify_multiboard_volume_electrothermal_result(record['request'], record['result'])
    return {'request': copy.deepcopy(record['request']), 'result': result}, prepared, current_digest


def handle_volume_electrothermal_project_request(method, params, *, request_id, application_version):
    if method not in {'read_volume_electrothermal_in_project', 'save_volume_electrothermal_in_project'}:
        return None
    try:
        saving = method.startswith('save_')
        required = {'project_path', 'expected_manifest_payload_sha256'} | ({'record'} if saving else set())
        if not isinstance(params, dict) or set(params) != required:
            raise ProjectPackageError('Exact project and manifest identities required.')
        path, opened = _open_current_project(params, 'accessing electrothermal studies', include_members=saving)
        analyses = opened.payload.get('analyses', {})
        if not isinstance(analyses, Mapping):
            raise ProjectPackageError('Project analysis index must be an object.')
        record = params['record'] if saving else analyses.get(STUDY_KEY)
        if record is None:
            return {'ok': True, 'result': {'state': 'missing', 'record': None}}
        try:
            admitted, prepared, digest = _admit(record, opened.payload.get('assembly_ir'))
        except AssemblyFieldStudyStale as exc:
            if saving:
                raise
            return {'ok': True, 'result': {'state': 'stale', 'record': None, 'action': str(exc)}}
        if not saving:
            return {'ok': True, 'result': {'state': 'current', 'record': admitted, 'prepared': prepared}}
        payload = copy.deepcopy(opened.payload)
        payload.setdefault('analyses', {})[STUDY_KEY] = admitted
        audit = payload.setdefault('audit', [])
        if not isinstance(audit, list):
            raise ProjectPackageError('Project audit must be an array.')
        audit.append({'event': 'volume_electrothermal_saved', 'assembly_digest': digest,
                      'has_result': admitted['result'] is not None, 'model_status': 'experimental'})
        if read_project(path).manifest.get('manifest_payload_sha256') != params['expected_manifest_payload_sha256']:
            raise ProjectPackageError('Project changed during validation; reopen before saving.')
        manifest = write_spike_package(path, payload, preserved_members=opened.members,
                                      profile=str(opened.manifest.get('profile', 'portable_project')),
                                      application_version=application_version)
        return {'ok': True, 'result': {'record': admitted, 'manifest': manifest, 'state': 'current'}}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, ProjectPackageError) as exc:
        return error_response('SPIKE-BE-PACKAGE-E-0002', str(exc), error_type=type(exc).__name__,
                              operation_id=operation_id(request_id))
