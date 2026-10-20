# SPDX-License-Identifier: Apache-2.0
"""Bounded local surface partition for opt-in owned drilled roundrect pads.

The outer surface has 32 inscribed chords per quarter circle. Its area deficit
is r**2/2 * (2*pi - 128*sin(2*pi/128)); the drill polygon is circumscribed.
Splitting both polygons at their combined vertex rays adds no area error.
This is geometry preparation, not a new conduction or barrel constitutive law.
"""
from math import atan2, ceil, cos, hypot, isfinite, pi, sin


def validate_metadata(pad):
    """Do not manufacture a radius or repair malformed physical dimensions."""
    def number(value):
        if isinstance(value, bool):
            raise ValueError
        return float(value)
    try:
        size = pad.get("size", (pad.get("width"), pad.get("height")))
        if len(size) != 2:
            raise ValueError
        width, height = (number(size[i]) for i in (0, 1))
        ratio = number(pad.get("roundrect_rratio", pad.get("rratio")))
        if not all(isfinite(v) for v in (width, height, ratio)) or min(width, height) < .01 or not 0 <= ratio <= .5:
            raise ValueError
        raw = pad.get("drill_size", pad.get("drill_size_mm"))
        if isinstance(raw, dict):
            raw = (raw.get("x", raw.get("width")), raw.get("y", raw.get("height")))
        if raw is None:
            raw = (pad.get("drill", 0),) * 2
        if len(raw) != 2:
            raise ValueError
        drill = tuple(number(raw[i]) for i in (0, 1))
        if not all(isfinite(v) and v >= 0 for v in drill) or (min(drill) == 0 < max(drill)):
            raise ValueError
        shape = pad.get("drill_shape")
        if shape not in {None, "", "none", "circle", "oval"} or (shape == "circle" and abs(drill[0]-drill[1]) > 1e-12):
            raise ValueError
        offset = pad.get("drill_offset", pad.get("drill_offset_mm", (0, 0)))
        if len(offset) != 2 or any(not isfinite(number(v)) or abs(number(v)) > 1e-12 for v in offset):
            raise ValueError
        at = pad.get("at", (0, 0))
        if len(at) != 2 or not isfinite(number(pad.get("rotation", 0))) or any(not isfinite(number(v)) for v in at):
            raise ValueError
    except (TypeError, ValueError, IndexError, KeyError) as error:
        raise ValueError("Owned roundrect requires finite dimensions >= .01 mm, an imported radius ratio in [0, .5], and valid centered drill metadata") from error


def outer_boundary(pad):
    """Use the established outer-only source adapter, with the drill explicit below."""
    from .quasistatic_copper_area import _source_polygon
    validate_metadata(pad)
    outer = dict(pad, at=[0, 0], rotation=0, drill=0)
    outer.pop("drill_size", None)
    outer.pop("drill_size_mm", None)
    return _source_polygon("pad", outer)


def _ray_point(polygon, angle):
    direction = (cos(angle), sin(angle))
    radius = float("inf")
    result = None
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        denominator = dx * direction[1] - dy * direction[0]
        if denominator < -1e-14:
            candidate = (dx * a[1] - dy * a[0]) / denominator
            if candidate < radius:
                radius = candidate
                fraction = -(a[0]*direction[1]-a[1]*direction[0])/denominator
                # Retain source vertices and exactly straight coordinates.
                # Polar reconstruction otherwise perturbs collinear vertices,
                # changing their sorted order in the existing hull operation.
                result = (a if abs(fraction) <= 1e-12 else b if abs(fraction-1) <= 1e-12
                          else (a[0]+fraction*dx, a[1]+fraction*dy))
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Owned roundrect polygon does not enclose its centered drill")
    return result


def local_cells(pad, target_mm, max_cells):
    from .hybrid_mesh import _circumscribed_shape_polygon, _pad_drill_size, _pad_drill_shape
    outline = outer_boundary(pad)
    width, height = (float(v) for v in pad["size"]) if "size" in pad else (float(pad["width"]), float(pad["height"]))
    drill_width, drill_height = _pad_drill_size(pad)
    if min(drill_width, drill_height) <= 0 or drill_width >= width or drill_height >= height:
        raise ValueError("Owned roundrect drill must be strictly inside its copper land")
    count = max(24, min(192, int(ceil(pi * max(width, height) / max(target_mm, .01)))))
    void = _circumscribed_shape_polygon(_pad_drill_shape(pad), drill_width, drill_height, count)
    angles = []
    for angle in sorted(atan2(y, x) % (2 * pi) for x, y in outline + void):
        if not angles or angle - angles[-1] > 1e-12:
            angles.append(angle)
    if len(angles) > 1 and angles[0] + 2 * pi - angles[-1] <= 1e-12:
        angles.pop()
    inner = [_ray_point(void, a) for a in angles]
    outer = [_ray_point(outline, a) for a in angles]
    clearance = min(hypot(*b) - hypot(*a) for a, b in zip(inner, outer))
    if clearance <= 1e-9:
        raise ValueError("Owned roundrect drill polygon leaves no positive copper ligament")
    rows = max(1, int(ceil(clearance / max(target_mm, .01))))
    if max_cells is None or len(angles) * rows > max_cells:
        raise ValueError("Owned roundrect annular partition exceeds the pad cell budget")
    rings = [[tuple(a[k] + (b[k] - a[k]) * row / rows for k in (0, 1))
              for a, b in zip(inner, outer)] for row in range(rows + 1)]
    cells, indices = [], []
    for row in range(rows):
        for side in range(len(angles)):
            next_side = (side + 1) % len(angles)
            cells.append([rings[row][side], rings[row + 1][side],
                          rings[row + 1][next_side], rings[row][next_side]])
            indices.append((row, side))
    return cells, indices
