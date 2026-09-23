"""Topology-preserving mesh for routed, planar, and vertical PCB copper."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import ctypes
from math import atan2, ceil, cos, hypot, pi, radians, sin, sqrt
import os
import platform
from typing import Any, Callable, Dict, Iterable, List, Tuple

from .contracts import AnalysisSpec, DesignIR, ValidationIssue
from .dc_result_utils import stratified_sample_records
from .layers import copper_stack_profile
from .local_mesh_controls import LocalTrackControls


COPPER_CONDUCTIVITY_S_M = 5.8e7
DEFAULT_COPPER_THICKNESS_MM = 0.035
DEFAULT_VIA_PLATING_MM = 0.025
GIBIBYTE = 1024 ** 3
MIN_SOLVER_MEMORY_GB = 2.0
DEFAULT_SOLVER_MEMORY_GB = 2.0
MAX_PHYSICAL_MEMORY_FRACTION = 0.75
SOLVER_MEMORY_WORKING_FRACTION = 0.65
# PEEC retains several real/complex dense matrices and factorization workspaces.
PEEC_DENSE_BYTES_PER_BRANCH_SQUARED = 96
DC_SPARSE_BYTES_PER_BRANCH = 16 * 1024
TOPOLOGY_ONLY_BRANCH_KINDS = {
    "zone_attachment",
    "pad_attachment",
    "pad_zone_attachment",
    "source_contact",
    "load_contact",
}
Point2D = Tuple[float, float]
# Imported zone boundaries are expressed in millimetres. This is deliberately
# much tighter than the cell-containment tolerance: it is only for recognising
# a numerical jog introduced while tessellating an authoritative fill.
ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM = 1e-6
# Per-zone containment memoization is transient while rasterizing one polygon.
# The cap prevents pathological geometry from turning a speed optimization into
# unbounded memory growth.
MAX_ZONE_CONTAINMENT_CACHE_ENTRIES = 131_072


def is_visualizable_physical_branch(branch: "MeshBranch") -> bool:
    """Keep graph-only connectivity links in solves but out of field plots."""

    return branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS


@dataclass
class MeshNode:
    id: int
    x_mm: float
    y_mm: float
    z_mm: float
    layer: str
    net: str


@dataclass
class MeshBranch:
    id: str
    kind: str
    node_p: int
    node_n: int
    start_mm: Tuple[float, float, float]
    end_mm: Tuple[float, float, float]
    width_mm: float
    thickness_mm: float
    conductivity_s_m: float
    layer: str
    net: str
    source_id: str
    evidence_id: str = ""

    @property
    def length_mm(self) -> float:
        return sqrt(sum((b - a) ** 2 for a, b in zip(self.start_mm, self.end_mm)))

    @property
    def resistance_ohm(self) -> float:
        area_m2 = self.width_mm * self.thickness_mm * 1e-6
        return self.length_mm * 1e-3 / (self.conductivity_s_m * area_m2)


@dataclass
class HybridMesh:
    nodes: List[MeshNode] = field(default_factory=list)
    branches: List[MeshBranch] = field(default_factory=list)
    cells: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    geometry_counts: Dict[str, int] = field(
        default_factory=lambda: {"track": 0, "zone": 0, "via": 0, "pad": 0}
    )
    target_size_mm: float = 1.0
    minimum_local_target_mm: float = 1.0
    feature_refined_track_count: int = 0
    truncated: bool = False
    branch_admission: Dict[str, Any] = field(default_factory=dict)
    zone_pad_connection_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_preview(self, max_cells: int = 25000) -> Dict[str, Any]:
        # Builder order is grouped by geometry kind. A prefix slice therefore
        # omitted later vias, zones, and pads and produced misleading streaks.
        # Use the same ownership- and extent-preserving admission policy as the
        # renderer-neutral meshing service.
        cells = stratified_sample_records(self.cells, max_cells)
        counts = {"track": 0, "zone": 0, "via": 0, "pad": 0, "dielectric": 0}
        for cell in cells:
            kind = str(cell.get("source_kind", "dielectric"))
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "contract": "spike/mesh-preview/v2",
            "formulation": "hybrid_conductor",
            "target_size_mm": self.target_size_mm,
            "minimum_local_target_mm": self.minimum_local_target_mm,
            "feature_refined_track_count": self.feature_refined_track_count,
            "cells": cells,
            "cell_count": len(cells),
            "counts": counts,
            "geometry_counts": dict(self.geometry_counts),
            "node_count": len(self.nodes),
            "branch_count": len(self.branches),
            "branch_admission": dict(self.branch_admission),
            "zone_pad_connection_evidence": {
                key: value for key, value in self.zone_pad_connection_evidence.items() if key != "records"
            },
            "truncated": self.truncated or len(self.cells) > max_cells,
            "estimated_matrix_unknowns": len(self.nodes) + len(self.branches),
            "estimated_geometry_bytes": len(cells) * 4 * 3 * 8,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _point(value: Any) -> Point2D:
    if isinstance(value, dict):
        return float(value.get("x", 0)), float(value.get("y", 0))
    return float(value[0]), float(value[1])


def _net(item: Dict[str, Any]) -> str:
    return str(item.get("net_name") or item.get("net") or "")


def _copper_stack(design: DesignIR) -> Tuple[List[str], Dict[str, float], Dict[str, float]]:
    return copper_stack_profile(design, DEFAULT_COPPER_THICKNESS_MM)


def _point_in_polygon(point: Point2D, polygon: List[Point2D], tolerance: float = 0.0) -> bool:
    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (
                (previous[1] - current[1]) or 1e-15
            ) + current[0]
            if x < crossing:
                inside = not inside
        previous = current
    if inside:
        return True
    return bool(
        tolerance
        and any(_distance_to_segment(point, a, b) <= tolerance for a, b in _segments(polygon))
    )


def _segments(polygon: List[Point2D]) -> Iterable[Tuple[Point2D, Point2D]]:
    for index, point in enumerate(polygon):
        yield point, polygon[(index + 1) % len(polygon)]


def _segment_inside_polygon(
    start: Point2D,
    end: Point2D,
    polygon: List[Point2D],
    tolerance: float,
) -> bool:
    """Return true only when every interval of a segment remains on copper."""

    return _segment_inside_polygon_with_predicate(
        start,
        end,
        _segments(polygon),
        tolerance,
        lambda point: _point_in_polygon(point, polygon, tolerance),
    )


def _segment_inside_polygon_with_predicate(
    start: Point2D,
    end: Point2D,
    edges: Iterable[Tuple[Point2D, Point2D]],
    tolerance: float,
    point_inside: Callable[[Point2D], bool],
) -> bool:
    """Evaluate segment containment using reusable edges and point predicate."""

    if not (point_inside(start) and point_inside(end)):
        return False
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator_scale = max(hypot(dx, dy), 1.0)
    parameters = [0.0, 1.0]
    for a, b in edges:
        sx, sy = b[0] - a[0], b[1] - a[1]
        denominator = dx * sy - dy * sx
        ax, ay = a[0] - start[0], a[1] - start[1]
        if abs(denominator) <= tolerance * denominator_scale:
            cross = ax * dy - ay * dx
            if abs(cross) > tolerance * denominator_scale:
                continue
            length_squared = dx * dx + dy * dy
            if length_squared <= tolerance * tolerance:
                continue
            for point in (a, b):
                projection = (
                    (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
                ) / length_squared
                if -tolerance <= projection <= 1 + tolerance:
                    parameters.append(max(0.0, min(1.0, projection)))
            continue
        t = (ax * sy - ay * sx) / denominator
        u = (ax * dy - ay * dx) / denominator
        if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
            parameters.append(max(0.0, min(1.0, t)))
    ordered = sorted(set(round(value, 12) for value in parameters))
    return all(
        point_inside((
            start[0] + dx * ((left + right) / 2),
            start[1] + dy * ((left + right) / 2),
        ))
        for left, right in zip(ordered, ordered[1:])
        if right - left > 1e-12
    )


class _PolygonContainmentCache:
    """Bound repeated exact containment work for one immutable polygon."""

    def __init__(
        self,
        polygon: List[Point2D],
        tolerance: float,
        maximum_entries: int = MAX_ZONE_CONTAINMENT_CACHE_ENTRIES,
    ) -> None:
        self.polygon = polygon
        self.tolerance = tolerance
        self.maximum_entries = max(1, int(maximum_entries))
        self.edges = tuple(_segments(polygon))
        self.point_results: Dict[Point2D, bool] = {}
        self.segment_results: Dict[Tuple[Point2D, Point2D], bool] = {}

    def point_inside(self, point: Point2D) -> bool:
        cached = self.point_results.get(point)
        if cached is not None:
            return cached
        result = _point_in_polygon(point, self.polygon, self.tolerance)
        if len(self.point_results) < self.maximum_entries:
            self.point_results[point] = result
        return result

    def segment_inside(self, start: Point2D, end: Point2D) -> bool:
        key = (start, end) if start <= end else (end, start)
        cached = self.segment_results.get(key)
        if cached is not None:
            return cached
        result = _segment_inside_polygon_with_predicate(
            start,
            end,
            self.edges,
            self.tolerance,
            self.point_inside,
        )
        if len(self.segment_results) < self.maximum_entries:
            self.segment_results[key] = result
        return result


def _polygon_area(polygon: List[Point2D]) -> float:
    return abs(sum(
        point[0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * point[1]
        for index, point in enumerate(polygon)
    )) / 2


def _signed_polygon_area(polygon: List[Point2D]) -> float:
    return sum(
        point[0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * point[1]
        for index, point in enumerate(polygon)
    ) / 2


def _clean_polygon(polygon: List[Point2D], tolerance: float = 1e-9) -> List[Point2D]:
    """Remove only duplicate or truly redundant polygon vertices.

    ECAD filled copper may contain closely spaced arc and clearance vertices.
    Removing merely *nearly* collinear points changes the authoritative copper
    boundary and can bridge narrow voids.  A vertex is removed only when it
    lies on the finite segment joining its neighbours within tolerance.
    """

    cleaned: List[Point2D] = []
    for point in polygon:
        if not cleaned or hypot(point[0] - cleaned[-1][0], point[1] - cleaned[-1][1]) > tolerance:
            cleaned.append(point)
    if len(cleaned) > 1 and hypot(
        cleaned[0][0] - cleaned[-1][0],
        cleaned[0][1] - cleaned[-1][1],
    ) <= tolerance:
        cleaned.pop()

    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        result: List[Point2D] = []
        for index, current in enumerate(cleaned):
            previous = cleaned[index - 1]
            following = cleaned[(index + 1) % len(cleaned)]
            dx, dy = following[0] - previous[0], following[1] - previous[1]
            length_squared = dx * dx + dy * dy
            if length_squared <= tolerance * tolerance:
                changed = True
                continue
            projection = (
                (current[0] - previous[0]) * dx + (current[1] - previous[1]) * dy
            ) / length_squared
            nearest = (previous[0] + projection * dx, previous[1] + projection * dy)
            if (
                -tolerance <= projection <= 1.0 + tolerance
                and hypot(current[0] - nearest[0], current[1] - nearest[1]) <= tolerance
            ):
                changed = True
                continue
            result.append(current)
        cleaned = result
    return cleaned


def _normalize_filled_zone_polygon(polygon: List[Point2D]) -> List[Point2D]:
    """Repair only lossless numerical jogs in an imported filled-zone outline.

    Filled copper is authoritative input, so this is intentionally not a
    general-purpose polygon repair. It removes adjacent vertices separated by
    at most one nanometre, accepts the result only when it is simple, and
    rejects any repair with a measurable area change. Concavities and holes
    represented by the source boundary are therefore left intact rather than
    being bridged or filled by a simplifier.
    """

    baseline = _clean_polygon(polygon, tolerance=1e-9)
    if _polygon_is_simple(baseline, ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM):
        return baseline

    normalized: List[Point2D] = []
    for point in baseline:
        if not normalized or hypot(
            point[0] - normalized[-1][0],
            point[1] - normalized[-1][1],
        ) > ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM:
            normalized.append(point)
    if len(normalized) > 1 and hypot(
        normalized[0][0] - normalized[-1][0],
        normalized[0][1] - normalized[-1][1],
    ) <= ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM:
        normalized.pop()

    baseline_area = _polygon_area(baseline) if len(baseline) >= 3 else 0.0
    normalized_area = _polygon_area(normalized) if len(normalized) >= 3 else 0.0
    area_delta = abs(normalized_area - baseline_area)
    allowed_area_delta = max(1e-10, baseline_area * 1e-9)
    if (
        len(normalized) >= 3
        and _polygon_is_simple(normalized, ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM)
        and area_delta <= allowed_area_delta
    ):
        return normalized
    return baseline


def _clip_polygon_to_rect(
    polygon: List[Point2D],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    tolerance: float = 1e-9,
) -> List[Point2D]:
    """Clip a copper polygon to one finite-volume cell."""

    def clip(
        points: List[Point2D],
        inside: Any,
        intersect: Any,
    ) -> List[Point2D]:
        if not points:
            return []
        output: List[Point2D] = []
        previous = points[-1]
        previous_inside = inside(previous)
        for current in points:
            current_inside = inside(current)
            if current_inside != previous_inside:
                output.append(intersect(previous, current))
            if current_inside:
                output.append(current)
            previous, previous_inside = current, current_inside
        return output

    def vertical(a: Point2D, b: Point2D, x: float) -> Point2D:
        ratio = (x - a[0]) / ((b[0] - a[0]) or 1e-15)
        return x, a[1] + ratio * (b[1] - a[1])

    def horizontal(a: Point2D, b: Point2D, y: float) -> Point2D:
        ratio = (y - a[1]) / ((b[1] - a[1]) or 1e-15)
        return a[0] + ratio * (b[0] - a[0]), y

    result = list(polygon)
    result = clip(result, lambda p: p[0] >= x0, lambda a, b: vertical(a, b, x0))
    result = clip(result, lambda p: p[0] <= x1, lambda a, b: vertical(a, b, x1))
    result = clip(result, lambda p: p[1] >= y0, lambda a, b: horizontal(a, b, y0))
    result = clip(result, lambda p: p[1] <= y1, lambda a, b: horizontal(a, b, y1))
    return _clean_polygon(result, tolerance)


def _point_in_triangle(
    point: Point2D,
    a: Point2D,
    b: Point2D,
    c: Point2D,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether a point lies in or on a triangle."""

    def cross(p: Point2D, q: Point2D, r: Point2D) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    values = (cross(a, b, point), cross(b, c, point), cross(c, a, point))
    return not (
        any(value < -tolerance for value in values)
        and any(value > tolerance for value in values)
    )


