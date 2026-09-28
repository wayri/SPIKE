# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original typed planar-PCB solid compiler using an injected Gmsh OCC API.

No caller scripts/CAD files are executed. The caller owns process isolation,
dependency admission and Gmsh initialization/finalization. Output limits are
checked after meshing: they are NOT OS memory limits or production qualification.
"""
from __future__ import annotations

import itertools
import math

class OccMeshingError(ValueError):
    """Invalid geometry, ambiguous ownership, or failed mesh acceptance."""


def _require(test, message):
    if not test:
        raise OccMeshingError(message)


def _keys(value, keys):
    _require(isinstance(value, dict) and set(value) == set(keys), 'Unexpected contract fields.')


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e6
    except OverflowError:
        valid = False
    _require(valid, 'Expected a finite bounded number, not bool or text.')
    return float(value)


def _loop(value):
    _require(isinstance(value, list) and 3 <= len(value) <= 2048, 'Invalid polygon vertex count.')
    for point in value:
        _require(isinstance(point, list) and len(point) == 2, 'Invalid planar point.')
        for coordinate in point:
            _number(coordinate)
    _require(len({tuple(p) for p in value}) == len(value), 'Repeated polygon vertex.')


def validate_request(request):
    """Validate all geometry before calling the native kernel."""
    _keys(request, ('contract', 'solids', 'mesh'))
    _require(request['contract'] == 'spike/gmsh-occ-mesh/v1', 'Unsupported contract.')
    solids = request['solids']
    _require(isinstance(solids, list) and 1 <= len(solids) <= 64, 'Invalid solid budget.')
    names, total_points = set(), 0
    for solid in solids:
        _keys(solid, ('id', 'material_id', 'priority', 'shape'))
        for key in ('id', 'material_id'):
            _require(isinstance(solid[key], str) and 0 < len(solid[key]) <= 256, 'Invalid identity.')
        _require(solid['id'] not in names, 'Duplicate source identity.')
        names.add(solid['id'])
        _require(type(solid['priority']) is int and abs(solid['priority']) <= 1000000, 'Invalid priority.')
        shape = solid['shape']
        _require(isinstance(shape, dict), 'Invalid shape.')
        if shape.get('kind') == 'polygon_prism':
            _keys(shape, ('kind', 'outer_mm', 'holes_mm', 'z_min_mm', 'z_max_mm'))
            _require(isinstance(shape['holes_mm'], list) and len(shape['holes_mm']) <= 128, 'Invalid holes.')
            for loop in [shape['outer_mm'], *shape['holes_mm']]:
                _loop(loop)
                total_points += len(loop)
            try:
                from shapely.geometry import Polygon
            except ImportError as error:
                raise OccMeshingError("GMSH_DEPENDENCY: polygon validation requires Shapely in the optional OCC runtime.") from error
            polygon = Polygon(shape['outer_mm'], shape['holes_mm'])
            _require(polygon.is_valid and not polygon.is_empty and polygon.area > 1e-12,
                     'Polygon must be simple with valid non-touching holes and positive area.')
        elif shape.get('kind') == 'tube':
            _keys(shape, ('kind', 'center_mm', 'outer_radius_mm', 'inner_radius_mm', 'z_min_mm', 'z_max_mm'))
            _require(isinstance(shape['center_mm'], list) and len(shape['center_mm']) == 2, 'Invalid center.')
            for coordinate in shape['center_mm']:
                _number(coordinate)
            outer, inner = _number(shape['outer_radius_mm']), _number(shape['inner_radius_mm'])
            _require(0 <= inner < outer and outer-inner >= 1e-6, 'Invalid tube radii.')
        else:
            raise OccMeshingError('Unsupported shape; only polygon prisms and analytic tubes are accepted.')
        _require(_number(shape['z_max_mm'])-_number(shape['z_min_mm']) >= 1e-6, 'Invalid solid thickness.')
    _require(total_points <= 2048, 'Total polygon vertex budget exceeded.')
    options = request['mesh']
    _keys(options, ('min_size_mm', 'max_size_mm', 'max_cells', 'max_vertices'))
    _require(1e-6 <= _number(options['min_size_mm']) <= _number(options['max_size_mm']), 'Invalid mesh size.')
    for key in ('max_cells', 'max_vertices'):
        _require(type(options[key]) is int and 4 <= options[key] <= 100000, 'Invalid output budget.')


def _solid(occ, shape):
    z, height = shape['z_min_mm'], shape['z_max_mm']-shape['z_min_mm']
    if shape['kind'] == 'tube':
        x, y = shape['center_mm']
        outer = occ.addCylinder(x, y, z, 0, 0, height, shape['outer_radius_mm'])
        if shape['inner_radius_mm'] == 0:
            return outer
        inner = occ.addCylinder(x, y, z, 0, 0, height, shape['inner_radius_mm'])
        result, _ = occ.cut([(3, outer)], [(3, inner)])
    else:
        loops = []
        for ring in [shape['outer_mm'], *shape['holes_mm']]:
            points = [occ.addPoint(x, y, z) for x, y in ring]
            lines = [occ.addLine(a, b) for a, b in zip(points, points[1:]+points[:1])]
            loops.append(occ.addCurveLoop(lines))
        surface = occ.addPlaneSurface(loops)
        result = occ.extrude([(2, surface)], 0, 0, height)
    volumes = [tag for dim, tag in result if dim == 3]
    _require(len(volumes) == 1, 'Solid construction did not produce one connected volume.')
    return volumes[0]


def _det(points, indices):
    a = points[indices[0]]
    b, c, d = [[points[i][j]-a[j] for j in range(3)] for i in indices[1:]]
    return b[0]*(c[1]*d[2]-c[2]*d[1])-b[1]*(c[0]*d[2]-c[2]*d[0])+b[2]*(c[0]*d[1]-c[1]*d[0])


def build_occ_mesh(gmsh, request):
    """Generate tetrahedra with exact Boolean ancestry and shared interfaces."""
    validate_request(request)
    gmsh.clear()
    gmsh.model.add('spike_typed_pcb')
    for key, value in {'General.NumThreads': 1, 'General.Terminal': 0,
                       'Mesh.Algorithm3D': 1, 'Mesh.ElementOrder': 1,
                       'Mesh.MeshSizeMin': request['mesh']['min_size_mm'],
                       'Mesh.MeshSizeMax': request['mesh']['max_size_mm'],
                       'Mesh.MeshSizeFromCurvature': 16}.items():
        gmsh.option.setNumber(key, value)
    solids, occ = request['solids'], gmsh.model.occ
    initial = [(3, _solid(occ, solid['shape'])) for solid in solids]
    source_volumes = {solid['id']: occ.getMass(3, entity[1]) for solid, entity in zip(solids, initial)}
    if len(initial) > 1:
        fragments, mapping = occ.fragment(initial[:1], initial[1:])
    else:
        fragments, mapping = initial, [initial]
    occ.synchronize()
    ownership = {}
    for dim, tag in fragments:
        if dim != 3:
            continue
        ancestors = [s for s, descendants in zip(solids, mapping) if (3, tag) in descendants]
        _require(bool(ancestors), 'Fragment lacks source ancestry.')
        priority = max(s['priority'] for s in ancestors)
        materials = {s['material_id'] for s in ancestors if s['priority'] == priority}
        _require(len(materials) == 1, 'Overlapping equal-priority materials are ambiguous.')
        ownership[tag] = {'source_object_ids': sorted(s['id'] for s in ancestors),
                          'material_id': materials.pop(), 'cad_volume_mm3': occ.getMass(3, tag)}
    _require(ownership and len(ownership) <= 4096, 'Invalid fragment count.')
    covered = {name for own in ownership.values() for name in own['source_object_ids']}
    _require(covered == {s['id'] for s in solids}, 'A source was lost during fragmentation.')
    for source, original_volume in source_volumes.items():
        recovered = sum(own['cad_volume_mm3'] for own in ownership.values() if source in own['source_object_ids'])
        _require(math.isfinite(original_volume) and original_volume > 0 and
                 abs(recovered-original_volume) <= max(1e-12, 1e-7*original_volume),
                 'Boolean fragmentation did not conserve source solid volume.')
    gmsh.model.mesh.generate(3)
    tags, coordinates, _ = gmsh.model.mesh.getNodes()
    _require(4 <= len(tags) <= request['mesh']['max_vertices'], 'Vertex output budget exceeded.')
    points = [list(map(float, coordinates[i:i+3])) for i in range(0, len(coordinates), 3)]
    node_map = {int(tag): index for index, tag in enumerate(tags)}
    _require(all(math.isfinite(x) for point in points for x in point), 'Nonfinite mesh coordinates.')
    cells, faces, volumes, qualities = [], {}, {}, []
    for tag, own in sorted(ownership.items()):
        types, element_tags, node_lists = gmsh.model.mesh.getElements(3, tag)
        volumes[tag] = 0.0
        for kind, ids, nodes in zip(types, element_tags, node_lists):
            _require(int(kind) == 4, 'Only first-order tetrahedra are admitted.')
            _require(len(cells)+len(ids) <= request['mesh']['max_cells'], 'Cell output budget exceeded.')
            for offset, element in enumerate(ids):
                indices = [node_map[int(n)] for n in nodes[4*offset:4*offset+4]]
                determinant = _det(points, indices)
                if determinant < 0:
                    indices[0], indices[1] = indices[1], indices[0]
                    determinant = -determinant
                _require(math.isfinite(determinant) and determinant > 0, 'Degenerate tetrahedron.')
                volume = determinant/6
                _require(volume > 0 and math.isfinite(volume), 'Unrepresentable tetrahedron volume.')
                volumes[tag] += volume
                edge_sum = sum(sum((points[i][axis]-points[j][axis])**2 for axis in range(3))
                               for i,j in itertools.combinations(indices, 2))
                quality = 12*(determinant/2)**(2/3)/edge_sum
                _require(math.isfinite(quality) and quality > 0, 'Invalid cell quality.')
                qualities.append(quality)
                cell = {'id': str(int(element)), 'kind': 'tetrahedron', 'vertices': indices,
                        'material_id': own['material_id'], 'source_object_ids': own['source_object_ids']}
                cell_index = len(cells)
                cells.append(cell)
                # Outward oriented faces for a positive tetrahedron.
                a, b, c, d = indices
                for face in ([b,c,d], [a,d,c], [a,b,d], [a,c,b]):
                    faces.setdefault(tuple(sorted(face)), []).append((cell_index, face, tag))
    _require(bool(cells), 'No tetrahedra generated.')
    surface_tags = {}
    for _, surface in gmsh.model.getEntities(2):
        types, _, node_lists = gmsh.model.mesh.getElements(2, surface)
        for kind, nodes in zip(types, node_lists):
            _require(int(kind) == 2, 'Only linear surface triangles are admitted.')
            for offset in range(0, len(nodes), 3):
                key = tuple(sorted(node_map[int(n)] for n in nodes[offset:offset+3]))
                _require(key not in surface_tags, 'Duplicate geometric interface triangle.')
                surface_tags[key] = surface
    boundary, interfaces = [], []
    for key, adjacent in faces.items():
        _require(1 <= len(adjacent) <= 2, 'Nonmanifold tetrahedral face.')
        is_interface = len(adjacent) == 2 and adjacent[0][2] != adjacent[1][2]
        if len(adjacent) == 1 or is_interface:
            _require(key in surface_tags, 'Unrepresented exterior or interface face.')
            record = {'vertices': adjacent[0][1], 'cad_surface_tag': surface_tags[key],
                      'cell_ids': [cells[item[0]]['id'] for item in adjacent],
                      'material_ids': [cells[item[0]]['material_id'] for item in adjacent],
                      'source_object_ids': sorted({s for item in adjacent for s in cells[item[0]]['source_object_ids']})}
            (boundary if len(adjacent) == 1 else interfaces).append(record)
    _require(set(surface_tags) <= set(faces), 'Orphan geometric surface triangle.')
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'mm', 'coordinate_system': 'right_handed_xyz',
            'vertices': points, 'cells': cells, 'object_map': {s['id']: {'kind': s['shape']['kind']} for s in solids},
            'counts': {'vertices': len(points), 'cells': len(cells)}}
    # Reuse the independent neutral-mesh admission (including opposite-side
    # face owners and finite positive per-cell volume/quality), not just Gmsh's
    # successful return code. This is still not global intersection detection.
    from .tetra_mesh_refinement import _validate
    _validate(mesh, [{'vertices': face['vertices'], 'label': 'surface_' + str(face['cad_surface_tag'])}
                     for face in boundary], request['mesh']['max_cells'], request['mesh']['max_vertices'])
    return {'contract': 'spike/gmsh-occ-mesh-result/v1', 'status': 'completed', 'mesh': mesh,
            'boundary_triangles': [face['vertices'] for face in boundary], 'boundary_faces': boundary,
            'interface_faces': interfaces, 'fragment_ownership': {str(k): v for k,v in ownership.items()},
            'metrics': {'cad_volume_mm3': sum(v['cad_volume_mm3'] for v in ownership.values()),
                        'tetrahedron_volume_mm3': sum(volumes.values()),
                        'minimum_mean_ratio_quality': min(qualities),
                        'source_cad_volumes_mm3': source_volumes,
                        'fragment_mesh_volumes_mm3': {str(k): v for k,v in volumes.items()}},
            'production_qualified': False,
            'scope': 'planar_polygon_prisms_and_analytic_tubes_first_order_tetrahedra'}
