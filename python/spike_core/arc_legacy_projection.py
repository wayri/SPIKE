# SPDX-License-Identifier: Apache-2.0
"""Exact arc ownership with an explicit, immutable legacy chord projection."""
from __future__ import annotations

import copy
import hashlib
import json
import math

EXTENSION = 'spike.v1.linearized_tracks'
ORDER = 'spike.v1.track_order'


def _number(value):
    if isinstance(value, bool):
        raise ValueError('ARC_PROJECTION_INVALID: finite numbers required.')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('ARC_PROJECTION_INVALID: finite numbers required.') from error
    if not math.isfinite(value):
        raise ValueError('ARC_PROJECTION_INVALID: finite numbers required.')
    return value


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('ARC_PROJECTION_INVALID: planar points required.')
    return tuple(_number(v) for v in value)


def _validate_chain(arc, children, *, net_resolver=None, layer_resolver=None):
    net_resolver = net_resolver or (lambda row: str(row.get('net_id') or row.get('net') or row.get('net_name') or ''))
    layer_resolver = layer_resolver or (lambda row: str(row.get('layer_id') or row.get('layer') or ''))
    if not 1 <= len(children) <= 64:
        raise ValueError('ARC_PROJECTION_INVALID: bounded chord chain required.')
    start, mid, end = (_point(arc[key]) for key in ('start', 'mid', 'end'))
    ux, uy = mid[0]-start[0], mid[1]-start[1]
    vx, vy = end[0]-start[0], end[1]-start[1]
    determinant = 2*(ux*vy-uy*vx)
    if determinant == 0:
        raise ValueError('ARC_PROJECTION_INVALID: noncollinear arc points required.')
    uu, vv = ux*ux+uy*uy, vx*vx+vy*vy
    center = (start[0]+(uu*vy-vv*uy)/determinant, start[1]+(ux*vv-vx*uu)/determinant)
    radius = math.dist(start, center)
    tolerance = 1e-9*max(1., radius) + 32*math.ulp(max(1., *(abs(v) for p in (start, mid, end) for v in p)))
    if not math.isfinite(radius) or radius <= tolerance:
        raise ValueError('ARC_PROJECTION_INVALID: unresolved arc conditioning.')
    angle = lambda p: math.atan2(p[1]-center[1], p[0]-center[0])
    a0, am, a1 = angle(start), angle(mid), angle(end)
    ccw = (a1-a0) % math.tau
    direction = 1 if (am-a0) % math.tau <= ccw else -1
    sweep = ccw if direction == 1 else math.tau-ccw
    previous, last_offset, ids = start, 0., set()
    for index, child in enumerate(children):
        if not isinstance(child, dict) or not isinstance(child.get('row'), dict):
            raise ValueError('ARC_PROJECTION_INVALID: chord records must be objects.')
        row = child['row']
        source = str(row.get('id') or row.get('source_id') or row.get('uuid') or '')
        width = _number(row.get('width', row.get('width_mm')))
        expected_width = _number(arc.get('width', arc.get('width_mm')))
        if (not source or source in ids or width <= 0 or expected_width <= 0
                or abs(width-expected_width) > 1e-12*max(1., expected_width)
                or net_resolver(row) != net_resolver(arc) or layer_resolver(row) != layer_resolver(arc)):
            raise ValueError('ARC_PROJECTION_INVALID: chord identity, net, layer or width differs.')
        ids.add(source)
        left, right = _point(row.get('start')), _point(row.get('end'))
        if math.dist(left, previous) > tolerance or math.dist(left, right) <= tolerance:
            raise ValueError('ARC_PROJECTION_INVALID: chord chain is discontinuous or collapsed.')
        for point in (left, right):
            if abs(math.dist(point, center)-radius) > tolerance:
                raise ValueError('ARC_PROJECTION_INVALID: chord endpoint is outside its source circle.')
        offset = (direction*(angle(right)-a0)) % math.tau
        if index == len(children)-1 and math.dist(right, end) <= tolerance:
            offset = sweep
        angular_tolerance = tolerance/radius
        if offset < last_offset-angular_tolerance or offset > sweep+angular_tolerance:
            raise ValueError('ARC_PROJECTION_INVALID: chord chain leaves the selected source sweep.')
        previous, last_offset = right, offset
    if math.dist(previous, end) > tolerance:
        raise ValueError('ARC_PROJECTION_INVALID: chord chain does not reach the source end.')


def partition_tracks(tracks, arcs, *, net_resolver=None, layer_resolver=None):
    owners = {str(row.get('source_id') or row.get('id') or row.get('uuid') or '') for row in arcs}
    owners.discard('')
    ordinary, children = [], {}
    for index, row in enumerate(tracks):
        parent = str(row.get('source_parent_id') or '')
        if parent in owners:
            children.setdefault(parent, []).append({'index': index, 'row': copy.deepcopy(dict(row))})
        else:
            ordinary.append((index, row))
    for arc in arcs:
        source = str(arc.get('source_id') or arc.get('id') or arc.get('uuid') or '')
        if source in children:
            _validate_chain(arc, children[source], net_resolver=net_resolver, layer_resolver=layer_resolver)
    return ordinary, children


