"""Validity-bounded single-reference PCB capacitance estimates.

This module does not replace a panel/BEM electrostatic field solver. It creates
an explicit engineering estimate for routed planar copper when a physical
stackup and reference conductor can be identified. Unsupported geometry is
counted and reported instead of receiving a fabricated capacitance.
"""

from __future__ import annotations

from math import cos, hypot, isfinite, log, pi, radians, sin, sqrt
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from .contracts import AnalysisSpec, DesignIR, ValidationIssue


EPSILON_0_F_M = 8.8541878128e-12
LIGHT_SPEED_M_S = 299_792_458.0


def zone_pad_mesh_dependence_issue(branches: Sequence[Any],
                                   physical_indices: Sequence[int],
                                   volume_extraction: bool) -> ValidationIssue | None:
    """Keep the unqualified area surrogate explicit to AC consumers."""
    if not volume_extraction or not any(
        branches[index].kind in {"zone", "pad"} for index in physical_indices
    ):
        return None
    return ValidationIssue(
        "PEEC_ZONE_PAD_CAPACITANCE_AREA_SURROGATE", "warning",
        "Zone/pad capacitance uses unique projected copper area and a parallel-plate surrogate; fringing and multiconductor coupling are omitted.",
        suggestion="Do not use this capacitance for bandwidth sign-off; use a validated electrostatic extractor.",
        status="approximate",
    )


def estimate_line_capacitance_per_m(
    width_mm: float,
    height_mm: float,
    epsilon_r: float,
) -> float:
    """Return the Hammerstad/Jensen zero-thickness microstrip C' estimate."""

    if width_mm <= 0 or height_mm <= 0 or epsilon_r < 1:
        return 0.0
    ratio = width_mm / height_mm
    effective_epsilon = (epsilon_r + 1.0) / 2.0 + (
        (epsilon_r - 1.0) / (2.0 * sqrt(1.0 + 12.0 / ratio))
    )
    if ratio < 1.0:
        effective_epsilon += 0.04 * (1.0 - ratio) ** 2
    if ratio <= 1.0:
        impedance = 60.0 / sqrt(effective_epsilon) * log(
            8.0 / ratio + 0.25 * ratio
        )
    else:
        impedance = 120.0 * pi / (
            sqrt(effective_epsilon)
            * (ratio + 1.393 + 0.667 * log(ratio + 1.444))
        )
    velocity = LIGHT_SPEED_M_S / sqrt(effective_epsilon)
    return 1.0 / max(impedance * velocity, 1e-30)


def stackup_profile(
    design: DesignIR,
) -> Tuple[Dict[str, float], List[Tuple[float, float, float, float | None]]]:
    """Return copper center Z values and dielectric intervals in millimetres."""

    copper_centers: Dict[str, float] = {}
    dielectrics: List[Tuple[float, float, float, float | None]] = []
    z_top = 0.0
    for item in design.stackup:
        name = str(item.get("name", ""))
        thickness = max(
            float(item.get("thickness") or item.get("thickness_mm") or 0), 0.0
        )
        z_bottom = z_top - thickness
        if name.endswith(".Cu"):
            copper_centers[name] = (z_top + z_bottom) / 2.0
        else:
            epsilon_value = item.get("epsilon_r", item.get("epsilonR"))
            loss_value = item.get("loss_tangent", item.get("lossTangent"))
            if thickness > 0 and epsilon_value is not None and float(epsilon_value) >= 1:
                dielectrics.append(
                    (
                        z_bottom,
                        z_top,
                        float(epsilon_value),
                        None if loss_value is None else max(float(loss_value), 0.0),
                    )
                )
        z_top = z_bottom
    return copper_centers, dielectrics


def dielectric_between(
    z_a: float,
    z_b: float,
    dielectrics: Sequence[Tuple[float, float, float, float | None]],
) -> Tuple[float, float, float | None] | None:
    """Return path-averaged epsilon, dielectric height, and loss tangent."""

    low, high = sorted((z_a, z_b))
    epsilon_weighted = 0.0
    loss_weighted = 0.0
    loss_covered = 0.0
    covered = 0.0
    for bottom, top, epsilon_r, loss_tangent in dielectrics:
        overlap = max(0.0, min(high, top) - max(low, bottom))
        epsilon_weighted += overlap * epsilon_r
        covered += overlap
        if loss_tangent is not None:
            loss_weighted += overlap * epsilon_r * loss_tangent
            loss_covered += overlap * epsilon_r
    if covered <= 0:
        return None
    epsilon_r = epsilon_weighted / covered
    loss_tangent = loss_weighted / loss_covered if loss_covered > 0 else None
    return epsilon_r, covered, loss_tangent


