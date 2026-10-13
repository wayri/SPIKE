# SPDX-License-Identifier: Apache-2.0
"""Bounded physical domains for source-filled paths with retraced bridges."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import heapq
from math import isfinite
from typing import Iterable, Sequence

from .planar_polygon_topology import (
    _cross,
    _integer_points,
    _intersects,
    _on_segment,
)
from .source_filled_boundary import (
    SourceFilledBoundary,
    SourceFilledBoundaryError,
    _distance_to_edge,
    _point as _source_point,
)


Point = tuple[float, float]
Edge = tuple[Point, Point]
# Match the native parser's existing per-component source-fill admission cap.
# This module duplicates the value instead of importing board_parser and
# creating a core-to-parser dependency cycle.
MAX_SOURCE_VERTICES = 131_072
MAX_HOLES = 4_096
MAX_TOPOLOGY_INTERSECTION_TESTS = 2_000_000
# Bounds aggregate sweep-candidate/filter visits and exact-ray point visits.
# The 2**27 ceiling admits the parser's 2**17 source-vertex limit while making
# adversarial quadratic topology validation fail closed at a declared limit.
MAX_TOPOLOGY_WORK = 134_217_728
MAX_CELL_FRAGMENT_WORK = 2_000_000
MAX_CELL_FRAGMENTS = 65_536


class FilledPathError(ValueError):
    """A source path cannot be represented as one bounded holed domain."""


class FilledPathBudgetError(FilledPathError):
    """Valid-looking source geometry exceeded a declared work or size limit."""


def _point(value: object, index: int) -> Point:
    try:
        return _source_point(value, index)
    except SourceFilledBoundaryError as error:
        raise FilledPathError(str(error)) from error


@dataclass
class _TopologyBudget:
    work: int = 0
    exact_intersections: int = 0

    def spend(self, amount: int = 1) -> None:
        self.work += amount
        if self.work > MAX_TOPOLOGY_WORK:
            raise FilledPathBudgetError(
                "topology validation exceeds the bounded aggregate work budget"
            )

    def exact_intersection(self) -> None:
        self.exact_intersections += 1
        if self.exact_intersections > MAX_TOPOLOGY_INTERSECTION_TESTS:
            raise FilledPathBudgetError(
                "topology validation exceeds the exact-intersection budget"
            )


def _signed_area2(ring: Sequence[Point]) -> float:
    return sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(ring, (*ring[1:], ring[0]))
    )


def _exact_area2(ring: Sequence[Point]) -> Fraction:
    return sum(
        Fraction(start[0]) * Fraction(end[1])
        - Fraction(end[0]) * Fraction(start[1])
        for start, end in zip(ring, (*ring[1:], ring[0]))
    )


def _strictly_inside_integer(point, ring) -> bool:
    inside = False
    for start, end in zip(ring, (*ring[1:], ring[0])):
        cross = _cross(start, end, point)
        if cross == 0 and _on_segment(start, end, point):
            return False
        if (start[1] > point[1]) == (end[1] > point[1]):
            continue
        left = (end[0] - start[0]) * (point[1] - start[1])
        right = (point[0] - start[0]) * (end[1] - start[1])
        if (left > right) == (end[1] > start[1]):
            inside = not inside
    return inside


def _inside_with_budget(point, ring, budget: _TopologyBudget) -> bool:
    budget.spend(len(ring))
    return _strictly_inside_integer(point, ring)


def _canonical_edge(edge: Edge) -> Edge:
    return edge if edge[0] <= edge[1] else (edge[1], edge[0])


def _edge_y(edge: Edge, x: float) -> float:
    start, end = _canonical_edge(edge)
    if x == start[0]:
        return start[1]
    if x == end[0]:
        return end[1]
    return start[1] + (x - start[0]) * (end[1] - start[1]) / (end[0] - start[0])


def _edge_x(edge: Edge, y: float) -> float:
    start, end = sorted(edge, key=lambda point: (point[1], point[0]))
    if y == start[1]:
        return start[0]
    if y == end[1]:
        return end[0]
    return start[0] + (y - start[1]) * (end[0] - start[0]) / (end[1] - start[1])


def _clockwise_piece(points: Iterable[Point]) -> list[Point] | None:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    if len(result) < 3:
        return None
    if not all(isfinite(value) for point in result for value in point):
        raise FilledPathError("cell clipping produced a non-finite fragment")
    area = _exact_area2(result)
    if not area:
        return None
    cross_signs = []
    exact = [(Fraction(x), Fraction(y)) for x, y in result]
    for previous, current, following in zip(
        exact[-1:] + exact[:-1], exact, exact[1:] + exact[:1],
    ):
        cross = (
            (current[0] - previous[0]) * (following[1] - current[1])
            - (current[1] - previous[1]) * (following[0] - current[0])
        )
        if cross:
            cross_signs.append(cross > 0)
    if cross_signs and any(sign != cross_signs[0] for sign in cross_signs):
        raise FilledPathError("cell clipping produced a non-convex fragment")
    if area > 0:
        result.reverse()
    if len(result) not in (3, 4):
        raise FilledPathError("cell clipping produced a non-convex fragment")
    return result


@dataclass(frozen=True)
class FilledCopperDomain(SourceFilledBoundary):
    """One physical outer ring and its holes, retaining the source path."""

    rings: tuple[tuple[Point, ...], ...]

    @property
    def outer(self) -> tuple[Point, ...]:
        return self.rings[0]

    @property
    def holes(self) -> tuple[tuple[Point, ...], ...]:
        return self.rings[1:]

    def contains(self, point: Sequence[float], tolerance: float = 0.0) -> bool:
        try:
            return super().contains(point, tolerance)
        except SourceFilledBoundaryError as error:
            raise FilledPathError(str(error)) from error

    def cell_fragments(
        self, x0: float, y0: float, x1: float, y1: float,
    ) -> list[list[Point]]:
        bounds = (x0, y0, x1, y1)
        if any(isinstance(value, bool) or type(value) not in (int, float) for value in bounds):
            raise ValueError("cell bounds must be finite numbers")
        x0, y0, x1, y1 = map(float, bounds)
        if not all(isfinite(value) for value in (x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
            raise ValueError("cell bounds must be finite and increasing")

        relevant = [
            (index, edge)
            for index, edge in enumerate(self.edges)
            if edge[0][0] != edge[1][0]
            and max(edge[0][0], edge[1][0]) > x0
            and min(edge[0][0], edge[1][0]) < x1
        ]
        events = {x0, x1}
        clip_event_y: dict[tuple[int, float], float] = {}
        for edge_index, edge in relevant:
            start, end = edge
            for x in (start[0], end[0]):
                if x0 < x < x1:
                    events.add(x)
            if start[1] != end[1]:
                for y in (y0, y1):
                    if min(start[1], end[1]) < y < max(start[1], end[1]):
                        x = _edge_x(edge, y)
                        if x0 < x < x1:
                            if (
                                (x == start[0] and y != start[1])
                                or (x == end[0] and y != end[1])
                            ):
                                raise FilledPathError(
                                    "cell clip intersection is not representable apart from a source vertex"
                                )
                            key = (edge_index, x)
                            if key in clip_event_y and clip_event_y[key] != y:
                                raise FilledPathError(
                                    "distinct cell clip intersections collapse to one coordinate"
                                )
                            clip_event_y[key] = y
                            events.add(x)
        xs = sorted(events)
        if len(xs) - 1 > MAX_SOURCE_VERTICES + 3:
            raise FilledPathBudgetError(
                "cell slab count exceeds the bounded source-vertex budget"
            )

        records: list[dict[str, object]] = []
        work = 0
        for left_x, right_x in zip(xs, xs[1:]):
            if left_x == right_x:
                continue
            middle_x = left_x + (right_x - left_x) / 2
            if not left_x < middle_x < right_x:
                raise FilledPathError(
                    "cell slab has no representable interior coordinate"
                )
            crossings = []
            for edge_index, edge in relevant:
                work += 1
                if work > MAX_CELL_FRAGMENT_WORK:
                    raise FilledPathBudgetError(
                        "cell fragment work exceeds the bounded work budget"
                    )
                low_x = min(edge[0][0], edge[1][0])
                high_x = max(edge[0][0], edge[1][0])
                if low_x < middle_x < high_x:
                    crossings.append((_edge_y(edge, middle_x), edge_index, edge))
            crossings.sort(key=lambda item: (item[0], item[1]))
            if len(crossings) % 2:
                raise FilledPathError("physical edges produce unmatched slab crossings")
            for lower, upper in zip(crossings[::2], crossings[1::2]):
                if upper[0] <= y0 or lower[0] >= y1:
                    continue
                lower_key: object = "cell-y0" if lower[0] < y0 else lower[1]
                upper_key: object = "cell-y1" if upper[0] > y1 else upper[1]
                low_left = max(
                    y0, clip_event_y.get(
                        (lower[1], left_x), _edge_y(lower[2], left_x),
                    ),
                )
                low_right = max(
                    y0, clip_event_y.get(
                        (lower[1], right_x), _edge_y(lower[2], right_x),
                    ),
                )
                high_left = min(
                    y1, clip_event_y.get(
                        (upper[1], left_x), _edge_y(upper[2], left_x),
                    ),
                )
                high_right = min(
                    y1, clip_event_y.get(
                        (upper[1], right_x), _edge_y(upper[2], right_x),
                    ),
                )
                if high_left < low_left or high_right < low_right:
                    raise FilledPathError("cell clipping inverted a filled interval")
                if high_left == low_left and high_right == low_right:
                    continue
                key = (lower_key, upper_key)
                merged = False
                for record in reversed(records):
                    if record["right_x"] != left_x:
                        break
                    if record["key"] == key:
                        record["right_x"] = right_x
                        record["low_right"] = low_right
                        record["high_right"] = high_right
                        merged = True
                        break
                if not merged:
                    records.append({
                        "key": key,
                        "left_x": left_x,
                        "right_x": right_x,
                        "low_left": low_left,
                        "low_right": low_right,
                        "high_left": high_left,
                        "high_right": high_right,
                    })
                    if len(records) > MAX_CELL_FRAGMENTS:
                        raise FilledPathBudgetError(
                            "cell fragment count exceeds the bounded budget"
                        )

        fragments: list[list[Point]] = []
        for record in records:
            piece = _clockwise_piece((
                (record["left_x"], record["low_left"]),
                (record["left_x"], record["high_left"]),
                (record["right_x"], record["high_right"]),
                (record["right_x"], record["low_right"]),
            ))
            if piece is not None:
                fragments.append(piece)
        return fragments


def _sweep_visit_count(edges, low_index, high_index, group_index=None) -> int:
    active = []
    active_groups = {}
    visits = 0
    for serial, edge in enumerate(sorted(edges, key=lambda item: item[low_index])):
        low = edge[low_index]
        while active and active[0][0] < low:
            _, _, group = heapq.heappop(active)
            if group_index is not None:
                active_groups[group] -= 1
        group = edge[group_index] if group_index is not None else None
        visits += len(active) - (active_groups.get(group, 0) if group_index is not None else 0)
        heapq.heappush(active, (edge[high_index], serial, group))
        if group_index is not None:
            active_groups[group] = active_groups.get(group, 0) + 1
    return visits


def _bounded_sweep_axis(edges, group_index=None) -> tuple[int, int, int, int]:
    x_visits = _sweep_visit_count(edges, 0, 1, group_index)
    y_visits = _sweep_visit_count(edges, 2, 3, group_index)
    return (0, 1, 2, 3) if x_visits <= y_visits else (2, 3, 0, 1)


def _validate_cross_ring_intersections(integer_rings, budget: _TopologyBudget) -> None:
    edges = []
    for ring_index, ring in enumerate(integer_rings):
        for edge_index, start in enumerate(ring):
            end = ring[(edge_index + 1) % len(ring)]
            edges.append((
                min(start[0], end[0]), max(start[0], end[0]),
                min(start[1], end[1]), max(start[1], end[1]),
                ring_index, edge_index, start, end,
            ))
    active = []
    low, high, secondary_low, secondary_high = _bounded_sweep_axis(edges, 4)
    for edge in sorted(edges, key=lambda item: (item[low], item[4], item[5])):
        survivors = []
        for other in active:
            budget.spend()
            if other[high] < edge[low]:
                continue
            survivors.append(other)
            if other[4] == edge[4]:
                continue
            if (
                other[secondary_high] < edge[secondary_low]
                or edge[secondary_high] < other[secondary_low]
            ):
                continue
            budget.exact_intersection()
            if _intersects(edge[6], edge[7], other[6], other[7]):
                raise FilledPathError("physical boundary rings intersect or touch")
        active = survivors
        active.append(edge)


def _integer_bbox(ring) -> tuple[int, int, int, int]:
    return (
        min(point[0] for point in ring),
        min(point[1] for point in ring),
        max(point[0] for point in ring),
        max(point[1] for point in ring),
    )


def _bbox_contains(outer, inner) -> bool:
    return (
        outer[0] <= inner[0] and outer[1] <= inner[1]
        and outer[2] >= inner[2] and outer[3] >= inner[3]
    )


def _bbox_overlaps(left, right) -> bool:
    return not (
        left[2] < right[0] or right[2] < left[0]
        or left[3] < right[1] or right[3] < left[1]
    )


def _bounded_non_simple_pair(
    ring: Sequence[Point], budget: _TopologyBudget,
) -> tuple[int, int] | None:
    integer = _integer_points(ring)
    count = len(integer)
    seen = {}
    for index, point in enumerate(integer):
        if point in seen:
            return seen[point], index
        seen[point] = index
        previous, following = integer[index - 1], integer[(index + 1) % count]
        if (
            _cross(previous, point, following) == 0
            and (previous[0] - point[0]) * (following[0] - point[0])
            + (previous[1] - point[1]) * (following[1] - point[1]) > 0
        ):
            return (index - 1) % count, index
    edges = [
        (
            min(start[0], end[0]), max(start[0], end[0]),
            min(start[1], end[1]), max(start[1], end[1]),
            index, start, end,
        )
        for index, start in enumerate(integer)
        for end in (integer[(index + 1) % count],)
    ]
    active = []
    low, high, secondary_low, secondary_high = _bounded_sweep_axis(edges)
    for edge in sorted(edges, key=lambda item: (item[low], item[4])):
        survivors = []
        for other in active:
            budget.spend()
            if other[high] < edge[low]:
                continue
            survivors.append(other)
            other_index = other[4]
            if (
                abs(edge[4] - other_index) in (1, count - 1)
                or other[secondary_high] < edge[secondary_low]
                or edge[secondary_high] < other[secondary_low]
            ):
                continue
            budget.exact_intersection()
            if _intersects(edge[5], edge[6], other[5], other[6]):
                return tuple(sorted((edge[4], other_index)))
        active = survivors
        active.append(edge)
    return None


def _has_retraced_edge(points: object) -> bool:
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return False
    raw = []
    for value in points:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return False
        if any(isinstance(item, bool) or type(item) not in (int, float) for item in value):
            return False
        if not all(isfinite(float(item)) for item in value):
            return False
        raw.append((float(value[0]), float(value[1])))
    directed = set()
    for index, start in enumerate(raw):
        end = raw[(index + 1) % len(raw)]
        if start == end:
            continue
        if (end, start) in directed:
            return True
        directed.add((start, end))
    return False


def prepare_filled_path(points: Sequence[Sequence[float]]) -> FilledCopperDomain | None:
    """Recover a bounded holed domain from an exact retraced-bridge path.

    ``None`` means the source has no exactly reversed edge pair and should use
    the ordinary simple-polygon path. Invalid retraced topology fails closed.
    """

    if not isinstance(points, (list, tuple)):
        raise FilledPathError("source path must be a list or tuple")
    if not _has_retraced_edge(points):
        return None
    if len(points) > MAX_SOURCE_VERTICES:
        raise FilledPathBudgetError("source path exceeds the vertex budget")
    source = tuple(_point(value, index) for index, value in enumerate(points))
    if len(source) < 3:
        raise FilledPathError("source path requires at least three points")

    source_edges: list[Edge] = []
    for index, start in enumerate(source):
        end = source[(index + 1) % len(source)]
        if start == end:
            if index == len(source) - 1 and source[-1] == source[0]:
                continue
            raise FilledPathError("source path contains a zero-length edge")
        source_edges.append((start, end))

    pending: dict[Edge, list[int]] = {}
    cancelled: set[int] = set()
    for index, edge in enumerate(source_edges):
        reverse = edge[1], edge[0]
        matches = pending.get(reverse)
        if matches:
            cancelled.add(index)
            cancelled.add(matches.pop())
            if not matches:
                del pending[reverse]
        else:
            pending.setdefault(edge, []).append(index)
    if not cancelled:
        return None
    physical_edges = tuple(
        edge for index, edge in enumerate(source_edges) if index not in cancelled
    )
    if not physical_edges:
        raise FilledPathError("retraced cancellation removed every physical edge")
    topology_budget = _TopologyBudget()

    outgoing: dict[Point, Point] = {}
    incoming: dict[Point, Point] = {}
    for start, end in physical_edges:
        if start in outgoing or end in incoming:
            raise FilledPathError("physical boundary must have one incoming and outgoing edge per vertex")
        outgoing[start] = end
        incoming[end] = start
    if set(outgoing) != set(incoming):
        raise FilledPathError("physical boundary contains an open loop")

    rings: list[tuple[Point, ...]] = []
    unvisited = set(outgoing)
    ordered_vertices = sorted(unvisited)
    vertex_cursor = 0
    while unvisited:
        while ordered_vertices[vertex_cursor] not in unvisited:
            vertex_cursor += 1
        first = ordered_vertices[vertex_cursor]
        ring = []
        current = first
        while current in unvisited:
            ring.append(current)
            unvisited.remove(current)
            current = outgoing[current]
        if current != first or len(ring) < 3:
            raise FilledPathError("physical boundary does not form closed rings")
        candidate = tuple(ring)
        if _bounded_non_simple_pair(candidate, topology_budget) is not None:
            raise FilledPathError("physical boundary ring is not simple")
        rings.append(candidate)
        if len(rings) > MAX_HOLES + 1:
            raise FilledPathBudgetError("filled path exceeds the hole budget")
    if len(rings) < 2:
        raise FilledPathError("retraced path does not encode an outer ring and hole")
    if len(rings) - 1 > MAX_HOLES:
        raise FilledPathBudgetError("filled path exceeds the hole budget")

    flattened = [point for ring in rings for point in ring]
    integers = _integer_points(flattened)
    integer_rings = []
    offset = 0
    for ring in rings:
        integer_rings.append(tuple(integers[offset:offset + len(ring)]))
        offset += len(ring)
    _validate_cross_ring_intersections(integer_rings, topology_budget)

    ring_bounds = [_integer_bbox(ring) for ring in integer_rings]
    global_bounds = (
        min(bounds[0] for bounds in ring_bounds),
        min(bounds[1] for bounds in ring_bounds),
        max(bounds[2] for bounds in ring_bounds),
        max(bounds[3] for bounds in ring_bounds),
    )
    outer_candidates = []
    for index, ring in enumerate(integer_rings):
        if not _bbox_contains(ring_bounds[index], global_bounds):
            continue
        if all(
            other == index
            or _inside_with_budget(
                integer_rings[other][0], ring, topology_budget,
            )
            for other in range(len(integer_rings))
        ):
            outer_candidates.append(index)
    if len(outer_candidates) != 1:
        raise FilledPathError("physical rings do not define exactly one containing outer ring")
    outer_index = outer_candidates[0]
    hole_indices = [index for index in range(len(rings)) if index != outer_index]
    for position, left in enumerate(hole_indices):
        for right in hole_indices[position + 1:]:
            topology_budget.spend()
            if not _bbox_overlaps(ring_bounds[left], ring_bounds[right]):
                continue
            left_in_right = (
                _bbox_contains(ring_bounds[right], ring_bounds[left])
                and _inside_with_budget(
                    integer_rings[left][0], integer_rings[right], topology_budget,
                )
            )
            right_in_left = (
                _bbox_contains(ring_bounds[left], ring_bounds[right])
                and _inside_with_budget(
                    integer_rings[right][0], integer_rings[left], topology_budget,
                )
            )
            if left_in_right or right_in_left:
                raise FilledPathError("nested holes are not supported")

    area_signs = []
    for ring in integer_rings:
        area2 = sum(
            start[0] * end[1] - end[0] * start[1]
            for start, end in zip(ring, (*ring[1:], ring[0]))
        )
        if not area2:
            raise FilledPathError("physical boundary ring has zero area")
        area_signs.append(1 if area2 > 0 else -1)
    outer_sign = area_signs[outer_index]
    if any(area_signs[index] == outer_sign for index in hole_indices):
        raise FilledPathError("hole orientation must oppose the outer ring")

    ordered = [rings[outer_index], *(rings[index] for index in hole_indices)]
    if outer_sign < 0:
        ordered = [tuple(reversed(ring)) for ring in ordered]
    return FilledCopperDomain(source, physical_edges, tuple(ordered))


# Stable integration name. The domain remains immutable while supporting the
# legacy sequence reads used for source-area hashes and coordinate iteration.
FilledCopperPath = FilledCopperDomain
