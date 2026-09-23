"""Small clean-room exact arrangement union for bounded simple polygon rings."""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Sequence

RationalPoint = tuple[Fraction, Fraction]


def _cross(a: RationalPoint, b: RationalPoint, c: RationalPoint) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: RationalPoint, b: RationalPoint, point: RationalPoint) -> bool:
    return (_cross(a, b, point) == 0
            and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))


def _parameter(a: RationalPoint, b: RationalPoint, point: RationalPoint) -> Fraction:
    if b[0] != a[0]:
        return (point[0] - a[0]) / (b[0] - a[0])
    return (point[1] - a[1]) / (b[1] - a[1])


def _intersection(
    a: RationalPoint, b: RationalPoint, c: RationalPoint, d: RationalPoint,
) -> list[RationalPoint]:
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    offset_x, offset_y = c[0] - a[0], c[1] - a[1]
    if denominator:
        left = (offset_x * sy - offset_y * sx) / denominator
        right = (offset_x * ry - offset_y * rx) / denominator
        if 0 <= left <= 1 and 0 <= right <= 1:
            return [(a[0] + left * rx, a[1] + left * ry)]
        return []
    if offset_x * ry - offset_y * rx:
        return []
    return list(dict.fromkeys(
        point for point in (a, b, c, d)
        if _on_segment(a, b, point) and _on_segment(c, d, point)
    ))


def _classification(point: RationalPoint, polygon: Sequence[RationalPoint]) -> int:
    """Return -1 outside, 0 on boundary, or 1 inside."""

    inside = False
    for a, b in zip(polygon, [*polygon[1:], polygon[0]]):
        if _on_segment(a, b, point):
            return 0
        if (a[1] > point[1]) != (b[1] > point[1]):
            crossing = a[0] + (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1])
            if crossing > point[0]:
                inside = not inside
    return 1 if inside else -1


def _ring(points: Iterable[Sequence[float]]) -> list[RationalPoint]:
    result = [(Fraction(str(point[0])), Fraction(str(point[1]))) for point in points]
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    if not result:
        return []
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(result, [*result[1:], result[0]]))
    return result if area > 0 else list(reversed(result))


def is_simple_polygon(points: Iterable[Sequence[float]]) -> bool:
    """Validate a finite nondegenerate simple ring with exact rational predicates."""

    polygon = _ring(points)
    if len(polygon) < 3:
        return False
    edges = list(zip(polygon, [*polygon[1:], polygon[0]]))
    if any(start == end for start, end in edges):
        return False
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)
    if not area:
        return False
    for left, (a, b) in enumerate(edges):
        for right in range(left + 1, len(edges)):
            if right == left + 1 or (left == 0 and right == len(edges) - 1):
                continue
            if _intersection(a, b, edges[right][0], edges[right][1]):
                return False
    return True


def polygon_contains_polygon(
    outer_points: Iterable[Sequence[float]], inner_points: Iterable[Sequence[float]],
) -> bool:
    """Return true when every exact segment partition of ``inner`` is in ``outer``."""

    outer, inner = _ring(outer_points), _ring(inner_points)
    if not is_simple_polygon(outer) or not is_simple_polygon(inner):
        return False
    outer_edges = list(zip(outer, [*outer[1:], outer[0]]))
    for start, end in zip(inner, [*inner[1:], inner[0]]):
        splits = {Fraction(0), Fraction(1)}
        for outer_start, outer_end in outer_edges:
            for point in _intersection(start, end, outer_start, outer_end):
                splits.add(_parameter(start, end, point))
        values = sorted(splits)
        for left, right in zip(values, values[1:]):
            midpoint_parameter = (left + right) / 2
            midpoint = (
                start[0] + midpoint_parameter * (end[0] - start[0]),
                start[1] + midpoint_parameter * (end[1] - start[1]),
            )
            if _classification(midpoint, outer) < 0:
                return False
    return True


def union_two_simple_polygons(
    first: Iterable[Sequence[float]], second: Iterable[Sequence[float]],
) -> list[list[float]]:
    """Return one CCW union boundary, rejecting disjoint/holed/ambiguous output."""

    polygons = (_ring(first), _ring(second))
    if any(len(polygon) < 3 for polygon in polygons):
        return []
    splits = [
        [{Fraction(0), Fraction(1)} for _ in polygon]
        for polygon in polygons
    ]
    for left_index, (a, b) in enumerate(zip(polygons[0], [*polygons[0][1:], polygons[0][0]])):
        for right_index, (c, d) in enumerate(zip(polygons[1], [*polygons[1][1:], polygons[1][0]])):
            for point in _intersection(a, b, c, d):
                splits[0][left_index].add(_parameter(a, b, point))
                splits[1][right_index].add(_parameter(c, d, point))

    retained: list[tuple[RationalPoint, RationalPoint]] = []
    for owner, polygon in enumerate(polygons):
        other = polygons[1 - owner]
        for edge_index, (a, b) in enumerate(zip(polygon, [*polygon[1:], polygon[0]])):
            values = sorted(splits[owner][edge_index])
            for start_value, end_value in zip(values, values[1:]):
                start = (a[0] + start_value * (b[0] - a[0]), a[1] + start_value * (b[1] - a[1]))
                end = (a[0] + end_value * (b[0] - a[0]), a[1] + end_value * (b[1] - a[1]))
                if start == end:
                    continue
                midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
                if _classification(midpoint, other) <= 0:
                    retained.append((start, end))

    grouped: dict[frozenset[RationalPoint], list[tuple[RationalPoint, RationalPoint]]] = {}
    for edge in retained:
        grouped.setdefault(frozenset(edge), []).append(edge)
    boundary: list[tuple[RationalPoint, RationalPoint]] = []
    for edges in grouped.values():
        directions = {(start, end) for start, end in edges}
        if any((end, start) in directions for start, end in directions):
            continue
        boundary.append(min(directions))
    outgoing: dict[RationalPoint, RationalPoint] = {}
    incoming: dict[RationalPoint, RationalPoint] = {}
    for start, end in boundary:
        if start in outgoing or end in incoming:
            return []
        outgoing[start], incoming[end] = end, start
    if not boundary or set(outgoing) != set(incoming):
        return []
    start = min(outgoing)
    result = [start]
    current = outgoing[start]
    while current != start and len(result) <= len(boundary):
        result.append(current)
        current = outgoing.get(current)
        if current is None:
            return []
    if current != start or len(result) != len(boundary):
        return []
    return [[float(x), float(y)] for x, y in result]


def union_simple_polygons(polygons: Iterable[Iterable[Sequence[float]]]) -> list[list[float]]:
    """Union one connected set deterministically; reject ambiguity or islands."""

    canonical = []
    for polygon in polygons:
        ring = _ring(polygon)
        if len(ring) < 3:
            return []
        start = min(range(len(ring)), key=lambda index: ring[index])
        rotated = ring[start:] + ring[:start]
        canonical.append([[float(x), float(y)] for x, y in rotated])
    if not canonical:
        return []
    canonical.sort(key=lambda polygon: tuple(tuple(point) for point in polygon))
    resolved = canonical.pop(0)
    while canonical:
        for index, polygon in enumerate(canonical):
            merged = union_two_simple_polygons(resolved, polygon)
            if merged:
                resolved = merged
                canonical.pop(index)
                break
        else:
            return []
    return resolved
