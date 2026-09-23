"""Clean-room geometry checks for controlled observed thermal attachments."""
from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

from python.core.simple_polygon_union import is_simple_polygon


Point = tuple[float, float]
GEOMETRY_TOLERANCE_MM = 1e-9
WIDTH_TOLERANCE_MM = 1e-6


def point(value) -> Point:
    values = list(value)
    result = (float(values[0]), float(values[1]))
    if not all(math.isfinite(item) for item in result):
        raise ValueError("points must be finite")
    return result


def polygon_area(polygon: Sequence[Point]) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(polygon, (*polygon[1:], polygon[0]))
    )


def admitted_simple_polygon(values: Iterable, *, maximum_vertices: int) -> list[Point]:
    polygon = [point(value) for value in values]
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    if not 3 <= len(polygon) <= maximum_vertices:
        raise ValueError("polygon vertex count is outside the controlled profile")
    if abs(polygon_area(polygon)) <= GEOMETRY_TOLERANCE_MM ** 2:
        raise ValueError("polygon has zero area")
    if not is_simple_polygon(polygon):
        raise ValueError("polygon is not simple")
    return polygon


def edge_frame(pad_boundary: Sequence[Point], edge_index: int) -> tuple[Point, Point, Point, float]:
    start = pad_boundary[edge_index]
    end = pad_boundary[(edge_index + 1) % len(pad_boundary)]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= GEOMETRY_TOLERANCE_MM:
        raise ValueError("pad edge is degenerate")
    tangent = (dx / length, dy / length)
    if polygon_area(pad_boundary) > 0:
        outward = (tangent[1], -tangent[0])
    else:
        outward = (-tangent[1], tangent[0])
    return start, end, tangent, length


def outward_normal(pad_boundary: Sequence[Point], edge_index: int) -> Point:
    _, _, tangent, _ = edge_frame(pad_boundary, edge_index)
    return (
        (tangent[1], -tangent[0]) if polygon_area(pad_boundary) > 0
        else (-tangent[1], tangent[0])
    )


def components_disjoint(
    polygons: Sequence[Sequence[Point]], *, charge: Callable[[], None],
) -> bool:
    from .hybrid_mesh import _point_in_polygon, _segment_intersection_points, _segments

    for left_index, left in enumerate(polygons):
        for right in polygons[left_index + 1:]:
            for left_start, left_end in _segments(left):
                for right_start, right_end in _segments(right):
                    charge()
                    if _segment_intersection_points(
                        left_start, left_end, right_start, right_end,
                        GEOMETRY_TOLERANCE_MM,
                    ):
                        return False
            charge()
            if _point_in_polygon(left[0], right, GEOMETRY_TOLERANCE_MM):
                return False
            charge()
            if _point_in_polygon(right[0], left, GEOMETRY_TOLERANCE_MM):
                return False
    return True


def line_sections(
    polygon: Sequence[Point], origin: Point, tangent: Point, normal: Point,
    *, charge: Callable[[], None],
) -> list[tuple[float, float]]:
    """Return exact inside intervals along an infinite line in local coordinates."""
    from .hybrid_mesh import _point_in_polygon, _segments

    cuts: list[float] = []
    for start, end in _segments(polygon):
        charge()
        local = []
        for value in (start, end):
            dx, dy = value[0] - origin[0], value[1] - origin[1]
            local.append((dx * tangent[0] + dy * tangent[1], dx * normal[0] + dy * normal[1]))
        (s0, n0), (s1, n1) = local
        if abs(n0) <= GEOMETRY_TOLERANCE_MM and abs(n1) <= GEOMETRY_TOLERANCE_MM:
            raise ValueError("cross-section is collinear with a source edge")
        if ((n0 <= GEOMETRY_TOLERANCE_MM and n1 >= -GEOMETRY_TOLERANCE_MM)
                or (n1 <= GEOMETRY_TOLERANCE_MM and n0 >= -GEOMETRY_TOLERANCE_MM)):
            denominator = n0 - n1
            if abs(denominator) <= GEOMETRY_TOLERANCE_MM:
                continue
            ratio = n0 / denominator
            if -GEOMETRY_TOLERANCE_MM <= ratio <= 1 + GEOMETRY_TOLERANCE_MM:
                cuts.append(s0 + (s1 - s0) * ratio)
    ordered: list[float] = []
    for value in sorted(cuts):
        if not ordered or abs(value - ordered[-1]) > GEOMETRY_TOLERANCE_MM:
            ordered.append(value)
    sections = []
    for left, right in zip(ordered, ordered[1:]):
        if right - left <= GEOMETRY_TOLERANCE_MM:
            continue
        middle = (left + right) / 2
        sample = (
            origin[0] + tangent[0] * middle,
            origin[1] + tangent[1] * middle,
        )
        charge()
        if _point_in_polygon(sample, polygon, GEOMETRY_TOLERANCE_MM):
            sections.append((left, right))
    return sections


def centered_section(
    polygon: Sequence[Point], boundary_center: Point, tangent: Point, normal: Point,
    offset_mm: float, *, charge: Callable[[], None],
) -> tuple[float, float]:
    origin = (
        boundary_center[0] + normal[0] * offset_mm,
        boundary_center[1] + normal[1] * offset_mm,
    )
    matches = [
        interval for interval in line_sections(polygon, origin, tangent, normal, charge=charge)
        if interval[0] <= GEOMETRY_TOLERANCE_MM and interval[1] >= -GEOMETRY_TOLERANCE_MM
    ]
    if len(matches) != 1:
        raise ValueError("cross-section has no unique centered copper interval")
    return matches[0]


def segment_is_contained(
    polygon: Sequence[Point], start: Point, end: Point, *, charge: Callable[[], None],
) -> bool:
    from .hybrid_mesh import _point_in_polygon, _segment_intersection_points, _segments

    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= GEOMETRY_TOLERANCE_MM ** 2:
        return False
    cuts = [0.0, 1.0]
    for edge_start, edge_end in _segments(polygon):
        charge()
        for hit in _segment_intersection_points(
            start, end, edge_start, edge_end, GEOMETRY_TOLERANCE_MM,
        ):
            cuts.append(max(0.0, min(1.0, (
                (hit[0] - start[0]) * dx + (hit[1] - start[1]) * dy
            ) / denominator)))
    ordered: list[float] = []
    for value in sorted(cuts):
        if not ordered or abs(value - ordered[-1]) > GEOMETRY_TOLERANCE_MM:
            ordered.append(value)
    for left, right in zip(ordered, ordered[1:]):
        if right - left <= GEOMETRY_TOLERANCE_MM:
            continue
        middle = (left + right) / 2
        sample = (start[0] + dx * middle, start[1] + dy * middle)
        charge()
        if not _point_in_polygon(sample, polygon, GEOMETRY_TOLERANCE_MM):
            return False
    return True


def angle_deg(vector: Point) -> float:
    return math.degrees(math.atan2(vector[1], vector[0])) % 360.0


def modulo_quadrant_delta(observed: float, configured: float) -> float:
    return min(abs(((observed - configured - offset + 180) % 360) - 180) for offset in (0, 90, 180, 270))
