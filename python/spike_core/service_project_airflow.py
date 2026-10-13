# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound assembly CAD airflow setup, execution and portable results."""
import copy
import json
import tempfile
from pathlib import Path

from .assembly_field_handoff import _assembly
from .assembly_frames import resolve_world
from .assembly_thermal_meshing import prepare_assembly_thermal_mesh, _artifact
from .multiboard_identity import canonical_json_digest
from .project_package import ProjectPackageError, write_spike_package
from .service_project_assembly_field import _open_current_project
from .service_project_thermal_mesh import _artifact_reader, IDENTITY_KEYS
from .service_helpers import error_response, operation_id

STUDY_KEY = 'assembly_airflow_study'
MAX_RESULT_BYTES = 32 * 1024**2


def _geometry(opened, reader, assignments, options):
    if assignments.get('encapsulation'):
        raise ProjectPackageError('AIRFLOW_ENCAPSULATION: generate and retain coating/potting solids first, then reload material assignments without generation recipes')
    plan = prepare_assembly_thermal_mesh(opened.payload, assignments, options, artifact_reader=reader)
    if plan['status'] != 'ready':
        raise ProjectPackageError('AIRFLOW_GEOMETRY: ' + json.dumps(plan['blockers']))
    assembly = _assembly(plan['assembly'])
    occurrences = {o.id: o for o in [*assembly.boards, *assembly.parts]}
    solids, owners = [], {}
    for entry in plan['jobs']:
        oid = entry['occurrence_id']
        if 'job' in entry:
            sources = copy.deepcopy(entry['job']['solids'])
        else:
            mid = next(iter(entry['material_map']))
            sources = [{'id': entry['reference_id'], 'material_id': mid, 'priority': 0,
                        'shape': {'kind': 'step_solid', 'path': entry['source_uri'],
                                  'sha256': entry['source_sha256'], 'transform': entry['model_transform']}}]
        for source in sources:
            sid = 'body_' + canonical_json_digest([oid, source['id']])[:32]
            owners[sid] = {'occurrence_id': oid, 'source_id': source['id']}
            source.update(id=sid, transform=list(resolve_world(assembly, occurrences[oid].frame)))
            solids.append(source)
    return solids, owners, plan


def read_setup(params):
    if set(params) != IDENTITY_KEYS | {'assignments', 'mesh_options'}:
        raise ProjectPackageError('AIRFLOW_FIELDS: project identity, assignments and mesh_options required')
    path, opened = _open_current_project(params, 'reading assembly airflow geometry', include_members=False)
    solids, owners, plan = _geometry(opened, _artifact_reader(path, opened), params['assignments'], params['mesh_options'])
    materials = []
    for material in plan['materials']:
        k = material['thermal_conductivity_w_mk']
        if type(k) not in (int, float):
            raise ProjectPackageError('AIRFLOW_MATERIAL: scalar isotropic conductivity required by this CHT adapter')
        materials.append({'id': material['id'], 'phase': 'solid', 'conductivity_w_mk': k,
                          'density_kg_m3': None, 'specific_heat_j_kgk': None})
    return {'solids': solids, 'owners': owners, 'materials': materials,
            'mesh': copy.deepcopy(params['mesh_options']), 'model_status': 'experimental',
            'required_inputs': ['air domain', 'solid density and heat capacity', 'air properties', 'heat loads', 'flow boundary conditions']}


