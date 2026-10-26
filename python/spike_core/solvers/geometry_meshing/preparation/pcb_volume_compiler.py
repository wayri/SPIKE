# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Compile normalized planar PCB polygons and plated vias into typed solids.

This is a CAD-neutral compiler, not a source-format importer. Supplied copper
contours are retained without clipping, simplification, net filtering, or ROI
cropping. Shapely validates straight-sided geometry; via circles remain analytic
and are checked by distances, not tessellated approximations. No mesher is run.
"""
from __future__ import annotations

import math
from numbers import Integral

MAX_SOLIDS = 10_000
MAX_POLYGON_POINTS = 131_072
MAX_HOLES = 128
MAX_PAIR_CHECKS = 1_000_000
MIN_FEATURE_MM = 1e-6
CONTRACT = 'spike/pcb-volume-model/v1'


class PcbVolumeError(ValueError):
    """Malformed, unsupported, electrically ambiguous, or over-budget input."""


def _require(condition, message):
    if not condition:
        raise PcbVolumeError(message)


def _keys(value, expected):
    _require(isinstance(value, dict) and set(value) == set(expected),
             'Unexpected PCB volume contract fields.')


def _identity(value):
    _require(isinstance(value, str) and 0 < len(value) <= 256, 'Invalid source, net, or material identity.')
    return value


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e6
    except OverflowError:
        valid = False
    _require(valid, 'Expected finite coordinates in [-1e6, 1e6] mm, not bool or text.')
    return float(value)


def _span(value):
    low, high = _number(value['z_min_mm']), _number(value['z_max_mm'])
    _require(high-low >= MIN_FEATURE_MM, 'Solid thickness must be at least 1e-6 mm.')
    return low, high


class _Geometry:
    def __init__(self):
        try:
            from shapely.geometry import Polygon, Point, box
            from shapely.strtree import STRtree
        except ImportError as exc:
            raise PcbVolumeError('PCB_VOLUME_DEPENDENCY: polygon validation requires Shapely.') from exc
        self.Polygon, self.Point, self.box, self.STRtree = Polygon, Point, box, STRtree
        self.points = self.pairs = 0

    def pair(self):
        self.pairs += 1
        _require(self.pairs <= MAX_PAIR_CHECKS, 'PCB geometry pair-work budget exceeded.')

    def loop(self, value):
        _require(isinstance(value, list) and 3 <= len(value) <= MAX_POLYGON_POINTS,
                 'Invalid polygon vertex count.')
        self.points += len(value)
        _require(self.points <= MAX_POLYGON_POINTS, 'Input polygon point budget exceeded.')
        result = []
        for point in value:
            _require(isinstance(point, list) and len(point) == 2, 'Invalid planar point.')
            result.append([_number(x) for x in point])
        _require(len({tuple(p) for p in result}) == len(result),
                 'Repeated polygon vertices, including repeated closing vertices, are unsupported.')
        return result

    def polygon(self, value):
        holes = value['holes_mm']
        _require(isinstance(holes, list) and len(holes) <= MAX_HOLES, 'Invalid polygon hole budget.')
        outer = self.loop(value['outer_mm'])
        inner = [self.loop(hole) for hole in holes]
        shell = self.Polygon(outer)
        polygon = self.Polygon(outer, inner)
        _require(shell.is_valid and polygon.is_valid and not polygon.is_empty and polygon.area > 1e-12,
                 'Polygon must be simple and have positive representable area and valid holes.')
        hole_polygons = [self.Polygon(hole) for hole in inner]
        for i, hole in enumerate(hole_polygons):
            _require(shell.covers(hole) and shell.boundary.disjoint(hole.boundary),
                     'Polygon holes must lie strictly inside the outer ring.')
            for other in hole_polygons[:i]:
                self.pair()
                _require(hole.disjoint(other), 'Polygon holes must not overlap or touch.')
        return polygon, outer, inner


def _uncertainty(*values):
    # Distances are floating GEOS/IEEE operations. Reject near-contact circle
    # decisions conservatively instead of treating numerical ambiguity as gap.
    return 64 * math.ulp(max(1., *(abs(value) for value in values)))


def _interference(a, b, geometry):
    if a['type'] == b['type'] == 'polygon':
        return a['geometry'].intersects(b['geometry']), 'Cross-net copper contact or overlap.'
    if a['type'] == 'polygon':
        a, b = b, a
    center, outer, inner = a['center'], a['outer'], a['inner']
    if b['type'] == 'polygon':
        distance = b['geometry'].distance(geometry.Point(center))
        tolerance = _uncertainty(*center, outer, *b['geometry'].bounds)
        if distance <= inner+tolerance:
            return True, 'Via drill intersects foreign-net copper; an explicit antipad is required.'
        return distance <= outer+tolerance, 'Via barrel contacts foreign-net copper.'
    distance = math.dist(center, b['center'])
    tolerance = _uncertainty(*center, *b['center'], outer, b['outer'])
    return distance <= outer+b['outer']+tolerance, 'Foreign-net via barrels/drills overlap or touch.'


def _electrical_checks(records, geometry):
    if not records:
        return
    shapes = [record['geometry'] for record in records]
    tree = geometry.STRtree(shapes)
    # Shapely 2 returns integer indices; earlier supported runtimes return the
    # stored geometries. Neither route inspects or depends on upstream code.
    indices = {id(shape): i for i, shape in enumerate(shapes)}
    for i, record in enumerate(records):
        for hit in tree.query(shapes[i]):
            j = int(hit) if isinstance(hit, Integral) else indices[id(hit)]
            if j <= i:
                continue
            geometry.pair()
            other = records[j]
            if record['net'] == other['net']:
                continue
            # A shared z face can be an electrical contact, not just an
            # overlap of positive volume, so equal span endpoints are included.
            if record['z'][1] < other['z'][0] or other['z'][1] < record['z'][0]:
                continue
            invalid, reason = _interference(record, other, geometry)
            _require(not invalid, reason+' Sources: '+record['id']+', '+other['id'])


def compile_pcb_volume_model(model):
    """Return whole-board typed solids, source metadata, and compiler evidence.

    Layers must be ordered, strictly positive thickness, and exactly contiguous
    in millimetres. Copper occupies its declared layer's full thickness. Through,
    blind, and buried via spans must remain within the stack. Drill cylinders
    override copper/background at priority 20; copper/barrels have priority 10.
    Same-net copper overlaps retain both source IDs for downstream Boolean
    ancestry. Cross-net contacts are rejected before any mesher allocation.
    """
    _keys(model, ('contract', 'board', 'layers', 'copper', 'vias',
                  'copper_material_id', 'drill_material_id'))
    _require(model['contract'] == CONTRACT, 'Unsupported PCB volume model contract.')
    copper_material = _identity(model['copper_material_id'])
    drill_material = _identity(model['drill_material_id'])
    _require(copper_material != drill_material, 'Copper and drill materials must be distinct.')
    board, layers, copper, vias = (model[k] for k in ('board', 'layers', 'copper', 'vias'))
    _keys(board, ('id', 'outer_mm', 'holes_mm'))
    _require(isinstance(layers, list) and 1 <= len(layers) <= MAX_SOLIDS and
             isinstance(copper, list) and len(copper) <= MAX_SOLIDS and
             isinstance(vias, list) and len(vias) <= MAX_SOLIDS,
             'Invalid layer, copper, or via array budget.')
    _require(len(layers)+len(copper)+2*len(vias) <= MAX_SOLIDS, 'Output solid budget exceeded.')
    geometry = _Geometry()
    board_polygon, outer, holes = geometry.polygon(board)
    board_id = _identity(board['id'])
    identities = {board_id}
    solids, metadata, records, layer_map = [], {}, [], {}
    declared_ids = [board_id]
    expanded_points = (len(outer)+sum(map(len, holes)))*len(layers)
    _require(expanded_points <= MAX_POLYGON_POINTS, 'Expanded output polygon point budget exceeded.')

    def reserve(value, declared=True):
        source = _identity(value)
        _require(source not in identities, 'Duplicate or generated-collision source identity: '+source)
        identities.add(source)
        if declared:
            declared_ids.append(source)
        return source

    def emit(source, material, priority, shape, data):
        solids.append({'id': source, 'material_id': material, 'priority': priority, 'shape': shape})
        metadata[source] = data

    previous = None
    for layer in layers:
        _keys(layer, ('id', 'z_min_mm', 'z_max_mm', 'background_material_id'))
        layer_id = reserve(layer['id'])
        source = reserve('layer:'+layer_id, declared=False)
        span = _span(layer)
        _require(previous is None or span[0] == previous,
                 'Layers must be ordered and exactly contiguous, without gaps or overlaps.')
        previous = span[1]
        material = _identity(layer['background_material_id'])
        _require(material != copper_material,
                 'Background material cannot equal copper material: background has no electrical net.')
        shape = {'kind': 'polygon_prism', 'outer_mm': [p[:] for p in outer],
                 'holes_mm': [[p[:] for p in ring] for ring in holes],
                 'z_min_mm': span[0], 'z_max_mm': span[1]}
        emit(source, material, 0, shape, {'kind': 'board_layer', 'layer': layer_id})
        layer_map[layer_id] = {'source_id': source, 'z_min_mm': span[0], 'z_max_mm': span[1]}
    stack_min, stack_max = _number(layers[0]['z_min_mm']), previous
    for feature in copper:
        _keys(feature, ('id', 'net', 'layer_id', 'outer_mm', 'holes_mm'))
        source = reserve(feature['id'])
        net, layer_id = _identity(feature['net']), _identity(feature['layer_id'])
        _require(layer_id in layer_map, 'Copper refers to an unknown layer.')
        polygon, ring, cutouts = geometry.polygon(feature)
        _require(board_polygon.covers(polygon),
                 'Copper lies outside the actual board outline or intersects a board cutout.')
        expanded_points += len(ring)+sum(map(len, cutouts))
        _require(expanded_points <= MAX_POLYGON_POINTS, 'Expanded output polygon point budget exceeded.')
        layer = layer_map[layer_id]
        span = (layer['z_min_mm'], layer['z_max_mm'])
        emit(source, copper_material, 10,
             {'kind': 'polygon_prism', 'outer_mm': ring, 'holes_mm': cutouts,
              'z_min_mm': span[0], 'z_max_mm': span[1]}, {'kind': 'copper', 'net': net, 'layer': layer_id})
        records.append({'id': source, 'net': net, 'z': span, 'type': 'polygon', 'geometry': polygon})
    via_spans = {}
    for via in vias:
        _keys(via, ('id', 'net', 'z_min_mm', 'z_max_mm', 'center_mm',
                    'outer_radius_mm', 'inner_radius_mm'))
        source = reserve(via['id'])
        drill_id = reserve(source+'__drill', declared=False)
        net, span = _identity(via['net']), _span(via)
        _require(stack_min <= span[0] < span[1] <= stack_max, 'Via span lies outside the layer stack.')
        _require(isinstance(via['center_mm'], list) and len(via['center_mm']) == 2, 'Invalid via center.')
        center = [_number(x) for x in via['center_mm']]
        radius, bore = _number(via['outer_radius_mm']), _number(via['inner_radius_mm'])
        _require(bore >= MIN_FEATURE_MM and radius-bore >= MIN_FEATURE_MM,
                 'Plated via requires a positive drill radius and wall at least 1e-6 mm.')
        point = geometry.Point(center)
        tolerance = _uncertainty(*center, radius, *board_polygon.bounds)
        _require(board_polygon.contains(point) and board_polygon.boundary.distance(point) > radius+tolerance,
                 'Via outer circle must be strictly inside the board; cutout crossings and castellations are unsupported.')
        shape = {'kind': 'tube', 'center_mm': center, 'outer_radius_mm': radius,
                 'inner_radius_mm': bore, 'z_min_mm': span[0], 'z_max_mm': span[1]}
        emit(source, copper_material, 10, shape, {'kind': 'plated_via', 'net': net})
        emit(drill_id, drill_material, 20,
             {**shape, 'center_mm': center[:], 'outer_radius_mm': bore, 'inner_radius_mm': 0.},
             {'kind': 'drill', 'net': net})
        via_spans[source] = {'z_min_mm': span[0], 'z_max_mm': span[1], 'drill_source_id': drill_id}
        records.append({'id': source, 'net': net, 'z': span, 'type': 'via', 'center': center,
                        'outer': radius, 'inner': bore,
                        'geometry': geometry.box(center[0]-radius-tolerance, center[1]-radius-tolerance,
                                                 center[0]+radius+tolerance, center[1]+radius+tolerance)})
    _electrical_checks(records, geometry)
    return {'solids': solids, 'object_metadata': metadata,
            'evidence': {'contract': CONTRACT, 'scope': 'normalized_planar_full_board',
                         'board_id': board_id, 'board_area_mm2': board_polygon.area,
                         'layer_sources': layer_map, 'via_spans': via_spans,
                         'declared_source_ids': declared_ids,
                         'net_ids': sorted({record['net'] for record in records}),
                         'all_declared_nets_retained': True, 'roi_cropping': False,
                         'polygon_contours_preserved': True, 'via_circles': 'analytic',
                         'electrical_contact_checks': 'foreign_net_contacts_rejected',
                         'drill_material_priority': 20, 'solid_count': len(solids),
                         'expanded_polygon_points': expanded_points, 'pair_checks': geometry.pairs,
                         'limits': {'solids': MAX_SOLIDS, 'polygon_points': MAX_POLYGON_POINTS,
                                    'holes_per_polygon': MAX_HOLES, 'pair_checks': MAX_PAIR_CHECKS},
                         'unsupported': ['bent_rigid_flex', 'curved_3d_copper', 'castellated_vias',
                                         'source_format_import', 'manufacturing_clearance_rules'],
                         'production_qualified': False}}
