"""Source-bound full reference-zone geometry with explicit circular antipads."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import content_digest
from .via_transition_geometry import CONTRACT as VIA_GEOMETRY_CONTRACT


CONTRACT = "spike/pcb-reference-plane-antipad-geometry/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0007"
MAX_REGIONS = 64
MAX_RING_POINTS = 4096


class ReferencePlaneAntipadGeometryError(ValueError):
    """Raised when a complete source plane cannot enter the exact contract."""

    code = ERROR_CODE


def _cross(left: Sequence[float], middle: Sequence[float], right: Sequence[float]) -> float:
    return ((float(middle[0]) - float(left[0])) * (float(right[1]) - float(middle[1]))
            - (float(middle[1]) - float(left[1])) * (float(right[0]) - float(middle[0])))


def _signed_area(points: Sequence[Sequence[float]]) -> float:
    return math.fsum(float(points[index][0]) * float(points[(index + 1) % len(points)][1])
                     - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
                     for index in range(len(points))) / 2.0


def _orientation(left: Sequence[float], middle: Sequence[float], right: Sequence[float]) -> int:
    value = _cross(left, middle, right)
    return 1 if value > 0.0 else -1 if value < 0.0 else 0


def _segments_intersect(a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float]) -> bool:
    first, second = _orientation(a, b, c), _orientation(a, b, d)
    third, fourth = _orientation(c, d, a), _orientation(c, d, b)
    return first * second <= 0 and third * fourth <= 0


def _canonical_convex_ring(raw: Sequence[Sequence[float]]) -> list[list[float]]:
    if not 3 <= len(raw) <= MAX_RING_POINTS:
        raise ReferencePlaneAntipadGeometryError("Reference-zone ring is outside the bounded point budget.")
    points = [[float(value) for value in point] for point in raw]
    if any(len(point) != 2 or any(not math.isfinite(value) for value in point) for point in points):
        raise ReferencePlaneAntipadGeometryError("Reference-zone ring requires finite two-dimensional points.")
    if any(points[index] == points[(index + 1) % len(points)] for index in range(len(points))):
        raise ReferencePlaneAntipadGeometryError("Reference-zone ring contains a zero-length edge.")
    for index in range(len(points)):
        for other in range(index + 1, len(points)):
            if other in {index, index + 1} or (index == 0 and other == len(points) - 1):
                continue
            if _segments_intersect(points[index], points[(index + 1) % len(points)],
                                   points[other], points[(other + 1) % len(points)]):
                raise ReferencePlaneAntipadGeometryError("Reference-zone ring is self-intersecting.")
    area = _signed_area(points)
    if area == 0.0:
        raise ReferencePlaneAntipadGeometryError("Reference-zone ring has zero area.")
    if area < 0.0:
        points.reverse()
    turns = [_cross(points[index], points[(index + 1) % len(points)],
                    points[(index + 2) % len(points)]) for index in range(len(points))]
    if any(value <= 0.0 for value in turns):
        raise ReferencePlaneAntipadGeometryError(
            "Reference-plane geometry v1 requires a strictly convex straight-edged source zone."
        )
    start = min(range(len(points)), key=lambda index: (points[index][0], points[index][1]))
    return points[start:] + points[:start]


def _edge_distance(center: Sequence[float], left: Sequence[float], right: Sequence[float]) -> float:
    dx, dy = float(right[0]) - float(left[0]), float(right[1]) - float(left[1])
    length = math.hypot(dx, dy)
    return abs(dx * (float(center[1]) - float(left[1]))
               - dy * (float(center[0]) - float(left[0]))) / length


def build_reference_plane_antipad_geometry(
    design: DesignIRV2, *, via_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Capture each complete admitted source zone and subtract its explicit antipad."""

    if via_geometry.get("contract") != VIA_GEOMETRY_CONTRACT:
        raise ReferencePlaneAntipadGeometryError("Full-plane geometry requires via-transition geometry v1.")
    if via_geometry.get("design_id") != design.design_id:
        raise ReferencePlaneAntipadGeometryError("Via geometry and source design identities differ.")
    antipads = via_geometry.get("antipads")
    if not isinstance(antipads, list) or not 1 <= len(antipads) <= MAX_REGIONS:
        raise ReferencePlaneAntipadGeometryError("Full-plane geometry requires bounded explicit antipads.")
    zones = {item.id: item for item in design.zones}
    layers = {item.id: item for item in design.layers}
    lands = {item["layer_id"]: item for item in via_geometry["lands"]}
    center = [float(value) for value in via_geometry["center_mm"]]
    regions = []
    for index, antipad in enumerate(antipads):
        zone = zones.get(antipad["reference_zone_id"])
        layer = layers.get(antipad["layer_id"])
        land = lands.get(antipad["layer_id"])
        if (zone is None or layer is None or land is None or zone.net_id != antipad["reference_net_id"]
                or antipad["layer_id"] not in zone.layer_ids):
            raise ReferencePlaneAntipadGeometryError("Reference zone/net/layer ownership is inconsistent.")
        if zone.boundary_rings or zone.holes_mm or len(zone.outlines_mm) != 1:
            raise ReferencePlaneAntipadGeometryError(
                "Reference-plane geometry v1 requires one hole-free straight-edged source-zone outline."
            )
        ring = _canonical_convex_ring(zone.outlines_mm[0])
        radius = float(antipad["diameter_mm"]) / 2.0
        minimum_margin = min(_edge_distance(center, ring[position], ring[(position + 1) % len(ring)])
                             - radius for position in range(len(ring)))
        if minimum_margin <= 0.0:
            raise ReferencePlaneAntipadGeometryError(
                "The antipad must be strictly inside the complete source-zone boundary."
            )
        z_min, z_max = float(land["z_min_mm"]), float(land["z_max_mm"])
        source_zone = {"zone_id": zone.id, "source_zone_id": zone.source_id,
                       "net_id": zone.net_id, "layer_id": antipad["layer_id"],
                       "outer_ring_mm": ring, "source_hole_rings_mm": []}
        hole = {"antipad_id": antipad["source_id"], "source_id": antipad["source_id"],
                "center_mm": center, "radius_mm": radius,
                "signal_clearance_mm": float(antipad["clearance_mm"])}
        exact_area = abs(_signed_area(ring)) - math.pi * radius * radius
        resolved = {"source_zone": source_zone, "antipad_holes": [hole],
                    "z_min_mm": z_min, "z_max_mm": z_max}
        regions.append({"region_id": f"reference:{index}:{zone.id}", **resolved,
                        "source_zone_sha256": content_digest(source_zone),
                        "resolved_region_sha256": content_digest(resolved),
                        "minimum_antipad_to_outer_boundary_mm": minimum_margin,
                        "exact_area_mm2": exact_area,
                        "exact_volume_mm3": exact_area * (z_max - z_min)})
    report: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {"design_contract": "spike/design-ir/v2",
                   "design_sha256": content_digest(design.to_dict()),
                   "via_geometry_contract": VIA_GEOMETRY_CONTRACT,
                   "via_geometry_sha256": content_digest(via_geometry),
                   "design_id": design.design_id, "via_id": via_geometry["via_id"],
                   "source_via_id": via_geometry["source_via_id"]},
        "regions": regions,
        "topology_audit": {"complete_source_zones_captured": True,
                           "strictly_convex_source_zones": True,
                           "existing_source_holes": 0,
                           "explicit_antipad_holes": len(regions),
                           "discrete_watertightness_checked": False},
        "qualification": {"state": "exact_full_source_zone_minus_explicit_antipad",
                          "native_handoff_ready": False, "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }
    return report


def validate_reference_plane_antipad_geometry(
    report: Mapping[str, Any], *, design: DesignIRV2, via_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Regenerate the bounded analytic artifact and reject stale or promoted claims."""

    if report.get("contract") != CONTRACT:
        raise ReferencePlaneAntipadGeometryError("Unexpected reference-plane geometry contract.")
    regenerated = build_reference_plane_antipad_geometry(design, via_geometry=via_geometry)
    if dict(report) != regenerated:
        raise ReferencePlaneAntipadGeometryError(
            "Reference-plane antipad geometry does not match deterministic regeneration."
        )
    return regenerated


__all__ = ["CONTRACT", "ERROR_CODE", "ReferencePlaneAntipadGeometryError",
           "build_reference_plane_antipad_geometry", "validate_reference_plane_antipad_geometry"]
