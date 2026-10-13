# SPDX-License-Identifier: Apache-2.0
"""Owned complete tetrahedral extension result, independent of solver choice."""
import copy
import json
import itertools

from .assembly_field_handoff import digest
from .multiboard_identity import canonical_json_digest
from .tetra_mesh_refinement import _validate

CONTRACT = 'spike/gmsh-mesh/v1'
MAX_BYTES = 8 * 1024**2


def admit_gmsh_mesh(raw, binding, *, extension_id='spike.gmsh-suite'):
    if not isinstance(raw, dict) or raw.get('contract') != CONTRACT:
        raise ValueError('GMSH_MESH_CONTRACT: expected typed Gmsh volume result')
    fields = {'contract','status','solved','model_status','production_qualified','units','coordinate_frame',
              'solver_mesh','nodes_mm','tetrahedra','triangles','boundary_faces','interface_faces','metrics',
              'fragment_ownership','geometry_evidence','provenance','compatibility'}
    if not fields <= set(raw) or set(raw)-fields-{'admission'}:
        raise ValueError('GMSH_MESH_FIELDS: unexpected or missing result fields')
    if (raw.get('status') != 'completed' or raw.get('solved') is not False or
            raw.get('model_status') != 'experimental' or raw.get('units') != 'mm' or
            raw.get('coordinate_frame') != 'normalized_board_local_mm' or raw.get('production_qualified') is not False):
        raise ValueError('GMSH_MESH_STATE: geometry result cannot claim a solved or qualified field')
    if len(json.dumps(raw, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('GMSH_MESH_BUDGET: complete result exceeds 8 MiB; use coarser sizing')
    provenance = raw.get('provenance', {})
    if (provenance.get('design_id') != binding['design_id'] or
            provenance.get('design_digest_sha256') != binding['digest_sha256'] or
            provenance.get('extension_id') != extension_id):
        raise ValueError('GMSH_MESH_BINDING: result does not belong to the current design/extension')
    for key in ('request_sha256', 'job_sha256', 'mesh_sha256'):
        digest(provenance.get(key))
    mesh = raw['solver_mesh']
    boundary = raw['boundary_faces']
    _validate(mesh, [{'vertices': f['vertices'], 'label': str(i)} for i,f in enumerate(boundary)], 100000, 100000)
    if mesh['units'] != 'mm' or canonical_json_digest(mesh) != provenance['mesh_sha256']:
        raise ValueError('GMSH_MESH_DIGEST: mesh content or units changed')
    if (raw.get('nodes_mm') != mesh['vertices'] or
            raw.get('tetrahedra') != [c['vertices'] for c in mesh['cells']] or
            raw.get('triangles') != [f['vertices'] for f in boundary]):
        raise ValueError('GMSH_MESH_TOPOLOGY: display arrays must equal the complete solver topology')
    if {s for cell in mesh['cells'] for s in cell['source_object_ids']} != set(mesh['object_map']):
        raise ValueError('GMSH_MESH_SOURCE: source ownership is incomplete')
    adjacent = {}
    for cell in mesh['cells']:
        for vertices in itertools.combinations(cell['vertices'], 3):
            adjacent.setdefault(tuple(sorted(vertices)), []).append(cell)
    interfaces = set()
    for records, expected_count in ((boundary, 1), (raw['interface_faces'], 2)):
        for face in records:
            vertices = tuple(sorted(face['vertices']))
            owners = adjacent.get(vertices, [])
            by_id = {c['id']: c for c in owners}
            if (len(owners) != expected_count or set(face['cell_ids']) != set(by_id) or
                    len(face['cell_ids']) != expected_count or
                    face['material_ids'] != [by_id[c]['material_id'] for c in face['cell_ids']] or
                    face['source_object_ids'] != sorted({s for c in owners for s in c['source_object_ids']})):
                raise ValueError('GMSH_MESH_FACE: CAD face ownership does not match its volume cells')
            if expected_count == 2:
                if vertices in interfaces:
                    raise ValueError('GMSH_MESH_FACE: duplicate material interface')
                interfaces.add(vertices)
    if any(len(cells) == 2 and cells[0]['material_id'] != cells[1]['material_id'] and face not in interfaces
           for face,cells in adjacent.items()):
        raise ValueError('GMSH_MESH_FACE: material interface coverage is incomplete')
    result = copy.deepcopy(raw)
    result['admission'] = {'contract': 'spike/extension-mesh-admission/v1', 'design_bound': True,
                           'complete_connectivity': True, 'physics_validated': False, 'cross_engine_reuse': False}
    return result


def mesh_result(generated, prepared, binding):
    mesh = generated['mesh']
    result = {'contract': CONTRACT, 'status': 'completed', 'solved': False, 'model_status': 'experimental',
              'production_qualified': False, 'units': 'mm', 'coordinate_frame': 'normalized_board_local_mm',
              'solver_mesh': mesh, 'nodes_mm': mesh['vertices'], 'tetrahedra': [c['vertices'] for c in mesh['cells']],
              'triangles': generated['boundary_triangles'], 'boundary_faces': generated['boundary_faces'],
              'interface_faces': generated['interface_faces'], 'metrics': generated['metrics'],
              'fragment_ownership': generated['fragment_ownership'],
              'geometry_evidence': prepared['geometry_evidence'],
              'provenance': {'extension_id': 'spike.gmsh-suite', 'design_id': binding['design_id'],
                  'design_digest_sha256': binding['digest_sha256'], 'request_sha256': prepared['request_sha256'],
                  'job_sha256': prepared['job_sha256'], 'mesh_sha256': canonical_json_digest(mesh),
                  'runtime': {**generated['runtime_provenance'],
                              'isolated_environment': generated.get('runtime_environment')}, 'operation': 'mesh_only',
                  'geometry_source': 'explicit_normalized_complete_pcb_volume_model'},
              'compatibility': {'thermal': 'Explicit physical materials and boundary/contact bindings required.',
                  'em': 'Geometry only; no Maxwell ports, air region or absorbing boundaries created.',
                  'si': 'Geometry only; no conductor terminals or S-parameter solver translator created.'}}
    return admit_gmsh_mesh(result, binding)
