"""Validity-bounded single-reference PCB capacitance estimates.

This module does not replace a panel/BEM electrostatic field solver. It creates
an explicit engineering estimate for routed planar copper when a physical
stackup and reference conductor can be identified. Unsupported geometry is
counted and reported instead of receiving a fabricated capacitance.
"""

from __future__ import annotations

from math import hypot, log, pi, sqrt
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

from .contracts import AnalysisSpec, DesignIR, ValidationIssue


EPSILON_0_F_M = 8.8541878128e-12
LIGHT_SPEED_M_S = 299_792_458.0


def zone_pad_mesh_dependence_issue(branches: Sequence[Any],
                                   physical_indices: Sequence[int],
                                   volume_extraction: bool) -> ValidationIssue | None:
    """Keep the current internal-edge C limitation explicit to AC consumers."""
    if not volume_extraction or not any(
        branches[index].kind in {"zone", "pad"} for index in physical_indices
    ):
        return None
    return ValidationIssue(
        "PEEC_ZONE_PAD_CAPACITANCE_MESH_DEPENDENT", "warning",
        "Zone/pad capacitance currently sums microstrip estimates on internal mesh links; refinement can change the total without changing copper geometry.",
        suggestion="Do not use this capacitance for bandwidth sign-off; compare mesh refinements and use a validated electrostatic extractor.",
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
            value *= 0.5
        if not np.isfinite(value) or value <= 0:
            skipped_reference += 1
            continue
        capacitance[index] = value
        if tan_delta is not None:
            loss_tangent[index] = tan_delta
            loss_known += 1
        estimated += 1
        reference_layers.add(reference_layer)

    total = float(np.sum(capacitance))
    weighted_loss = float(np.sum(capacitance * loss_tangent) / total) if total > 0 else 0.0
    return capacitance, loss_tangent, {
        "contract": "spike/distributed-capacitance/v1",
        "model": "hammerstad_jensen_single_reference",
        "status": "approximate" if estimated else "unsupported",
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
        "validity": [
            "single-reference quasi-static microstrip approximation",
            "zero conductor-thickness correction",
            "no via/antipad capacitance without a validated via field model",
            "not a multiconductor capacitance matrix",
        ],
    }
