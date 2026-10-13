# SPDX-License-Identifier: Apache-2.0
"""Bounded straight Edge.Cuts topology, shared by import and volume consumers."""
from __future__ import annotations

import math


def straight_outline_rings(drawings: list[dict]) -> list[dict]:
    """Retain one simple outer polygon and disjoint strictly contained cutouts.

    Endpoints must match exactly. No snapping, bounding-box substitution,
    curve tessellation or inferred island ownership is performed.
    """
    from shapely.geometry import Polygon

    if not isinstance(drawings, list) or len(drawings) > 4096:
        raise ValueError('Board outline drawing budget exceeded.')
    edges = []
    def point(value):
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
            raise ValueError('Board outline requires finite millimetre points.')
        return tuple(float(v) for v in value)
    for row in drawings:
        if not isinstance(row, dict):
            raise ValueError('Board outline drawings must be objects.')
        if row.get('layer') != 'Edge.Cuts':
            continue
        kind = row.get('type')
        if kind == 'line':
            points = row.get('points')
            if points is None:
                points = [row.get('start'), row.get('end')]
            if not isinstance(points, (list, tuple)) or len(points) != 2:
                raise ValueError('Board outline line requires two points.')
        elif kind == 'rect':
            points = row.get('points')
            if points is None:
                a, b = point(row.get('start')), point(row.get('end'))
                points = [a, (b[0], a[1]), b, (a[0], b[1]), a]
            if not isinstance(points, (list, tuple)) or len(points) not in (4, 5):
                raise ValueError('Board outline rectangle requires four corners.')
            points = [point(p) for p in points]
            if len(points) == 4:
                points.append(points[0])
            if points[-1] != points[0]:
                raise ValueError('Board outline rectangle is not closed.')
        else:
            raise ValueError('Straight outline admission does not support this primitive.')
        points = [point(p) for p in points]
        edges.extend(zip(points, points[1:]))
        if len(edges) > 4096:
            raise ValueError('Board outline edge budget exceeded.')
    if not edges:
        return []
    adjacency, unique = {}, set()
    for index, (a, b) in enumerate(edges):
        key = tuple(sorted((a, b)))
        if a == b or key in unique:
            raise ValueError('Board outline has zero-length or duplicate edges.')
        unique.add(key)
        adjacency.setdefault(a, []).append(index)
        adjacency.setdefault(b, []).append(index)
    if any(len(indices) != 2 for indices in adjacency.values()):
        raise ValueError('Board edge graph is open or branched; exact closed rings required.')
    remaining = set(range(len(edges)))
    loops = []
    while remaining:
        if len(loops) >= 128:
            raise ValueError('Board outline ring budget exceeded.')
        first = min(remaining, key=lambda i: tuple(sorted(edges[i])))
        start = min(edges[first])
        points, current = [start], start
        while True:
            choices = [i for i in adjacency[current] if i in remaining]
            if not choices:
                raise ValueError('Board outline traversal is not closed.')
            index = min(choices, key=lambda i: tuple(sorted(edges[i])))
            remaining.remove(index)
            a, b = edges[index]
            current = b if a == current else a
            points.append(current)
            if current == start:
                break
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise ValueError('Board outline polygon is self-intersecting or degenerate.')
        loops.append((points, polygon))
    outer = [i for i, (_, polygon) in enumerate(loops)
             if all(i == j or polygon.contains(other) and not polygon.boundary.intersects(other.boundary)
                    for j, (_, other) in enumerate(loops))]
    if len(outer) != 1:
        raise ValueError('Board outline requires one outer ring and strictly contained cutouts.')
    outer_index = outer[0]
    holes = [item for i, item in enumerate(loops) if i != outer_index]
    for i, (_, left) in enumerate(holes):
        if any(left.intersects(right) for _, right in holes[i+1:]):
            raise ValueError('Board cutouts overlap, touch or contain nested islands.')
    ordered = [loops[outer_index], *sorted(holes, key=lambda item: item[0][0])]
    return [{'role': 'outer' if index == 0 else 'cutout', 'start_mm': list(points[0]),
             'segments': [{'kind': 'line', 'end_mm': list(p)} for p in points[1:]]}
            for index, (points, _) in enumerate(ordered)]
