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


def _loop(value, max_points=2048):
    _require(isinstance(value, list) and 3 <= len(value) <= max_points, 'Invalid polygon vertex count.')
    for point in value:
        _require(isinstance(point, list) and len(point) == 2, 'Invalid planar point.')
        for coordinate in point:
            _number(coordinate)
    _require(len({tuple(p) for p in value}) == len(value), 'Repeated polygon vertex.')


def validate_request(request):
    """Validate all geometry before calling the native kernel."""
    if isinstance(request, dict) and request.get('contract') == 'spike/gmsh-occ-assembly/v1':
        from .assembly_thermal_joint_mesh import validate_joint_job
        validate_joint_job(request)
        return
    if isinstance(request, dict) and request.get('contract') == 'spike/gmsh-occ-step/v1':
        from .assembly_thermal_cad import validate_step_job
        validate_step_job(request)
        return
    _require(isinstance(request, dict), 'Request must be an object.')
    focused = request.get('contract') == 'spike/gmsh-occ-mesh/v2'
    _keys(request, ('contract', 'solids', 'mesh', 'object_metadata', 'focus') if focused
          else ('contract', 'solids', 'mesh'))
    _require(request['contract'] in ('spike/gmsh-occ-mesh/v1', 'spike/gmsh-occ-mesh/v2'),
             'Unsupported contract.')
    solid_limit, point_limit = (10000, 131072) if focused else (64, 2048)
    solids = request['solids']
    _require(isinstance(solids, list) and 1 <= len(solids) <= solid_limit, 'Invalid solid budget.')
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
                _loop(loop, point_limit)
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
    _require(total_points <= point_limit, 'Total polygon vertex budget exceeded.')
    options = request['mesh']
    _keys(options, ('min_size_mm', 'max_size_mm', 'max_cells', 'max_vertices'))
    _require(1e-6 <= _number(options['min_size_mm']) <= _number(options['max_size_mm']), 'Invalid mesh size.')
    for key in ('max_cells', 'max_vertices'):
        _require(type(options[key]) is int and 4 <= options[key] <= 100000, 'Invalid output budget.')
    if focused:
        metadata = request['object_metadata']
        _require(isinstance(metadata, dict) and set(metadata) == names,
                 'Object metadata must cover every source solid exactly.')
        for value in metadata.values():
            _require(isinstance(value, dict) and 'kind' in value and
                     set(value) <= {'kind', 'net', 'layer'} and
                     all(isinstance(item, str) and 0 < len(item) <= 256 for item in value.values()),
                     'Invalid source metadata.')
        from .pcb_focus_sizing import plan_focus_regions
        plan = plan_focus_regions(solids, metadata, request['focus'], include_solids=False)
        _require(options['max_size_mm'] == request['focus']['coarse_size_mm'],
                 'Global maximum size must match the coarse background target.')
        _require(options['min_size_mm'] <= min(region['target_size_mm'] for region in plan['regions']),
                 'Global minimum size would clamp the focus target.')
        for region in plan['regions']:
            thickness = (options['max_size_mm']-region['target_size_mm'])/region['growth_rate']
            _require(math.isfinite(thickness) and thickness <= 1e6,
                     'Focus transition thickness exceeds the bounded CAD coordinate range.')


def _focus_fields(gmsh, plan, coarse_size):
    """Create fixed numeric fields only; no caller expressions or scripts."""
    fields = gmsh.model.mesh.field
    tags = []
    for region in plan['regions']:
        tag = fields.add('Box')
        tags.append(tag)
        low, high = region['bounds_mm']
        halo = region['halo_mm']
        values = {'VIn': region['target_size_mm'], 'VOut': coarse_size,
                  'Thickness': (coarse_size-region['target_size_mm'])/region['growth_rate']}
        for axis, name in enumerate(('X', 'Y', 'Z')):
            values[name+'Min'], values[name+'Max'] = low[axis]-halo, high[axis]+halo
        for name, value in values.items():
            fields.setNumber(tag, name, value)
    minimum = fields.add('Min')
    fields.setNumbers(minimum, 'FieldsList', tags)
    fields.setAsBackgroundMesh(minimum)
    # Small copper edges do not force their fine size across whole adjacent
    # board volumes. Geometric edge/curve constraints still remain mandatory.
    gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)