def _triangulate_polygon(polygon: List[Point2D]) -> List[List[Point2D]]:
    """Triangulate a simple polygon without introducing edges outside copper."""

    points = _clean_polygon(polygon)
    if len(points) < 3 or not _polygon_is_simple(points):
        return []
    orientation = 1.0 if _signed_polygon_area(points) > 0 else -1.0
    indexes = list(range(len(points)))
    triangles: List[List[Point2D]] = []
    guard = len(points) * len(points)
    while len(indexes) > 3 and guard > 0:
        guard -= 1
        ear_found = False
        for position, current in enumerate(indexes):
            previous = indexes[position - 1]
            following = indexes[(position + 1) % len(indexes)]
            a, b, c = points[previous], points[current], points[following]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if orientation * cross <= 1e-10:
                continue
            if any(
                _point_in_triangle(points[candidate], a, b, c)
                for candidate in indexes
                if candidate not in {previous, current, following}
            ):
                continue
            triangles.append([a, b, c])
            indexes.pop(position)
            ear_found = True
            break
        if not ear_found:
            return []
    if len(indexes) == 3:
        triangles.append([points[index] for index in indexes])
    return triangles


def _polygon_edges_inside(
    candidate: List[Point2D],
    source: List[Point2D],
    tolerance: float,
) -> bool:
    return all(
        _segment_inside_polygon(start, end, source, tolerance)
        for start, end in _segments(candidate)
    )


def _polygon_is_contained_in(
    candidate: List[Point2D],
    source: List[Point2D],
    tolerance: float,
    containment_cache: _PolygonContainmentCache | None = None,
) -> bool:
    """Return true only for a simple face wholly contained by source copper.

    Checking only a clipped face's perimeter is insufficient for a concave
    source: a clipped rectangle can enclose a void while its corner vertices
    still appear valid.  Triangulating the candidate makes every rendered
    interior edge explicit and rejects that false bridge before it can reach
    the solver or result projection.
    """

    face = _clean_polygon(candidate)
    if len(face) < 3 or _polygon_area(face) <= 1e-12:
        return False
    triangles = _triangulate_polygon(face)
    if not triangles:
        return False
    for triangle in triangles:
        if containment_cache is None:
            edges_inside = _polygon_edges_inside(triangle, source, tolerance)
        else:
            edges_inside = all(
                containment_cache.segment_inside(start, end)
                for start, end in _segments(triangle)
            )
        if not edges_inside:
            return False
        center = (
            sum(point[0] for point in triangle) / 3,
            sum(point[1] for point in triangle) / 3,
        )
        if not (
            containment_cache.point_inside(center)
            if containment_cache is not None
            else _point_in_polygon(center, source, tolerance)
        ):
            return False
    return True


def _interior_polygon_point(polygon: List[Point2D]) -> Point2D | None:
    """Return a point guaranteed to lie in a simple polygon when possible."""

    triangles = _triangulate_polygon(_clean_polygon(polygon))
    if not triangles:
        return None
    triangle = max(triangles, key=_polygon_area)
    return (
        sum(point[0] for point in triangle) / 3,
        sum(point[1] for point in triangle) / 3,
    )


def _clip_polygon_to_rect_fragments(
    polygon: List[Point2D],
    triangles: List[List[Point2D]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    tolerance: float,
    containment_cache: _PolygonContainmentCache | None = None,
    triangle_bounds: List[Tuple[float, float, float, float]] | None = None,
) -> List[List[Point2D]]:
    """Clip one cell while preserving disconnected concave copper fragments."""

    clipped = _clip_polygon_to_rect(polygon, x0, y0, x1, y1, tolerance)
    if len(clipped) < 3:
        return []
    if _polygon_is_contained_in(
        clipped, polygon, tolerance, containment_cache
    ):
        return [clipped]

    fragments: List[List[Point2D]] = []
    for triangle_index, triangle in enumerate(triangles):
        # A strict bounding-box rejection cannot remove a positive-area
        # fragment. Touching boxes stay on the exact clipping path so cell
        # order and boundary behavior remain unchanged.
        if triangle_bounds is not None:
            triangle_min_x, triangle_min_y, triangle_max_x, triangle_max_y = (
                triangle_bounds[triangle_index]
            )
            if (
                triangle_max_x < x0 - tolerance
                or x1 + tolerance < triangle_min_x
                or triangle_max_y < y0 - tolerance
                or y1 + tolerance < triangle_min_y
            ):
                continue
        fragment = _clip_polygon_to_rect(triangle, x0, y0, x1, y1, tolerance)
        if (
            len(fragment) >= 3
            and _polygon_area(fragment) > 1e-12
            and _polygon_is_contained_in(
                fragment, polygon, tolerance, containment_cache
            )
        ):
            fragments.append(fragment)
    return fragments


def _polygons_touch(
    left: List[Point2D],
    right: List[Point2D],
    tolerance: float,
) -> bool:
    return any(
        _distance_to_segment(point, start, end) <= tolerance
        for point in left
        for start, end in _segments(right)
    ) or any(
        _distance_to_segment(point, start, end) <= tolerance
        for point in right
        for start, end in _segments(left)
    )


def _distance_to_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return hypot(point[0] - start[0], point[1] - start[1])
    ratio = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / length_squared,
        ),
    )
    return hypot(
        point[0] - start[0] - ratio * dx,
        point[1] - start[1] - ratio * dy,
    )


