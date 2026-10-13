# SPDX-License-Identifier: Apache-2.0
"""Retain generated encapsulant STEP solids without losing project members."""
import copy
import hashlib
from pathlib import Path

from .assembly_field_study import export_assembly_field_study
from .assembly_field_handoff import prepare_assembly_field_handoff
from .multiboard_study import physical_assembly
from .assembly_thermal_components import MATERIALS_KEY
from .project_package import ProjectPackageError, write_spike_package
from .service_project_assembly import _invalidate_saved_results
from .service_project_assembly_field import _open_current_project

MAX_GENERATED_BYTES = 64 * 1024**2


def retain_generated_encapsulation(params, opened, path, result, mesh_root, *, application_version):
    sources = result.get('encapsulation_sources', [])
    if not sources:
        return result
    if len(sources) > 8:
        raise ProjectPackageError('ENCAPSULATION_BUDGET: at most eight generated solids may be retained')
    root = Path(mesh_root).resolve()
    payload = copy.deepcopy(opened.payload)
    before = copy.deepcopy(payload['assembly_ir'])
    payload['assembly_ir'] = copy.deepcopy(result['request']['assembly'])
    payload, invalidated = _invalidate_saved_results(payload, before)
    models = payload.setdefault('models', {'contract': 'spike/model-index/v1', 'models': []})
    records = models.setdefault('models', [])
    artifacts, total = {}, 0
    ids = {model['id'] for model in records}
    source_ids = {source['occurrence_id'] for source in sources}
    before_ids = {p['id'] for p in before.get('parts', [])} | {b['id'] for b in before.get('boards', [])}
    parts = {p['id']:p for p in payload['assembly_ir'].get('parts', [])}
    bodies = {b['occurrence_id']:b for b in result['request']['bodies']}
    if len(source_ids) != len(sources) or source_ids & before_ids:
        raise ProjectPackageError('ENCAPSULATION_SOURCE: duplicate or existing generated occurrence')
    stripped = copy.deepcopy(payload['assembly_ir'])
    stripped['parts'] = [p for p in stripped.get('parts', []) if p['id'] not in source_ids]
    if physical_assembly(stripped) != physical_assembly(before):
        raise ProjectPackageError('ENCAPSULATION_SOURCE: generation changed retained source assembly')
    for source in sources:
        part, body = parts.get(source['occurrence_id'], {}), bodies.get(source['occurrence_id'], {})
        if (part.get('model_id') != source['model_id'] or body.get('reference_id') != source['model_id'] or
                body.get('source_sha256') != source['sha256'] or
                part.get('material_id') != source['material_id'] or
                part.get('extensions', {}).get('spike.v1.encapsulation', {}).get('recipe') != source['recipe']):
            raise ProjectPackageError('ENCAPSULATION_SOURCE: generated source identity does not match physical body')
        raw_target = Path(source['path'])
        if not raw_target.is_absolute() or raw_target.suffix.lower() not in ('.step', '.stp') or any(
                p.is_symlink() for p in (raw_target, *raw_target.parents)):
            raise ProjectPackageError('ENCAPSULATION_SOURCE: generated STEP path must be an owned regular file')
        target = raw_target.resolve(strict=True)
        if not target.is_relative_to(root) or target.is_symlink() or not target.is_file():
            raise ProjectPackageError('ENCAPSULATION_SOURCE: generated STEP must stay inside the owned mesh directory')
        size = target.stat().st_size
        total += size
        if not 0 < size <= MAX_GENERATED_BYTES or total > MAX_GENERATED_BYTES:
            raise ProjectPackageError('ENCAPSULATION_BUDGET: generated STEP artifacts exceed 64 MiB')
        data = target.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != source['sha256'] or source['model_id'] in ids:
            raise ProjectPackageError('ENCAPSULATION_SOURCE: changed or conflicting generated model')
        name = 'encapsulation-' + digest + '.step'
        records.append({'id': source['model_id'], 'model_type': 'step',
                        'uri': 'package:models/artifacts/' + name, 'digest': digest})
        ids.add(source['model_id'])
        artifacts[name] = data
    materials = payload['assembly_ir'].setdefault('extensions', {}).setdefault(MATERIALS_KEY, {})
    for material in params['assignments']['materials']:
        materials[material['id']] = copy.deepcopy(material)
    # Store the new physical volume draft as well as the actual STEP solids.
    # Reopening therefore uses the same geometry without a missing file dialog.
    request = copy.deepcopy(result['request'])
    payload['assembly_ir'] = physical_assembly(payload['assembly_ir'])
    request['assembly'] = copy.deepcopy(payload['assembly_ir'])
    payload.setdefault('analyses', {})['assembly_field_study'] = export_assembly_field_study(
        request, {'contract': 'spike/assembly-field-thermal-problem/v1',
                  'boundaries': [], 'contacts': [], 'heat_sources': []})
    retained_assignments = copy.deepcopy(params['assignments'])
    retained_assignments.pop('encapsulation', None)
    retained_assignments['parts'].update({source['occurrence_id']:source['material_id'] for source in sources})
    payload['analyses']['assembly_thermal_mesh_setup'] = retained_assignments
    payload.setdefault('audit', []).append({'event': 'thermal_encapsulation_generated',
        'occurrence_ids': [s['occurrence_id'] for s in sources], 'invalidated_results': invalidated})
    _open_current_project(params, 'retaining generated encapsulation', include_members=False)
    manifest = write_spike_package(path, payload, model_artifacts=artifacts,
        preserved_members=opened.members, profile=str(opened.manifest.get('profile', 'portable_project')),
        application_version=application_version,
        expected_manifest_payload_sha256=params['expected_manifest_payload_sha256'])
    clean = copy.deepcopy(result)
    clean['encapsulation_sources'] = [{key: value for key, value in source.items() if key != 'path'} for source in sources]
    clean.update(request=request, handoff=prepare_assembly_field_handoff(request),
                 manifest=manifest, project_updated=True, saved_volume_setup=True,
                 retained_assignments=retained_assignments)
    return clean
