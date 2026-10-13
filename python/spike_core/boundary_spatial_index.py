# SPDX-License-Identifier: Apache-2.0
"""Linear-memory candidate indexes for immutable filled-source boundaries."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import inf, isfinite, isnan, nextafter
from typing import Sequence


Point = tuple[float, float]
Edge = tuple[Point, Point]
Bounds = tuple[float, float, float, float]
MAX_INDEX_EDGES = 131_072
MAX_INDEX_POINTS = 131_072
BVH_LEAF_SIZE = 8


class BoundarySpatialIndexError(ValueError):
    """A boundary or query cannot be represented by the bounded index."""


def canonical_edge(edge: Edge) -> Edge:
    return edge if edge[0] <= edge[1] else (edge[1], edge[0])


def _nearest_axis_bounds(start: float, end: float) -> tuple[float, float]:
    """Bound ``fl(start + fl(ratio * fl(end-start)))`` for ratio in [0, 1]."""

    delta = end - start
    if not isfinite(delta):
        return -inf, inf
    lower = start + min(0.0, delta)
    upper = start + max(0.0, delta)
    if not isfinite(lower) or not isfinite(upper):
        return -inf, inf
    return min(start, end, lower), max(start, end, upper)


def conservative_edge_bounds(edge: Edge) -> Bounds:
    """Cover raw endpoints and every rounded nearest point on the segment."""

    start, end = canonical_edge(edge)
    x0, x1 = _nearest_axis_bounds(start[0], end[0])
    y0, y1 = _nearest_axis_bounds(start[1], end[1])
    return (
        min(x0, start[0], end[0]),
        min(y0, start[1], end[1]),
        max(x1, start[0], end[0]),
        max(y1, start[1], end[1]),
    )


def tolerance_query_bounds(point: Point, tolerance: float) -> Bounds:
    """Conservatively cover rounded residuals whose hypot is at most tolerance."""

    if not all(isfinite(value) for value in point):
        raise BoundarySpatialIndexError("query point coordinates must be finite")
    if isinstance(tolerance, bool) or type(tolerance) not in (int, float):
        raise BoundarySpatialIndexError(
            "query tolerance must be a finite non-negative number"
        )
    tolerance = float(tolerance)
    if not isfinite(tolerance) or tolerance < 0:
        raise BoundarySpatialIndexError(
            "query tolerance must be a finite non-negative number"
        )
    radius = nextafter(tolerance, inf)
    return (
        nextafter(point[0] - radius, -inf),
        nextafter(point[1] - radius, -inf),
        nextafter(point[0] + radius, inf),
        nextafter(point[1] + radius, inf),
    )


def _validate_bounds(bounds: Sequence[float]) -> Bounds:
    if len(bounds) != 4:
        raise BoundarySpatialIndexError("query bounds must contain four values")
    if any(isinstance(value, bool) or type(value) not in (int, float) for value in bounds):
        raise BoundarySpatialIndexError("query bounds must be numeric")
    result = tuple(float(value) for value in bounds)
    if any(isnan(value) for value in result):
        raise BoundarySpatialIndexError("query bounds must not contain NaN")
    if result[2] < result[0] or result[3] < result[1]:
        raise BoundarySpatialIndexError("query bounds must be increasing")
    return result  # type: ignore[return-value]


def _intersects(left: Bounds, right: Bounds) -> bool:
    return not (
        left[2] < right[0] or right[2] < left[0]
        or left[3] < right[1] or right[3] < left[1]
    )


@dataclass(frozen=True, slots=True)
class _IntervalNode:
    center: float
    by_low: tuple[tuple[float, int], ...]
    by_high: tuple[tuple[float, int], ...]
    left: _IntervalNode | None
    right: _IntervalNode | None


def _build_interval_node(
    intervals: Sequence[tuple[float, float, int]],
) -> _IntervalNode | None:
    if not intervals:
        return None
    centers = sorted(
        min(high, max(low, low / 2 + high / 2))
        for low, high, _ in intervals
    )
    center = centers[len(centers) // 2]
    left = []
    right = []
    crossing = []
    for low, high, index in intervals:
        if high < center:
            left.append((low, high, index))
        elif low > center:
            right.append((low, high, index))
        else:
            crossing.append((low, high, index))
    return _IntervalNode(
        center,
        tuple(sorted((low, index) for low, _, index in crossing)),
        tuple(sorted((high, index) for _, high, index in crossing)),
        _build_interval_node(left),
        _build_interval_node(right),
    )


def _query_interval_node(node: _IntervalNode | None, value: float, found: set[int]) -> None:
    if node is None:
        return
    if value < node.center:
        stop = bisect_right(node.by_low, (value, MAX_INDEX_EDGES))
        found.update(index for _, index in node.by_low[:stop])
        _query_interval_node(node.left, value, found)
    elif value > node.center:
        start = bisect_left(node.by_high, (value, -1))
        found.update(index for _, index in node.by_high[start:])
        _query_interval_node(node.right, value, found)
    else:
        found.update(index for _, index in node.by_low)


@dataclass(frozen=True, slots=True)
class _BvhNode:
    bounds: Bounds
    indices: tuple[int, ...]
    left: _BvhNode | None
    right: _BvhNode | None


def _union_bounds(indices: Sequence[int], edge_bounds: Sequence[Bounds]) -> Bounds:
    return (
        min(edge_bounds[index][0] for index in indices),
        min(edge_bounds[index][1] for index in indices),
        max(edge_bounds[index][2] for index in indices),
        max(edge_bounds[index][3] for index in indices),
    )


def _build_bvh(indices: Sequence[int], edge_bounds: Sequence[Bounds]) -> _BvhNode | None:
    if not indices:
        return None
    bounds = _union_bounds(indices, edge_bounds)
    if len(indices) <= BVH_LEAF_SIZE:
        return _BvhNode(bounds, tuple(indices), None, None)
    x_span = bounds[2] - bounds[0]
    y_span = bounds[3] - bounds[1]
    axis = 0 if x_span >= y_span else 1
    ordered = sorted(
        indices,
        key=lambda index: (
            edge_bounds[index][axis] + edge_bounds[index][axis + 2], index,
        ),
    )
    middle = len(ordered) // 2
    return _BvhNode(
        bounds,
        (),
        _build_bvh(ordered[:middle], edge_bounds),
        _build_bvh(ordered[middle:], edge_bounds),
    )


def _query_bvh(
    node: _BvhNode | None, bounds: Bounds, edge_bounds: Sequence[Bounds], found: list[int],
) -> None:
    if node is None or not _intersects(node.bounds, bounds):
        return
    if node.indices:
        found.extend(
            index for index in node.indices if _intersects(edge_bounds[index], bounds)
        )
        return
    _query_bvh(node.left, bounds, edge_bounds, found)
    _query_bvh(node.right, bounds, edge_bounds, found)


class BoundarySpatialIndex:
    """Immutable linear-space indexes that return conservative candidates."""

    __slots__ = (
        "original_edges", "edges", "points", "_edge_bounds", "_interval_root", "_bvh_root",
        "_points_by_x", "_point_xs",
    )

    def __init__(self, edges: Sequence[Edge], points: Sequence[Point]) -> None:
        if len(edges) > MAX_INDEX_EDGES:
            raise BoundarySpatialIndexError("boundary exceeds the edge index budget")
        if len(points) > MAX_INDEX_POINTS:
            raise BoundarySpatialIndexError("boundary exceeds the point index budget")
        self.original_edges = tuple(edges)
        self.edges = tuple(canonical_edge(edge) for edge in self.original_edges)
        self.points = tuple(points)
        self._edge_bounds = tuple(conservative_edge_bounds(edge) for edge in self.edges)
        self._interval_root = _build_interval_node(tuple(
            (min(edge[0][1], edge[1][1]), max(edge[0][1], edge[1][1]), index)
            for index, edge in enumerate(self.edges)
        ))
        self._bvh_root = _build_bvh(tuple(range(len(self.edges))), self._edge_bounds)
        self._points_by_x = tuple(sorted(
            (point[0], index, point) for index, point in enumerate(self.points)
        ))
        self._point_xs = tuple(item[0] for item in self._points_by_x)

    def ray_edges(self, y: float) -> tuple[Edge, ...]:
        if not isfinite(y):
            raise BoundarySpatialIndexError("ray coordinate must be finite")
        found: set[int] = set()
        _query_interval_node(self._interval_root, y, found)
        return tuple(self.edges[index] for index in sorted(found))

    def query_edges(self, bounds: Sequence[float]) -> tuple[Edge, ...]:
        """Return original directed physical edges conservatively intersecting bounds."""

        indices = self._query_edge_indices(bounds)
        return tuple(self.original_edges[index] for index in indices)

    def query_canonical_edges(self, bounds: Sequence[float]) -> tuple[Edge, ...]:
        """Return the same candidates with stable endpoint order for containment."""

        indices = self._query_edge_indices(bounds)
        return tuple(self.edges[index] for index in indices)

    def _query_edge_indices(self, bounds: Sequence[float]) -> tuple[int, ...]:
        query = _validate_bounds(bounds)
        found: list[int] = []
        _query_bvh(self._bvh_root, query, self._edge_bounds, found)
        return tuple(sorted(found))

    def query_points(self, bounds: Sequence[float]) -> tuple[Point, ...]:
        query = _validate_bounds(bounds)
        start = bisect_left(self._point_xs, query[0])
        stop = bisect_right(self._point_xs, query[2])
        found = [
            (index, point)
            for _, index, point in self._points_by_x[start:stop]
            if query[1] <= point[1] <= query[3]
        ]
        found.sort(key=lambda item: item[0])
        return tuple(point for _, point in found)
