"""Deterministic, bounded flattening of DesignIR zone line/arc boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

from .design_ir_v2_schema import content_digest


GRID_MM = 0.000001
MAXIMUM_SAGITTA_MM = 0.001
MAXIMUM_SEGMENT_LENGTH_MM = 0.25
MAXIMUM_SEGMENTS_PER_ARC = 4096
MAXIMUM_POINTS_PER_RING = 8192
MAXIMUM_TOTAL_POINTS = 16384
MAXIMUM_GRID_COORDINATE = 1_000_000_000
GRID_SNAP_BOUND_MM = math.sqrt(2.0) * GRID_MM / 2.0
ROUNDING_GUARD_GRID_UNITS = 0.000001


class PlanarCurveTessellationError(ValueError):
    pass


@dataclass(frozen=True)
class FlattenedZoneBoundaries:
    outer_ring_mm: list[list[float]]
    cutout_rings_mm: list[list[list[float]]]
    source_boundary_sha256: str
    source_arc_count: int
    flattened_segment_count: int
    maximum_certified_curve_deviation_mm: float
    arc_tessellations: list[dict[str, Any]]


def policy_payload() -> dict[str, Any]:
    return {
        "coordinate_grid_mm": GRID_MM,
        "curve_admission": "bounded_design_ir_line_and_circular_arc",
        "arc_subdivision": "indexed_equal_angle_sagitta_and_length_bounded",
        "maximum_sagitta_mm": MAXIMUM_SAGITTA_MM,
        "maximum_segment_length_mm": MAXIMUM_SEGMENT_LENGTH_MM,
        "maximum_segments_per_arc": MAXIMUM_SEGMENTS_PER_ARC,
        "maximum_points_per_ring": MAXIMUM_POINTS_PER_RING,
        "maximum_total_points": MAXIMUM_TOTAL_POINTS,
        "grid_snap_bound_mm": GRID_SNAP_BOUND_MM,
        "rounding_guard_grid_units": ROUNDING_GUARD_GRID_UNITS,
    }


def _grid_point(values: Sequence[float], label: str) -> tuple[int, int]:
    if len(values) != 2 or not all(math.isfinite(float(value)) for value in values):
        raise PlanarCurveTessellationError(f"{label} must be a finite two-dimensional point.")
    result = tuple(int(round(float(value) / GRID_MM)) for value in values)
    if any(abs(float(values[index]) / GRID_MM - result[index]) > 1e-6 for index in (0, 1)):
        raise PlanarCurveTessellationError(f"{label} must lie on the declared coordinate grid.")
    if any(abs(value) > MAXIMUM_GRID_COORDINATE for value in result):
        raise PlanarCurveTessellationError(f"{label} exceeds the bounded coordinate domain.")
    return result  # type: ignore[return-value]


def _point_mm(point: tuple[int, int]) -> list[float]:
    return [point[0] * GRID_MM, point[1] * GRID_MM]


def _guarded_grid_round(value: float) -> int:
    fraction = value - math.floor(value)
    if abs(fraction - 0.5) <= ROUNDING_GUARD_GRID_UNITS:
        raise PlanarCurveTessellationError(
            "Arc sample is too close to a coordinate-grid rounding decision boundary."
        )
    return int(round(value))


def _source_payload(rings: Sequence[Any]) -> list[dict[str, Any]]:
    payload = []
    for ring in rings:
        segments = []
        for segment in ring.segments:
            item: dict[str, Any] = {"kind": segment.kind, "end_mm": list(segment.end_mm)}
            if segment.kind == "arc":
                item.update({"center_mm": list(segment.center_mm), "clockwise": segment.clockwise})
            segments.append(item)
        payload.append({"role": ring.role, "start_mm": list(ring.start_mm), "segments": segments})
    return payload


def _legacy_payload(outlines: Sequence[Sequence[Sequence[float]]],
                    holes: Sequence[Sequence[Sequence[float]]]) -> list[dict[str, Any]]:
    result = []
    for role, ring in [("outer", outlines[0]), *(("cutout", item) for item in holes)]:
        points = [_grid_point(item, f"{role} boundary point") for item in ring]
        if len(points) < 3:
            raise PlanarCurveTessellationError("Zone boundary rings require at least three points.")
        segments = [{"kind": "line", "end_mm": _point_mm(points[(index + 1) % len(points)])}
                    for index in range(len(points))]
        result.append({"role": role, "start_mm": _point_mm(points[0]), "segments": segments})
    return result


def _arc_sweep(start: tuple[int, int], end: tuple[int, int], center: tuple[int, int],
               clockwise: bool) -> tuple[float, float, float]:
    sx, sy = (start[0] - center[0]) * GRID_MM, (start[1] - center[1]) * GRID_MM
    ex, ey = (end[0] - center[0]) * GRID_MM, (end[1] - center[1]) * GRID_MM
    radius, end_radius = math.hypot(sx, sy), math.hypot(ex, ey)
    if radius <= 0.0 or not math.isclose(radius, end_radius, rel_tol=1e-12, abs_tol=GRID_MM * 1e-6):
        raise PlanarCurveTessellationError("Arc endpoints require equal positive radii on the grid.")
    start_angle, end_angle = math.atan2(sy, sx), math.atan2(ey, ex)
    sweep = ((start_angle - end_angle) if clockwise else (end_angle - start_angle)) % (2.0 * math.pi)
    if sweep <= 1e-15:
        raise PlanarCurveTessellationError("Full-circle and zero-sweep single arc segments are not admitted.")
    return radius, start_angle, -sweep if clockwise else sweep


def _flatten_arc(start: tuple[int, int], end: tuple[int, int], center: tuple[int, int],
                 clockwise: bool) -> tuple[list[tuple[int, int]], float, float]:
    radius, start_angle, signed_sweep = _arc_sweep(start, end, center, clockwise)
    usable_sagitta = MAXIMUM_SAGITTA_MM - GRID_SNAP_BOUND_MM
    if usable_sagitta <= 0.0:
        raise PlanarCurveTessellationError("The curve tolerance does not cover coordinate-grid snapping.")
    if usable_sagitta >= radius:
        sagitta_count = 1
    else:
        maximum_angle = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - usable_sagitta / radius)))
        sagitta_count = math.ceil(abs(signed_sweep) / maximum_angle)
    length_count = math.ceil(radius * abs(signed_sweep) / MAXIMUM_SEGMENT_LENGTH_MM)
    count = max(1, sagitta_count, length_count)
    while count <= MAXIMUM_SEGMENTS_PER_ARC:
        points: list[tuple[int, int]] = []
        for index in range(1, count + 1):
            if index == count:
                point = end
            else:
                angle = start_angle + signed_sweep * index / count
                point = (
                    _guarded_grid_round(center[0] + radius * math.cos(angle) / GRID_MM),
                    _guarded_grid_round(center[1] + radius * math.sin(angle) / GRID_MM),
                )
            if point == (points[-1] if points else start):
                break
            points.append(point)
        if len(points) == count:
            maximum_length = max(math.hypot((second[0] - first[0]) * GRID_MM,
                                            (second[1] - first[1]) * GRID_MM)
                                 for first, second in zip([start, *points[:-1]], points))
            nominal_sagitta = radius * (1.0 - math.cos(abs(signed_sweep) / (2.0 * count)))
            certified_deviation = nominal_sagitta + GRID_SNAP_BOUND_MM
            if maximum_length <= MAXIMUM_SEGMENT_LENGTH_MM and certified_deviation <= MAXIMUM_SAGITTA_MM:
                return points, certified_deviation, math.degrees(signed_sweep)
        count += 1
    raise PlanarCurveTessellationError("Arc subdivision exceeds the declared segment budget.")


def flatten_zone_boundaries(zone: Any) -> FlattenedZoneBoundaries:
    if zone.boundary_rings:
        rings, source = list(zone.boundary_rings), _source_payload(zone.boundary_rings)
    else:
        if len(zone.outlines_mm) != 1:
            raise PlanarCurveTessellationError("Curve topology requires one connected source-zone outer ring.")
        source = _legacy_payload(zone.outlines_mm, zone.holes_mm)
        rings = None

    flattened: list[list[tuple[int, int]]] = []
    source_arc_count = 0
    maximum_deviation = 0.0
    arc_tessellations: list[dict[str, Any]] = []
    total_points = 0
    for ring_index, item in enumerate(source):
        role = item["role"]
        if role != ("outer" if ring_index == 0 else "cutout"):
            raise PlanarCurveTessellationError("Zone boundaries require one outer ring followed by cutouts.")
        start = _grid_point(item["start_mm"], f"{role} boundary start")
        points = [start]
        current = start
        for segment_index, segment in enumerate(item["segments"]):
            end = _grid_point(segment["end_mm"], f"{role} segment endpoint")
            if segment["kind"] == "line":
                additions, deviation = [end], 0.0
            elif segment["kind"] == "arc":
                center = _grid_point(segment["center_mm"], f"{role} arc center")
                additions, deviation, sweep_degrees = _flatten_arc(
                    current, end, center, bool(segment["clockwise"])
                )
                arc_tessellations.append({
                    "ring_index": ring_index,
                    "segment_index": segment_index,
                    "emitted_segment_count": len(additions),
                    "directed_sweep_deg": sweep_degrees,
                    "maximum_certified_deviation_mm": deviation,
                })
                source_arc_count += 1
            else:
                raise PlanarCurveTessellationError("Unsupported zone boundary segment kind.")
            if additions[0] == current:
                raise PlanarCurveTessellationError("Curve tessellation collapsed a boundary segment on the grid.")
            points.extend(additions)
            maximum_deviation = max(maximum_deviation, deviation)
            current = end
        if current != start:
            raise PlanarCurveTessellationError("Zone boundary ring is not closed on the declared grid.")
        points.pop()
        if len(points) < 3 or len(points) > MAXIMUM_POINTS_PER_RING or len(set(points)) != len(points):
            raise PlanarCurveTessellationError("Flattened ring is degenerate or exceeds its point budget.")
        total_points += len(points)
        if total_points > MAXIMUM_TOTAL_POINTS:
            raise PlanarCurveTessellationError("Flattened zone exceeds the total point budget.")
        flattened.append(points)

    return FlattenedZoneBoundaries(
        outer_ring_mm=[_point_mm(item) for item in flattened[0]],
        cutout_rings_mm=[[_point_mm(point) for point in ring] for ring in flattened[1:]],
        source_boundary_sha256=content_digest(source),
        source_arc_count=source_arc_count,
        flattened_segment_count=total_points,
        maximum_certified_curve_deviation_mm=maximum_deviation,
        arc_tessellations=arc_tessellations,
    )


__all__ = [
    "GRID_MM", "MAXIMUM_POINTS_PER_RING", "MAXIMUM_SEGMENTS_PER_ARC", "MAXIMUM_TOTAL_POINTS",
    "PlanarCurveTessellationError", "FlattenedZoneBoundaries", "flatten_zone_boundaries", "policy_payload",
]