def _solid(occ, shape, model=None, *, apply_transform=True):
    if shape['kind'] == 'step_solid':
        from .assembly_thermal_cad import import_step_solid
        return import_step_solid(occ, shape, model, apply_transform=apply_transform)
    z, height = shape['z_min_mm'], shape['z_max_mm']-shape['z_min_mm']
    if shape['kind'] == 'polygon_prism' and not shape['holes_mm']:
        ring = shape['outer_mm']
        xs, ys = sorted({p[0] for p in ring}), sorted({p[1] for p in ring})
        if len(ring) == 4 and len(xs) == len(ys) == 2 and all(
                a[0] == b[0] or a[1] == b[1] for a,b in zip(ring,ring[1:]+ring[:1])):
            return occ.addBox(xs[0],ys[0],z,xs[1]-xs[0],ys[1]-ys[0],height)
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
    focused = request['contract'] == 'spike/gmsh-occ-mesh/v2'
    focus_plan = None
    if focused:
        from .pcb_focus_sizing import plan_focus_regions
        focus_plan = plan_focus_regions(request['solids'], request['object_metadata'], request['focus'],
                                        include_solids=False)
    gmsh.clear()
    gmsh.model.add('spike_typed_pcb')
    joint = request['contract'] == 'spike/gmsh-occ-assembly/v1'
    if request['contract'] == 'spike/gmsh-occ-step/v1' or joint:
        gmsh.option.setString('Geometry.OCCTargetUnit', 'MM')
    for key, value in {'General.NumThreads': 1, 'General.Terminal': 0,
                       'Mesh.Algorithm3D': 1, 'Mesh.ElementOrder': 1,
                       'Mesh.MeshSizeMin': request['mesh']['min_size_mm'],
                       'Mesh.MeshSizeMax': request['mesh']['max_size_mm'],
                       'Mesh.MeshSizeFromCurvature': 16}.items():
        gmsh.option.setNumber(key, value)
    solids, occ = request['solids'], gmsh.model.occ
    initial = [(3, _solid(occ, solid['shape'], gmsh.model, apply_transform=not joint)) for solid in solids]
    if joint:
        from .assembly_thermal_joint_geometry import capture_joint_source_boundaries, source_world_transform
        source_geometry = capture_joint_source_boundaries(gmsh, solids, initial)
        for solid, entity in zip(solids, initial):
            from .assembly_thermal_encapsulation_occ import rigid_place
            rigid_place(occ, entity, source_world_transform(solid))
    encapsulation_exports = []
    if joint and request.get('encapsulation'):
        from .assembly_thermal_encapsulation_occ import construct_encapsulation
        solids, initial, encapsulation_exports = construct_encapsulation(gmsh, request['encapsulation'], solids, initial, source_geometry)
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
        if joint:
            _require(len({s['occurrence_id'] for s in ancestors}) == 1,
                     'ASSEMBLY_JOINT_OVERLAP: retained occurrences have intersecting positive CAD volumes.')
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
    if focus_plan is not None:
        _focus_fields(gmsh, focus_plan, request['mesh']['max_size_mm'])
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
    _require(all(math.isfinite(value) and value > 0 for value in volumes.values()),
             'A CAD fragment is unmeshed or has no representable positive tetrahedron volume.')
    mesh_covered = {source for cell in cells for source in cell['source_object_ids']}
    _require(mesh_covered == covered, 'Source coverage was lost during tetrahedral meshing.')
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
    if joint:
        from .assembly_thermal_joint_geometry import verify_joint_source_interfaces
        interface_admission = verify_joint_source_interfaces(source_geometry, interfaces, points)
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'mm', 'coordinate_system': 'right_handed_xyz',
            'vertices': points, 'cells': cells, 'object_map': (
                {key: dict(value) for key, value in request['object_metadata'].items()} if focused
                else {s['id']: {'kind': s['shape']['kind']} for s in solids}),
            'counts': {'vertices': len(points), 'cells': len(cells)}}
    # Reuse the independent neutral-mesh admission (including opposite-side
    # face owners and finite positive per-cell volume/quality), not just Gmsh's
    # successful return code. This is still not global intersection detection.
    from .tetra_mesh_refinement import _validate
    _validate(mesh, [{'vertices': face['vertices'], 'label': 'surface_' + str(face['cad_surface_tag'])}
                     for face in boundary], request['mesh']['max_cells'], request['mesh']['max_vertices'])
    result = {'contract': 'spike/gmsh-occ-mesh-result/v2' if focused else 'spike/gmsh-occ-mesh-result/v1',
            'status': 'completed', 'mesh': mesh,
            'boundary_triangles': [face['vertices'] for face in boundary], 'boundary_faces': boundary,
            'interface_faces': interfaces, 'fragment_ownership': {str(k): v for k,v in ownership.items()},
            'metrics': {'cad_volume_mm3': sum(v['cad_volume_mm3'] for v in ownership.values()),
                        'tetrahedron_volume_mm3': sum(volumes.values()),
                        'minimum_mean_ratio_quality': min(qualities),
                        'source_cad_volumes_mm3': source_volumes,
                        'fragment_mesh_volumes_mm3': {str(k): v for k,v in volumes.items()}},
            'production_qualified': False,
            'scope': 'planar_polygon_prisms_and_analytic_tubes_first_order_tetrahedra'}
    if request['contract'] == 'spike/gmsh-occ-step/v1':
        result['scope'] = 'single_closed_step_solid_first_order_tetrahedra'
    if joint:
        result['scope'] = 'joint_retained_occurrence_conformal_first_order_tetrahedra'
        result['joint_interface_admission'] = interface_admission
        result['encapsulation_exports'] = encapsulation_exports
        result['encapsulation_origins'] = {s['id']: {'occurrence_id':s['occurrence_id'],
            'local_source_id':s['id'], 'metadata':{'kind':s['shape']['kind']}}
            for s in solids if s['shape']['kind'] in ('coating','potting')}
    if focus_plan is not None:
        from .pcb_focus_sizing import assess_focus_mesh
        result['focus_plan'] = focus_plan
        result['focus_assessment'] = assess_focus_mesh(mesh, focus_plan['regions'], request['focus']['coarse_size_mm'],
                                                       include_mesh=False)
        result['whole_model_retained'] = mesh_covered == {s['id'] for s in solids}
    return result
