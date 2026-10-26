# SPDX-License-Identifier: Apache-2.0
"""Bounded forbidden-region checks on supplied eye-diagram polylines.

Original clean-room geometry: orientation is the signed 2D determinant;
closed segment intersection and odd/even ray parity define polygon occupancy.
Fraction arithmetic evaluates the supplied binary floats exactly, including
boundary contact; it does not recover accuracy lost in waveform sampling.
No protocol mask coordinates or normative compliance criteria are embedded.
"""
from __future__ import annotations

from fractions import Fraction
import math
from typing import Any

SCHEMA = "spike/si-eye-mask/v1"
MAX_POLYGONS = 16
MAX_VERTICES = 64
MAX_TRACES = 4096
MAX_POINTS = 100_000
MAX_EDGE_CHECKS = 1_000_000


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError(f"{label} must be nonempty text (at most 2048 characters)")
    return value


def _exact(point):
    return tuple(Fraction(value) for value in point)


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p):
    return (_orient(a, b, p) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _intersects(a, b, c, d):
    ab_c, ab_d = _orient(a, b, c), _orient(a, b, d)
    cd_a, cd_b = _orient(c, d, a), _orient(c, d, b)
    if ((ab_c > 0 > ab_d or ab_d > 0 > ab_c)
            and (cd_a > 0 > cd_b or cd_b > 0 > cd_a)):
        return True
    return ((ab_c == 0 and _on_segment(a, b, c))
            or (ab_d == 0 and _on_segment(a, b, d))
            or (cd_a == 0 and _on_segment(c, d, a))
            or (cd_b == 0 and _on_segment(c, d, b)))


def _edges(polygon):
    return list(zip(polygon, polygon[1:] + polygon[:1]))


def _inside(point, edges):
    inside = False
    for a, b in edges:
        if _on_segment(a, b, point):
            return True
        if (a[1] > point[1]) != (b[1] > point[1]):
            crossing_x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if crossing_x > point[0]:
                inside = not inside
    return inside


def validate_eye_mask(mask: Any) -> dict:
    """Validate and copy the strict v1 contract; vertices have implicit closure."""
    fields = {"schema", "id", "name", "protocol", "revision", "source", "voltage_unit", "polygons"}
    if not isinstance(mask, dict) or set(mask) != fields or mask.get("schema") != SCHEMA:
        raise ValueError("mask must have exactly the spike/si-eye-mask/v1 fields")
    result = {"schema": SCHEMA}
    for field in ("id", "name", "protocol", "revision"):
        result[field] = _text(mask[field], field)
    source = mask["source"]
    if not isinstance(source, dict) or set(source) != {"locator", "clause"}:
        raise ValueError("source requires exactly locator and clause")
    result["source"] = {key: _text(source[key], f"source.{key}") for key in ("locator", "clause")}
    if mask["voltage_unit"] not in ("V", "normalized"):
        raise ValueError("voltage_unit must be V or normalized")
    result["voltage_unit"] = mask["voltage_unit"]
    polygons = mask["polygons"]
    if not isinstance(polygons, list) or not 1 <= len(polygons) <= MAX_POLYGONS:
        raise ValueError(f"mask requires 1..{MAX_POLYGONS} polygons")
    result["polygons"] = []
    for polygon in polygons:
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= MAX_VERTICES:
            raise ValueError(f"polygon requires 3..{MAX_VERTICES} vertices")
        points = []
        for point in polygon:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("polygon vertices must be [time_ui, voltage]")
            points.append([_number(point[0], "time_ui"), _number(point[1], "voltage")])
        exact = [_exact(point) for point in points]
        if len(set(exact)) != len(exact):
            raise ValueError("polygon vertices must be distinct; closure is implicit")
        edges = _edges(exact)
        if sum(a[0] * b[1] - a[1] * b[0] for a, b in edges) == 0:
            raise ValueError("polygon must have nonzero area")
        for i, (a, b) in enumerate(edges):
            # Adjacent edges may share only their common endpoint, never overlap.
            c = exact[(i + 2) % len(exact)]
            if _on_segment(a, b, c) or _on_segment(b, c, a):
                raise ValueError("polygon has overlapping adjacent edges")
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if _intersects(a, b, *edges[j]):
                    raise ValueError("polygon must be simple (no self intersections)")
        result["polygons"].append(points)
    return result


def evaluate_eye_mask(mask: Any, traces: Any, voltage_unit: str, evidence: dict | None = None) -> dict:
    """Check forbidden polygons against finite points and connecting segments.

    Traces are separate lists of {time_ui, value} points, ordered by nondecreasing
    time. Split traces at eye-wrap boundaries: this evaluator never joins traces.
    A hit counts each offending point or segment once across all polygons; it is
    not a count of physical errors or independent waveform events.
    """
    mask = validate_eye_mask(mask)
    if voltage_unit != mask["voltage_unit"]:
        raise ValueError("trace voltage_unit must match mask; no implicit normalization")
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    if not isinstance(traces, list) or not 1 <= len(traces) <= MAX_TRACES:
        raise ValueError(f"traces requires 1..{MAX_TRACES} separate traces")
    if any(not isinstance(trace, list) or not trace for trace in traces):
        raise ValueError("each trace must contain at least one sample")
    count = sum(len(trace) for trace in traces)
    edge_count = sum(len(polygon) for polygon in mask["polygons"])
    if count > MAX_POINTS or (2 * count - len(traces)) * edge_count > MAX_EDGE_CHECKS:
        raise ValueError("eye-mask evaluation exceeds bounded point/edge work limit")
    polygons = [_edges([_exact(point) for point in polygon]) for polygon in mask["polygons"]]
    point_hits = segment_hits = 0
    for trace in traces:
        previous = None
        previous_hit = False
        for sample in trace:
            if not isinstance(sample, dict) or set(sample) != {"time_ui", "value"}:
                raise ValueError("trace samples require exactly time_ui and value")
            point = _exact((_number(sample["time_ui"], "time_ui"), _number(sample["value"], "value")))
            if previous is not None and point[0] < previous[0]:
                raise ValueError("trace time_ui must be nondecreasing; split eye wraps into separate traces")
            hit = any(_inside(point, edges) for edges in polygons)
            point_hits += int(hit)
            if previous is not None:
                segment_hits += int(previous_hit or hit or any(
                    _intersects(previous, point, a, b) for edges in polygons for a, b in edges))
            previous, previous_hit = point, hit
    hits = point_hits + segment_hits
    return {
        "schema": "spike/si-eye-mask-result/v1", "status": "fail" if hits else "pass",
        "passed": hits == 0, "hit_count": hits, "point_hit_count": point_hits,
        "segment_hit_count": segment_hits, "sample_count": count,
        "trace_count": len(traces), "mask_id": mask["id"], "mask_name": mask["name"],
        "protocol": mask["protocol"], "revision": mask["revision"], "source": mask["source"],
        "voltage_unit": voltage_unit, "evidence": dict(evidence or {}),
        "limitations": [
            "Pass/fail applies only to supplied sampled points and linear segments.",
            "Boundary touching is a violation. No mask translation or fitting is performed.",
            "No unsampled waveform, BER, or normative protocol compliance claim is established.",
            "Source attribution is user supplied and is not independent standards verification.",
        ],
    }