def _geometry_layers_for_net(design: DesignIR, net: str) -> set[str]:
    layers: set[str] = set()
    for collection in (design.tracks, design.pads, design.zones):
        for item in collection:
            item_net = str(item.get("net_name") or item.get("net") or "")
            if item_net != net:
                continue
            layer = str(item.get("layer", ""))
            layers.update(str(value) for value in item.get("layers", []) if str(value).endswith(".Cu"))
            if layer.endswith(".Cu"):
                layers.add(layer)
    for via in design.vias:
        item_net = str(via.get("net_name") or via.get("net") or "")
        if item_net == net:
            layers.update(str(value) for value in via.get("layers", []) if str(value).endswith(".Cu"))
    return layers


def _xy(value: Any) -> Tuple[float, float]:
    if isinstance(value, dict):
        return float(value.get("x", 0.0)), float(value.get("y", 0.0))
    return float(value[0]), float(value[1])


def _distance_to_segment(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-30:
        return hypot(point[0] - start[0], point[1] - start[1])
    position = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq),
    )
    return hypot(point[0] - (start[0] + position * dx), point[1] - (start[1] + position * dy))


def _point_in_polygon(point: Tuple[float, float], polygon: Sequence[Tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing = (previous[0] - current[0]) * (point[1] - current[1]) / (
                (previous[1] - current[1]) or 1e-30
            ) + current[0]
            if point[0] < crossing:
                inside = not inside
        previous = current
    return inside


def _polygon_area(points: Sequence[Tuple[float, float]]) -> float:
    return abs(sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, (*points[1:], points[0]))
    )) / 2.0 if len(points) >= 3 else 0.0


def _pad_polygon(pad: Dict[str, Any]) -> List[Tuple[float, float]] | None:
    """Return exact pad corners for the deliberately narrow admitted subset."""
    if str(pad.get("shape", "")) != "rect" or pad.get("drill", 0):
        return None
    size = pad.get("size", [0.0, 0.0])
    try:
        width, height = (float(size), float(size)) if isinstance(size, (int, float)) else _xy(size)
        cx, cy = _xy(pad.get("at", [0.0, 0.0]))
        angle = radians(float(pad.get("rotation", 0.0)) % 360.0)
    except (TypeError, ValueError, OverflowError, IndexError, KeyError):
        return None
    if not all(isfinite(value) for value in (width, height, cx, cy, angle)) or width <= 0 or height <= 0:
        return None
    ca, sa = cos(angle), sin(angle)
    return [
        (cx + ca * x - sa * y, cy + sa * x + ca * y)
        for x, y in ((-width / 2, -height / 2), (width / 2, -height / 2),
                     (width / 2, height / 2), (-width / 2, height / 2))
    ]


def _bbox(points: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlaps(a: Sequence[Tuple[float, float]], b: Sequence[Tuple[float, float]]) -> bool:
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    return min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0)


