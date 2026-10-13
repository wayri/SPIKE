# SPDX-License-Identifier: Apache-2.0
"""One conformal OCC mesh split into separately owned retained thermal bodies.

Joint CAD fragmentation supplies matching triangles. Splitting copies shared
interface nodes into each occurrence: the thermal solver still requires an
explicit retained contact and its reviewed conductance, never implicit welding.
"""
import copy
import itertools
import math
import numpy as np

from .assembly_frames import inverse_affine, resolve_world
from .assembly_field_handoff import _assembly, prepare_assembly_field_handoff
from .multiboard_identity import canonical_json_digest


def validate_joint_job(request):
    from .assembly_frames import validate_rigid_transform
    from .gmsh_occ_mesher import _keys, _number, _require, validate_request
    _keys(request, ('contract', 'solids', 'mesh', *(['encapsulation'] if 'encapsulation' in request else [])))
    _require(request['contract'] == 'spike/gmsh-occ-assembly/v1', 'Invalid joint mesh contract.')
    _require(isinstance(request['solids'], list) and 1 <= len(request['solids']) <= 64,
             'ASSEMBLY_JOINT_BUDGET: joint meshing requires 1..64 source solids.')
    seen, points = set(), 0
    for solid in request['solids']:
        _keys(solid, ('id', 'material_id', 'priority', 'shape', 'occurrence_id', 'transform'))
        _require(isinstance(solid['occurrence_id'], str) and 0 < len(solid['occurrence_id']) <= 256,
                 'Invalid occurrence identity.')
        _require(solid['id'] not in seen, 'Duplicate joint source identity.')
        seen.add(solid['id'])
        transform = solid['transform']
        _require(isinstance(transform, list) and len(transform) == 16, 'Joint source requires rigid world placement.')
        for value in transform:
            _number(value)
        validate_rigid_transform(transform, 'Joint occurrence placement')
        source = {key: solid[key] for key in ('id', 'material_id', 'priority', 'shape')}
        step = solid['shape'].get('kind') == 'step_solid'
        validate_request({'contract': 'spike/gmsh-occ-step/v1' if step else 'spike/gmsh-occ-mesh/v1',
                          'solids': [source], 'mesh': request['mesh']})
        if solid['shape'].get('kind') == 'polygon_prism':
            points += len(solid['shape']['outer_mm']) + sum(map(len, solid['shape']['holes_mm']))
    if 'encapsulation' in request:
        from .assembly_thermal_encapsulation import validate_encapsulation
        validate_encapsulation(request['encapsulation'], {r['material_id'] for r in request['encapsulation']},
                               {s['occurrence_id'] for s in request['solids']}, request['mesh'])
    _require(points <= 2048, 'ASSEMBLY_JOINT_BUDGET: total polygon point budget exceeded.')


def _split_joint_mesh(plan, generated, origins, transforms):
    world = generated['mesh']
    by_owner = {entry['occurrence_id']: [] for entry in plan['jobs']}
    for cell in world['cells']:
        owners = {origins[sid]['occurrence_id'] for sid in cell['source_object_ids']}
        if len(owners) != 1:
            raise ValueError('ASSEMBLY_JOINT_OVERLAP: cross-occurrence cell ownership is ambiguous')
        by_owner[next(iter(owners))].append(cell)
    xyz = np.asarray(world['vertices'])
    bodies, evidence = [], []
    count = 0
    for entry in plan['jobs']:
        oid = entry['occurrence_id']
        owned = by_owner[oid]
        if not owned:
            raise ValueError('ASSEMBLY_JOINT_COVERAGE: retained occurrence has no tetrahedra')
        node_ids = sorted({v for cell in owned for v in cell['vertices']})
        mapping = {node: i for i, node in enumerate(node_ids)}
        count += len(node_ids)
        if count > plan['mesh_options']['max_vertices']:
            raise ValueError('ASSEMBLY_MESH_BUDGET: duplicated occurrence interface nodes exceed aggregate vertex budget')
        inverse = np.asarray(inverse_affine(transforms[oid])).reshape(4, 4)
        local = xyz[node_ids] @ inverse[:3, :3].T + inverse[:3, 3]
        cells, exterior = [], {}
        source_ids = set()
        volume = 0.
        for cell in owned:
            source_ids.update(cell['source_object_ids'])
            cell_sources = [origins[sid]['local_source_id'] for sid in cell['source_object_ids']]
            vertices = [mapping[v] for v in cell['vertices']]
            cells.append({**cell, 'vertices': vertices, 'source_object_ids': cell_sources})
            tetra = xyz[cell['vertices']]
            volume += float(np.linalg.det((tetra[1:]-tetra[0]).T)/6)
            for face in itertools.combinations(cell['vertices'], 3):
                key = tuple(sorted(face))
                exterior[key] = exterior.get(key, 0)+1
        boundary = [{'id': 'joint:'+':'.join(map(str, key)), 'vertices': [mapping[v] for v in key]}
                    for key, owners in sorted(exterior.items()) if owners == 1]
        mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'mm', 'coordinate_system': 'right_handed_xyz',
                'vertices': local.tolist(), 'cells': cells,
                'object_map': {origins[sid]['local_source_id']: origins[sid]['metadata'] for sid in sorted(source_ids)},
                'counts': {'vertices': len(node_ids), 'cells': len(cells)}}
        body = {key: copy.deepcopy(entry[key]) for key in ('occurrence_id', 'reference_id', 'source_sha256', 'material_map')}
        body.update(mesh=mesh, boundary_faces=boundary)
        if 'stack_binding' in entry:
            body['stack_binding'] = copy.deepcopy(entry['stack_binding'])
        bodies.append(body)
        source_volumes = {origins[sid]['local_source_id']: value
                          for sid, value in generated['metrics']['source_cad_volumes_mm3'].items()
                          if origins[sid]['occurrence_id'] == oid}
        # Cross-occurrence overlaps were rejected. Within a board, priority
        # fragments may overlap their input sources, so sum owned CAD fragments.
        cad_volume = math.fsum(fragment['cad_volume_mm3'] for fragment in generated['fragment_ownership'].values()
                              if origins[fragment['source_object_ids'][0]]['occurrence_id'] == oid)
        evidence.append({'occurrence_id': oid, 'representation': entry['representation'],
                         'approximations': entry['approximations'], 'meshing_mode': 'joint_conformal',
                         'metrics': {'cad_volume_mm3': cad_volume, 'tetrahedron_volume_mm3': volume,
                                     'source_cad_volumes_mm3': source_volumes,
                                     'minimum_mean_ratio_quality': generated['metrics']['minimum_mean_ratio_quality']}})
    return bodies, evidence


