# SPDX-License-Identifier: Apache-2.0
"""Approximate, source-bounded planar copper occupancy for thermal grids.

Coordinates and spacing are millimetres. Coverage is dimensionless and has
shape (ny, nx). Subcell sampling unions overlapping artwork before averaging;
it is an approximation, not an electrical connectivity or thermal solution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

from .contracts import DesignIR
from .hybrid_mesh import (_normalize_filled_zone_polygon, _pad_boundary_polygon,
                          _pad_layers, _polygon_area, _polygon_is_simple)


class CopperGeometryError(ValueError):
    """Source geometry could not be represented without inventing copper."""

    def __init__(self, diagnostics: list[dict[str, Any]]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(item["message"] for item in diagnostics))


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{label} must be {'positive' if positive else 'finite'}")
    return result


def _point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError(f"{label} must be a two-dimensional point")
    return _number(value[0], f"{label} x"), _number(value[1], f"{label} y")


def _ring(value: Any, label: str, *, allow_source_path: bool = False) -> list[tuple[float, float]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a polygon")
    points = _normalize_filled_zone_polygon([_point(p, label) for p in value])
    if (len(points) < 3 or _polygon_area(points) <= 1e-12
            or (not allow_source_path and not _polygon_is_simple(points))):
        raise ValueError(f"{label} must be a nonempty simple polygon")
    return points


def _inside_polygon(x: np.ndarray, y: np.ndarray, ring: Sequence[tuple[float, float]]) -> np.ndarray:
    inside = np.zeros(x.shape, dtype=bool)
    for (ax, ay), (bx, by) in zip(ring, (*ring[1:], ring[0])):
        if ay == by:
            continue
        crossing = ((ay > y) != (by > y)) & (x < (bx - ax) * (y - ay) / (by - ay) + ax)
        inside ^= crossing
    return inside


def _paint(mask: np.ndarray, bounds: tuple[float, float, float, float],
           spacing: tuple[float, float], samples: int,
           box: tuple[float, float, float, float], contains: Any) -> None:
    xmin, ymin, _, _ = bounds
    dx, dy = spacing
    nx, ny = mask.shape[1] // samples, mask.shape[0] // samples
    ix0 = max(0, math.floor((box[0] - xmin) / dx * samples))
    ix1 = min(nx * samples, math.ceil((box[2] - xmin) / dx * samples))
    iy0 = max(0, math.floor((box[1] - ymin) / dy * samples))
    iy1 = min(ny * samples, math.ceil((box[3] - ymin) / dy * samples))
    if ix0 >= ix1 or iy0 >= iy1:
        return
    x = xmin + (np.arange(ix0, ix1) + 0.5) * dx / samples
    y = ymin + (np.arange(iy0, iy1) + 0.5) * dy / samples
    xx, yy = np.meshgrid(x, y)
    mask[iy0:iy1, ix0:ix1] |= contains(xx, yy)


def _polygon_box(ring: Sequence[tuple[float, float]]) -> tuple[float, float, float, float]:
    return min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)


def _scanline_polygon(mask: np.ndarray, bounds: tuple[float, float, float, float],
                      spacing: tuple[float, float], samples: int,
                      ring: Sequence[tuple[float, float]], *, clear: bool = False) -> None:
    """Even-odd source-path fill, including cutouts connected by retraced bridges."""
    xmin, ymin, _, _ = bounds
    dx, dy = spacing
    x0, y0, x1, y1 = _polygon_box(ring)
    col0 = max(0, math.floor((x0 - xmin) / dx * samples))
    col1 = min(mask.shape[1], math.ceil((x1 - xmin) / dx * samples))
    row0 = max(0, math.floor((y0 - ymin) / dy * samples))
    row1 = min(mask.shape[0], math.ceil((y1 - ymin) / dy * samples))
    if col0 >= col1 or row0 >= row1:
        return
    vertices = np.asarray(ring, dtype=float)
    x_a, y_a = vertices[:, 0], vertices[:, 1]
    x_b, y_b = np.roll(x_a, -1), np.roll(y_a, -1)
    x = xmin + (np.arange(col0, col1) + 0.5) * dx / samples
    for row in range(row0, row1):
        y = ymin + (row + 0.5) * dy / samples
        crossing = ((y_a <= y) & (y < y_b)) | ((y_b <= y) & (y < y_a))
        intersections = np.sort(x_a[crossing] + (y - y_a[crossing])
                                * (x_b[crossing] - x_a[crossing])
                                / (y_b[crossing] - y_a[crossing]))
        if len(intersections) % 2:
            raise ValueError("source polygon has unmatched scanline intersections")
        hit = np.searchsorted(intersections, x, side="right") % 2 == 1
        if clear:
            mask[row, col0:col1] &= ~hit
        else:
            mask[row, col0:col1] |= hit


def _layers(raw: Any, available: Sequence[str], label: str) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{label} has invalid layer membership")
    if any(str(item) in {"*.Cu", "F&B.Cu"} for item in raw):
        return list(available)
    result = [str(item) for item in raw if str(item).endswith(".Cu")]
    unknown = set(result) - set(available)
    if unknown:
        raise ValueError(f"{label} references unknown copper layers {sorted(unknown)}")
    return list(dict.fromkeys(result))


def rasterize_copper(
    design: DesignIR,
    bounds: tuple[float, float, float, float],
    shape: tuple[int, int],
    spacing_mm: tuple[float, float],
    layer_names: Sequence[str],
    *,
    fuzzy_sigma_mm: float = 0.0,
    include_tracks: bool = True,
    include_pads: bool = True,
    include_zones: bool = True,
    include_via_lands: bool = True,
    samples_per_axis: int = 6,
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Return union coverage per copper layer and provenance diagnostics.

    Unfilled/unknown zones and unsupported selected objects raise
    ``CopperGeometryError`` with structured diagnostics. ``fuzzy_sigma_mm``
    blurs each layer's *cell coverage*, conserving its sum with reflecting
    boundaries. The grid is a rectangle; board cutouts are not inferred.
    """
    if design.units != "mm":
        raise ValueError("Copper geometry requires DesignIR millimetres")
    if len(bounds) != 4 or len(shape) != 2 or len(spacing_mm) != 2:
        raise ValueError("Invalid copper raster grid")
    box = tuple(_number(v, "board bound") for v in bounds)
    nx, ny = shape
    dx, dy = (_number(v, "grid spacing", positive=True) for v in spacing_mm)
    if (not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in shape)
            or nx * ny > 8192 or not isinstance(samples_per_axis, int)
            or isinstance(samples_per_axis, bool) or not 2 <= samples_per_axis <= 12
            or box[2] <= box[0] or box[3] <= box[1]
            or abs(nx * dx - (box[2] - box[0])) > 1e-7
            or abs(ny * dy - (box[3] - box[1])) > 1e-7):
        raise ValueError("Copper raster grid must cover positive board bounds with at most 8192 cells")
    sigma = _number(fuzzy_sigma_mm, "fuzzy_sigma_mm")
    if sigma < 0:
        raise ValueError("fuzzy_sigma_mm must be nonnegative")
    names = list(layer_names)
    if not names or len(names) != len(set(names)) or any(not name.endswith(".Cu") for name in names):
        raise ValueError("Supply unique copper layer names in stack order")
    masks = {name: np.zeros((ny * samples_per_axis, nx * samples_per_axis), dtype=bool) for name in names}
    issues: list[dict[str, Any]] = []

    def fail(kind: str, index: int, reason: str) -> None:
        issues.append({"code": "THERMAL_COPPER_UNSUPPORTED_GEOMETRY", "severity": "error",
                       "path": f"design.{kind}[{index}]", "message": f"{kind}[{index}]: {reason}"})

    if include_tracks:
        for index, item in enumerate(design.tracks):
            try:
                if not isinstance(item, Mapping):
                    raise ValueError("track must be an object")
                layers = _layers([item.get("layer")], names, "track")
                if not layers:
                    raise ValueError("track lacks a copper layer")
                a, b = _point(item.get("start"), "track start"), _point(item.get("end"), "track end")
                width = _number(item.get("width"), "track width", positive=True)
                vx, vy = b[0] - a[0], b[1] - a[1]
                length2 = vx * vx + vy * vy
                if length2 <= 1e-18:
                    raise ValueError("zero-length track")
                radius = width / 2
                rectangle = (min(a[0], b[0]) - radius, min(a[1], b[1]) - radius,
                             max(a[0], b[0]) + radius, max(a[1], b[1]) + radius)
                def contains(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                    t = np.clip(((x - a[0]) * vx + (y - a[1]) * vy) / length2, 0, 1)
                    return (x - a[0] - t * vx) ** 2 + (y - a[1] - t * vy) ** 2 <= radius ** 2
                for layer in layers:
                    _paint(masks[layer], box, (dx, dy), samples_per_axis, rectangle, contains)
            except (ValueError, TypeError, OverflowError) as exc:
                fail("tracks", index, str(exc))

    if include_pads:
        for index, item in enumerate(design.pads):
            try:
                if not isinstance(item, Mapping):
                    raise ValueError("pad must be an object")
                layers = _pad_layers(dict(item), names)
                if not layers:
                    continue
                if set(layers) - set(names):
                    raise ValueError("pad references unknown copper layers")
                if str(item.get("shape", "rect")).lower() not in {"rect", "rectangle", "roundrect", "circle", "oval", "custom"}:
                    raise ValueError("unsupported pad shape")
                polygon = _ring(_pad_boundary_polygon(dict(item), curve_segments=64), "pad perimeter")
                raw_drill = item.get("drill_size", item.get("drill_size_mm", item.get("drill", 0)))
                if isinstance(raw_drill, Mapping):
                    drill = (_number(raw_drill.get("x", raw_drill.get("width")), "drill x"),
                             _number(raw_drill.get("y", raw_drill.get("height")), "drill y"))
                elif isinstance(raw_drill, (list, tuple)):
                    drill = _point(raw_drill, "pad drill")
                else:
                    d = _number(raw_drill, "pad drill")
                    drill = (d, d)
                if min(drill) < 0 or (min(drill) == 0 and max(drill) > 0):
                    raise ValueError("invalid pad drill")
                if min(drill) > 0 and str(item.get("drill_shape", "circle")).lower() not in {"circle", "oval"}:
                    raise ValueError("unsupported pad drill shape")
                center = _point(item.get("at"), "pad center")
                angle = math.radians(_number(item.get("rotation", 0), "pad rotation"))
                ca, sa = math.cos(angle), math.sin(angle)
                shape_name = str(item.get("shape", "rect")).lower()
                size = item.get("size")
                if shape_name == "roundrect":
                    if not isinstance(size, (list, tuple)) or len(size) < 2:
                        raise ValueError("roundrect pad lacks size")
                    pad_width, pad_height = _point(size, "roundrect size")
                    ratio = _number(item.get("roundrect_rratio"), "roundrect radius ratio")
                    if min(pad_width, pad_height) <= 0 or not 0 <= ratio <= 0.5:
                        raise ValueError("invalid roundrect geometry")
                    corner = ratio * min(pad_width, pad_height)
                def contains(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                    hit = _inside_polygon(x, y, polygon)
                    u, v = x - center[0], y - center[1]
                    lx, ly = u * ca + v * sa, -u * sa + v * ca
                    if shape_name == "roundrect" and corner > 0:
                        qx = np.maximum(np.abs(lx) - (pad_width / 2 - corner), 0)
                        qy = np.maximum(np.abs(ly) - (pad_height / 2 - corner), 0)
                        hit &= qx * qx + qy * qy <= corner * corner
                    if min(drill) > 0:
                        if drill[0] == drill[1]:
                            hole = lx * lx + ly * ly <= (drill[0] / 2) ** 2
                        else:
                            horizontal = drill[0] > drill[1]
                            long_axis, short_axis = (lx, ly) if horizontal else (ly, lx)
                            half_span = abs(drill[0] - drill[1]) / 2
                            hole = (np.maximum(np.abs(long_axis) - half_span, 0) ** 2 + short_axis ** 2
                                    <= (min(drill) / 2) ** 2)
                        hit &= ~hole
                    return hit
                for layer in layers:
                    _paint(masks[layer], box, (dx, dy), samples_per_axis, _polygon_box(polygon), contains)
            except (ValueError, TypeError, OverflowError) as exc:
                fail("pads", index, str(exc))

    if include_zones:
        for index, item in enumerate(design.zones):
            try:
                if not isinstance(item, Mapping):
                    raise ValueError("zone must be an object")
                layers = _layers(item.get("layers", [item.get("layer")]), names, "zone")
                if not layers:
                    continue
                if item.get("source_kind") == "footprint_graphic_polygon":
                    if item.get("holes"):
                        raise ValueError("graphic copper polygon cutouts are unsupported")
                elif (item.get("filled_copper_state") != "source_filled"
                      or item.get("source_fill_provenance_complete") is not True):
                    raise ValueError("zone lacks trustworthy source-filled copper")
                if item.get("boundary_rings"):
                    raise ValueError("exact curved zone boundaries require a dedicated rasterizer")
                polygon = _ring(item.get("points"), "filled zone",
                                allow_source_path=item.get("source_fill_representation") == "flat_polygon_path")
                raw_holes = item.get("holes", [])
                if not isinstance(raw_holes, (list, tuple)):
                    raise ValueError("invalid zone holes")
                holes = [_ring(value, "zone cutout") for value in raw_holes]
                zone_mask = np.zeros_like(next(iter(masks.values())))
                _scanline_polygon(zone_mask, box, (dx, dy), samples_per_axis, polygon)
                for hole in holes:
                    _scanline_polygon(zone_mask, box, (dx, dy), samples_per_axis, hole, clear=True)
                represented_area = float(zone_mask.sum()) * dx * dy / samples_per_axis ** 2
                expected_area = _polygon_area(polygon) - sum(_polygon_area(hole) for hole in holes)
                perimeter = sum(math.dist(a, b) for a, b in zip(polygon, (*polygon[1:], polygon[0])))
                # A sample centre can misclassify only subcells intersected by
                # the boundary. This bound scales with boundary length, not
                # with the interior area of a large complex zone.
                tolerance = max(2 * dx * dy / samples_per_axis,
                                perimeter * math.hypot(dx, dy) / samples_per_axis)
                if (expected_area <= 0 or abs(represented_area - expected_area) > tolerance):
                    raise ValueError("filled path area disagrees with rasterized even-odd copper")
                for layer in layers:
                    masks[layer] |= zone_mask
            except (ValueError, TypeError, OverflowError) as exc:
                fail("zones", index, str(exc))

    if include_via_lands:
        for index, item in enumerate(design.vias):
            try:
                if not isinstance(item, Mapping):
                    raise ValueError("via must be an object")
                raw = item.get("layers")
                if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                    raise ValueError("via needs two span endpoint layers")
                ends = _layers(raw, names, "via")
                if len(ends) != 2:
                    raise ValueError("via span endpoints must differ")
                lo, hi = sorted((names.index(ends[0]), names.index(ends[1])))
                center = _point(item.get("at"), "via center")
                diameter = _number(item.get("size", item.get("diameter")), "via diameter", positive=True)
                drill = _number(item.get("drill"), "via drill", positive=True)
                if drill >= diameter:
                    raise ValueError("via drill must be smaller than its land")
                r2, h2 = (diameter / 2) ** 2, (drill / 2) ** 2
                rectangle = (center[0] - diameter / 2, center[1] - diameter / 2,
                             center[0] + diameter / 2, center[1] + diameter / 2)
                def contains(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                    distance2 = (x - center[0]) ** 2 + (y - center[1]) ** 2
                    return (distance2 <= r2) & (distance2 > h2)
                for layer in names[lo:hi + 1]:
                    _paint(masks[layer], box, (dx, dy), samples_per_axis, rectangle, contains)
            except (ValueError, TypeError, OverflowError) as exc:
                fail("vias", index, str(exc))

    if issues:
        raise CopperGeometryError(issues)
    result = {name: mask.reshape(ny, samples_per_axis, nx, samples_per_axis).mean(axis=(1, 3))
              for name, mask in masks.items()}
    if sigma > 0:
        result = {name: gaussian_filter(value, (sigma / dy, sigma / dx), mode="reflect")
                  for name, value in result.items()}
    diagnostics = [{"code": "THERMAL_COPPER_SAMPLED", "severity": "warning",
                    "message": f"Copper union sampled at {samples_per_axis} x {samples_per_axis} points per cell; area and edges are approximate."}]
    if sigma > 0:
        diagnostics.append({"code": "THERMAL_COPPER_FUZZY", "severity": "warning",
                            "message": "Per-layer Gaussian blur conserves integrated sampled coverage but changes local geometry and connectivity."})
    return result, diagnostics


__all__ = ["CopperGeometryError", "rasterize_copper"]
