"""Fail-closed source ownership checks for conductor field meshes."""

from __future__ import annotations

from collections import Counter
from math import hypot, isfinite
from typing import Any, Dict, Iterable, Mapping, Sequence

from .contracts import DesignIR
from .hybrid_mesh import (
    _net,
    _normalize_filled_zone_polygon,
    _custom_pad_local_polygon,
    _pad_drill_shape,
    _pad_layers,
    _pad_drill_size,
    _pad_size,
    _pad_world_to_local,
    _point,
    _point_in_capsule_local,
    _point_in_polygon,
    _polygon_is_contained_in,
    _segment_inside_polygon,
)
from .layers import copper_stack_profile


OWNERSHIP_ERROR = "SPIKE-BE-MESH-E-0001"
SUPPORTED_SOURCE_KINDS = {"track", "zone", "pad", "pad_barrel", "via"}


def _fail(message: str) -> None:
    raise ValueError(f"{OWNERSHIP_ERROR}: {message}")


def _source_map(
    records: Iterable[Dict[str, Any]],
    fallback_prefix: str,
    id_fields: Sequence[str] = ("id",),
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for index, record in enumerate(records):
        source_id = ""
        for field in id_fields:
            source_id = str(record.get(field) or "").strip()
            if source_id:
                break
        source_id = source_id or f"{fallback_prefix}-{index + 1}"
        if source_id in result:
            _fail(f"duplicate {fallback_prefix} source id {source_id!r}")
        result[source_id] = record
    return result


def _face_xy(volume: Mapping[str, Any]) -> list[tuple[float, float]]:
    vertices = volume.get("vertices_mm")
    if not isinstance(vertices, list) or len(vertices) < 6 or len(vertices) % 2:
        _fail(f"volume {volume.get('id', '')!r} has invalid volumetric vertices")
    points: list[tuple[float, float]] = []
    for raw in vertices:
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            _fail(f"volume {volume.get('id', '')!r} has a malformed vertex")
        values = tuple(float(value) for value in raw[:3])
        if not all(isfinite(value) for value in values):
            _fail(f"volume {volume.get('id', '')!r} has a non-finite vertex")
        points.append((values[0], values[1]))
    return points[: len(points) // 2]


def _track_contains(
    face: Sequence[tuple[float, float]],
    track: Mapping[str, Any],
    tolerance_mm: float,
) -> bool:
    start, end = _point(track.get("start", (0, 0))), _point(track.get("end", (0, 0)))
    width = max(float(track.get("width", 0.0)), 0.0)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if width <= 0.0 or length_squared <= 1e-18:
        return False
    radius = width / 2 + tolerance_mm
    for x, y in face:
        ratio = max(0.0, min(1.0, ((x - start[0]) * dx + (y - start[1]) * dy) / length_squared))
        if hypot(x - start[0] - ratio * dx, y - start[1] - ratio * dy) > radius:
            return False
    return True


def _via_spans(design: DesignIR, via: Mapping[str, Any]) -> set[str]:
    copper_layers = copper_stack_profile(design)[0]
    raw_layers = [str(value) for value in via.get("layers", ("F.Cu", "B.Cu"))]
    if len(raw_layers) < 2:
        return set()
    try:
        first = copper_layers.index(raw_layers[0])
        last = copper_layers.index(raw_layers[-1])
        lo, hi = sorted((first, last))
        layers = copper_layers[lo : hi + 1]
    except ValueError:
        layers = raw_layers[:2]
    return {f"{left}->{right}" for left, right in zip(layers, layers[1:])}


def _pad_spans(design: DesignIR, pad: Mapping[str, Any]) -> set[str]:
    copper_layers = copper_stack_profile(design)[0]
    layers = _pad_layers(dict(pad), copper_layers)
    ordered = [layer for layer in copper_layers if layer in layers]
    return {f"{left}->{right}" for left, right in zip(ordered, ordered[1:])}


def _pad_contains(
    face: Sequence[tuple[float, float]],
    pad: Mapping[str, Any],
    tolerance_mm: float,
) -> bool:
    """Check a convex pad face against its authoritative rotated shape."""

    width, height = _pad_size(dict(pad))
    shape = str(pad.get("shape", "rect")).lower()
    half_width = width / 2 + tolerance_mm
    half_height = height / 2 + tolerance_mm
    local_face: list[tuple[float, float]] = []
    for world_x, world_y in face:
        local_x, local_y = _pad_world_to_local(dict(pad), (world_x, world_y))
        local_face.append((local_x, local_y))
        if shape == "custom":
            continue
        if shape == "oval":
            if not _point_in_capsule_local(
                (local_x, local_y), width, height, tolerance_mm
            ):
                return False
        elif shape == "circle":
            if (local_x / half_width) ** 2 + (local_y / half_height) ** 2 > 1.0:
                return False
        elif abs(local_x) > half_width or abs(local_y) > half_height:
            return False
    if shape == "custom":
        polygon = _custom_pad_local_polygon(dict(pad))
        distinct: list[tuple[float, float]] = []
        for point in local_face:
            if not distinct or hypot(point[0] - distinct[-1][0], point[1] - distinct[-1][1]) > 1e-12:
                distinct.append(point)
        if len(distinct) > 1 and hypot(
            distinct[0][0] - distinct[-1][0], distinct[0][1] - distinct[-1][1],
        ) <= 1e-12:
            distinct.pop()
        outer_owned = (
            _polygon_is_contained_in(distinct, polygon, tolerance_mm)
            if len(distinct) >= 3
            else len(distinct) == 2 and _segment_inside_polygon(
                distinct[0], distinct[1], polygon, tolerance_mm,
            )
        )
        if not polygon or not outer_owned:
            return False
    drill_width, drill_height = _pad_drill_size(dict(pad))
    drill_half_width = max(drill_width / 2 - tolerance_mm, 0.0)
    drill_half_height = max(drill_height / 2 - tolerance_mm, 0.0)
    if drill_half_width > 0.0 and drill_half_height > 0.0:
        if _pad_drill_shape(dict(pad)) == "oval":
            shrunk_width, shrunk_height = 2 * drill_half_width, 2 * drill_half_height
            if any(
                _point_in_capsule_local(point, shrunk_width, shrunk_height)
                for point in local_face
            ):
                return False
            if shrunk_width >= shrunk_height:
                half_segment = (shrunk_width - shrunk_height) / 2
                axis_start, axis_end = (-half_segment, 0.0), (half_segment, 0.0)
                radius = shrunk_height / 2
            else:
                half_segment = (shrunk_height - shrunk_width) / 2
                axis_start, axis_end = (0.0, -half_segment), (0.0, half_segment)
                radius = shrunk_width / 2
            for start, end in zip(local_face, local_face[1:] + local_face[:1]):
                if _segment_distance(start, end, axis_start, axis_end) < radius - 1e-9:
                    return False
            if _point_in_polygon((0.0, 0.0), local_face):
                return False
            return bool(face)
        normalized = [
            (x / drill_half_width, y / drill_half_height)
            for x, y in local_face
        ]
        if any(hypot(x, y) < 1.0 - 1e-9 for x, y in normalized):
            return False
        for start, end in zip(normalized, normalized[1:] + normalized[:1]):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length_squared = dx * dx + dy * dy
            ratio = 0.0 if length_squared <= 1e-18 else max(
                0.0,
                min(1.0, -(start[0] * dx + start[1] * dy) / length_squared),
            )
            if hypot(start[0] + ratio * dx, start[1] + ratio * dy) < 1.0 - 1e-9:
                return False
        # Catch a face that surrounds the complete hole without any edge
        # entering it (possible for a coarse convex polygon).
        inside = False
        for start, end in zip(normalized, normalized[1:] + normalized[:1]):
            if (start[1] > 0) != (end[1] > 0):
                crossing = start[0] + (end[0] - start[0]) * (-start[1]) / (end[1] - start[1])
                if crossing > 0:
                    inside = not inside
        if inside:
            return False
    # Supported outer pad primitives are convex. Drill exclusion above checks
    # vertices, edges, and full enclosure, so the entire face is owned copper.
    return bool(face)


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segment_distance(
    left_start: tuple[float, float],
    left_end: tuple[float, float],
    right_start: tuple[float, float],
    right_end: tuple[float, float],
) -> float:
    """Return the minimum distance between two closed 2D segments."""

    left_a = _orientation(left_start, left_end, right_start)
    left_b = _orientation(left_start, left_end, right_end)
    right_a = _orientation(right_start, right_end, left_start)
    right_b = _orientation(right_start, right_end, left_end)
    if left_a * left_b <= 0.0 and right_a * right_b <= 0.0:
        return 0.0

    def point_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        ratio = 0.0 if length_squared <= 1e-18 else max(
            0.0,
            min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared),
        )
        return hypot(point[0] - start[0] - ratio * dx, point[1] - start[1] - ratio * dy)

    return min(
        point_distance(left_start, right_start, right_end),
        point_distance(left_end, right_start, right_end),
        point_distance(right_start, left_start, left_end),
        point_distance(right_end, left_start, left_end),
    )


def _via_contains(
    face: Sequence[tuple[float, float]],
    via: Mapping[str, Any],
    tolerance_mm: float,
) -> bool:
    center = _point(via.get("at", (0, 0)))
    drill = max(float(via.get("drill", 0.0)), 0.0)
    plating = max(float(via.get("plating_thickness", via.get("plating_thickness_mm", 0.025))), 0.0)
    inner_radius = max(0.0, drill / 2 - tolerance_mm)
    outer_radius = drill / 2 + plating + tolerance_mm
    return bool(face) and all(
        inner_radius <= hypot(x - center[0], y - center[1]) <= outer_radius
        for x, y in face
    )


def _barrel_faces_xy(
    volume: Mapping[str, Any],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    vertices = volume.get("vertices_mm")
    if not isinstance(vertices, list) or len(vertices) < 8 or len(vertices) % 2:
        _fail(f"barrel volume {volume.get('id', '')!r} has invalid vertices")
    half = len(vertices) // 2
    outer = [(float(point[0]), float(point[1])) for point in vertices[:half]]
    inner = [(float(point[0]), float(point[1])) for point in vertices[half:]]
    return outer, inner


def _pad_barrel_contains(
    volume: Mapping[str, Any],
    pad: Mapping[str, Any],
    tolerance_mm: float,
) -> bool:
    outer, inner = _barrel_faces_xy(volume)
    if not (_pad_contains(outer, pad, tolerance_mm) and _pad_contains(inner, pad, tolerance_mm)):
        return False
    drill_width, drill_height = _pad_drill_size(dict(pad))
    plating = max(
        float(
            volume.get(
                "plating_thickness_mm",
                pad.get("plating_thickness", pad.get("plating_thickness_mm", 0.025)),
            )
        ),
        0.0,
    )
    envelope_width = drill_width + 2 * (plating + tolerance_mm)
    envelope_height = drill_height + 2 * (plating + tolerance_mm)
    drill_shape = _pad_drill_shape(dict(pad))
    for world_x, world_y in [*outer, *inner]:
        local = _pad_world_to_local(dict(pad), (world_x, world_y))
        if drill_shape == "oval":
            if not _point_in_capsule_local(local, envelope_width, envelope_height):
                return False
        else:
            half_width = max(envelope_width / 2, 1e-12)
            half_height = max(envelope_height / 2, 1e-12)
            if (local[0] / half_width) ** 2 + (local[1] / half_height) ** 2 > 1.0 + 1e-9:
                return False
    return True


def audit_dc_conductor_volume_ownership(
    design: DesignIR,
    volumes: Sequence[Dict[str, Any]],
    tolerance_mm: float = 1e-6,
) -> Dict[str, Any]:
    """Prove that every solver volume remains inside its canonical copper owner."""

    try:
        tolerance = float(tolerance_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{OWNERSHIP_ERROR}: ownership tolerance must be numeric") from exc
    if not isfinite(tolerance) or not 0.0 <= tolerance <= 0.1:
        _fail("ownership tolerance must be between 0 and 0.1 mm")

    sources = {
        "track": _source_map(design.tracks, "track"),
        "zone": _source_map(design.zones, "zone"),
        "pad": _source_map(design.pads, "pad", ("id", "component_pad")),
        "pad_barrel": _source_map(design.pads, "pad", ("id", "component_pad")),
        "via": _source_map(design.vias, "via"),
    }
    copper_layers = copper_stack_profile(design)[0]
    counts: Counter[str] = Counter()
    seen_cells: set[str] = set()
    for volume in volumes:
        cell_id = str(volume.get("id") or "").strip()
        if not cell_id or cell_id in seen_cells:
            _fail(f"volume id {cell_id!r} is missing or duplicated")
        seen_cells.add(cell_id)
        source_kind = str(volume.get("source_kind") or "").strip()
        source_id = str(volume.get("source_id") or "").strip()
        if source_kind not in SUPPORTED_SOURCE_KINDS:
            _fail(f"volume {cell_id!r} has unsupported source kind {source_kind!r}")
        source = sources[source_kind].get(source_id)
        if source is None:
            _fail(f"volume {cell_id!r} references unknown {source_kind} {source_id!r}")
        source_net = _net(source)
        if str(volume.get("net") or "") != source_net:
            _fail(f"volume {cell_id!r} net does not match source {source_id!r}")
        layer = str(volume.get("layer") or "")
        face = _face_xy(volume)
        contained = False
        if source_kind == "track":
            contained = layer == str(source.get("layer", "F.Cu")) and _track_contains(face, source, tolerance)
        elif source_kind == "zone":
            polygon = _normalize_filled_zone_polygon([_point(value) for value in source.get("points", [])])
            contained = (
                layer == str(source.get("layer") or "")
                and len(polygon) >= 3
                and _polygon_is_contained_in(face, polygon, tolerance)
            )
        elif source_kind == "pad":
            contained = (
                layer in _pad_layers(source, copper_layers)
                and _pad_contains(face, source, tolerance)
            )
        elif source_kind == "pad_barrel":
            contained = (
                layer in _pad_spans(design, source)
                and _pad_barrel_contains(volume, source, tolerance)
            )
        elif source_kind == "via":
            contained = layer in _via_spans(design, source) and _via_contains(face, source, tolerance)
        if not contained:
            _fail(f"volume {cell_id!r} escapes {source_kind} owner {source_id!r}")
        counts[source_kind] += 1

    if not counts:
        _fail("no conductor volumes were supplied for ownership validation")
    return {
        "status": "passed",
        "checked_volumes": sum(counts.values()),
        "by_source_kind": dict(sorted(counts.items())),
        "tolerance_mm": tolerance,
    }
