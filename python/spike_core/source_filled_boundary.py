# SPDX-License-Identifier: Apache-2.0
"""Physical boundary views for source-filled paths with retraced bridges."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot, isfinite
from typing import Callable, Sequence

from .boundary_spatial_index import (
    BoundarySpatialIndex,
    canonical_edge as _canonical_edge,
    tolerance_query_bounds,
)


Point = tuple[float, float]
Edge = tuple[Point, Point]
# Match the native parser's existing per-component source-fill admission cap.
MAX_SOURCE_VERTICES = 131_072


class SourceFilledBoundaryError(ValueError):
    """A retraced source path cannot form an unambiguous boundary view."""


class SourceFilledBoundaryBudgetError(SourceFilledBoundaryError):
    """A retraced source path exceeds a declared source-size limit."""


class SourceFilledBoundaryCancelled(SourceFilledBoundaryError):
    """Boundary preparation was cancelled without returning partial data."""


def _cancel(cancel_check: Callable[[], object] | None) -> None:
    if cancel_check is not None and bool(cancel_check()):
        raise SourceFilledBoundaryCancelled("source boundary preparation was cancelled")


def _point(value: object, index: int) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SourceFilledBoundaryError(
            f"source point {index} must contain exactly two coordinates"
        )
    if any(isinstance(item, bool) or type(item) not in (int, float) for item in value):
        raise SourceFilledBoundaryError(
            f"source point {index} coordinates must be Python integers or floats"
        )
    point = float(value[0]), float(value[1])
    if not all(isfinite(item) for item in point):
        raise SourceFilledBoundaryError(
            f"source point {index} coordinates must be finite"
        )
    return point


def _distance_to_edge(point: Point, edge: Edge) -> float:
    start, end = _canonical_edge(edge)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return hypot(point[0] - start[0], point[1] - start[1])
    ratio = max(0.0, min(
        1.0,
        ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
        / length_squared,
    ))
    return hypot(
        point[0] - (start[0] + ratio * dx),
        point[1] - (start[1] + ratio * dy),
    )


def _has_retraced_edge(
    points: object, cancel_check: Callable[[], object] | None,
) -> bool:
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return False
    raw = []
    for index, value in enumerate(points):
        if index % 1_024 == 0:
            _cancel(cancel_check)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return False
        if any(isinstance(item, bool) or type(item) not in (int, float) for item in value):
            return False
        converted = float(value[0]), float(value[1])
        if not all(isfinite(item) for item in converted):
            return False
        raw.append(converted)
    directed = set()
    for index, start in enumerate(raw):
        if index % 1_024 == 0:
            _cancel(cancel_check)
        end = raw[(index + 1) % len(raw)]
        if start == end:
            continue
        if (end, start) in directed:
            return True
        directed.add((start, end))
    _cancel(cancel_check)
    return False


@dataclass(frozen=True)
class SourceFilledBoundary:
    """Immutable source sequence with retraced bridges removed from its edges."""

    points: tuple[Point, ...]
    edges: tuple[Edge, ...]
    _canonical_edges: tuple[Edge, ...] = field(init=False, compare=False, repr=False)
    _spatial_index: BoundarySpatialIndex = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        index = BoundarySpatialIndex(self.edges, self.points)
        object.__setattr__(self, "_canonical_edges", index.edges)
        object.__setattr__(self, "_spatial_index", index)

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self):
        return iter(self.points)

    def __getitem__(self, index):
        return self.points[index]

    def contains(self, point: Sequence[float], tolerance: float = 0.0) -> bool:
        candidate = _point(point, 0)
        if isinstance(tolerance, bool) or type(tolerance) not in (int, float):
            raise ValueError("tolerance must be a finite non-negative number")
        tolerance = float(tolerance)
        if not isfinite(tolerance) or tolerance < 0:
            raise ValueError("tolerance must be a finite non-negative number")
        inside = False
        x, y = candidate
        for start, end in self._spatial_index.ray_edges(y):
            if (start[1] > y) == (end[1] > y):
                continue
            crossing_x = start[0] + (y - start[1]) * (
                end[0] - start[0]
            ) / (end[1] - start[1])
            if x < crossing_x:
                inside = not inside
        if inside:
            return True
        bounds = tolerance_query_bounds(candidate, tolerance)
        return any(
            _distance_to_edge(candidate, edge) <= tolerance
            for edge in self._spatial_index.query_canonical_edges(bounds)
        )

    def query_edges(self, bounds: Sequence[float]) -> tuple[Edge, ...]:
        return self._spatial_index.query_edges(bounds)

    def query_points(self, bounds: Sequence[float]) -> tuple[Point, ...]:
        return self._spatial_index.query_points(bounds)


def prepare_source_filled_boundary(
    points: Sequence[Sequence[float]],
    *,
    cancel_check: Callable[[], object] | None = None,
) -> SourceFilledBoundary | None:
    """Return a physical-edge view only when an exact retrace is present.

    Paths without an exact reversed edge return ``None`` so their established
    simple-polygon normalization path remains responsible for admission.
    """

    if not isinstance(points, (list, tuple)):
        raise SourceFilledBoundaryError("source path must be a list or tuple")
    if not _has_retraced_edge(points, cancel_check):
        return None
    if len(points) > MAX_SOURCE_VERTICES:
        raise SourceFilledBoundaryBudgetError("source path exceeds the vertex budget")
    converted_source = []
    for index, value in enumerate(points):
        if index % 1_024 == 0:
            _cancel(cancel_check)
        converted_source.append(_point(value, index))
    source = tuple(converted_source)
    if len(source) < 3:
        raise SourceFilledBoundaryError("source path requires at least three points")

    source_edges: list[Edge] = []
    directed_counts: dict[Edge, int] = {}
    for index, start in enumerate(source):
        if index % 1_024 == 0:
            _cancel(cancel_check)
        end = source[(index + 1) % len(source)]
        if start == end:
            if index == len(source) - 1 and source[-1] == source[0]:
                continue
            raise SourceFilledBoundaryError("source path contains a zero-length edge")
        edge = start, end
        source_edges.append(edge)
        directed_counts[edge] = directed_counts.get(edge, 0) + 1

    residual_counts: dict[Edge, int] = {}
    visited: set[Edge] = set()
    cancelled_pair = False
    for edge, forward_count in directed_counts.items():
        if edge in visited:
            continue
        reverse = edge[1], edge[0]
        reverse_count = directed_counts.get(reverse, 0)
        visited.add(edge)
        visited.add(reverse)
        cancelled = min(forward_count, reverse_count)
        cancelled_pair = cancelled_pair or bool(cancelled)
        if cancelled and (forward_count > 1 or reverse_count > 1):
            raise SourceFilledBoundaryError(
                "source path contains ambiguous repeated bridge cancellation"
            )
        forward_left = forward_count - cancelled
        reverse_left = reverse_count - cancelled
        if forward_left > 1 or reverse_left > 1:
            raise SourceFilledBoundaryError(
                "source path contains duplicate physical-edge multiplicity"
            )
        residual_counts[edge] = forward_left
        residual_counts[reverse] = reverse_left
    if not cancelled_pair:
        return None
    physical: list[Edge] = []
    for index, edge in enumerate(source_edges):
        if index % 1_024 == 0:
            _cancel(cancel_check)
        if residual_counts.get(edge, 0):
            physical.append(edge)
            residual_counts[edge] -= 1
    if not physical:
        raise SourceFilledBoundaryError(
            "retraced cancellation removed every physical edge"
        )

    balance: dict[Point, int] = {}
    for start, end in physical:
        balance[start] = balance.get(start, 0) + 1
        balance[end] = balance.get(end, 0) - 1
    if any(balance.values()):
        raise SourceFilledBoundaryError(
            "physical boundary has unbalanced open incidence"
        )
    _cancel(cancel_check)
    return SourceFilledBoundary(source, tuple(physical))
