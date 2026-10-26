# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Solver-neutral graded PCB focus-size planning and mesh assessment.

Selected typed PCB solids are represented by conservative axis-aligned source
bounds.  This deliberately measures distance to a bounding box, not exact CAD
distance.  It never crops solids, calls Gmsh, or claims mesh convergence.
"""
from __future__ import annotations

import copy
import itertools
import math

from .tetra_mesh_refinement import _det

POLICY_CONTRACT = 'spike/pcb-focus-sizing/v1'
MAX_SOLIDS = 10_000
MAX_SELECTOR_VALUES = 10_000
MAX_MANUAL_REGIONS = 4_096
MAX_GENERATED_REGIONS = 4_096
MAX_POLYGON_POINTS = 131_072
MAX_MESH_CELLS = 100_000
MAX_MESH_VERTICES = 100_000
MAX_ASSESSMENT_COMPARISONS = 5_000_000
MAX_ABS_MM = 1_000_000.0


class PcbFocusSizingError(ValueError):
    """Malformed focus policy, solid geometry, or assessment mesh."""


def _require(condition, message):
    if not condition:
        raise PcbFocusSizingError(message)


def _keys(value, expected, label):
    _require(isinstance(value, dict) and set(value) == set(expected),
             f'{label} fields do not match the contract.')


def _number(value, label, *, bounded_mm=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    _require(valid, f'{label} must be a finite number, not bool or text.')
    result = float(value)
    if bounded_mm:
        _require(abs(result) <= MAX_ABS_MM, f'{label} exceeds the coordinate budget.')
    return result


def _name_list(value, label):
    _require(isinstance(value, list) and len(value) <= MAX_SELECTOR_VALUES and
             all(isinstance(item, str) and 0 < len(item) <= 256 for item in value) and
             len(set(value)) == len(value), f'{label} must contain unique nonempty strings.')
    return list(value)


def _bounds(value, label):
    _require(isinstance(value, list) and len(value) == 2 and
             all(isinstance(point, list) and len(point) == 3 for point in value),
             f'{label} must contain two three-dimensional points.')
    result = [[_number(coordinate, label, bounded_mm=True) for coordinate in point]
              for point in value]
    _require(all(result[0][axis] <= result[1][axis] for axis in range(3)),
             f'{label} minimum must not exceed its maximum.')
    return result


def _polygon_loop(value, point_budget):
    _require(isinstance(value, list) and 3 <= len(value) <= MAX_POLYGON_POINTS,
             'Invalid polygon loop vertex count.')
    _require(point_budget[0] + len(value) <= MAX_POLYGON_POINTS,
             'Total polygon point budget exceeded.')
    points = []
    for point in value:
        _require(isinstance(point, list) and len(point) == 2, 'Invalid polygon point.')
        points.append([_number(point[0], 'Polygon coordinate', bounded_mm=True),
                       _number(point[1], 'Polygon coordinate', bounded_mm=True)])
    _require(len(set(map(tuple, points))) == len(points), 'Repeated polygon vertex.')
    # Recenter before the shoelace sum.  Direct products of large translated
    # coordinates can cancel away a small but representable polygon area.
    origin_x, origin_y = points[0]
    local = [(point[0] - origin_x, point[1] - origin_y) for point in points]
    area2 = math.fsum(local[index][0] * local[(index + 1) % len(local)][1] -
                      local[(index + 1) % len(local)][0] * local[index][1]
                      for index in range(len(local)))
    _require(math.isfinite(area2) and area2 != 0, 'Degenerate polygon loop.')
    point_budget[0] += len(points)
    return points


def _solid_bounds(solid, point_budget):
    _keys(solid, ('id', 'material_id', 'priority', 'shape'), 'Solid')
    _require(isinstance(solid['id'], str) and 0 < len(solid['id']) <= 256 and
             isinstance(solid['material_id'], str) and 0 < len(solid['material_id']) <= 256 and
             type(solid['priority']) is int and abs(solid['priority']) <= 1_000_000,
             'Invalid solid identity, material, or priority.')
    shape = solid['shape']
    _require(isinstance(shape, dict), 'Invalid solid shape.')
    kind = shape.get('kind')
    if kind == 'polygon_prism':
        _keys(shape, ('kind', 'outer_mm', 'holes_mm', 'z_min_mm', 'z_max_mm'),
              'Polygon prism')
        _require(isinstance(shape['holes_mm'], list) and len(shape['holes_mm']) <= 128,
                 'Invalid polygon hole array.')
        outer = _polygon_loop(shape['outer_mm'], point_budget)
        for hole in shape['holes_mm']:
            _polygon_loop(hole, point_budget)
        xmin, xmax = min(point[0] for point in outer), max(point[0] for point in outer)
        ymin, ymax = min(point[1] for point in outer), max(point[1] for point in outer)
    elif kind == 'tube':
        _keys(shape, ('kind', 'center_mm', 'outer_radius_mm', 'inner_radius_mm',
                      'z_min_mm', 'z_max_mm'), 'Tube')
        _require(isinstance(shape['center_mm'], list) and len(shape['center_mm']) == 2,
                 'Invalid tube center.')
        x = _number(shape['center_mm'][0], 'Tube center', bounded_mm=True)
        y = _number(shape['center_mm'][1], 'Tube center', bounded_mm=True)
        outer = _number(shape['outer_radius_mm'], 'Outer radius', bounded_mm=True)
        inner = _number(shape['inner_radius_mm'], 'Inner radius', bounded_mm=True)
        _require(0 <= inner < outer and outer - inner >= 1e-6, 'Invalid tube radii.')
        xmin, xmax, ymin, ymax = x - outer, x + outer, y - outer, y + outer
        _require(max(abs(xmin), abs(xmax), abs(ymin), abs(ymax)) <= MAX_ABS_MM,
                 'Tube bounds exceed the coordinate budget.')
    else:
        raise PcbFocusSizingError('Only polygon_prism and tube solids are supported.')
    zmin = _number(shape['z_min_mm'], 'Solid z minimum', bounded_mm=True)
    zmax = _number(shape['z_max_mm'], 'Solid z maximum', bounded_mm=True)
    _require(zmax - zmin >= 1e-6, 'Solid thickness must be at least 1e-6 mm.')
    return [[xmin, ymin, zmin], [xmax, ymax, zmax]]


def _validate_policy(policy):
    _keys(policy, ('contract', 'net_names', 'source_ids', 'fine_size_mm',
                   'coarse_size_mm', 'halo_mm', 'growth_rate', 'regions'), 'Policy')
    _require(policy['contract'] == POLICY_CONTRACT, 'Unsupported PCB focus policy contract.')
    nets = _name_list(policy['net_names'], 'net_names')
    sources = _name_list(policy['source_ids'], 'source_ids')
    fine = _number(policy['fine_size_mm'], 'fine_size_mm', bounded_mm=True)
    coarse = _number(policy['coarse_size_mm'], 'coarse_size_mm', bounded_mm=True)
    halo = _number(policy['halo_mm'], 'halo_mm', bounded_mm=True)
    growth = _number(policy['growth_rate'], 'growth_rate')
    _require(0 < fine <= coarse, 'Size policy requires 0 < fine_size_mm <= coarse_size_mm.')
    _require(halo >= 0, 'halo_mm must be nonnegative.')
    _require(0 < growth <= 1, 'growth_rate must be in (0, 1].')
    raw_regions = policy['regions']
    _require(isinstance(raw_regions, list) and len(raw_regions) <= MAX_MANUAL_REGIONS,
             'At most 4096 manual focus regions are admitted.')
    regions = []
    ids = set()
    for raw in raw_regions:
        _keys(raw, ('id', 'bounds_mm', 'target_size_mm'), 'Manual region')
        _require(isinstance(raw['id'], str) and 0 < len(raw['id']) <= 256 and
                 raw['id'] not in ids, 'Manual region IDs must be unique nonempty strings.')
        ids.add(raw['id'])
        target = _number(raw['target_size_mm'], 'target_size_mm', bounded_mm=True)
        _require(0 < target <= coarse, 'Manual target_size_mm must be in (0, coarse_size_mm].')
        regions.append({'id': raw['id'], 'bounds_mm': _bounds(raw['bounds_mm'], 'bounds_mm'),
                        'target_size_mm': target})
    _require(bool(nets or sources or regions), 'At least one net, source, or manual region is required.')
    return nets, sources, fine, coarse, halo, growth, regions


def _validate_metadata(object_metadata, solid_ids):
    _require(isinstance(object_metadata, dict) and len(object_metadata) <= MAX_SOLIDS,
             'Invalid object metadata map.')
    _require(set(object_metadata) == solid_ids,
             'Object metadata must cover every source solid exactly.')
    result = {}
    for solid_id, raw in object_metadata.items():
        _require(isinstance(solid_id, str) and isinstance(raw, dict) and 'kind' in raw and
                 set(raw) <= {'kind', 'net', 'layer'}, 'Invalid object metadata fields.')
        parsed = {}
        for key, value in raw.items():
            _require(isinstance(value, str) and 0 < len(value) <= 256,
                     'Object metadata values must be nonempty strings.')
            parsed[key] = value
        result[solid_id] = parsed
    return result


def _region_record(identifier, bounds, target, halo, growth):
    return {'id': identifier, 'bounds_mm': copy.deepcopy(bounds),
            'target_size_mm': target, 'halo_mm': halo, 'growth_rate': growth}


def plan_focus_regions(solids, object_metadata, policy, *, include_solids=True):
    """Create independent conservative focus boxes while retaining all solids.

    Net and explicit source selectors are unioned.  Every requested selector
    must resolve.  A selected plane naturally receives its full source bounds;
    use a manual region when only part of a plane should be focused.
    """
    nets, source_ids, fine, coarse, halo, growth, manual = _validate_policy(policy)
    _require(isinstance(solids, list) and 1 <= len(solids) <= MAX_SOLIDS,
             'Invalid solid resource budget.')
    point_budget = [0]
    source_bounds = {}
    for solid in solids:
        bounds = _solid_bounds(solid, point_budget)
        _require(solid['id'] not in source_bounds, 'Duplicate solid ID.')
        source_bounds[solid['id']] = bounds
    solid_ids = set(source_bounds)
    metadata = _validate_metadata(object_metadata, solid_ids)

    unknown_sources = sorted(set(source_ids) - solid_ids)
    if unknown_sources:
        raise PcbFocusSizingError(f'Unknown source selector: {unknown_sources[0]}')
    available_nets = {item.get('net') for item in metadata.values() if item.get('net')}
    unknown_nets = sorted(set(nets) - available_nets)
    if unknown_nets:
        raise PcbFocusSizingError(f'Unknown net selector: {unknown_nets[0]}')

    source_selected = set(source_ids)
    net_selected = {solid_id for solid_id, item in metadata.items()
                    if item.get('net') in set(nets)}
    selected = sorted(source_selected | net_selected)
    _require(len(selected) + len(manual) <= MAX_GENERATED_REGIONS,
             'Generated focus region budget exceeded.')

    regions = [_region_record(f'source:{solid_id}', source_bounds[solid_id], fine, halo, growth)
               for solid_id in selected]
    regions.extend(_region_record(f'manual:{item["id"]}', item['bounds_mm'],
                                  item['target_size_mm'], halo, growth)
                   for item in sorted(manual, key=lambda item: item['id']))
    reasons = {solid_id: sorted((['source'] if solid_id in source_selected else []) +
                                (['net'] if solid_id in net_selected else []))
               for solid_id in selected}
    return {
        **({'solids': copy.deepcopy(solids)} if include_solids else {}),
        'regions': regions,
        'policy': copy.deepcopy(policy),
        'evidence': {
            'input_solid_count': len(solids),
            'retained_solid_count': len(solids),
            'all_solids_retained': True,
            'metadata_solid_count': len(metadata),
            'metadata_coverage_complete': set(metadata) == solid_ids,
            'selected_source_ids': selected,
            'selection_reasons': reasons,
            'requested_net_names': list(nets),
            'source_box_count': len(selected),
            'manual_box_count': len(manual),
            'generated_box_count': len(regions),
            'distance_model': 'axis_aligned_source_bounds_not_exact_shape_distance',
            'geometry_cropped': False,
        },
        'production_qualified': False,
    }


def _validate_regions(regions, coarse_size_mm):
    coarse = _number(coarse_size_mm, 'coarse_size_mm', bounded_mm=True)
    _require(coarse > 0, 'coarse_size_mm must be positive.')
    _require(isinstance(regions, list) and len(regions) <= MAX_GENERATED_REGIONS,
             'Invalid focus region array.')
    parsed = []
    ids = set()
    for raw in regions:
        _keys(raw, ('id', 'bounds_mm', 'target_size_mm', 'halo_mm', 'growth_rate'),
              'Focus region')
        _require(isinstance(raw['id'], str) and 0 < len(raw['id']) <= 512 and
                 raw['id'] not in ids, 'Focus region IDs must be unique nonempty strings.')
        ids.add(raw['id'])
        target = _number(raw['target_size_mm'], 'target_size_mm', bounded_mm=True)
        halo = _number(raw['halo_mm'], 'halo_mm', bounded_mm=True)
        growth = _number(raw['growth_rate'], 'growth_rate')
        _require(0 < target <= coarse and halo >= 0 and 0 < growth <= 1,
                 'Invalid focus region sizing controls.')
        parsed.append({'id': raw['id'], 'bounds_mm': _bounds(raw['bounds_mm'], 'bounds_mm'),
                       'target_size_mm': target, 'halo_mm': halo, 'growth_rate': growth})
    return parsed, coarse


def _distance_to_box(point, bounds):
    offsets = []
    for coordinate, lower, upper in zip(point, bounds[0], bounds[1]):
        offsets.append(lower - coordinate if coordinate < lower else
                       coordinate - upper if coordinate > upper else 0.0)
    return max(offsets)


def _target_size_at_parsed(point, regions, coarse):
    size = coarse
    for region in regions:
        distance = _distance_to_box(point, region['bounds_mm'])
        candidate = region['target_size_mm'] + region['growth_rate'] * max(
            0.0, distance - region['halo_mm'])
        _require(math.isfinite(candidate), 'Target size is outside representable range.')
        size = min(size, candidate)
    return size


def _bvh_node(regions):
    lower = [min(region['bounds_mm'][0][axis] for region in regions) for axis in range(3)]
    upper = [max(region['bounds_mm'][1][axis] for region in regions) for axis in range(3)]
    node = {'bounds_mm': [lower, upper],
            'minimum_target': min(region['target_size_mm'] for region in regions),
            'minimum_growth': min(region['growth_rate'] for region in regions),
            'maximum_halo': max(region['halo_mm'] for region in regions)}
    if len(regions) <= 8:
        node['regions'] = regions
        return node
    centers = [[(region['bounds_mm'][0][axis] + region['bounds_mm'][1][axis]) / 2.0
                for axis in range(3)] for region in regions]
    spans = [max(center[axis] for center in centers) - min(center[axis] for center in centers)
             for axis in range(3)]
    axis = max(range(3), key=lambda candidate: (spans[candidate], -candidate))
    ordered = sorted(regions, key=lambda region: (
        (region['bounds_mm'][0][axis] + region['bounds_mm'][1][axis]) / 2.0,
        region['id']))
    middle = len(ordered) // 2
    node['children'] = (_bvh_node(ordered[:middle]), _bvh_node(ordered[middle:]))
    return node


def _bvh_lower_bound(point, node):
    distance = _distance_to_box(point, node['bounds_mm'])
    return node['minimum_target'] + node['minimum_growth'] * max(
        0.0, distance - node['maximum_halo'])


def _target_size_bvh(point, node, best, comparisons):
    if node is None or _bvh_lower_bound(point, node) >= best:
        return best
    if 'regions' in node:
        for region in node['regions']:
            comparisons[0] += 1
            _require(comparisons[0] <= MAX_ASSESSMENT_COMPARISONS,
                     'Focus assessment comparison budget exceeded.')
            distance = _distance_to_box(point, region['bounds_mm'])
            candidate = region['target_size_mm'] + region['growth_rate'] * max(
                0.0, distance - region['halo_mm'])
            best = min(best, candidate)
        return best
    children = sorted(node['children'], key=lambda child: _bvh_lower_bound(point, child))
    for child in children:
        best = _target_size_bvh(point, child, best, comparisons)
    return best


def target_size_at(point_mm, regions, coarse_size_mm):
    """Evaluate the minimum graded size using L-infinity box distance in mm."""
    parsed, coarse = _validate_regions(regions, coarse_size_mm)
    _require(isinstance(point_mm, (list, tuple)) and len(point_mm) == 3,
             'point_mm must contain three coordinates.')
    point = [_number(value, 'point_mm coordinate', bounded_mm=True) for value in point_mm]
    return _target_size_at_parsed(point, parsed, coarse)


def _validate_assessment_mesh(mesh):
    _keys(mesh, ('contract', 'units', 'coordinate_system', 'vertices', 'cells',
                 'counts', 'object_map'), 'Mesh')
    _require(mesh['contract'] == 'spike/solver-mesh/v1' and
             mesh['units'] in ('m', 'mm') and
             mesh['coordinate_system'] == 'right_handed_xyz',
             'Invalid mesh identity, units, or coordinate system.')
    points, cells = mesh['vertices'], mesh['cells']
    _require(isinstance(points, list) and 4 <= len(points) <= MAX_MESH_VERTICES and
             isinstance(cells, list) and 1 <= len(cells) <= MAX_MESH_CELLS,
             'Mesh assessment resource budget exceeded.')
    _keys(mesh['counts'], ('vertices', 'cells'), 'Mesh counts')
    _require(mesh['counts'] == {'vertices': len(points), 'cells': len(cells)} and
             all(type(mesh['counts'][key]) is int for key in ('vertices', 'cells')),
             'Mesh counts mismatch.')
    parsed_points = []
    scale = 1_000.0 if mesh['units'] == 'm' else 1.0
    for point in points:
        _require(isinstance(point, list) and len(point) == 3, 'Invalid mesh coordinate.')
        converted = [_number(value, 'Mesh coordinate') * scale for value in point]
        _require(all(math.isfinite(value) and abs(value) <= MAX_ABS_MM for value in converted),
                 'Converted mesh coordinates exceed the mm coordinate budget.')
        parsed_points.append(converted)
    _require(len(set(map(tuple, parsed_points))) == len(parsed_points), 'Duplicate mesh vertices.')
    objects = mesh['object_map']
    _require(isinstance(objects, dict) and len(objects) <= 100_000, 'Invalid mesh object map.')
    for object_id, metadata in objects.items():
        _require(isinstance(object_id, str) and bool(object_id) and
                 isinstance(metadata, dict) and 'kind' in metadata and
                 set(metadata) <= {'kind', 'net', 'layer'} and
                 all(isinstance(value, str) and bool(value) for value in metadata.values()),
                 'Invalid mesh object metadata.')
    cell_ids, cell_vertices = set(), set()
    for cell in cells:
        _keys(cell, ('id', 'kind', 'vertices', 'material_id', 'source_object_ids'), 'Mesh cell')
        _require(isinstance(cell['id'], str) and 0 < len(cell['id']) <= 256 and
                 cell['id'] not in cell_ids, 'Invalid or duplicate mesh cell ID.')
        cell_ids.add(cell['id'])
        vertices = cell['vertices']
        _require(cell['kind'] == 'tetrahedron' and isinstance(vertices, list) and
                 len(vertices) == 4 and len(set(vertices)) == 4 and
                 all(type(index) is int and 0 <= index < len(points) for index in vertices),
                 'Invalid tetrahedral mesh cell.')
        canonical_vertices = tuple(sorted(vertices))
        _require(canonical_vertices not in cell_vertices, 'Duplicate tetrahedral mesh cell.')
        cell_vertices.add(canonical_vertices)
        _require(isinstance(cell['material_id'], str) and bool(cell['material_id']) and
                 isinstance(cell['source_object_ids'], list) and
                 1 <= len(cell['source_object_ids']) <= 1_024 and
                 len(set(cell['source_object_ids'])) == len(cell['source_object_ids']) and
                 all(isinstance(item, str) and item in objects for item in cell['source_object_ids']),
                 'Invalid mesh cell ownership.')
        determinant = _det(parsed_points, vertices)
        _require(math.isfinite(determinant) and determinant > 0,
                 'Inverted, degenerate, or unrepresentable tetrahedron.')
    return parsed_points, cells


def assess_focus_mesh(mesh, regions, coarse_size_mm, *, include_mesh=True):
    """Assess every tetrahedron at its centroid without removing mesh cells."""
    parsed_regions, coarse = _validate_regions(regions, coarse_size_mm)
    points, cells = _validate_assessment_mesh(mesh)
    tree = _bvh_node(parsed_regions) if parsed_regions else None
    comparisons = [0]
    assessments = []
    near = far = above = 0
    for cell in cells:
        vertices = cell['vertices']
        centroid = [math.fsum(points[index][axis] for index in vertices) / 4.0
                    for axis in range(3)]
        target = _target_size_bvh(centroid, tree, coarse, comparisons)
        longest = max(math.dist(points[a], points[b])
                      for a, b in itertools.combinations(vertices, 2))
        _require(math.isfinite(longest) and longest > 0, 'Invalid mesh edge length.')
        ratio = longest / target
        _require(math.isfinite(ratio), 'Mesh size ratio is outside representable range.')
        is_near = target < coarse
        near += int(is_near)
        far += int(not is_near)
        above += int(ratio > 1.0)
        assessments.append({'cell_id': cell['id'], 'centroid_mm': centroid,
                            'target_size_mm': target, 'longest_edge_mm': longest,
                            'edge_to_target_ratio': ratio, 'near_focus': is_near})
    return {
        **({'mesh': copy.deepcopy(mesh)} if include_mesh else {}),
        'cell_assessments': assessments,
        'counts': {'cells': len(cells), 'near_focus': near, 'far_field': far,
                   'above_target': above},
        'maximum_edge_to_target_ratio': max(item['edge_to_target_ratio']
                                            for item in assessments),
        'coordinate_conversion': 'm_to_mm' if mesh['units'] == 'm' else 'identity_mm',
        'region_cell_comparisons': comparisons[0],
        'evaluation': 'exact_bvh_with_bounded_region_comparisons',
        'assessment_scope': 'requested_target_diagnostics_not_gmsh_field_proof',
        'near_focus_definition': 'centroid_target_size_mm_less_than_coarse_size_mm',
        'all_cells_retained': True,
        'production_qualified': False,
    }
