# SPDX-License-Identifier: Apache-2.0
"""Exact incidence of the represented coordinates of a planar polygon.

Finite float coordinates are dyadic rationals. Multiplying by their common
power-of-two denominator maps them to integers without rounding or moving a
vertex. Integer orientation and closed endpoint bounds then decide segment
incidence. A sweep prunes disjoint edge bounds, with quadratic worst-case work
and linear transient storage. This checks topology, not polygon area or quality.
"""
from __future__ import annotations


def _integer_points(points):
    if any(type(value) not in (int, float) for point in points for value in point):
        raise ValueError('Polygon coordinates must be Python integers or floats.')
    ratios = [(x.as_integer_ratio(), y.as_integer_ratio()) for x, y in points]
    denominator = max(value[1] for point in ratios for value in point)
    return [(x[0] * (denominator // x[1]), y[0] * (denominator // y[1]))
            for x, y in ratios]


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _on_segment(a, b, p):
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _intersects(a, b, c, d):
    abc, abd, cda, cdb = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ((abc == 0 and _on_segment(a, b, c)) or
            (abd == 0 and _on_segment(a, b, d)) or
            (cda == 0 and _on_segment(c, d, a)) or
            (cdb == 0 and _on_segment(c, d, b))):
        return True
    return ((abc < 0 < abd or abd < 0 < abc)
            and (cda < 0 < cdb or cdb < 0 < cda))


def first_non_simple_edge_pair(points):
    """Return intersecting edge indices, or None for a simple boundary.

Zero edges/repeated vertices and adjacent retracing are rejected. Adjacent
edges may share only their common endpoint. Nonfinite coordinates fail closed.
There is no distance tolerance: proximity alone is not a topological crossing.
Indices refer to the original boundary, regardless of sweep ordering.
"""
    if len(points) < 3:
        return (0, 0)
    try:
        polygon = _integer_points(points)
    except (OverflowError, ValueError, AttributeError, TypeError):
        return (0, 0)
    count = len(polygon)
    seen = {}
    for index, point in enumerate(polygon):
        if point in seen:
            return (seen[point], index)
        seen[point] = index
        previous, following = polygon[index-1], polygon[(index+1) % count]
        if (_cross(previous, point, following) == 0 and
                (previous[0]-point[0])*(following[0]-point[0]) +
                (previous[1]-point[1])*(following[1]-point[1]) > 0):
            return ((index-1) % count, index)

    edges = []
    for index, start in enumerate(polygon):
        end = polygon[(index+1) % count]
        edges.append((min(start[0], end[0]), max(start[0], end[0]),
                      min(start[1], end[1]), max(start[1], end[1]), index, start, end))
    active = []
    for edge in sorted(edges, key=lambda item: (item[0], item[4])):
        low_x, high_x, low_y, high_y, index, start, end = edge
        active = [other for other in active if other[1] >= low_x]
        for other in active:
            other_index = other[4]
            if (abs(index-other_index) == 1 or abs(index-other_index) == count-1
                    or other[3] < low_y or high_y < other[2]):
                continue
            if _intersects(start, end, other[5], other[6]):
                return tuple(sorted((index, other_index)))
        active.append(edge)
    return None
