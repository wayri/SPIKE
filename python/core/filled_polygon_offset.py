"""Bounded clean-room round offset for one filled simple polygon.

The routine implements the geometric definition directly: a filled polygon
with a centered outline of width ``w`` has the outer boundary of the polygon
dilated by a disk of radius ``w / 2``.  Straight edge offsets are exact on the
declared grid; convex round joins use inscribed equal-angle chords; concave
joins use the adjacent shifted-line intersection.  Ambiguous topology fails
closed instead of invoking a generic repair operation.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable, Sequence

from .simple_polygon_union import is_simple_polygon


def _canonical_ring(points: Iterable[Sequence[float]]) -> list[tuple[float, float]]:
    ring = [(float(point[0]), float(point[1])) for point in points]
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    if len(set(ring)) != len(ring):
        return []
    area = sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(ring, [*ring[1:], ring[0]])
    ) if ring else 0.0
    if area < 0:
        ring.reverse()
    if ring:
        start = min(range(len(ring)), key=lambda index: ring[index])
        ring = ring[start:] + ring[:start]
    return ring


def _line_intersection(
    first_point: tuple[float, float], first_direction: tuple[float, float],
    second_point: tuple[float, float], second_direction: tuple[float, float],
) -> tuple[float, float] | None:
    denominator = (
        first_direction[0] * second_direction[1]
        - first_direction[1] * second_direction[0]
    )
    scale = max(*(abs(value) for value in (*first_direction, *second_direction)), 1.0)
    if abs(denominator) <= 1e-14 * scale * scale:
        return None
    dx = second_point[0] - first_point[0]
    dy = second_point[1] - first_point[1]
    parameter = (dx * second_direction[1] - dy * second_direction[0]) / denominator
    return (
        first_point[0] + parameter * first_direction[0],
        first_point[1] + parameter * first_direction[1],
    )


def inflate_filled_simple_polygon_round_inside_v1(
    points: Iterable[Sequence[float]], stroke_width_mm: float, *,
    maximum_radial_error_mm: float = 0.001,
    quantization_grid_mm: float = 1e-8,
    max_input_vertices: int = 128,
    max_output_vertices: int = 4096,
) -> tuple[list[list[float]], dict]:
    """Return a deterministic inner approximation of a round polygon offset.

    An empty polygon and evidence object indicate fail-closed rejection.
    """

    try:
        width = float(stroke_width_mm)
        raw = [(float(point[0]), float(point[1])) for point in points]
    except (TypeError, ValueError, IndexError):
        return [], {}
    if (not math.isfinite(width) or width <= 0 or width > 2_000
            or not math.isfinite(maximum_radial_error_mm)
            or not 0 < maximum_radial_error_mm <= 0.001
            or quantization_grid_mm != 1e-8):
        return [], {}
    if any(not math.isfinite(value) or abs(value) > 1_000_000 for point in raw for value in point):
        return [], {}
    ring = _canonical_ring(raw)
    if not 3 <= len(ring) <= max_input_vertices or not is_simple_polygon(ring):
        return [], {}

    radius = width / 2.0
    rounding_bound = quantization_grid_mm / math.sqrt(2.0)
    effective_radius = radius - rounding_bound
    if effective_radius <= 0:
        return [], {}

    def quantize(point: tuple[float, float]) -> list[float]:
        return [round(point[0], 8), round(point[1], 8)]

    edges: list[tuple[float, float]] = []
    normals: list[tuple[float, float]] = []
    for start, end in zip(ring, [*ring[1:], ring[0]]):
        edge = (end[0] - start[0], end[1] - start[1])
        length = math.hypot(*edge)
        if length <= quantization_grid_mm:
            return [], {}
        edges.append(edge)
        normals.append((edge[1] / length, -edge[0] / length))

    output: list[list[float]] = []
    generated_segments = 0
    worst_bound = 2.0 * rounding_bound
    for index, vertex in enumerate(ring):
        previous_edge = edges[index - 1]
        next_edge = edges[index]
        previous_normal = normals[index - 1]
        next_normal = normals[index]
        turn = previous_edge[0] * next_edge[1] - previous_edge[1] * next_edge[0]
        turn_scale = max(math.hypot(*previous_edge) * math.hypot(*next_edge), 1.0)
        tolerance = 1e-14 * turn_scale
        if turn > tolerance:
            start_angle = math.atan2(previous_normal[1], previous_normal[0])
            end_angle = math.atan2(next_normal[1], next_normal[0])
            sweep = (end_angle - start_angle) % (2.0 * math.pi)
            if not 0 < sweep < math.pi + 1e-10:
                return [], {}
            count = 1
            while count <= 256:
                bound = radius - effective_radius * math.cos(sweep / (2.0 * count)) + rounding_bound
                if (bound <= maximum_radial_error_mm
                        and effective_radius * sweep / count <= 0.25):
                    break
                count += 1
            if count > 256:
                return [], {}
            for step in range(count + 1):
                angle = start_angle + sweep * step / count
                point = quantize((
                    vertex[0] + effective_radius * math.cos(angle),
                    vertex[1] + effective_radius * math.sin(angle),
                ))
                if not output or point != output[-1]:
                    output.append(point)
            generated_segments += count
            worst_bound = max(worst_bound, bound)
        elif turn < -tolerance:
            previous_point = (
                vertex[0] + effective_radius * previous_normal[0],
                vertex[1] + effective_radius * previous_normal[1],
            )
            next_point = (
                vertex[0] + effective_radius * next_normal[0],
                vertex[1] + effective_radius * next_normal[1],
            )
            intersection = _line_intersection(
                previous_point, previous_edge, next_point, next_edge,
            )
            if intersection is None or math.hypot(
                intersection[0] - vertex[0], intersection[1] - vertex[1],
            ) > 8.0 * radius + quantization_grid_mm:
                return [], {}
            point = quantize(intersection)
            if not output or point != output[-1]:
                output.append(point)
        else:
            dot = previous_edge[0] * next_edge[0] + previous_edge[1] * next_edge[1]
            if dot <= 0:
                return [], {}
            point = quantize((
                vertex[0] + effective_radius * next_normal[0],
                vertex[1] + effective_radius * next_normal[1],
            ))
            if not output or point != output[-1]:
                output.append(point)

        if len(output) > max_output_vertices:
            return [], {}

    if len(output) > 1 and output[0] == output[-1]:
        output.pop()
    if (not 3 <= len(output) <= max_output_vertices
            or any(not math.isfinite(value) or abs(value) > 1_000_000
                   for point in output for value in point)
            or not is_simple_polygon(output)):
        return [], {}
    source_payload = json.dumps(
        {"points": [[x, y] for x, y in ring], "stroke_width_mm": width},
        allow_nan=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    evidence = {
        "method": "inscribed_round_offset_v1",
        "source_primitive_kind": "gr_poly",
        "source_width_mm": width,
        "source_vertex_count": len(ring),
        "source_geometry_sha256": hashlib.sha256(source_payload).hexdigest(),
        "maximum_radial_error_mm": worst_bound,
        "quantization_grid_mm": quantization_grid_mm,
        "flattened_segment_count": generated_segments,
        "round_join": True,
        "closed_path_no_caps": True,
        "conservative_source_containment": True,
    }
    return output, evidence