def _orientation(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_intersection(a: Tuple[float, float], b: Tuple[float, float],
                         c: Tuple[float, float], d: Tuple[float, float]) -> bool:
    return (_orientation(a, b, c) * _orientation(a, b, d) < 0
            and _orientation(c, d, a) * _orientation(c, d, b) < 0)


def _on_segment(a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float]) -> bool:
    return (abs(_orientation(a, b, p)) <= 1e-12
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _segments_intersect(a: Tuple[float, float], b: Tuple[float, float],
                        c: Tuple[float, float], d: Tuple[float, float]) -> bool:
    return (_proper_intersection(a, b, c, d) or _on_segment(a, b, c)
            or _on_segment(a, b, d) or _on_segment(c, d, a) or _on_segment(c, d, b))


def _polygon_is_simple(points: Sequence[Tuple[float, float]]) -> bool:
    edges = list(zip(points, (*points[1:], points[0])))
    count = len(edges)
    for i, (a, b) in enumerate(edges):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if _segments_intersect(a, b, *edges[j]):
                return False
    return True


def _polygon_strictly_contains(container: Sequence[Tuple[float, float]],
                               contained: Sequence[Tuple[float, float]]) -> bool:
    if not all(_point_in_polygon(point, container) for point in contained):
        return False
    container_edges = list(zip(container, (*container[1:], container[0])))
    contained_edges = list(zip(contained, (*contained[1:], contained[0])))
    return not any(
        _proper_intersection(a, b, c, d)
        for a, b in container_edges for c, d in contained_edges
    )


def _planar_owner_areas(design: DesignIR) -> Tuple[Dict[Tuple[str, str], float], set[Tuple[str, str]], int]:
    """Admit unique source copper area, failing closed on ambiguous unions.

    Source-filled simple zone polygons and undrilled rectangular pads are the
    only admitted shapes. A pad wholly inside a same-net filled zone is already
    represented by that fill and is counted zero times. Any other overlapping
    source bounding boxes are rejected rather than pretending their areas add.
    """
    areas: Dict[Tuple[str, str], float] = {}
    polygons: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}
    ambiguous: set[Tuple[str, str]] = set()
    for zone in design.zones:
        owner, layer = str(zone.get("id", "")), str(zone.get("layer", ""))
        key = (owner, layer)
        try:
            points = [_xy(value) for value in zone.get("points", zone.get("polygon", []))]
        except (TypeError, ValueError, OverflowError, IndexError, KeyError):
            ambiguous.add(key)
            continue
        if (key in polygons or key in ambiguous or not owner or not layer
                or zone.get("holes") or zone.get("interiors")
                or zone.get("filled_copper_state") not in (None, "source_filled")
                or zone.get("source_fill_provenance_complete") is False
                or len(points) < 3 or not all(isfinite(value) for point in points for value in point)
                or not _polygon_is_simple(points) or not isfinite(_polygon_area(points))
                or _polygon_area(points) <= 0):
            ambiguous.add(key)
            continue
        polygons[key], areas[key] = points, _polygon_area(points)
    for pad in design.pads:
        owner = str(pad.get("id") or pad.get("component_pad") or "")
        layers = [str(v) for v in pad.get("layers", []) if str(v).endswith(".Cu")]
        if not layers and str(pad.get("layer", "")).endswith(".Cu"):
            layers = [str(pad["layer"])]
        polygon = _pad_polygon(pad)
        for layer in layers:
            key = (owner, layer)
            if key in polygons or key in ambiguous or not owner or polygon is None:
                ambiguous.add(key)
            else:
                polygons[key], areas[key] = polygon, _polygon_area(polygon)

    # Only same-net/source-layer overlap is relevant. Owner ids are resolved
    # back to their source records here to avoid inferring electrical unions.
    net_by_key: Dict[Tuple[str, str], str] = {}
    for item in (*design.zones, *design.pads):
        owner = str(item.get("id") or item.get("component_pad") or "")
        item_layers = [str(v) for v in item.get("layers", []) if str(v).endswith(".Cu")]
        if not item_layers:
            item_layers = [str(item.get("layer", ""))]
        for layer in item_layers:
            net_by_key[(owner, layer)] = str(item.get("net_name") or item.get("net") or "")
    keys = list(polygons)
    zone_keys = {(str(z.get("id", "")), str(z.get("layer", ""))) for z in design.zones}
    for pos, key_a in enumerate(keys):
        for key_b in keys[pos + 1:]:
            if key_a[1] != key_b[1] or net_by_key.get(key_a) != net_by_key.get(key_b):
                continue
            if not _bbox_overlaps(polygons[key_a], polygons[key_b]):
                continue
            if key_a in zone_keys and _polygon_strictly_contains(polygons[key_a], polygons[key_b]):
                areas[key_b] = 0.0
            elif key_b in zone_keys and _polygon_strictly_contains(polygons[key_b], polygons[key_a]):
                areas[key_a] = 0.0
            else:
                ambiguous.update((key_a, key_b))
    # Filled zones may already contain same-net routed copper. Without a robust
    # polygon union, even a possible overlap makes the zone area unsupported.
    for track in design.tracks:
        layer = str(track.get("layer", ""))
        net = str(track.get("net_name") or track.get("net") or "")
        start, end = _xy(track.get("start", [0, 0])), _xy(track.get("end", [0, 0]))
        half = max(float(track.get("width", 0.0)), 0.0) / 2.0
        track_box = [(min(start[0], end[0]) - half, min(start[1], end[1]) - half),
                     (max(start[0], end[0]) + half, min(start[1], end[1]) - half),
                     (max(start[0], end[0]) + half, max(start[1], end[1]) + half),
                     (min(start[0], end[0]) - half, max(start[1], end[1]) + half)]
        for key in zone_keys:
            if key in polygons and key[1] == layer and net_by_key.get(key) == net \
                    and _bbox_overlaps(polygons[key], track_box):
                ambiguous.add(key)
    return areas, ambiguous, len(polygons)