def _pad_size(pad: Dict[str, Any]) -> Point2D:
    size = pad.get("size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return max(float(size[0]), 0.01), max(float(size[1]), 0.01)
    width = max(float(pad.get("width", 1.0)), 0.01)
    return width, max(float(pad.get("height", width)), 0.01)


def _pad_drill_size(pad: Dict[str, Any]) -> Point2D:
    """Return the authoritative pad drill/slot dimensions in millimetres."""

    raw = pad.get("drill_size", pad.get("drill_size_mm"))
    if isinstance(raw, dict):
        raw = (raw.get("x", raw.get("width", 0.0)), raw.get("y", raw.get("height", 0.0)))
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return max(float(raw[0]), 0.0), max(float(raw[1]), 0.0)
        except (TypeError, ValueError):
            return 0.0, 0.0
    try:
        diameter = max(float(pad.get("drill", 0.0) or 0.0), 0.0)
    except (TypeError, ValueError):
        diameter = 0.0
    return diameter, diameter


def _pad_has_drill(pad: Dict[str, Any]) -> bool:
    width, height = _pad_drill_size(pad)
    return width > 0.0 and height > 0.0


def _pad_layers(pad: Dict[str, Any], copper_layers: List[str]) -> List[str]:
    raw = [str(value).strip('"') for value in pad.get("layers", [])]
    if any(value in {"*.Cu", "F&B.Cu"} for value in raw):
        return copper_layers
    result = [value for value in raw if value.endswith(".Cu")]
    if not result:
        layer = str(pad.get("layer", "F.Cu"))
        result = [layer] if layer.endswith(".Cu") else []
    return list(dict.fromkeys(result))


def _pad_local_to_world(pad: Dict[str, Any], x: float, y: float) -> Point2D:
    center = _point(pad.get("at", (0, 0)))
    angle = radians(float(pad.get("rotation", 0)))
    return (
        center[0] + x * cos(angle) - y * sin(angle),
        center[1] + x * sin(angle) + y * cos(angle),
    )


def _pad_world_to_local(pad: Dict[str, Any], point: Point2D) -> Point2D:
    """Transform a board-space point into the pad's authoritative local frame."""

    center = _point(pad.get("at", (0, 0)))
    angle = -radians(float(pad.get("rotation", 0)))
    dx, dy = point[0] - center[0], point[1] - center[1]
    return (
        dx * cos(angle) - dy * sin(angle),
        dx * sin(angle) + dy * cos(angle),
    )


def _point_in_capsule_local(
    point: Point2D,
    width: float,
    height: float,
    tolerance: float = 0.0,
) -> bool:
    """Return whether a local point lies in a KiCad oval (stadium/capsule)."""

    expanded_width = max(float(width) + 2 * tolerance, 0.0)
    expanded_height = max(float(height) + 2 * tolerance, 0.0)
    radius = min(expanded_width, expanded_height) / 2
    if radius <= 0.0:
        return False
    x, y = point
    if expanded_width >= expanded_height:
        half_segment = (expanded_width - expanded_height) / 2
        return hypot(max(abs(x) - half_segment, 0.0), y) <= radius
    half_segment = (expanded_height - expanded_width) / 2
    return hypot(x, max(abs(y) - half_segment, 0.0)) <= radius


def _capsule_ray_radius(width: float, height: float, angle: float) -> float:
    """Intersect a center-origin ray with a capsule boundary."""

    if width >= height:
        major_component, minor_component = cos(angle), sin(angle)
        half_segment, radius = (width - height) / 2, height / 2
    else:
        major_component, minor_component = sin(angle), cos(angle)
        half_segment, radius = (height - width) / 2, width / 2
    if abs(minor_component) > 1e-12:
        side_radius = radius / abs(minor_component)
        if abs(side_radius * major_component) <= half_segment + 1e-12:
            return side_radius
    cap_center = half_segment if major_component >= 0.0 else -half_segment
    discriminant = max(radius * radius - half_segment * half_segment * minor_component ** 2, 0.0)
    return max(major_component * cap_center + sqrt(discriminant), 0.0)


def _shape_ray_radius(
    shape: str,
    width: float,
    height: float,
    angle: float,
) -> float:
    if shape == "oval":
        return _capsule_ray_radius(width, height, angle)
    if shape == "circle":
        denominator = hypot(height * cos(angle), width * sin(angle))
        return width * height / max(2 * denominator, 1e-12)
    return _rect_ray_radius(width / 2, height / 2, angle)


def _shape_support_radius(
    shape: str,
    width: float,
    height: float,
    normal_angle: float,
) -> float:
    """Return the support distance for a centered convex pad primitive."""

    normal_x, normal_y = cos(normal_angle), sin(normal_angle)
    if shape == "oval":
        if width >= height:
            return (width - height) / 2 * abs(normal_x) + height / 2
        return (height - width) / 2 * abs(normal_y) + width / 2
    if shape == "circle":
        return hypot(width / 2 * normal_x, height / 2 * normal_y)
    return width / 2 * abs(normal_x) + height / 2 * abs(normal_y)


def _circumscribed_shape_polygon(
    shape: str,
    width: float,
    height: float,
    side_count: int,
) -> List[Point2D]:
    """Build a tangent polygon whose edges cannot enter the convex shape."""

    points: List[Point2D] = []
    for index in range(side_count):
        first_angle = 2 * pi * index / side_count
        second_angle = 2 * pi * (index + 1) / side_count
        first = (cos(first_angle), sin(first_angle))
        second = (cos(second_angle), sin(second_angle))
        first_support = _shape_support_radius(shape, width, height, first_angle)
        second_support = _shape_support_radius(shape, width, height, second_angle)
        determinant = first[0] * second[1] - first[1] * second[0]
        points.append((
            (first_support * second[1] - first[1] * second_support) / determinant,
            (first[0] * second_support - first_support * second[0]) / determinant,
        ))
    return points


def _pad_drill_shape(pad: Dict[str, Any]) -> str:
    raw = str(pad.get("drill_shape", "")).strip().lower()
    if raw in {"circle", "oval"}:
        return raw
    width, height = _pad_drill_size(pad)
    return "oval" if abs(width - height) > 1e-12 else "circle"


def _pad_is_plated(pad: Dict[str, Any]) -> bool:
    raw = pad.get("plated")
    if isinstance(raw, bool):
        return raw
    return str(pad.get("type", "")).strip().lower() != "np_thru_hole"


def _custom_pad_local_polygon(pad: Dict[str, Any]) -> List[Point2D]:
    geometry = pad.get("custom_geometry")
    if not isinstance(geometry, dict) or geometry.get("status") != "supported" \
            or geometry.get("coordinate_space") != "pad_local_mm":
        return []
    raw = geometry.get("positive_filled_polygon")
    if not isinstance(raw, list):
        return []
    try:
        mirror = -1.0 if geometry.get("mirror_x") is True else 1.0
        polygon = [(mirror * float(item[0]), float(item[1])) for item in raw
                   if isinstance(item, (list, tuple)) and len(item) == 2]
    except (TypeError, ValueError):
        return []
    polygon = _clean_polygon(polygon)
    return polygon if len(polygon) >= 3 and _polygon_is_simple(polygon) else []


def _point_in_pad(point: Point2D, pad: Dict[str, Any]) -> bool:
    x, y = _pad_world_to_local(pad, point)
    width, height = _pad_size(pad)
    shape = str(pad.get("shape", "rect")).lower()
    if shape == "custom":
        polygon = _custom_pad_local_polygon(pad)
        inside_outer = bool(polygon) and _point_in_polygon((x, y), polygon)
    elif shape == "oval":
        inside_outer = _point_in_capsule_local((x, y), width, height)
    elif shape == "circle":
        inside_outer = (x / (width / 2)) ** 2 + (y / (height / 2)) ** 2 <= 1.0
    else:
        inside_outer = abs(x) <= width / 2 and abs(y) <= height / 2
    if not inside_outer:
        return False
    drill_width, drill_height = _pad_drill_size(pad)
    if drill_width <= 0.0 or drill_height <= 0.0:
        return True
    if _pad_drill_shape(pad) == "oval":
        return not _point_in_capsule_local((x, y), drill_width, drill_height)
    return (x / (drill_width / 2)) ** 2 + (y / (drill_height / 2)) ** 2 >= 1.0


def _rect_ray_radius(half_width: float, half_height: float, angle: float) -> float:
    x_scale = half_width / max(abs(cos(angle)), 1e-12)
    y_scale = half_height / max(abs(sin(angle)), 1e-12)
    return min(x_scale, y_scale)


def _annular_pad_local_cells(
    pad: Dict[str, Any],
    target_mm: float,
    max_custom_cells: int | None = None,
) -> tuple[List[List[Point2D]], List[tuple[int, int]]]:
    """Create conformal annular sectors that do not cross a pad drill void."""

    width, height = _pad_size(pad)
    drill_width, drill_height = _pad_drill_size(pad)
    if (
        drill_width <= 0.0
        or drill_height <= 0.0
        or drill_width >= width
        or drill_height >= height
    ):
        return [], []
    shape = str(pad.get("shape", "rect")).lower()
    custom_polygon = _custom_pad_local_polygon(pad) if shape == "custom" else []
    if shape == "custom" and (
        not custom_polygon or not _point_in_polygon((0.0, 0.0), custom_polygon, 1e-9)
    ):
        return [], []
    circumference = (
        sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in _segments(custom_polygon))
        if custom_polygon else pi * max(width, height)
    )
    side_count = max(24, min(192, int(ceil(circumference / max(target_mm, 0.01)))))
    drill_shape = _pad_drill_shape(pad)

    inner = _circumscribed_shape_polygon(
        drill_shape, drill_width, drill_height, side_count
    )
    outer: List[Point2D] = []
    for inner_point in inner:
        angle = atan2(inner_point[1], inner_point[0])
        if custom_polygon:
            direction = (cos(angle), sin(angle))
            intersections: List[float] = []
            for start, end in _segments(custom_polygon):
                edge = (end[0] - start[0], end[1] - start[1])
                denominator = direction[0] * edge[1] - direction[1] * edge[0]
                scale = max(hypot(*edge), 1.0)
                if abs(denominator) <= 1e-12 * scale:
                    if abs(start[0] * direction[1] - start[1] * direction[0]) <= 1e-12 * scale:
                        intersections.extend(
                            value for value in (
                                start[0] * direction[0] + start[1] * direction[1],
                                end[0] * direction[0] + end[1] * direction[1],
                            ) if value > 1e-12
                        )
                    continue
                ray_distance = (start[0] * edge[1] - start[1] * edge[0]) / denominator
                edge_ratio = (start[0] * direction[1] - start[1] * direction[0]) / denominator
                if ray_distance > 1e-12 and -1e-12 <= edge_ratio <= 1 + 1e-12:
                    intersections.append(ray_distance)
            unique: List[float] = []
            for value in sorted(intersections):
                if not unique or abs(value - unique[-1]) > 1e-8:
                    unique.append(value)
            if len(unique) != 1:
                return [], []
            outer_radius = unique[0]
        else:
            outer_radius = _shape_ray_radius(shape, width, height, angle)
        if outer_radius <= hypot(*inner_point) + 1e-9:
            return [], []
        outer.append((outer_radius * cos(angle), outer_radius * sin(angle)))

    if custom_polygon and not _polygon_is_contained_in(outer, custom_polygon, 1e-8):
        return [], []
    clearance = min(
        hypot(outer_point[0] - inner_point[0], outer_point[1] - inner_point[1])
        for outer_point, inner_point in zip(outer, inner)
    )
    radial_count = max(1, int(ceil(clearance / max(target_mm, 0.01))))
    if custom_polygon and (
        max_custom_cells is None or side_count * radial_count > max_custom_cells
    ):
        return [], []

    rings: List[List[Point2D]] = []
    for radial in range(radial_count + 1):
        ratio = radial / radial_count
        rings.append([
            (
                inner[index][0] + ratio * (outer[index][0] - inner[index][0]),
                inner[index][1] + ratio * (outer[index][1] - inner[index][1]),
            )
            for index in range(side_count)
        ])

    cells: List[List[Point2D]] = []
    indices: List[tuple[int, int]] = []
    for radial in range(radial_count):
        for side in range(side_count):
            next_side = (side + 1) % side_count
            cells.append([
                rings[radial][side],
                rings[radial + 1][side],
                rings[radial + 1][next_side],
                rings[radial][next_side],
            ])
            indices.append((radial, side))
    if custom_polygon and any(
        not _polygon_is_contained_in(cell, custom_polygon, 1e-8) for cell in cells
    ):
        return [], []
    return cells, indices


def _pad_boundary_polygon(pad: Dict[str, Any], curve_segments: int = 32) -> List[Point2D]:
    """Return a bounded polygonal representation of the pad perimeter."""

    width, height = _pad_size(pad)
    shape = str(pad.get("shape", "rect")).lower()
    if shape == "custom":
        return [_pad_local_to_world(pad, x, y) for x, y in _custom_pad_local_polygon(pad)]
    if shape in {"circle", "oval"}:
        count = max(int(curve_segments), 12)
        return [
            _pad_local_to_world(
                pad,
                _shape_ray_radius(shape, width, height, 2 * pi * index / count)
                * cos(2 * pi * index / count),
                _shape_ray_radius(shape, width, height, 2 * pi * index / count)
                * sin(2 * pi * index / count),
            )
            for index in range(count)
        ]
    return [
        _pad_local_to_world(pad, x, y)
        for x, y in (
            (-width / 2, -height / 2),
            (width / 2, -height / 2),
            (width / 2, height / 2),
            (-width / 2, height / 2),
        )
    ]


