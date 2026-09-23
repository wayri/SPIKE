"""Validation for the bounded exact custom-pad geometry contract."""

from __future__ import annotations

import math
from typing import Any, Sequence


def _polygon_is_simple(points: Sequence[tuple[float, float]]) -> bool:
    if not 3 <= len(points) <= 4096:
        return False
    area = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, [*points[1:], points[0]])
    )
    if not math.isfinite(area) or abs(area) <= 1e-18:
        return False

    def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a: tuple[float, float], b: tuple[float, float], point: tuple[float, float]) -> bool:
        scale = max(*(abs(value) for item in (a, b, point) for value in item), 1.0)
        tolerance = 1e-12 * scale * scale
        return (
            abs(orientation(a, b, point)) <= tolerance
            and min(a[0], b[0]) - tolerance <= point[0] <= max(a[0], b[0]) + tolerance
            and min(a[1], b[1]) - tolerance <= point[1] <= max(a[1], b[1]) + tolerance
        )

    def intersects(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
        values = (orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b))
        scale = max(*(abs(value) for item in (a, b, c, d) for value in item), 1.0)
        tolerance = 1e-12 * scale * scale
        if ((values[0] > tolerance and values[1] < -tolerance) or (values[0] < -tolerance and values[1] > tolerance)) \
                and ((values[2] > tolerance and values[3] < -tolerance) or (values[2] < -tolerance and values[3] > tolerance)):
            return True
        return (
            (abs(values[0]) <= tolerance and on_segment(a, b, c))
            or (abs(values[1]) <= tolerance and on_segment(a, b, d))
            or (abs(values[2]) <= tolerance and on_segment(c, d, a))
            or (abs(values[3]) <= tolerance and on_segment(c, d, b))
        )

    edges = list(zip(points, [*points[1:], points[0]]))
    if any(
        (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2 <= 1e-24
        for start, end in edges
    ):
        return False
    for left_index, (left_a, left_b) in enumerate(edges):
        for right_index in range(left_index + 1, len(edges)):
            if right_index == left_index + 1 or (left_index == 0 and right_index == len(edges) - 1):
                continue
            right_a, right_b = edges[right_index]
            if intersects(left_a, left_b, right_a, right_b):
                return False
    return True


def validate_custom_pad_geometries(pads: Sequence[Any]) -> None:
    """Validate the admitted undrilled custom-pad boundary and evidence."""

    for pad in pads:
        geometry = pad.custom_geometry
        if not geometry:
            continue
        if frozenset(geometry) not in {
            frozenset({"status", "coordinate_space", "mirror_x", "positive_filled_polygon"}),
            frozenset({"status", "coordinate_space", "mirror_x", "positive_filled_polygon", "curve_approximation"}),
            frozenset({"status", "coordinate_space", "mirror_x", "positive_filled_polygon", "stroke_approximation"}),
            frozenset({"status", "reason"}),
        }:
            raise ValueError("Custom pad geometry has unsupported fields.")
        status = geometry.get("status")
        if status == "unsupported":
            reason = geometry.get("reason")
            if not isinstance(reason, str) or not reason or len(reason) > 128:
                raise ValueError("Unsupported custom pad geometry requires a bounded reason.")
            continue
        if (status != "supported" or geometry.get("coordinate_space") != "pad_local_mm"
                or not isinstance(geometry.get("mirror_x"), bool)):
            raise ValueError("Custom pad geometry status or coordinate space is invalid.")
        if pad.shape.lower() != "custom":
            raise ValueError("Custom pad geometry requires a custom pad shape.")
        drilled = any(value > 0.0 for value in pad.drill_size_mm)
        if drilled:
            drill_width, drill_height = (float(value) for value in pad.drill_size_mm)
            size_width, size_height = (float(value) for value in pad.size_mm)
            if (not pad.plated or pad.drill_shape not in {"circle", "oval"}
                    or not all(math.isfinite(value) and value > 0.0
                               for value in (drill_width, drill_height))
                    or drill_width >= size_width or drill_height >= size_height
                    or (pad.drill_shape == "circle"
                        and not math.isclose(drill_width, drill_height, rel_tol=0.0, abs_tol=1e-12))):
                raise ValueError(
                    "An admitted drilled custom pad requires one centered contained plated circle or oval."
                )
        curve = geometry.get("curve_approximation")
        if curve is not None:
            if not isinstance(curve, dict) or frozenset(curve) != frozenset({
                "method", "maximum_sagitta_mm", "source_circle_count",
                "flattened_segment_count", "conservative_source_containment",
            }):
                raise ValueError("Custom pad curve approximation fields are invalid.")
            sagitta = float(curve.get("maximum_sagitta_mm", 0.0))
            if (curve.get("method") != "inscribed_equal_angle_v1"
                    or not math.isfinite(sagitta) or not 0.0 < sagitta <= 0.001
                    or not isinstance(curve.get("source_circle_count"), int)
                    or not 1 <= curve["source_circle_count"] <= 16
                    or not isinstance(curve.get("flattened_segment_count"), int)
                    or not 12 <= curve["flattened_segment_count"] <= 4096
                    or curve.get("conservative_source_containment") is not True):
                raise ValueError("Custom pad curve approximation evidence is invalid.")
        stroke = geometry.get("stroke_approximation")
        if stroke is not None:
            required = frozenset({
                "method", "source_primitive_kind", "source_width_mm",
                "source_vertex_count", "source_geometry_sha256",
                "maximum_radial_error_mm", "quantization_grid_mm",
                "flattened_segment_count", "round_join", "closed_path_no_caps",
                "conservative_source_containment",
            })
            if not isinstance(stroke, dict) or frozenset(stroke) != required:
                raise ValueError("Custom pad stroke approximation fields are invalid.")
            width = float(stroke.get("source_width_mm", 0.0))
            error = float(stroke.get("maximum_radial_error_mm", 0.0))
            digest = stroke.get("source_geometry_sha256")
            if (stroke.get("method") != "inscribed_round_offset_v1"
                    or stroke.get("source_primitive_kind") != "gr_poly"
                    or not math.isfinite(width) or not 0.0 < width <= 2_000
                    or not isinstance(stroke.get("source_vertex_count"), int)
                    or not 3 <= stroke["source_vertex_count"] <= 128
                    or not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                    or not math.isfinite(error) or not 0.0 < error <= 0.001
                    or stroke.get("quantization_grid_mm") != 1e-8
                    or not isinstance(stroke.get("flattened_segment_count"), int)
                    or not 1 <= stroke["flattened_segment_count"] <= 4096
                    or stroke.get("round_join") is not True
                    or stroke.get("closed_path_no_caps") is not True
                    or stroke.get("conservative_source_containment") is not True):
                raise ValueError("Custom pad stroke approximation evidence is invalid.")
        raw_points = geometry.get("positive_filled_polygon")
        if not isinstance(raw_points, list):
            raise ValueError("Custom pad geometry requires a positive filled polygon.")
        points: list[tuple[float, float]] = []
        for raw in raw_points:
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ValueError("Custom pad polygon points must be two-dimensional.")
            point_value = (float(raw[0]), float(raw[1]))
            if not all(math.isfinite(value) and abs(value) <= 1_000_000 for value in point_value):
                raise ValueError("Custom pad polygon coordinates are invalid.")
            points.append(point_value)
        if not _polygon_is_simple(points):
            raise ValueError("Custom pad polygon must be finite, simple, and nondegenerate.")