def _reference_overlaps_branch(
    design: DesignIR,
    return_net: str,
    layer: str,
    branch: Any,
) -> bool:
    """Require projected return copper beneath an explicit-reference branch."""

    midpoint = (
        (float(branch.start_mm[0]) + float(branch.end_mm[0])) / 2.0,
        (float(branch.start_mm[1]) + float(branch.end_mm[1])) / 2.0,
    )
    signal_half_width = max(float(branch.width_mm), 0.0) / 2.0
    for track in design.tracks:
        net = str(track.get("net_name") or track.get("net") or "")
        if net != return_net or str(track.get("layer", "")) != layer:
            continue
        return_half_width = max(float(track.get("width", 0.0)), 0.0) / 2.0
        if _distance_to_segment(midpoint, _xy(track["start"]), _xy(track["end"])) <= signal_half_width + return_half_width:
            return True
    for zone in design.zones:
        net = str(zone.get("net_name") or zone.get("net") or "")
        if net != return_net or str(zone.get("layer", "")) != layer:
            continue
        points = [_xy(value) for value in zone.get("points", zone.get("polygon", []))]
        if _point_in_polygon(midpoint, points):
            return True
    for pad in design.pads:
        net = str(pad.get("net_name") or pad.get("net") or "")
        layers = {str(value) for value in pad.get("layers", [])}
        pad_layer = str(pad.get("layer", ""))
        if net != return_net or (layer != pad_layer and layer not in layers and "*.Cu" not in layers):
            continue
        center = _xy(pad.get("at", [0.0, 0.0]))
        size = pad.get("size", [0.0, 0.0])
        width, height = (float(size), float(size)) if isinstance(size, (int, float)) else _xy(size)
        if abs(midpoint[0] - center[0]) <= width / 2.0 + signal_half_width and abs(midpoint[1] - center[1]) <= height / 2.0 + signal_half_width:
            return True
    return False