def _segment_intersection_points(
    left_start: Point2D,
    left_end: Point2D,
    right_start: Point2D,
    right_end: Point2D,
    tolerance: float,
) -> List[Point2D]:
    """Return bounded intersections, including endpoints of collinear overlap."""

    left_dx, left_dy = left_end[0] - left_start[0], left_end[1] - left_start[1]
    right_dx, right_dy = right_end[0] - right_start[0], right_end[1] - right_start[1]
    denominator = left_dx * right_dy - left_dy * right_dx
    offset_x, offset_y = right_start[0] - left_start[0], right_start[1] - left_start[1]
    scale = max(hypot(left_dx, left_dy), hypot(right_dx, right_dy), 1.0)
    if abs(denominator) > tolerance * scale:
        left_ratio = (offset_x * right_dy - offset_y * right_dx) / denominator
        right_ratio = (offset_x * left_dy - offset_y * left_dx) / denominator
        if -tolerance <= left_ratio <= 1 + tolerance and -tolerance <= right_ratio <= 1 + tolerance:
            return [(
                left_start[0] + max(0.0, min(1.0, left_ratio)) * left_dx,
                left_start[1] + max(0.0, min(1.0, left_ratio)) * left_dy,
            )]
        return []

    if abs(offset_x * left_dy - offset_y * left_dx) > tolerance * scale:
        return []
    return [
        point
        for point in (left_start, left_end, right_start, right_end)
        if _distance_to_segment(point, left_start, left_end) <= tolerance
        and _distance_to_segment(point, right_start, right_end) <= tolerance
    ]


def _polygon_is_simple(polygon: List[Point2D], tolerance: float = 1e-9) -> bool:
    """Reject self-intersecting filled outlines before ear clipping them."""

    if len(polygon) < 3 or _polygon_area(polygon) <= tolerance * tolerance:
        return False
    edges = list(_segments(polygon))
    edge_count = len(edges)
    for left_index, (left_start, left_end) in enumerate(edges):
        for right_index in range(left_index + 1, edge_count):
            if right_index in {left_index - 1, left_index, left_index + 1}:
                continue
            if left_index == 0 and right_index == edge_count - 1:
                continue
            if _segment_intersection_points(
                left_start,
                left_end,
                edges[right_index][0],
                edges[right_index][1],
                tolerance,
            ):
                return False
    return True


def _pad_polygon_overlap_points(
    pad: Dict[str, Any],
    polygon: List[Point2D],
    tolerance: float,
) -> List[Point2D]:
    """Find physical pad/zone contact points without relying on mesh centers."""

    boundary = _pad_boundary_polygon(pad)
    candidates: List[Point2D] = []
    center = _point(pad.get("at", (0, 0)))
    if _point_in_polygon(center, polygon, tolerance):
        candidates.append(center)
    candidates.extend(
        point for point in boundary if _point_in_polygon(point, polygon, tolerance)
    )
    candidates.extend(point for point in polygon if _point_in_pad(point, pad))
    for pad_start, pad_end in _segments(boundary):
        for zone_start, zone_end in _segments(polygon):
            candidates.extend(
                _segment_intersection_points(
                    pad_start,
                    pad_end,
                    zone_start,
                    zone_end,
                    tolerance,
                )
            )

    unique: List[Point2D] = []
    merge_tolerance = max(tolerance, 1e-7)
    for point in candidates:
        if not _point_in_pad(point, pad) or not _point_in_polygon(point, polygon, tolerance):
            continue
        if not any(hypot(point[0] - other[0], point[1] - other[1]) <= merge_tolerance for other in unique):
            unique.append(point)
    return unique


def _pad_overlaps_polygon(pad: Dict[str, Any], polygon: List[Point2D], tolerance: float) -> bool:
    return bool(_pad_polygon_overlap_points(pad, polygon, tolerance))