def run_in_project(params, *, application_version):
    expected = IDENTITY_KEYS | {'assignments', 'mesh_options', 'request'}
    if set(params) != expected:
        raise ProjectPackageError('AIRFLOW_FIELDS: project identity, assignments, mesh_options and request required')
    path, opened = _open_current_project(params, 'running assembly airflow', include_members=True)
    reader = _artifact_reader(path, opened)
    solids, owners, _ = _geometry(opened, reader, params['assignments'], params['mesh_options'])
    portable = copy.deepcopy(params['request'])
    if portable.get('geometry', {}).get('solids') != solids or portable['geometry'].get('mesh') != params['mesh_options']:
        raise ProjectPackageError('AIRFLOW_SOURCE_STALE: read project geometry again; solids and mesh must match retained inputs')
    # Only manifest-verified package bytes become solver STEP files. The caller
    # cannot supply a local path or change the source hash behind the GUI.
    with tempfile.TemporaryDirectory(prefix='spike-assembly-airflow-') as directory:
        root = Path(directory)
        runtime_request = copy.deepcopy(portable)
        for index, solid in enumerate(runtime_request['geometry']['solids']):
            shape = solid['shape']
            if shape['kind'] == 'step_solid':
                step = root / (str(index) + '.step')
                step.write_bytes(_artifact(reader, shape['path'], shape['sha256']))
                shape['path'] = str(step)
        from .assembly_airflow import run_assembly_airflow
        result = run_assembly_airflow(runtime_request, root / 'run')
    if result.get('status') not in ('completed', 'success', 'passed'):
        return {'status': 'failed', 'result': result, 'saved': False}
    result['portable_request_digest'] = canonical_json_digest(portable)
    result['source_owners'] = owners
    encoded = json.dumps(result, allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_RESULT_BYTES:
        raise ProjectPackageError('AIRFLOW_RESULT_BUDGET: saved result exceeds 32 MiB; reduce field mesh resolution')
    # Recheck before writing, preserving every unrelated member and concurrent edit.
    _open_current_project(params, 'saving assembly airflow results', include_members=False)
    payload = copy.deepcopy(opened.payload)
    payload.setdefault('analyses', {})[STUDY_KEY] = {
        'contract': 'spike/assembly-airflow-study/v1',
        'assembly_digest': canonical_json_digest(payload['assembly_ir']),
        'assignments': copy.deepcopy(params['assignments']), 'mesh_options': copy.deepcopy(params['mesh_options']),
        'request': portable, 'request_digest': canonical_json_digest(portable),
        'result': result, 'result_digest': canonical_json_digest(result)}
    manifest = write_spike_package(path, payload, preserved_members=opened.members,
        profile=str(opened.manifest.get('profile', 'portable_project')), application_version=application_version,
        expected_manifest_payload_sha256=params['expected_manifest_payload_sha256'])
    return {'status': 'completed', 'result': result, 'manifest': manifest, 'saved': True}


def read_study(params):
    if set(params) != IDENTITY_KEYS:
        raise ProjectPackageError('AIRFLOW_FIELDS: exact project identity required')
    path, opened = _open_current_project(params, 'reading saved airflow', include_members=False)
    record = (opened.payload.get('analyses') or {}).get(STUDY_KEY)
    if record is None:
        return {'state': 'absent', 'record': None}
    if not isinstance(record, dict) or record.get('contract') != 'spike/assembly-airflow-study/v1':
        raise ProjectPackageError('AIRFLOW_STUDY: unsupported record')
    if canonical_json_digest(record.get('request')) != record.get('request_digest') or canonical_json_digest(record.get('result')) != record.get('result_digest'):
        raise ProjectPackageError('AIRFLOW_STUDY_DIGEST: changed request or result')
    if record['result'].get('portable_request_digest') != record['request_digest']:
        raise ProjectPackageError('AIRFLOW_STUDY_BINDING: saved fields belong to a different request')
    if record.get('assembly_digest') != canonical_json_digest(opened.payload.get('assembly_ir')):
        return {'state': 'stale', 'record': None, 'reason': 'Assembly changed; run airflow again.'}
    try:
        solids, _, _ = _geometry(opened, _artifact_reader(path, opened), record['assignments'], record['mesh_options'])
        if solids != record['request']['geometry']['solids']:
            return {'state': 'stale', 'record': None, 'reason': 'Retained physical sources changed; run airflow again.'}
    except (ValueError, KeyError, TypeError):
        return {'state': 'stale', 'record': None, 'reason': 'Retained physical sources are no longer admissible.'}
    return {'state': 'current', 'record': record}


def handle_airflow_project_request(method, params, *, request_id, application_version):
    operations = {'read_assembly_airflow_setup_in_project': read_setup,
                  'read_assembly_airflow_study_in_project': read_study}
    if method not in operations and method != 'run_assembly_airflow_in_project':
        return None
    try:
        if not isinstance(params, dict):
            raise ProjectPackageError('AIRFLOW_FIELDS: parameters must be an object')
        result = (run_in_project(params, application_version=application_version)
                  if method == 'run_assembly_airflow_in_project' else operations[method](params))
        return {'ok': True, 'result': result}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RuntimeError) as exc:
        return error_response('SPIKE-BE-THERMAL-E-0003', str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