def estimate_branch_capacitance(
    design: DesignIR,
    spec: AnalysisSpec,
    branches: Sequence[Any],
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Estimate branch shunt C and loss tangent to one reference conductor."""

    capacitance = np.zeros(len(branches), dtype=float)
    loss_tangent = np.zeros(len(branches), dtype=float)
    copper_centers, dielectrics = stackup_profile(design)
    if len(copper_centers) < 2 or not dielectrics:
        return capacitance, loss_tangent, {
            "contract": "spike/distributed-capacitance/v1",
            "model": "hammerstad_jensen_single_reference",
            "status": "unsupported",
            "reason": "At least two copper layers and dielectric epsilon/thickness are required.",
            "total_capacitance_f": 0.0,
        }

    mode = str(spec.options.get("capacitance_model", "auto")).lower()
    if mode == "none" or spec.options.get("include_dielectric") is False:
        return capacitance, loss_tangent, {
            "contract": "spike/distributed-capacitance/v1",
            "model": "none",
            "status": "unsupported",
            "reason": "Capacitance extraction was disabled by the analysis request.",
            "total_capacitance_f": 0.0,
        }

    return_mode = str(spec.return_path.get("mode", "implicit"))
    return_net = (
        str(spec.return_path.get("net", ""))
        if return_mode in {"explicit", "isolated_secondary"}
        else ""
    )
    explicit_layers = _geometry_layers_for_net(design, return_net) if return_net else set()
    reference_layers: set[str] = set()
    estimated = 0
    skipped_via = 0
    skipped_reference = 0
    skipped_reference_geometry = 0
    loss_known = 0
    owner_areas, ambiguous_owners, source_geometry_count = _planar_owner_areas(design)
    branch_reference: Dict[int, Tuple[str, float, float, float | None]] = {}

    for index, branch in enumerate(branches):
        kind = str(branch.kind)
        if "via" in kind or "barrel" in kind:
            skipped_via += 1
            continue
        layer = str(branch.layer)
        layer_z = copper_centers.get(layer)
        if layer_z is None or float(branch.length_mm) <= 0:
            skipped_reference += 1
            continue
        candidates: Iterable[str]
        if return_net:
            candidates = (name for name in explicit_layers if name != layer and name in copper_centers)
        else:
            candidates = (name for name in copper_centers if name != layer)
        candidate_list = list(candidates)
        if return_net:
            candidate_list = [
                name for name in candidate_list
                if _reference_overlaps_branch(design, return_net, name, branch)
            ]
        if not candidate_list:
            skipped_reference += 1
            if return_net:
                skipped_reference_geometry += 1
            continue
        reference_layer = min(
            candidate_list, key=lambda name: abs(copper_centers[name] - layer_z)
        )
        dielectric = dielectric_between(
            layer_z, copper_centers[reference_layer], dielectrics
        )
        if dielectric is None:
            skipped_reference += 1
            continue
        epsilon_r, height_mm, tan_delta = dielectric
        value = estimate_line_capacitance_per_m(
            float(branch.width_mm), height_mm, epsilon_r
        ) * float(branch.length_mm) * 1e-3
        if kind.startswith("zone") or kind.startswith("pad"):
            # Replaced below by a source-area value counted once per owner.
            branch_reference[index] = (reference_layer, epsilon_r, height_mm, tan_delta)
        if not np.isfinite(value) or value <= 0:
            skipped_reference += 1
            continue
        capacitance[index] = value
        if tan_delta is not None:
            loss_tangent[index] = tan_delta
            loss_known += 1
        estimated += 1
        reference_layers.add(reference_layer)

    planar_groups: Dict[Tuple[str, str], List[int]] = {}
    for index, branch in enumerate(branches):
        if str(branch.kind).startswith(("zone", "pad")):
            planar_groups.setdefault((str(branch.source_id), str(branch.layer)), []).append(index)
    unsupported_planar = 0
    admitted_planar = 0
    for owner, indices in planar_groups.items():
        old_estimated = sum(capacitance[index] > 0 for index in indices)
        old_loss_known = sum(loss_tangent[index] > 0 for index in indices)
        capacitance[indices] = 0.0
        loss_tangent[indices] = 0.0
        estimated -= old_estimated
        loss_known -= old_loss_known
        references = [branch_reference.get(index) for index in indices]
        area_mm2 = owner_areas.get(owner)
        if (owner in ambiguous_owners or area_mm2 is None or area_mm2 <= 0
                or any(value is None for value in references)
                or len({value[:3] for value in references if value is not None}) != 1):
            unsupported_planar += 1
            skipped_reference += len(indices)
            continue
        reference_layer, epsilon_r, height_mm, tan_delta = references[0]  # type: ignore[misc]
        weights = np.asarray([max(float(branches[index].length_mm), 0.0) for index in indices])
        if float(np.sum(weights)) <= 0:
            unsupported_planar += 1
            continue
        owner_capacitance = EPSILON_0_F_M * epsilon_r * area_mm2 * 1e-3 / height_mm
        shares = owner_capacitance * weights / float(np.sum(weights))
        capacitance[indices] = shares
        if tan_delta is not None:
            loss_tangent[indices] = tan_delta
            loss_known += len(indices)
        estimated += len(indices)
        reference_layers.add(reference_layer)
        admitted_planar += 1

    # A mixed result would silently retain track C while dropping an
    # overlapping zone/pad owner, which is neither a union nor a bound. Fail
    # the entire capacitance estimate closed when any requested planar owner
    # cannot be uniquely counted.
    if unsupported_planar:
        capacitance[:] = 0.0
        loss_tangent[:] = 0.0
        estimated = 0
        loss_known = 0

    total = float(np.sum(capacitance))
    weighted_loss = float(np.sum(capacitance * loss_tangent) / total) if total > 0 else 0.0
    return capacitance, loss_tangent, {
        "contract": "spike/distributed-capacitance/v1",
        "model": "hammerstad_jensen_tracks_plus_unique_area_parallel_plate",
        "status": "approximate" if estimated else "unsupported",
        "reason": ("Zone/pad copper union or reference geometry is ambiguous; capacitance was omitted."
                   if unsupported_planar else ""),
        "reference_mode": "explicit_return_conductor" if return_net else "implicit_nearest_copper",
        "reference_net": return_net,
        "reference_layers": sorted(reference_layers),
        "estimated_branch_count": estimated,
        "skipped_via_branch_count": skipped_via,
        "skipped_reference_branch_count": skipped_reference,
        "skipped_reference_geometry_branch_count": skipped_reference_geometry,
        "branch_coverage": estimated / max(len(branches), 1),
        "loss_tangent_branch_coverage": loss_known / max(estimated, 1),
        "effective_loss_tangent": weighted_loss,
        "total_capacitance_f": total,
        "planar_source_geometry_count": source_geometry_count,
        "planar_source_count": len(planar_groups),
        "admitted_planar_source_count": admitted_planar,
        "unsupported_planar_source_count": unsupported_planar,
        "validity": [
            "single-reference quasi-static microstrip approximation",
            "zone/pad capacitance uses each admitted source copper area once with no fringing correction",
            "ambiguous or unsupported zone/pad source geometry and overlap are omitted",
            "zero conductor-thickness correction",
            "no via/antipad capacitance without a validated via field model",
            "not a multiconductor capacitance matrix",
        ],
    }