def require_legacy_arc_geometry(design):
    """Reject omitted exact copper at v1 numerical geometry boundaries."""
    arcs = design.metadata.get('arcs', [])
    if not isinstance(arcs, list):
        raise ValueError('ARC_UNSUPPORTED: invalid retained exact arc records.')
    if not arcs:
        return
    _, children = partition_tracks(design.tracks, arcs)
    for arc in arcs:
        source = str(arc.get('source_id') or arc.get('id') or arc.get('uuid') or '')
        if not source or source not in children:
            raise ValueError('ARC_UNSUPPORTED: numerical legacy geometry cannot omit exact curved copper.')


def arc_basis(arc):
    return {'net_id': arc.net_id, 'layer_id': arc.layer_id, 'start_mm': list(arc.start_mm),
            'mid_mm': list(arc.mid_mm), 'end_mm': list(arc.end_mm), 'width_mm': arc.width_mm}


def bind_chords(arc, children):
    if children:
        digest = hashlib.sha256(json.dumps(children, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        arc.extensions[EXTENSION] = {'basis': arc_basis(arc), 'children': children, 'children_sha256': digest}


def hydrate_conductors(tracks, arcs, *, source_format, source_digest, net_id, layer_id):
    from .spider_v2_schema import (Track, Arc, entity_id, source_id, point, number, text,
                                  track_path_from_v1)
    ordinary, children = partition_tracks(tracks, arcs, net_resolver=net_id, layer_resolver=layer_id)
    canonical_tracks = [Track(
        id=entity_id(source_format, source_digest, 'track', raw, index),
        source_id=str(raw.get('id', index)), name=str(raw.get('name', '')),
        net_id=net_id(raw), layer_id=layer_id(raw), start_mm=point(raw.get('start')),
        end_mm=point(raw.get('end')), width_mm=float(raw.get('width', raw.get('width_mm', 0.)) or 0.),
        path=track_path_from_v1(raw),
        extensions={'spike.v1': dict(raw), **({ORDER: index} if children else {})},
    ) for index, raw in ordinary]
    canonical_arcs = [Arc(
        id=entity_id(source_format, source_digest, 'arc', raw, index), source_id=source_id(raw, index),
        name=text(raw.get('name')), net_id=net_id(raw), layer_id=layer_id(raw),
        start_mm=point(raw.get('start')), mid_mm=point(raw.get('mid', raw.get('middle'))),
        end_mm=point(raw.get('end')), width_mm=number(raw.get('width', raw.get('width_mm'))),
        extensions={'spike.v1': dict(raw)},
    ) for index, raw in enumerate(arcs)]
    for arc in canonical_arcs:
        bind_chords(arc, children.get(arc.source_id, []))
    return canonical_tracks, canonical_arcs


def restore_tracks(tracks, arcs, project, *, allow_unprojected_arcs=False, nets=(), layers=()):
    """Restore admitted source chords; never tessellate or reuse edited arc data."""
    ordered, unindexed = [], []
    def aliases(entities):
        result = {}
        for entity in entities:
            for key in (entity.id, entity.source_id, entity.name, *getattr(entity, 'aliases', [])):
                if key:
                    result[str(key)] = entity.id
        return result
    net_aliases, layer_aliases = aliases(nets), aliases(layers)
    def resolve_net(row):
        key = str(row.get('net_id') or row.get('net') or row.get('net_name') or '')
        return net_aliases.get(key, key)
    def resolve_layer(row):
        key = str(row.get('layer_id') or row.get('layer') or '')
        return layer_aliases.get(key, key)
    has_chords = any(EXTENSION in arc.extensions for arc in arcs)
    for track in tracks:
        row = project(track)
        if has_chords and ORDER in track.extensions:
            ordered.append((track.extensions[ORDER], row))
        else:
            unindexed.append(row)
    for arc in arcs:
        projection = arc.extensions.get(EXTENSION)
        if projection is None:
            if not allow_unprojected_arcs:
                raise ValueError('ARC_UNSUPPORTED: exact arc lacks an admitted legacy solver projection.')
            continue
        if not isinstance(projection, dict) or projection.get('basis') != arc_basis(arc):
            raise ValueError('ARC_PROJECTION_STALE: changed exact arc requires a newly admitted legacy projection.')
        children = projection.get('children')
        if not isinstance(children, list) or not 1 <= len(children) <= 64:
            raise ValueError('ARC_PROJECTION_INVALID: bounded source chord records required.')
        digest = hashlib.sha256(json.dumps(children, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if projection.get('children_sha256') != digest:
            raise ValueError('ARC_PROJECTION_STALE: legacy chord records changed.')
        _validate_chain({'start': arc.start_mm, 'mid': arc.mid_mm, 'end': arc.end_mm,
                         'width_mm': arc.width_mm, 'net_id': arc.net_id, 'layer_id': arc.layer_id},
                        children, net_resolver=resolve_net, layer_resolver=resolve_layer)
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get('row'), dict):
                raise ValueError('ARC_PROJECTION_INVALID: chord row is missing.')
            row = child['row']
            if str(row.get('source_parent_id') or '') != arc.source_id:
                raise ValueError('ARC_PROJECTION_INVALID: chord source ownership differs from its arc.')
            ordered.append((child.get('index'), copy.deepcopy(row)))
    indices = [index for index, _ in ordered]
    if (any(type(index) is not int or index < 0 for index in indices)
            or len(indices) != len(set(indices))):
        raise ValueError('ARC_PROJECTION_INVALID: legacy track indices must be unique nonnegative integers.')
    return [row for _, row in sorted(ordered, key=lambda item: item[0])] + unindexed