def _physical_memory_bytes() -> int | None:
    """Return installed physical RAM without an optional runtime dependency."""

    try:
        if platform.system() == "Windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys)
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        total = int(page_size) * int(page_count)
        return total if total > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _branch_admission(spec: AnalysisSpec) -> Dict[str, Any]:
    """Derive a conductor limit from the configured solve-memory budget."""

    resource_limits = spec.options.get("resource_limits", {})
    configured_gb = float(
        spec.mesh.get(
            "solver_memory_limit_gb",
            resource_limits.get("memory_limit_gb", DEFAULT_SOLVER_MEMORY_GB)
            if isinstance(resource_limits, dict)
            else DEFAULT_SOLVER_MEMORY_GB,
        )
    )
    valid = configured_gb >= MIN_SOLVER_MEMORY_GB
    admitted_gb = max(configured_gb, MIN_SOLVER_MEMORY_GB)
    configured_bytes = int(admitted_gb * GIBIBYTE)
    physical_bytes = _physical_memory_bytes()
    physical_ceiling = (
        int(physical_bytes * MAX_PHYSICAL_MEMORY_FRACTION)
        if physical_bytes is not None and physical_bytes > 0
        else configured_bytes
    )
    effective_bytes = min(configured_bytes, physical_ceiling)
    workspace_bytes = max(1, int(effective_bytes * SOLVER_MEMORY_WORKING_FRACTION))
    dense_mode = spec.mode in {"ac", "broadband_hf", "si", "transient"}
    if dense_mode:
        capacity = max(
            16,
            int(sqrt(workspace_bytes / PEEC_DENSE_BYTES_PER_BRANCH_SQUARED)),
        )
        storage_model = "96*N^2 bytes dense PEEC workspace"
        estimated_at_capacity = PEEC_DENSE_BYTES_PER_BRANCH_SQUARED * capacity ** 2
    else:
        capacity = max(16, workspace_bytes // DC_SPARSE_BYTES_PER_BRANCH)
        storage_model = "16 KiB per branch sparse DC workspace"
        estimated_at_capacity = DC_SPARSE_BYTES_PER_BRANCH * capacity

    explicit = spec.mesh.get("max_conductors")
    requested_limit = max(int(explicit), 16) if explicit is not None else None
    effective_limit = min(requested_limit, capacity) if requested_limit is not None else capacity
    return {
        "configured_memory_gb": configured_gb,
        "minimum_memory_gb": MIN_SOLVER_MEMORY_GB,
        "configuration_valid": valid,
        "configured_memory_bytes": configured_bytes,
        "physical_memory_bytes": physical_bytes,
        "effective_memory_bytes": effective_bytes,
        "workspace_fraction": SOLVER_MEMORY_WORKING_FRACTION,
        "workspace_bytes": workspace_bytes,
        "workload_class": "dense" if dense_mode else "sparse",
        "storage_model": storage_model,
        "memory_capacity_branches": capacity,
        "requested_branch_limit": requested_limit,
        "effective_branch_limit": effective_limit,
        "estimated_storage_at_capacity_bytes": estimated_at_capacity,
        "limited_by_memory": requested_limit is None or capacity < requested_limit,
        "meaning": "Resource admission only; numerical convergence and model validity are separate gates.",
    }


class _Builder:
    def __init__(self, design: DesignIR, spec: AnalysisSpec):
        self.design = design
        self.spec = spec
        self.target = max(float(spec.mesh.get("target_size_mm", 1.0)), 0.05)
        self.zone_target = max(float(spec.mesh.get("zone_cell_mm", self.target)), 0.05)
        self.feature_aware = bool(spec.mesh.get("feature_aware", True))
        self.max_track_aspect_ratio = max(
            float(spec.mesh.get("max_track_cell_aspect_ratio", 2.0)),
            0.25,
        )
        self.minimum_feature_target = max(
            float(spec.mesh.get("minimum_feature_target_mm", 0.01)),
            0.005,
        )
        # Node merging may be intentionally relaxed for imperfect CAD input,
        # but it must never define the copper-boundary tolerance.  Keeping the
        # latter small prevents a narrow void in a concave zone from becoming
        # a mesh bridge or a rendered result streak.
        self.node_tolerance = max(float(spec.mesh.get("node_tolerance_mm", 0.001)), 1e-5)
        self.containment_tolerance = max(
            min(
                float(spec.mesh.get("containment_tolerance_mm", 0.0001)),
                self.node_tolerance,
            ),
            1e-6,
        )
        self.branch_admission = _branch_admission(spec)
        self.max_branches = int(self.branch_admission["effective_branch_limit"])
        self.max_zone_cells = max(int(spec.mesh.get("max_zone_cells", 3000)), 4)
        self.max_pad_cells = max(int(spec.mesh.get("max_pad_cells", self.max_zone_cells)), 4)
        self.requested = {str(value) for value in spec.net_names if str(value)}
        self.local_controls = LocalTrackControls(spec.mesh.get("local_controls"),
            design.tracks, self.requested, self.node_tolerance)
        self.copper_layers, self.layer_z, self.thickness = _copper_stack(design)
        self.mesh = HybridMesh(
            target_size_mm=self.target,
            minimum_local_target_mm=self.target,
            branch_admission=dict(self.branch_admission),
        )
        self.node_map: Dict[Tuple[int, int, str, str], int] = {}
        self.nodes_by_layer_net: Dict[Tuple[str, str], List[int]] = {}
        self.zone_regions: List[Dict[str, Any]] = []
        self.unresolved_zone_attachments: set[str] = set()
        self.zone_pad_evidence_required = any(
            zone.get("filled_copper_state") == "source_filled" for zone in self.design.zones
        )
        self.zone_pad_attachment_evidence: Dict[Tuple[str, str, str], str] = {}
        if self.zone_pad_evidence_required:
            self._prepare_zone_pad_connection_evidence()

    def _prepare_zone_pad_connection_evidence(self) -> None:
        from .design_ir_v2 import DesignIRV2
        from .zone_pad_connection_evidence import build_zone_pad_connection_evidence
        try:
            typed = DesignIRV2.from_v1(self.design)
            report = build_zone_pad_connection_evidence(typed)
            pad_sources = {item.id: item.source_id or item.id for item in typed.pads}
            zone_sources = {item.id: item.source_id or item.id for item in typed.zones}
            layer_names = {item.id: item.name for item in typed.layers}
            self.mesh.zone_pad_connection_evidence = report
            self.zone_pad_attachment_evidence = {
                (pad_sources[item["pad_id"]], zone_sources[item["zone_id"]], layer_names[item["layer_id"]]): item["record_id"]
                for item in report["records"]
                if item["observation"] == "source_filled_copper_contact"
                and item["resolved_mode"] in {"thermal", "solid"}
            }
        except (TypeError, ValueError, KeyError) as error:
            self.mesh.issues.append(ValidationIssue(
                "SPIKE-BE-MESH-E-0018", "error",
                f"Typed zone-pad connectivity could not be proven: {error}",
                suggestion="Repair retained zone/pad/footprint policy or source-filled copper evidence before solving.",
                status="failed",
            ))

    def node(self, point: Point2D, layer: str, net: str) -> int:
        key = (
            round(point[0] / self.node_tolerance),
            round(point[1] / self.node_tolerance),
            layer,
            net,
        )
        if key not in self.node_map:
            index = len(self.mesh.nodes)
            self.node_map[key] = index
            self.mesh.nodes.append(
                MeshNode(index, point[0], point[1], self.layer_z.get(layer, 0.0), layer, net)
            )
            self.nodes_by_layer_net.setdefault((layer, net), []).append(index)
        return self.node_map[key]

    def zone_node(self, point: Point2D, layer: str, net: str) -> int:
        """Create a zone node without merging across a narrow copper void.

        Zone cells have explicit, containment-tested branch links.  Reusing
        the general topology snap map here can otherwise merge centroids from
        separate islands before those links are evaluated.
        """

        index = len(self.mesh.nodes)
        self.mesh.nodes.append(
            MeshNode(index, point[0], point[1], self.layer_z.get(layer, 0.0), layer, net)
        )
        self.nodes_by_layer_net.setdefault((layer, net), []).append(index)
        return index

    def nearest_grid_node(
        self,
        grid: Dict[Tuple[int, int], List[int]],
        point: Point2D,
        min_x: float,
        min_y: float,
        cell: float,
    ) -> int:
        column = int((point[0] - min_x) // cell)
        row = int((point[1] - min_y) // cell)
        for radius in range(3):
            candidates = [
                node_id
                for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1)
                if max(abs(dx), abs(dy)) == radius
                for node_id in grid.get((column + dx, row + dy), [])
            ]
            if candidates:
                return min(
                    candidates,
                    key=lambda candidate: hypot(
                        point[0] - self.mesh.nodes[candidate].x_mm,
                        point[1] - self.mesh.nodes[candidate].y_mm,
                    ),
                )
        return min(
            (node_id for node_ids in grid.values() for node_id in node_ids),
            key=lambda candidate: hypot(
                point[0] - self.mesh.nodes[candidate].x_mm,
                point[1] - self.mesh.nodes[candidate].y_mm,
            ),
        )

    def local_zone_node(
        self,
        region: Dict[str, Any],
        point: Point2D,
        containment_cache: _PolygonContainmentCache | None = None,
    ) -> int | None:
        """Find a nearby zone node without crossing a void or another island."""

        candidate = self.nearest_grid_node(
            region["grid"],
            point,
            float(region["min_x"]),
            float(region["min_y"]),
            float(region["cell_mm"]),
        )
        node = self.mesh.nodes[candidate]
        distance = hypot(point[0] - node.x_mm, point[1] - node.y_mm)
        cell = float(region["cell_mm"])
        if distance > sqrt(2.0) * cell + self.node_tolerance:
            return None
        end = (node.x_mm, node.y_mm)
        contained = (
            containment_cache.segment_inside(point, end)
            if containment_cache is not None
            else _segment_inside_polygon(
                point,
                end,
                region["polygon"],
                self.containment_tolerance,
            )
        )
        if not contained:
            return None
        return candidate

    def warn_unresolved_zone_attachment(self, source_id: str) -> None:
        if source_id in self.unresolved_zone_attachments:
            return
        self.unresolved_zone_attachments.add(source_id)
        self.mesh.issues.append(ValidationIssue(
            "ZONE_ATTACHMENT_UNRESOLVED",
            "warning",
            f"{source_id} could not be connected to a local zone cell without crossing unfilled space.",
            suggestion="Refine the local zone mesh or inspect the imported copper island before solving.",
            status="approximate",
        ))

    def add_branch(
        self,
        branch_id: str,
        kind: str,
        a: int,
        b: int,
        width: float,
        thickness: float,
        layer: str,
        net: str,
        source_id: str,
        evidence_id: str = "",
    ) -> None:
        if a == b or self.mesh.truncated:
            return
        if len(self.mesh.branches) >= self.max_branches:
            self.mesh.truncated = True
            return
        p, n = self.mesh.nodes[a], self.mesh.nodes[b]
        self.mesh.branches.append(
            MeshBranch(
                branch_id,
                kind,
                a,
                b,
                (p.x_mm, p.y_mm, p.z_mm),
                (n.x_mm, n.y_mm, n.z_mm),
                max(width, 0.001),
                max(thickness, 0.001),
                COPPER_CONDUCTIVITY_S_M,
                layer,
                net,
                source_id,
                evidence_id,
            )
        )

    def add_cell(
        self,
        cell_id: str,
        kind: str,
        source_id: str,
        layer: str,
        net: str,
        vertices: List[Tuple[float, float, float]],
        role: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        cell = {
            "id": cell_id,
            "kind": "surface",
            "source_kind": kind,
            "source_id": source_id,
            "layer": layer,
            "net": net,
            "vertices_mm": [list(point) for point in vertices],
        }
        if role:
            cell["role"] = role
        if metadata:
            cell.update(metadata)
        self.mesh.cells.append(cell)

    def tracks(self) -> None:
        endpoint_caps: Dict[Tuple[int, int, str, str], Dict[str, Any]] = {}
        for index, track in enumerate(self.design.tracks):
            net = _net(track)
            if not net or (self.requested and net not in self.requested):
                continue
            start, end = _point(track["start"]), _point(track["end"])
            length = hypot(end[0] - start[0], end[1] - start[1])
            width = max(float(track.get("width", 0.2)), 0.01)
            if length <= 1e-9:
                continue
            layer = str(track.get("layer", "F.Cu"))
            thickness = self.thickness.get(layer, DEFAULT_COPPER_THICKNESS_MM)
            source_id = str(track.get("id", f"track-{index + 1}"))
            for point in (start, end):
                key = (
                    round(point[0] / self.node_tolerance),
                    round(point[1] / self.node_tolerance),
                    layer,
                    net,
                )
                previous_cap = endpoint_caps.get(key)
                radius = width / 2
                if previous_cap is None or radius > float(previous_cap["radius_mm"]):
                    endpoint_caps[key] = {
                        "point": point,
                        "radius_mm": radius,
                        "layer": layer,
                        "net": net,
                        "source_id": source_id,
                    }
            local_target = self.target
            if self.feature_aware:
                local_target = max(
                    min(self.target, width * self.max_track_aspect_ratio),
                    self.minimum_feature_target,
                )
                if local_target < self.target - 1e-12:
                    self.mesh.feature_refined_track_count += 1
                    self.mesh.minimum_local_target_mm = min(
                        self.mesh.minimum_local_target_mm,
                        local_target,
                    )
            fractions = self.local_controls.fractions(source_id, start, end, local_target,
                min(1_000_000, max(1, self.max_branches - len(self.mesh.branches))))
            if fractions is not None and len(fractions) > self.max_branches - len(self.mesh.branches):
                raise ValueError("Local mesh controls exceed remaining branch capacity")
            count = max(1, int(ceil(length / local_target))) if fractions is None else len(fractions)
            nx, ny = -(end[1] - start[1]) / length * width / 2, (end[0] - start[0]) / length * width / 2
            previous = self.node(start, layer, net)
            for segment in range(count):
                ratio = (segment + 1) / count if fractions is None else fractions[segment]
                point = (
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                )
                current = self.node(point, layer, net)
                branch_id = f"{source_id}:segment:{segment + 1}"
                self.add_branch(branch_id, "track", previous, current, width, thickness, layer, net, source_id)
                p0, p1 = self.mesh.nodes[previous], self.mesh.nodes[current]
                z = p0.z_mm
                self.add_cell(
                    branch_id,
                    "track",
                    source_id,
                    layer,
                    net,
                    [
                        (p0.x_mm + nx, p0.y_mm + ny, z),
                        (p1.x_mm + nx, p1.y_mm + ny, z),
                        (p1.x_mm - nx, p1.y_mm - ny, z),
                        (p0.x_mm - nx, p0.y_mm - ny, z),
                    ],
                )
                previous = current
            self.mesh.geometry_counts["track"] += 1

        # KiCad routed segments are round-ended strokes. Rectangular branch
        # cells alone only touch at their centerline endpoints and leave a
        # wedge at angled joints. One shared cap per layer/net endpoint makes
        # the preview domain match the imported copper without altering the
        # electrical branch graph.
        for cap_index, (_, cap) in enumerate(sorted(endpoint_caps.items()), start=1):
            point = cap["point"]
            radius = float(cap["radius_mm"])
            layer = str(cap["layer"])
            net = str(cap["net"])
            source_id = str(cap["source_id"])
            z = self.layer_z.get(layer, 0.0)
            chord_target = max(min(self.target, radius), 0.01)
            sides = max(12, min(32, int(ceil(2 * pi * radius / chord_target))))
            self.add_cell(
                f"{source_id}:endpoint-cap:{cap_index}",
                "track",
                source_id,
                layer,
                net,
                [
                    (
                        point[0] + radius * cos(2 * pi * side / sides),
                        point[1] + radius * sin(2 * pi * side / sides),
                        z,
                    )
                    for side in range(sides)
                ],
                role="track_endpoint_cap",
            )

    def vias(self) -> None:
        via_model = str(self.spec.mesh.get("via_model", "extracted"))
        if via_model not in {"extracted", "plated_cylinder"}:
            raise ValueError(f"Unsupported via model: {via_model}")
        plating_default = max(
            float(self.spec.mesh.get("via_plating_thickness_mm", DEFAULT_VIA_PLATING_MM)),
            0.005,
        )
        for index, via in enumerate(self.design.vias):
            net = _net(via)
            if not net or (self.requested and net not in self.requested):
                continue
            raw_layers = [str(value) for value in via.get("layers", ("F.Cu", "B.Cu"))]
            if len(raw_layers) < 2:
                continue
            try:
                first, last = self.copper_layers.index(raw_layers[0]), self.copper_layers.index(raw_layers[-1])
                lo, hi = sorted((first, last))
                layers = self.copper_layers[lo : hi + 1]
            except ValueError:
                layers = raw_layers[:2]
            point = _point(via.get("at", (0, 0)))
            drill = max(float(via.get("drill", 0.3)), 0.01)
            plating = plating_default
            if via_model == "extracted":
                plating = max(
                    float(via.get("plating_thickness", via.get("plating_thickness_mm", plating_default))),
                    0.005,
                )
            # width * thickness exactly equals the annular barrel cross-section.
            barrel_width = pi * (drill + plating)
            source_id = str(via.get("id", f"via-{index + 1}"))
            via_nodes = [self.node(point, layer, net) for layer in layers]
            for span, (layer_a, layer_b, a, b) in enumerate(
                zip(layers, layers[1:], via_nodes, via_nodes[1:])
            ):
                branch_id = f"{source_id}:barrel:{span + 1}"
                self.add_branch(
                    branch_id,
                    "via",
                    a,
                    b,
                    barrel_width,
                    plating,
                    f"{layer_a}->{layer_b}",
                    net,
                    source_id,
                )
                radius = drill / 2 + plating
                sides = max(8, min(24, int(ceil(2 * pi * radius / self.target))))
                top, bottom = self.mesh.nodes[a].z_mm, self.mesh.nodes[b].z_mm
                for side in range(sides):
                    angle_a, angle_b = 2 * pi * side / sides, 2 * pi * (side + 1) / sides
                    inner_radius = drill / 2
                    self.add_cell(
                        f"{branch_id}:face:{side + 1}",
                        "via",
                        source_id,
                        f"{layer_a}->{layer_b}",
                        net,
                        [
                            (point[0] + radius * cos(angle_a), point[1] + radius * sin(angle_a), top),
                            (point[0] + radius * cos(angle_b), point[1] + radius * sin(angle_b), top),
                            (point[0] + radius * cos(angle_b), point[1] + radius * sin(angle_b), bottom),
                            (point[0] + radius * cos(angle_a), point[1] + radius * sin(angle_a), bottom),
                        ],
                        metadata={
                            "inner_vertices_mm": [
                                [point[0] + inner_radius * cos(angle_a), point[1] + inner_radius * sin(angle_a), top],
                                [point[0] + inner_radius * cos(angle_b), point[1] + inner_radius * sin(angle_b), top],
                                [point[0] + inner_radius * cos(angle_b), point[1] + inner_radius * sin(angle_b), bottom],
                                [point[0] + inner_radius * cos(angle_a), point[1] + inner_radius * sin(angle_a), bottom],
                            ],
                            "plating_thickness_mm": plating,
                        },
                    )
            self.mesh.geometry_counts["via"] += 1

    def zones(self) -> None:
        for index, zone in enumerate(self.design.zones):
            net = _net(zone)
            layer = str(zone.get("layer", ""))
            if not net or not layer.endswith(".Cu") or (self.requested and net not in self.requested):
                continue
            source_id = str(zone.get("id", f"zone-{index + 1}"))
            # Preserve the filled-zone perimeter supplied by the importer.
            # The mesher may simplify only numerical duplicates, never a
            # shallow clearance or curved boundary feature.
            polygon = _normalize_filled_zone_polygon(
                [_point(value) for value in zone.get("points", [])]
            )
            if (
                len(polygon) < 3
                or _polygon_area(polygon) <= 1e-12
                or not _polygon_is_simple(
                    polygon,
                    ZONE_BOUNDARY_VALIDATION_TOLERANCE_MM,
                )
            ):
                self.mesh.issues.append(ValidationIssue(
                    "SPIKE-BE-MESH-W-0002",
                    "warning",
                    f"{source_id} has no usable simple filled copper polygon.",
                    path=f"design.zones[{source_id}]",
                    suggestion="Repair the imported zone outline before using it for a conductor solve.",
                    status="approximate",
                ))
                continue
            min_x, max_x = min(p[0] for p in polygon), max(p[0] for p in polygon)
            min_y, max_y = min(p[1] for p in polygon), max(p[1] for p in polygon)
            estimated = max(1.0, (max_x - min_x) * (max_y - min_y) / self.zone_target**2)
            cell = self.zone_target * sqrt(max(1.0, estimated / self.max_zone_cells))
            columns = max(1, int(ceil((max_x - min_x) / cell)))
            rows = max(1, int(ceil((max_y - min_y) / cell)))
            existing = list(self.nodes_by_layer_net.get((layer, net), []))
            triangles = _triangulate_polygon(polygon)
            triangle_bounds = [
                (
                    min(x for x, _ in triangle),
                    min(y for _, y in triangle),
                    max(x for x, _ in triangle),
                    max(y for _, y in triangle),
                )
                for triangle in triangles
            ]
            containment_cache = _PolygonContainmentCache(
                polygon,
                self.containment_tolerance,
            )
            grid: Dict[Tuple[int, int], List[int]] = {}
            fragment_polygons: Dict[Tuple[int, int], List[List[Point2D]]] = {}
            z = self.layer_z.get(layer, 0.0)
            for row in range(rows):
                for column in range(columns):
                    x0, y0 = min_x + column * cell, min_y + row * cell
                    x1, y1 = min(x0 + cell, max_x), min(y0 + cell, max_y)
                    fragments = _clip_polygon_to_rect_fragments(
                        polygon,
                        triangles,
                        x0,
                        y0,
                        x1,
                        y1,
                        self.containment_tolerance,
                        containment_cache,
                        triangle_bounds,
                    )
                    for fragment_index, clipped in enumerate(fragments):
                        if _polygon_area(clipped) <= max(1e-12, cell * cell * 1e-10):
                            continue
                        center = _interior_polygon_point(clipped)
                        if center is None:
                            continue
                        key = (column, row)
                        grid.setdefault(key, []).append(self.zone_node(center, layer, net))
                        fragment_polygons.setdefault(key, []).append(clipped)
                        self.add_cell(
                            f"{source_id}:cell:{column}:{row}:fragment:{fragment_index}",
                            "zone",
                            source_id,
                            layer,
                            net,
                            [(x, y, z) for x, y in clipped],
                        )
            if not grid:
                interior_point = _interior_polygon_point(polygon)
                if interior_point is None:
                    self.mesh.issues.append(ValidationIssue(
                        "SPIKE-BE-MESH-W-0002",
                        "warning",
                        f"{source_id} could not be triangulated into usable filled copper.",
                        path=f"design.zones[{source_id}]",
                        suggestion="Repair the imported zone outline before using it for a conductor solve.",
                        status="approximate",
                    ))
                    continue
                grid[(0, 0)] = [self.zone_node(interior_point, layer, net)]
                fragment_polygons[(0, 0)] = [polygon]
            thickness = self.thickness.get(layer, DEFAULT_COPPER_THICKNESS_MM)
            for (column, row), current_nodes in grid.items():
                current_polygons = fragment_polygons[(column, row)]
                for left_index, left_node in enumerate(current_nodes):
                    for right_index in range(left_index + 1, len(current_nodes)):
                        if not _polygons_touch(
                            current_polygons[left_index],
                            current_polygons[right_index],
                            self.containment_tolerance,
                        ):
                            continue
                        left_point = self.mesh.nodes[left_node]
                        right_point = self.mesh.nodes[current_nodes[right_index]]
                        if not containment_cache.segment_inside(
                            (left_point.x_mm, left_point.y_mm),
                            (right_point.x_mm, right_point.y_mm),
                        ):
                            continue
                        self.add_branch(
                            f"{source_id}:fragment-link:{column}:{row}:{left_index}:{right_index}",
                            "zone",
                            left_node,
                            current_nodes[right_index],
                            cell,
                            thickness,
                            layer,
                            net,
                            source_id,
                        )
                for neighbor_key in ((column + 1, row), (column, row + 1)):
                    neighbor_nodes = grid.get(neighbor_key, [])
                    neighbor_polygons = fragment_polygons.get(neighbor_key, [])
                    for current_index, current in enumerate(current_nodes):
                        for neighbor_index, neighbor in enumerate(neighbor_nodes):
                            if not _polygons_touch(
                                current_polygons[current_index],
                                neighbor_polygons[neighbor_index],
                                self.containment_tolerance,
                            ):
                                continue
                            current_point = self.mesh.nodes[current]
                            neighbor_point = self.mesh.nodes[neighbor]
                            if not containment_cache.segment_inside(
                                (current_point.x_mm, current_point.y_mm),
                                (neighbor_point.x_mm, neighbor_point.y_mm),
                            ):
                                continue
                            self.add_branch(
                                f"{source_id}:link:{column}:{row}:{current_index}:{neighbor_key[0]}:{neighbor_key[1]}:{neighbor_index}",
                                "zone",
                                current,
                                neighbor,
                                cell,
                                thickness,
                                layer,
                                net,
                                source_id,
                            )
            zone_nodes = [node_id for node_ids in grid.values() for node_id in node_ids]
            region = {
                "net": net,
                "layer": layer,
                "polygon": polygon,
                "nodes": zone_nodes,
                "grid": grid,
                "min_x": min_x,
                "min_y": min_y,
                "cell_mm": cell,
                "source_id": source_id,
            }
            self.zone_regions.append(region)
            for node_id in existing:
                node = self.mesh.nodes[node_id]
                if node.layer != layer or node.net != net:
                    continue
                point = (node.x_mm, node.y_mm)
                if not _point_in_polygon(point, polygon, self.containment_tolerance):
                    continue
                nearest = self.local_zone_node(region, point, containment_cache)
                if nearest is None:
                    self.warn_unresolved_zone_attachment(source_id)
                    continue
                self.add_branch(
                    f"{source_id}:attachment:{node_id}",
                    "zone_attachment",
                    node_id,
                    nearest,
                    cell,
                    thickness,
                    layer,
                    net,
                    source_id,
                )
            if cell > self.zone_target * 1.01:
                self.mesh.issues.append(
                    ValidationIssue(
                        "ZONE_MESH_COARSENED",
                        "warning",
                        f"{source_id} used {cell:.4g} mm cells to respect max_zone_cells.",
                        suggestion="Increase max_zone_cells or isolate the net for a convergence run.",
                        status="approximate",
                    )
                )
            self.mesh.geometry_counts["zone"] += 1

    def pads(self) -> None:
        warned_shapes: set[str] = set()
        # Zone coupling is owned by the evidence-gated pad_zone_attachment
        # path below. A second full-pad-width link for each zone centroid
        # inside the pad duplicates that contact and appears/disappears as
        # the zone grid moves under refinement. Track/via nodes still use
        # the generic attachment path.
        zone_nodes = {node for region in self.zone_regions for node in region["nodes"]}
        for index, pad in enumerate(self.design.pads):
            net = _net(pad)
            if not net or (self.requested and net not in self.requested):
                continue
            layers = _pad_layers(pad, self.copper_layers)
            if not layers:
                continue
            width, height = _pad_size(pad)
            shape = str(pad.get("shape", "rect")).lower()
            source_id = str(pad.get("id") or pad.get("component_pad") or f"pad-{index + 1}")
            custom_boundary: List[Point2D] = []
            custom_triangles: List[List[Point2D]] = []
            if shape == "custom":
                custom_boundary = _custom_pad_local_polygon(pad)
                custom_triangles = _triangulate_polygon(custom_boundary)
                if not custom_boundary or (not _pad_has_drill(pad) and not custom_triangles):
                    self.mesh.issues.append(ValidationIssue(
                        "SPIKE-BE-MESH-E-0016",
                        "error",
                        f"Custom pad {source_id} has no admitted resolved polygon/drill geometry.",
                        path=f"design.pads[{source_id}]",
                        suggestion="Use an admitted resolved custom boundary with a centered contained circular/oval plated drill.",
                        status="unsupported",
                    ))
                    continue
            elif shape not in {"rect", "circle", "oval"} and shape not in warned_shapes:
                warned_shapes.add(shape)
                self.mesh.issues.append(ValidationIssue(
                    "SPIKE-BE-MESH-W-0003",
                    "warning",
                    f"Pad shape '{shape}' is meshed using its extracted bounding dimensions.",
                    path=f"design.pads[{pad.get('id') or pad.get('component_pad') or index + 1}]",
                    suggestion="Inspect the mesh preview and run convergence; custom pad primitives require a future polygonal-pad importer.",
                    status="approximate",
                ))
            center = _point(pad.get("at", (0, 0)))
            drilled = _pad_has_drill(pad)
            drill_width, drill_height = _pad_drill_size(pad)
            if drilled and (drill_width >= width or drill_height >= height):
                self.mesh.issues.append(ValidationIssue(
                    "SPIKE-BE-MESH-E-0002",
                    "error",
                    f"Pad {source_id} drill {drill_width:g} x {drill_height:g} mm is not smaller than its {width:g} x {height:g} mm copper land.",
                    path=f"design.pads[{source_id}]",
                    suggestion="Correct the source pad/drill dimensions before solving.",
                    status="unsupported",
                ))
                continue
            if shape == "custom" and drilled:
                plating = max(
                    float(pad.get(
                        "plating_thickness",
                        self.spec.mesh.get("via_plating_thickness_mm", DEFAULT_VIA_PLATING_MM),
                    )),
                    0.005,
                )
                drill_envelope = _circumscribed_shape_polygon(
                    _pad_drill_shape(pad),
                    drill_width + 2 * (plating + self.containment_tolerance),
                    drill_height + 2 * (plating + self.containment_tolerance),
                    96,
                )
                if (not _pad_is_plated(pad)
                        or not _polygon_is_contained_in(
                            drill_envelope, custom_boundary, self.containment_tolerance,
                        )):
                    self.mesh.issues.append(ValidationIssue(
                        "SPIKE-BE-MESH-E-0016", "error",
                        f"Custom pad {source_id} drill/plating envelope is not admitted inside source copper.",
                        path=f"design.pads[{source_id}]",
                        suggestion="Use a centered plated circle/oval drill with positive copper web to the resolved boundary.",
                        status="unsupported",
                    ))
                    continue
            if shape == "custom":
                local_boundary = custom_boundary
            elif shape in {"circle", "oval"}:
                side_count = max(24, min(96, int(ceil(pi * max(width, height) / max(self.target, 0.01)))))
                local_boundary = [
                    (
                        _shape_ray_radius(shape, width, height, 2 * pi * side / side_count)
                        * cos(2 * pi * side / side_count),
                        _shape_ray_radius(shape, width, height, 2 * pi * side / side_count)
                        * sin(2 * pi * side / side_count),
                    )
                    for side in range(side_count)
                ]
            else:
                local_boundary = [
                    (-width / 2, -height / 2),
                    (width / 2, -height / 2),
                    (width / 2, height / 2),
                    (-width / 2, height / 2),
                ]
            annular_cells: List[List[Point2D]] = []
            annular_indices: List[tuple[int, int]] = []
            if drilled:
                annular_cells, annular_indices = _annular_pad_local_cells(
                    pad, self.target, self.max_pad_cells if shape == "custom" else None,
                )
                if not annular_cells:
                    self.mesh.issues.append(ValidationIssue(
                        "SPIKE-BE-MESH-E-0016" if shape == "custom" else "SPIKE-BE-MESH-E-0002",
                        "error",
                        f"Pad {source_id} drill subtraction could not form a contained annular mesh.",
                        path=f"design.pads[{source_id}]",
                        suggestion="Use a centered contained circle/oval drill within mesh resource limits.",
                        status="unsupported",
                    ))
                    continue
            layer_anchors: List[int] = []
            anchor_layers: List[str] = []
            for layer in layers:
                existing = list(self.nodes_by_layer_net.get((layer, net), []))
                thickness = self.thickness.get(layer, DEFAULT_COPPER_THICKNESS_MM)
                grid: Dict[Tuple[int, int], int] = {}
                z = self.layer_z.get(layer, 0.0)
                if drilled:
                    for local_corners, (radial, side) in zip(annular_cells, annular_indices):
                        local = _interior_polygon_point(local_corners)
                        if local is None:
                            continue
                        point = _pad_local_to_world(pad, *local)
                        node_id = self.node(point, layer, net)
                        grid[(side, radial)] = node_id
                        corners = [_pad_local_to_world(pad, x, y) for x, y in local_corners]
                        self.add_cell(
                            f"{source_id}:{layer}:annulus:{radial}:{side}",
                            "pad",
                            source_id,
                            layer,
                            net,
                            [(x, y, z) for x, y in corners],
                            metadata={"node_id": node_id},
                        )
                    if grid:
                        side_count = max(side for side, _ in grid) + 1
                        radial_count = max(radial for _, radial in grid) + 1
                        for (side, radial), current in grid.items():
                            for neighbor_key in (
                                ((side + 1) % side_count, radial),
                                (side, radial + 1),
                            ):
                                neighbor = grid.get(neighbor_key)
                                if neighbor is not None:
                                    self.add_branch(
                                        f"{source_id}:{layer}:annular-link:{side}:{radial}:{neighbor_key[0]}:{neighbor_key[1]}",
                                        "pad",
                                        current,
                                        neighbor,
                                        max(min(width, height) / side_count, 0.01),
                                        thickness,
                                        layer,
                                        net,
                                        source_id,
                                    )
                        anchor = grid[min(grid, key=lambda key: (key[1], key[0]))]
                        layer_anchors.append(anchor)
                        anchor_layers.append(layer)
                    pad_nodes = list(grid.values())
                else:
                    if shape == "custom":
                        min_x = min(point[0] for point in local_boundary)
                        max_x = max(point[0] for point in local_boundary)
                        min_y = min(point[1] for point in local_boundary)
                        max_y = max(point[1] for point in local_boundary)
                        span_x, span_y = max_x - min_x, max_y - min_y
                        columns = max(1, int(ceil(span_x / self.target)))
                        rows = max(1, int(ceil(span_y / self.target)))
                        if columns * rows > self.max_pad_cells:
                            scale = sqrt(self.max_pad_cells / (columns * rows))
                            columns = max(1, int(columns * scale))
                            rows = max(1, int(rows * scale))
                            while columns * rows > self.max_pad_cells:
                                if columns >= rows and columns > 1:
                                    columns -= 1
                                elif rows > 1:
                                    rows -= 1
                                else:
                                    break
                            self.mesh.issues.append(ValidationIssue(
                                "CUSTOM_PAD_MESH_COARSENED",
                                "warning",
                                f"{source_id} used a bounded {columns} x {rows} custom-pad grid.",
                                path=f"design.pads[{source_id}]",
                                suggestion="Increase max_pad_cells only within the admitted resource budget and rerun convergence.",
                                status="approximate",
                            ))
                        dx, dy = span_x / columns, span_y / rows
                        custom_grid: Dict[Tuple[int, int], List[int]] = {}
                        fragment_polygons: Dict[Tuple[int, int], List[List[Point2D]]] = {}
                        for row in range(rows):
                            for column in range(columns):
                                x0, y0 = min_x + column * dx, min_y + row * dy
                                fragments = _clip_polygon_to_rect_fragments(
                                    local_boundary,
                                    custom_triangles,
                                    x0,
                                    y0,
                                    min(x0 + dx, max_x),
                                    min(y0 + dy, max_y),
                                    self.containment_tolerance,
                                )
                                for fragment_index, clipped_local in enumerate(fragments):
                                    if _polygon_area(clipped_local) <= max(1e-12, dx * dy * 1e-10):
                                        continue
                                    local = _interior_polygon_point(clipped_local)
                                    if local is None:
                                        continue
                                    point = _pad_local_to_world(pad, *local)
                                    key = (column, row)
                                    node_id = self.zone_node(point, layer, net)
                                    custom_grid.setdefault(key, []).append(node_id)
                                    fragment_polygons.setdefault(key, []).append(clipped_local)
                                    corners = [_pad_local_to_world(pad, x, y) for x, y in clipped_local]
                                    self.add_cell(
                                        f"{source_id}:{layer}:cell:{column}:{row}:fragment:{fragment_index}",
                                        "pad",
                                        source_id,
                                        layer,
                                        net,
                                        [(x, y, z) for x, y in corners],
                                        metadata={"node_id": node_id},
                                    )
                        for (column, row), current_nodes in custom_grid.items():
                            current_polygons = fragment_polygons[(column, row)]
                            candidates = [((column, row), current_nodes, current_polygons)]
                            for neighbor_key in ((column + 1, row), (column, row + 1)):
                                candidates.append((
                                    neighbor_key,
                                    custom_grid.get(neighbor_key, []),
                                    fragment_polygons.get(neighbor_key, []),
                                ))
                            for neighbor_key, neighbor_nodes, neighbor_polygons in candidates:
                                for current_index, current in enumerate(current_nodes):
                                    start_index = current_index + 1 if neighbor_key == (column, row) else 0
                                    for neighbor_index in range(start_index, len(neighbor_nodes)):
                                        if not _polygons_touch(
                                            current_polygons[current_index],
                                            neighbor_polygons[neighbor_index],
                                            self.containment_tolerance,
                                        ):
                                            continue
                                        neighbor = neighbor_nodes[neighbor_index]
                                        current_point = self.mesh.nodes[current]
                                        neighbor_point = self.mesh.nodes[neighbor]
                                        if not _segment_inside_polygon(
                                            (current_point.x_mm, current_point.y_mm),
                                            (neighbor_point.x_mm, neighbor_point.y_mm),
                                            [_pad_local_to_world(pad, x, y) for x, y in local_boundary],
                                            self.containment_tolerance,
                                        ):
                                            continue
                                        self.add_branch(
                                            f"{source_id}:{layer}:link:{column}:{row}:{current_index}:{neighbor_key[0]}:{neighbor_key[1]}:{neighbor_index}",
                                            "pad",
                                            current,
                                            neighbor,
                                            max(min(dx, dy), 0.01),
                                            thickness,
                                            layer,
                                            net,
                                            source_id,
                                        )
                        pad_nodes = [node for nodes in custom_grid.values() for node in nodes]
                        if not pad_nodes:
                            self.mesh.issues.append(ValidationIssue(
                                "SPIKE-BE-MESH-E-0016",
                                "error",
                                f"Custom pad {source_id} produced no contained mesh cells on {layer}.",
                                path=f"design.pads[{source_id}]",
                                suggestion="Repair the custom polygon or adjust the bounded mesh policy.",
                                status="unsupported",
                            ))
                            continue
                        anchor = min(
                            pad_nodes,
                            key=lambda candidate: hypot(
                                center[0] - self.mesh.nodes[candidate].x_mm,
                                center[1] - self.mesh.nodes[candidate].y_mm,
                            ),
                        )
                        layer_anchors.append(anchor)
                        anchor_layers.append(layer)
                    else:
                        cell = min(self.target, width, height)
                        columns, rows = max(1, int(ceil(width / cell))), max(1, int(ceil(height / cell)))
                        dx, dy = width / columns, height / rows
                        for row in range(rows):
                            for column in range(columns):
                                x0 = -width / 2 + column * dx
                                y0 = -height / 2 + row * dy
                                clipped_local = _clip_polygon_to_rect(
                                    local_boundary, x0, y0, x0 + dx, y0 + dy,
                                    self.containment_tolerance,
                                )
                                if len(clipped_local) < 3 or _polygon_area(clipped_local) <= 1e-12:
                                    continue
                                local = _interior_polygon_point(clipped_local)
                                if local is None:
                                    continue
                                point = _pad_local_to_world(pad, *local)
                                node_id = self.node(point, layer, net)
                                grid[(column, row)] = node_id
                                corners = [_pad_local_to_world(pad, x, y) for x, y in clipped_local]
                                self.add_cell(
                                    f"{source_id}:{layer}:cell:{column}:{row}", "pad", source_id,
                                    layer, net, [(x, y, z) for x, y in corners],
                                    metadata={"node_id": node_id},
                                )
                        for (column, row), current in grid.items():
                            for neighbor_key, branch_width in (
                                ((column + 1, row), dy), ((column, row + 1), dx),
                            ):
                                neighbor = grid.get(neighbor_key)
                                if neighbor is not None:
                                    self.add_branch(
                                        f"{source_id}:{layer}:link:{column}:{row}:{neighbor_key[0]}:{neighbor_key[1]}",
                                        "pad", current, neighbor, branch_width, thickness, layer, net, source_id,
                                    )
                        center_node = self.node(center, layer, net)
                        layer_anchors.append(center_node)
                        anchor_layers.append(layer)
                        pad_nodes = list(grid.values()) or [center_node]
                        nearest_center = min(
                            pad_nodes,
                            key=lambda candidate: hypot(
                                center[0] - self.mesh.nodes[candidate].x_mm,
                                center[1] - self.mesh.nodes[candidate].y_mm,
                            ),
                        )
                        self.add_branch(
                            f"{source_id}:{layer}:center", "pad_attachment", center_node,
                            nearest_center, min(width, height), thickness, layer, net, source_id,
                        )
                if not pad_nodes:
                    continue
                for node_id in existing:
                    if node_id in zone_nodes:
                        continue
                    node = self.mesh.nodes[node_id]
                    if node.layer != layer or node.net != net or not _point_in_pad((node.x_mm, node.y_mm), pad):
                        continue
                    nearest = min(
                        pad_nodes,
                        key=lambda candidate: hypot(
                            node.x_mm - self.mesh.nodes[candidate].x_mm,
                            node.y_mm - self.mesh.nodes[candidate].y_mm,
                        ),
                    )
                    self.add_branch(
                        f"{source_id}:{layer}:attachment:{node_id}",
                        "pad_attachment",
                        node_id,
                        nearest,
                        min(width, height),
                        thickness,
                        layer,
                        net,
                        source_id,
                    )
                for region in self.zone_regions:
                    if region["net"] != net or region["layer"] != layer:
                        continue
                    evidence_id = self.zone_pad_attachment_evidence.get(
                        (source_id, str(region["source_id"]), layer), ""
                    )
                    if self.zone_pad_evidence_required and not evidence_id:
                        continue
                    polygon = region["polygon"]
                    overlap_points = _pad_polygon_overlap_points(
                        pad,
                        polygon,
                        self.containment_tolerance,
                    )
                    overlaps = bool(overlap_points)
                    if not overlaps:
                        overlaps = any(
                            _point_in_pad(
                                (self.mesh.nodes[node_id].x_mm, self.mesh.nodes[node_id].y_mm),
                                pad,
                            )
                            for node_id in region["nodes"]
                        )
                    if not overlaps:
                        continue
                    candidates = []
                    for overlap_point in overlap_points:
                        zone_node = self.local_zone_node(region, overlap_point)
                        if zone_node is None:
                            continue
                        pad_node = min(
                            pad_nodes,
                            key=lambda candidate: hypot(
                                overlap_point[0] - self.mesh.nodes[candidate].x_mm,
                                overlap_point[1] - self.mesh.nodes[candidate].y_mm,
                            ),
                        )
                        candidates.append((pad_node, zone_node))
                    if not candidates:
                        self.warn_unresolved_zone_attachment(str(region["source_id"]))
                        continue
                    pad_node, zone_node = min(
                        candidates,
                        key=lambda pair: hypot(
                            self.mesh.nodes[pair[0]].x_mm - self.mesh.nodes[pair[1]].x_mm,
                            self.mesh.nodes[pair[0]].y_mm - self.mesh.nodes[pair[1]].y_mm,
                        ),
                    )
                    self.add_branch(
                        f"{source_id}:{layer}:zone:{region['source_id']}",
                        "pad_zone_attachment",
                        pad_node,
                        zone_node,
                        min(width, height, float(region["cell_mm"])),
                        thickness,
                        layer,
                        net,
                        source_id,
                        evidence_id=evidence_id,
                    )
            if len(layer_anchors) > 1 and drilled and _pad_is_plated(pad):
                drill = max(sqrt(drill_width * drill_height), 0.01)
                plating = max(
                    float(
                        pad.get(
                            "plating_thickness",
                            self.spec.mesh.get("via_plating_thickness_mm", DEFAULT_VIA_PLATING_MM),
                        )
                    ),
                    0.005,
                )
                barrel_width = pi * (drill + plating)
                drill_shape = _pad_drill_shape(pad)
                barrel_sides = max(
                    24,
                    min(384, int(ceil(pi * max(drill_width, drill_height) / max(self.target, 0.01)))),
                )
                inner_local = _circumscribed_shape_polygon(
                    drill_shape, drill_width, drill_height, barrel_sides
                )
                outer_width = drill_width + 2 * plating
                outer_height = drill_height + 2 * plating
                outer_local: List[Point2D] = []
                while True:
                    outer_local = []
                    for inner_point in inner_local:
                        angle = atan2(inner_point[1], inner_point[0])
                        radius = _shape_ray_radius(drill_shape, outer_width, outer_height, angle)
                        outer_local.append((radius * cos(angle), radius * sin(angle)))
                    if all(
                        hypot(*outer) > hypot(*inner) + 1e-12
                        for outer, inner in zip(outer_local, inner_local)
                    ):
                        break
                    if barrel_sides >= 384:
                        raise ValueError(
                            f"Pad {source_id} plating is too thin for a bounded barrel discretization."
                        )
                    barrel_sides = min(384, barrel_sides * 2)
                    inner_local = _circumscribed_shape_polygon(
                        drill_shape, drill_width, drill_height, barrel_sides
                    )

                for span, (a, b, layer_a, layer_b) in enumerate(zip(
                    layer_anchors,
                    layer_anchors[1:],
                    anchor_layers,
                    anchor_layers[1:],
                )):
                    span_layer = f"{layer_a}->{layer_b}"
                    self.add_branch(
                        f"{source_id}:barrel:{span + 1}",
                        "pad_barrel",
                        a,
                        b,
                        barrel_width,
                        plating,
                        span_layer,
                        net,
                        source_id,
                    )
                    top = self.mesh.nodes[a].z_mm
                    bottom = self.mesh.nodes[b].z_mm
                    for side in range(barrel_sides):
                        next_side = (side + 1) % barrel_sides
                        outer_a = _pad_local_to_world(pad, *outer_local[side])
                        outer_b = _pad_local_to_world(pad, *outer_local[next_side])
                        inner_a = _pad_local_to_world(pad, *inner_local[side])
                        inner_b = _pad_local_to_world(pad, *inner_local[next_side])
                        self.add_cell(
                            f"{source_id}:barrel:{span + 1}:face:{side + 1}",
                            "pad_barrel",
                            source_id,
                            span_layer,
                            net,
                            [
                                (outer_a[0], outer_a[1], top),
                                (outer_b[0], outer_b[1], top),
                                (outer_b[0], outer_b[1], bottom),
                                (outer_a[0], outer_a[1], bottom),
                            ],
                            metadata={
                                "inner_vertices_mm": [
                                    [inner_a[0], inner_a[1], top],
                                    [inner_b[0], inner_b[1], top],
                                    [inner_b[0], inner_b[1], bottom],
                                    [inner_a[0], inner_a[1], bottom],
                                ],
                                "plating_thickness_mm": plating,
                                "drill_shape": drill_shape,
                            },
                        )
            self.mesh.geometry_counts["pad"] += 1

    def build(self) -> HybridMesh:
        self.tracks()
        self.vias()
        self.zones()
        self.pads()
        if self.mesh.truncated:
            memory_limited = bool(self.branch_admission.get("limited_by_memory"))
            self.mesh.issues.append(
                ValidationIssue(
                    "HYBRID_MESH_MEMORY_LIMIT" if memory_limited else "HYBRID_MESH_BRANCH_LIMIT",
                    "error",
                    (
                        f"Hybrid mesh exceeded the RAM-admitted {self.max_branches} branch capacity."
                        if memory_limited
                        else f"Hybrid mesh exceeded the configured {self.max_branches} branch limit."
                    ),
                    suggestion=(
                        "Increase the solver memory limit only when system RAM permits, coarsen the mesh, or isolate fewer nets."
                        if memory_limited
                        else "Increase target_size_mm, isolate fewer nets, or raise max_conductors within the admitted RAM capacity."
                    ),
                    status="failed",
                )
            )
        return self.mesh


def build_hybrid_mesh(design: DesignIR, spec: AnalysisSpec) -> HybridMesh:
    """Build one connected conductor topology for preview and solver adapters."""

    return _Builder(design, spec).build()


def nearest_mesh_node(
    mesh: HybridMesh,
    terminal: Dict[str, Any],
    net: str = "",
    default_snap_mm: float = 2.0,
) -> int | None:
    raw = terminal.get("position_mm") or terminal.get("at")
    if raw is None:
        return None
    point = _point(raw)
    layer = str(terminal.get("layer", ""))
    layer_scope = str(terminal.get("layer_scope", "single" if layer else "connected_conductor"))
    candidate_layers = {
        str(value) for value in terminal.get("layer_candidates", []) if str(value)
    }
    if layer_scope == "single" and layer:
        candidate_layers = {layer}
    snap = max(float(terminal.get("snap_distance_mm", default_snap_mm)), 0.001)
    anchor = terminal.get("geometry_anchor")
    anchor_id = str(anchor.get("id", "")) if isinstance(anchor, dict) else str(terminal.get("geometry_anchor_id", ""))
    anchored_nodes = {
        node_id
        for branch in mesh.branches
        if anchor_id and branch.source_id == anchor_id
        for node_id in (branch.node_p, branch.node_n)
    }
    candidates = [
        node
        for node in mesh.nodes
        if (not net or node.net == net)
        and (not candidate_layers or node.layer in candidate_layers)
        and (not anchored_nodes or node.id in anchored_nodes)
    ]
    if not candidates and anchored_nodes:
        candidates = [
            node for node in mesh.nodes
            if (not net or node.net == net) and node.id in anchored_nodes
        ]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda node: hypot(point[0] - node.x_mm, point[1] - node.y_mm))
    distance = hypot(point[0] - nearest.x_mm, point[1] - nearest.y_mm)
    return nearest.id if distance <= snap else None
