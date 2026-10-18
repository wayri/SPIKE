# SPDX-License-Identifier: Apache-2.0
"""Conforming OCC air complement of explicit closed CAD solids, in millimetres."""
from .gmsh_occ_mesher import _solid, _det, validate_request


def validate_geometry(job):
    if set(job) != {'solids', 'air_domain', 'mesh'} or not 1 <= len(job['solids']) <= 64:
        raise ValueError('AIRFLOW_GEOMETRY: bounded explicit solids required')
    names = set()
    for solid in job['solids']:
        if 'transform' in solid:
            from .assembly_frames import validate_rigid_transform
            validate_rigid_transform(solid['transform'], 'Airflow solid transform')
        contract = ('spike/gmsh-occ-step/v1' if solid['shape']['kind'] == 'step_solid'
                    else 'spike/gmsh-occ-mesh/v1')
        validate_request({'contract': contract, 'solids': [{k:v for k,v in solid.items() if k != 'transform'}], 'mesh': job['mesh']})
        if solid['id'] in names or solid['id'] == 'air':
            raise ValueError('AIRFLOW_GEOMETRY: duplicate/reserved source identity')
        names.add(solid['id'])
    validate_request({'contract': 'spike/gmsh-occ-mesh/v1', 'mesh': job['mesh'],
        'solids': [{'id': 'air', 'material_id': 'air', 'priority': 0, 'shape': job['air_domain']}]})


def build_air_mesh(gmsh, job):
    validate_geometry(job)
    gmsh.clear()
    gmsh.model.add('assembly_air_complement')
    gmsh.option.setString('Geometry.OCCTargetUnit', 'MM')
    for key, value in {'General.NumThreads': 1, 'General.Terminal': 0,
                       'Mesh.Algorithm3D': 1, 'Mesh.ElementOrder': 1,
                       'Mesh.MeshSizeMin': job['mesh']['min_size_mm'],
                       'Mesh.MeshSizeMax': job['mesh']['max_size_mm']}.items():
        gmsh.option.setNumber(key, value)
    occ = gmsh.model.occ
    air = (3, _solid(occ, job['air_domain'], gmsh.model))
    solids = [(3, _solid(occ, s['shape'], gmsh.model)) for s in job['solids']]
    for source, entity in zip(job['solids'], solids):
        if 'transform' in source:
            occ.affineTransform([entity], source['transform'])
    source_volumes = [occ.getMass(*entity) for entity in solids]
    fragments, mapping = occ.fragment([air], solids)
    occ.synchronize()
    owners = {}
    for dim, tag in fragments:
        if dim != 3:
            continue
        ancestry = [i for i, descendants in enumerate(mapping[1:]) if (3, tag) in descendants]
        if len(ancestry) > 1:
            raise ValueError('AIRFLOW_OVERLAP: solid interiors intersect')
        if (3, tag) not in mapping[0]:
            raise ValueError('AIRFLOW_DOMAIN: air domain does not contain every solid')
        owners[tag] = 'air' if not ancestry else 'solid_' + str(ancestry[0])
    if 'air' not in owners.values():
        raise ValueError('AIRFLOW_DOMAIN: no air volume remains')
    for i, original in enumerate(source_volumes):
        recovered = sum(occ.getMass(3, tag) for tag, owner in owners.items() if owner == 'solid_'+str(i))
        if original <= 0 or abs(recovered-original) > 1e-7*original:
            raise ValueError('AIRFLOW_VOLUME: source volume not conserved')
    gmsh.model.mesh.generate(3)
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    if len(tags) > job['mesh']['max_vertices']:
        raise ValueError('AIRFLOW_RESOURCE: vertex limit exceeded')
    points = [list(map(float, xyz[i:i+3])) for i in range(0, len(xyz), 3)]
    indices = {int(tag): i for i, tag in enumerate(tags)}
    cells, volumes = [], {}
    for tag, owner in owners.items():
        kinds, element_tags, node_lists = gmsh.model.mesh.getElements(3, tag)
        for kind, ids, nodes in zip(kinds, element_tags, node_lists):
            if kind != 4:
                raise ValueError('AIRFLOW_MESH: linear tetrahedra required')
            for offset, element in enumerate(ids):
                vertices = [indices[int(n)] for n in nodes[offset*4:offset*4+4]]
                determinant = _det(points, vertices)
                if determinant < 0:
                    vertices[0], vertices[1] = vertices[1], vertices[0]
                    determinant = -determinant
                if determinant <= 0:
                    raise ValueError('AIRFLOW_MESH: degenerate tetrahedron')
                volumes[owner] = volumes.get(owner, 0) + determinant/6
                cells.append({'id': 'cell_'+str(element), 'kind': 'tetrahedron',
                    'vertices': vertices, 'material_id': owner, 'source_object_ids': [owner]})
                if len(cells) > job['mesh']['max_cells']:
                    raise ValueError('AIRFLOW_RESOURCE: cell limit exceeded')
    if set(volumes) != set(owners.values()):
        raise ValueError('AIRFLOW_MESH: unmeshed region')
    for i, cad in enumerate(source_volumes):
        if abs(volumes['solid_'+str(i)]-cad) > .02*cad:
            raise ValueError('AIRFLOW_MESH: solid mesh volume differs from CAD by more than two percent; refine mesh')
    return {'units': 'mm', 'vertices': points, 'cells': cells, 'volumes_mm3': volumes,
            'source_ids': {'solid_'+str(i): s['id'] for i, s in enumerate(job['solids'])},
            'cad_volumes_mm3': {'solid_'+str(i): v for i, v in enumerate(source_volumes)}}