def run_joint_assembly_mesh(plan, root, runtime, *, artifact_reader, timeout_s, memory_limit_mb):
    from .assembly_thermal_meshing import _artifact
    from .gmsh_occ_runtime import run_occ_case
    assembly = _assembly(plan['assembly'])
    occurrences = {o.id: o for o in [*assembly.boards, *assembly.parts]}
    origins, transforms, solids = {}, {}, []
    for index, entry in enumerate(plan['jobs']):
        oid = entry['occurrence_id']
        transforms[oid] = list(resolve_world(assembly, occurrences[oid].frame))
        if 'encapsulation' in entry:
            continue
        if 'job' in entry:
            local_solids = copy.deepcopy(entry['job']['solids'])
        else:
            path = root/(str(index)+'.step')
            path.write_bytes(_artifact(artifact_reader, entry['source_uri'], entry['source_sha256']))
            local_solids = [{'id': entry['reference_id'], 'material_id': next(iter(entry['material_map'])),
                             'priority': 0, 'shape': {'kind': 'step_solid', 'path': str(path),
                                 'sha256': entry['source_sha256'], 'transform': entry['model_transform']}}]
        for solid in local_solids:
            local_id = solid['id']
            sid = canonical_json_digest([oid, local_id])
            origins[sid] = {'occurrence_id': oid, 'local_source_id': local_id,
                            'metadata': copy.deepcopy(entry.get('object_metadata', {}).get(local_id, {'kind': solid['shape']['kind']}))}
            solids.append({**solid, 'id': sid, 'occurrence_id': oid, 'transform': transforms[oid]})
    job = {'contract': 'spike/gmsh-occ-assembly/v1', 'solids': solids, 'mesh': plan['mesh_options']}
    if plan.get('encapsulation'):
        job['encapsulation'] = plan['encapsulation']
    case = root/'case-joint'
    try:
        generated = run_occ_case(job, case, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb)
    except RuntimeError as error:
        log = case/'worker.log'
        detail = str(error)
        if log.is_file() and not log.is_symlink():
            with log.open('rb') as stream:
                detail = stream.read(8192).decode('utf-8', errors='replace')
        return {**plan, 'status': 'blocked', 'blockers': [{'occurrence_id': '', 'code': 'CAD_MESH_FAILED', 'message': detail}]}
    encapsulation_sources = []
    for artifact in generated.get('encapsulation_exports', []):
        entry = next(e for e in plan['jobs'] if e['occurrence_id']==artifact['occurrence_id'])
        entry['source_sha256'] = artifact['sha256']
        encapsulation_sources.append({'model_id':entry['reference_id'], 'occurrence_id':entry['occurrence_id'],
            'path':str(case/artifact['file']), 'sha256':artifact['sha256'],
            'material_id':entry['encapsulation']['material_id'], 'recipe':copy.deepcopy(entry['encapsulation'])})
    for sid, data in generated.get('encapsulation_origins', {}).items():
        origins[sid] = data
    bodies, evidence = _split_joint_mesh(plan, generated, origins, transforms)
    request = {'contract': 'spike/assembly-field-handoff-request/v1', 'assembly': plan['assembly'],
               'domain': 'thermal', 'materials': plan['materials'], 'bodies': bodies}
    handoff = prepare_assembly_field_handoff(request)
    return {'contract': 'spike/assembly-thermal-mesh-result/v1', 'status': 'completed', 'request': request,
            'handoff': handoff, 'evidence': evidence, 'runtime': runtime, 'production_qualified': False,
            'meshing_mode': 'joint_conformal', 'contacts_inferred': False, 'boundary_conditions_inferred': False,
            'encapsulation_sources': encapsulation_sources,
            'joint_mesh_metrics': generated['metrics'], 'joint_interface_admission': generated['joint_interface_admission']}
