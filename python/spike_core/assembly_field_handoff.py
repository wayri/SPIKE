# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original bounded retained-volume handoff, independent of EDA/CAD engines.

Consumes supplied conforming volumes; it does not derive volumes from a
viewport, a STEP reference, a stack identifier, or a reduced network model.
Occurrence nodes remain distinct even where coordinates coincide. Assembly
placements rotate anisotropic thermal tensors into world SI coordinates.
"""
import copy
import json
import re
import numpy as np

from .assembly_field_geometry import (
    MAX_CELLS, MAX_VERTICES, assert_disjoint_occurrences, identity, keys,
    lower_body, number, thermal_tensor, validate_frames,
)
from .assembly_frames import resolve_world
from .multiboard_identity import assembly_physics_digest, canonical_json_digest
from .spider_v2 import AssemblyIRV1

REQUEST_CONTRACT = 'spike/assembly-field-handoff-request/v1'
RESULT_CONTRACT = 'spike/assembly-field-handoff/v1'
MAX_CONTROL_BYTES = 8*1024*1024
ROUTED_EM_PROFILE = 'routed_pcb_em_v1'


def field_resource_limits(value):
    """Explicit EM-only larger envelope; ordinary thermal/SI limits are unchanged."""
    profile=value.get('resource_profile') if isinstance(value,dict) else None
    if profile is None:
        return {'max_cells':MAX_CELLS,'max_vertices':MAX_VERTICES,'max_control_bytes':MAX_CONTROL_BYTES}
    if profile != ROUTED_EM_PROFILE or value.get('domain') != 'em':
        raise ValueError('ASSEMBLY_FIELD_RESOURCE: routed_pcb_em_v1 is an explicit EM-only profile')
    return {'max_cells':600000,'max_vertices':200000,'max_control_bytes':128*1024*1024}


def bounded_json(value, *, max_bytes=MAX_CONTROL_BYTES):
    try:
        payload = json.dumps(value, allow_nan=False, separators=(',', ':')).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('ASSEMBLY_FIELD_JSON: finite bounded JSON required') from exc
    if len(payload) > max_bytes:
        raise ValueError('ASSEMBLY_FIELD_RESOURCE: control payload exceeds '+str(max_bytes//1024**2)+' MiB')


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError('ASSEMBLY_FIELD_ID: bounded nonempty identity required')
    return value


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('ASSEMBLY_FIELD_DIGEST: lowercase SHA-256 required')
    return value


def _materials(raw, domain):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 1024:
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: bounded material table required')
    result = {}
    properties = ('thermal_conductivity_w_mk',) if domain == 'thermal' else (
        'conductivity_s_m', 'relative_permittivity', 'relative_permeability')
    for item in raw:
        keys(item, ('id', 'provenance', *properties))
        mid = text(item['id'])
        text(item['provenance'])
        if mid in result:
            raise ValueError('ASSEMBLY_FIELD_MATERIAL: duplicate material')
        if domain == 'thermal':
            thermal_tensor(item['thermal_conductivity_w_mk'])
        else:
            if number(item['conductivity_s_m']) < 0:
                raise ValueError('ASSEMBLY_FIELD_MATERIAL: negative conductivity')
            for prop in ('relative_permittivity', 'relative_permeability'):
                number(item[prop], positive=True)
        result[mid] = item
    return result


def _assembly(raw):
    if not isinstance(raw, dict):
        raise ValueError('ASSEMBLY_FIELD_ASSEMBLY: retained AssemblyIR required')
    # Check raw values before dataclass hydration can convert strings/bools.
    for item in [raw, *raw.get('boards', []), *raw.get('parts', [])]:
        frame = item.get('frame', {})
        if not isinstance(frame, dict):
            raise ValueError('ASSEMBLY_FIELD_FRAME: frame must be an object')
        transform = frame.get('transform', [])
        if not isinstance(transform, (list, tuple)):
            raise ValueError('ASSEMBLY_FIELD_FRAME: transform must be an array')
        for value in transform:
            number(value)
    assembly = AssemblyIRV1.from_dict(raw)
    validate_frames(assembly)
    return assembly


def prepare_assembly_field_handoff(request):
    """Return geometry plus explicit execution limits, not a field solution."""
    limits=field_resource_limits(request)
    bounded_json(request,max_bytes=limits['max_control_bytes'])
    keys(request, ('contract', 'assembly', 'domain', 'bodies', 'materials'), ('ports','resource_profile'))
    domain = request['domain']
    if request['contract'] != REQUEST_CONTRACT or domain not in ('thermal', 'em', 'si'):
        raise ValueError('ASSEMBLY_FIELD_CONTRACT: unsupported handoff')
    assembly = _assembly(request['assembly'])
    physical = {o.id: o for o in [*assembly.boards, *assembly.parts]
                if not (getattr(o, 'part_type', '') == 'subassembly' and not o.model_id)}
    materials = _materials(request['materials'], domain)
    if not isinstance(request['bodies'], list) or len(request['bodies']) != len(physical) or not physical:
        raise ValueError('ASSEMBLY_FIELD_COVERAGE: every physical occurrence needs one volume')
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'm', 'coordinate_system': 'right_handed_xyz',
            'vertices': [], 'cells': [], 'object_map': {}, 'counts': {}}
    faces, traces, world_materials, owners, seen, used_materials = [], [], [], [], set(), set()
    compact=request.get('resource_profile')==ROUTED_EM_PROFILE
    for body_index,body in enumerate(request['bodies']):
        keys(body, ('occurrence_id', 'reference_id', 'source_sha256', 'mesh', 'boundary_faces', 'material_map'),
             ('stack_binding',))
        oid = text(body['occurrence_id'])
        if oid not in physical or oid in seen:
            raise ValueError('ASSEMBLY_FIELD_COVERAGE: unknown or duplicate occurrence')
        seen.add(oid)
        occurrence = physical[oid]
        is_board = hasattr(occurrence, 'design_id')
        reference = occurrence.design_id if is_board else occurrence.model_id
        if not reference or body['reference_id'] != reference:
            raise ValueError('ASSEMBLY_FIELD_REFERENCE: retained design/model reference mismatch')
        digest(body['source_sha256'])
        if is_board:
            keys(body.get('stack_binding'), ('id', 'source_sha256'))
            text(body['stack_binding']['id'])
            digest(body['stack_binding']['source_sha256'])
        elif 'stack_binding' in body:
            raise ValueError('ASSEMBLY_FIELD_STACK: stack binding is board-only')
        placement_audit={}
        local, matrix, volume = lower_body(assembly, occurrence, body, set(materials),
            max_cells=limits['max_cells'],max_vertices=limits['max_vertices'],
            roundoff_aware=compact,transform_audit=placement_audit)
        if domain != 'em' and any(item.get('kind')=='em_material_region' for item in local['object_map'].values()):
            raise ValueError('ASSEMBLY_FIELD_GEOMETRY: planar EM material regions do not assert global FEM conformity')
        if len(mesh['vertices'])+len(local['vertices']) > limits['max_vertices'] or len(mesh['cells'])+len(local['cells']) > limits['max_cells']:
            raise ValueError('ASSEMBLY_FIELD_RESOURCE: aggregate mesh budget exceeded')
        offset = len(mesh['vertices'])
        mesh['vertices'].extend(local['vertices'])
        object_ids = {sid: ('source:'+str(body_index)+':'+str(i) if compact else identity('source',oid,sid))
                      for i,sid in enumerate(sorted(local['object_map']) if compact else local['object_map'])}
        material_ids = {}
        material_entries=sorted(body['material_map'].items()) if compact else body['material_map'].items()
        for material_index,(local_id, physical_id) in enumerate(material_entries):
            used_materials.add(physical_id)
            global_id = ('material:'+str(body_index)+':'+str(material_index) if compact else identity('material',oid,local_id))
            material_ids[local_id] = global_id
            entry = {**materials[physical_id], 'id': global_id}
            if domain == 'thermal':
                rotation = matrix[:3, :3]
                rotated = rotation@thermal_tensor(entry['thermal_conductivity_w_mk'])@rotation.T
                # Floating rotation may differ by rounding in symmetric entries.
                entry['thermal_conductivity_w_mk'] = ((rotated+rotated.T)/2).tolist()
            world_materials.append(entry)
        mesh['object_map'].update({object_ids[sid]: copy.deepcopy(data)
                                   for sid, data in local['object_map'].items()})
        cell_map = {}
        for cell_index,cell in enumerate(local['cells']):
            cell_id = ('cell:'+str(body_index)+':'+str(cell_index) if compact else identity('cell',oid,cell['id']))
            cell_map[cell['id']] = cell_id
            mesh['cells'].append({**cell, 'id': cell_id, 'vertices': [v+offset for v in cell['vertices']],
                                 'material_id': material_ids[cell['material_id']],
                                 'source_object_ids': [object_ids[sid] for sid in cell['source_object_ids']]})
            owners.append(oid)
        face_map = {}
        for face_index,face in enumerate(body['boundary_faces']):
            fid = ('face:'+str(body_index)+':'+str(face_index) if compact else identity('face',oid,face['id']))
            face_map[face['id']] = fid
            faces.append({'id': fid, 'occurrence_id': oid, 'local_face_id': face['id'],
                          'vertices': [v+offset for v in face['vertices']]})
        traces.append({'occurrence_id': oid, 'kind': 'board' if is_board else occurrence.part_type,
                       'reference_id': reference, 'source_sha256': body['source_sha256'],
                       'world_transform_mm': matrix.reshape(-1).tolist(), 'volume_m3': volume,
                       'local_mesh_sha256': canonical_json_digest(body['mesh']),
                       'vertex_range': [offset, offset+len(local['vertices'])],
                       'source_map': object_ids, 'cell_map': cell_map, 'face_map': face_map,
                       'material_map': material_ids, 'stack_binding': body.get('stack_binding')})
        if compact:
            traces[-1]['placement_audit']=placement_audit
    if used_materials != set(materials):
        raise ValueError('ASSEMBLY_FIELD_MATERIAL: unused material records are not admitted')
    mesh['counts'] = {'vertices': len(mesh['vertices']), 'cells': len(mesh['cells'])}
    audit = assert_disjoint_occurrences(mesh, owners,spatial_index=compact)
    ports = _ports(request.get('ports', []), faces, mesh, world_materials, domain)
    pending = []
    for field in ('harnesses', 'connector_mappings', 'rigid_flex_links', 'electrical_bonds'):
        if getattr(assembly, field):
            pending.append({'code': 'ASSEMBLY_FIELD_CONNECTIVITY_UNSUPPORTED', 'collection': field,
                            'ids': [item.id for item in getattr(assembly, field)]})
    if domain != 'thermal':
        pending.append({'code': 'ASSEMBLY_FIELD_BACKEND_UNAVAILABLE',
                        'detail': 'General retained-volume Maxwell/SI translator is not implemented.'})
    result = {'contract': RESULT_CONTRACT, 'domain': domain, 'model_status': 'experimental',
              'production_qualified': False, 'mesh': mesh, 'boundary_faces': faces,
              'materials': world_materials, 'ports': ports, 'source_traceability': traces,
              'assembly_digest': assembly_physics_digest(request['assembly']),
              'request_digest': canonical_json_digest(request), 'mesh_digest': canonical_json_digest(mesh),
              'geometry_audit': audit, 'execution_issues': pending,
              'excluded_hierarchy': [{'id': o.id, 'world_transform_mm': list(resolve_world(assembly, o.frame))}
                                     for o in assembly.parts if o.id not in physical],
              'limitations': ['Caller-supplied volumes; CAD/source and stack digest authenticity not verified.',
                              'Separate occurrence nodes; no implicit welding or thermal/electrical bonds.',
                              'Bounded floating-point intersection tests are not exact CAD certification.',
                              'No automatic airflow, nonlinear radiation, transient or full-wave execution.']}
    if compact:
        result['resource_profile']=ROUTED_EM_PROFILE
        result['limitations'].append('EM-only closed material regions; global FEM interface conformity is not asserted.')
    result['handoff_digest'] = canonical_json_digest(result)
    bounded_json(result,max_bytes=limits['max_control_bytes'])
    return copy.deepcopy(result)


def _ports(ports, faces, mesh, materials, domain):
    if not isinstance(ports, list) or len(ports) > 64 or (domain == 'thermal' and ports):
        raise ValueError('ASSEMBLY_FIELD_PORT: ports only supported as bounded EM/SI metadata')
    lookup = {(f['occurrence_id'], f['local_face_id']): f for f in faces}
    properties = {m['id']: m for m in materials}
    conductor_faces = set()
    for cell in mesh['cells']:
        if domain != 'thermal' and properties[cell['material_id']]['conductivity_s_m'] > 0:
            import itertools
            conductor_faces.update(tuple(sorted(face)) for face in itertools.combinations(cell['vertices'], 3))
    result, ids = [], set()
    for port in ports:
        keys(port, ('id', 'signal', 'return', 'reference_impedance_ohm'))
        pid = text(port['id'])
        if pid in ids:
            raise ValueError('ASSEMBLY_FIELD_PORT: duplicate port')
        ids.add(pid)
        number(port['reference_impedance_ohm'], positive=True)
        endpoints = []
        for name in ('signal', 'return'):
            keys(port[name], ('occurrence_id', 'face_id'))
            face = lookup.get((text(port[name]['occurrence_id']), text(port[name]['face_id'])))
            if not face or tuple(sorted(face['vertices'])) not in conductor_faces:
                raise ValueError('ASSEMBLY_FIELD_PORT: explicit exterior conductor face required')
            endpoints.append(face['id'])
        if endpoints[0] == endpoints[1]:
            raise ValueError('ASSEMBLY_FIELD_PORT: signal and return must differ')
        result.append({**copy.deepcopy(port), 'signal_face_id': endpoints[0], 'return_face_id': endpoints[1],
                       'modal_normalization': 'unsupported', 'executable': False})
    return result
