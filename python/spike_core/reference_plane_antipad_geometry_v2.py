"""General straight-segment reference-plane topology on the native exact grid."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

from python import spike_peec_native as native

from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import content_digest
from .via_transition_geometry import CONTRACT as VIA_GEOMETRY_CONTRACT


CONTRACT = "spike/pcb-reference-plane-antipad-geometry/v2"
ERROR_CODE = "SPIKE-BE-MESH-E-0011"
GRID_MM = 0.000001
MAX_REGIONS = 64
MAX_TOTAL_POINTS = 16384


class ReferencePlaneAntipadGeometryV2Error(ValueError):
    code = ERROR_CODE


def _point(values: Sequence[float]) -> Any:
    item = native.PlanarPoint2()
    item.x, item.y = float(values[0]), float(values[1])
    return item


def _inside(point: tuple[int, int], ring: Sequence[Any]) -> bool:
    winding = 0
    for index, first in enumerate(ring):
        second = ring[(index + 1) % len(ring)]
        cross = ((second.x - first.x) * (point[1] - first.y)
                 - (second.y - first.y) * (point[0] - first.x))
        if cross == 0 and min(first.x, second.x) <= point[0] <= max(first.x, second.x) \
                and min(first.y, second.y) <= point[1] <= max(first.y, second.y):
            raise ReferencePlaneAntipadGeometryV2Error("Antipad center touches a source boundary.")
        if first.y <= point[1] < second.y and cross > 0:
            winding += 1
        elif second.y <= point[1] < first.y and cross < 0:
            winding -= 1
    return winding != 0


def _circle_clear(ring: Sequence[Any], center: tuple[int, int], radius: int) -> bool:
    radius2 = radius * radius
    for index, first in enumerate(ring):
        second = ring[(index + 1) % len(ring)]
        dx, dy = second.x - first.x, second.y - first.y
        px, py = center[0] - first.x, center[1] - first.y
        length2, projection = dx * dx + dy * dy, px * dx + py * dy
        if projection <= 0:
            separated = px * px + py * py > radius2
        elif projection >= length2:
            qx, qy = center[0] - second.x, center[1] - second.y
            separated = qx * qx + qy * qy > radius2
        else:
            cross = dx * py - dy * px
            separated = cross * cross > radius2 * length2
        if not separated:
            return False
    return True


def _ring_mm(ring: Any) -> list[list[float]]:
    return [[item.x * GRID_MM, item.y * GRID_MM] for item in ring.points]


def build_reference_plane_antipad_geometry_v2(
    design: DesignIRV2, *, via_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    if via_geometry.get("contract") != VIA_GEOMETRY_CONTRACT or via_geometry.get("design_id") != design.design_id:
        raise ReferencePlaneAntipadGeometryV2Error("General plane topology requires matching via geometry v1.")
    antipads = via_geometry.get("antipads")
    if not isinstance(antipads, list) or not 1 <= len(antipads) <= MAX_REGIONS:
        raise ReferencePlaneAntipadGeometryV2Error("General plane topology requires bounded explicit antipads.")
    zones, layers = {item.id: item for item in design.zones}, {item.id: item for item in design.layers}
    lands = {item["layer_id"]: item for item in via_geometry["lands"]}
    regions = []
    for index, antipad in enumerate(antipads):
        zone, layer, land = (zones.get(antipad["reference_zone_id"]),
                             layers.get(antipad["layer_id"]), lands.get(antipad["layer_id"]))
        if (zone is None or layer is None or land is None or zone.net_id != antipad["reference_net_id"]
                or antipad["layer_id"] not in zone.layer_ids):
            raise ReferencePlaneAntipadGeometryV2Error("Reference zone/net/layer ownership is inconsistent.")
        if zone.boundary_rings:
            raise ReferencePlaneAntipadGeometryV2Error(
                "Geometry v2 admits straight segments only; exact boundary arcs require the bounded curve gate."
            )
        if len(zone.outlines_mm) != 1:
            raise ReferencePlaneAntipadGeometryV2Error("Geometry v2 requires one connected source-zone outer ring.")
        try:
            topology = native.canonicalize_planar_region(
                [_point(item) for item in zone.outlines_mm[0]],
                [[_point(item) for item in ring] for ring in zone.holes_mm],
                GRID_MM, MAX_TOTAL_POINTS,
            )
            center = tuple(int(round(float(value) / GRID_MM)) for value in via_geometry["center_mm"])
            radius_grid = (float(antipad["diameter_mm"]) / 2.0) / GRID_MM
            radius = int(round(radius_grid))
            if any(abs(float(value) / GRID_MM - center[axis]) > 1e-6
                   for axis, value in enumerate(via_geometry["center_mm"])) \
                    or abs(radius_grid - radius) > 1e-6 or radius <= 0:
                raise ReferencePlaneAntipadGeometryV2Error("Antipad circle is off-grid or invalid.")
            if not _inside(center, topology.outer.points) or not _circle_clear(topology.outer.points, center, radius):
                raise ReferencePlaneAntipadGeometryV2Error("Antipad is not strictly inside the source outer ring.")
            for cutout in topology.cutouts:
                if (_inside(center, cutout.points) or not _circle_clear(cutout.points, center, radius)
                        or any((item.x - center[0]) ** 2 + (item.y - center[1]) ** 2 <= radius * radius
                               for item in cutout.points)):
                    raise ReferencePlaneAntipadGeometryV2Error("Antipad intersects, contains, or occupies a source cutout.")
        except ReferencePlaneAntipadGeometryV2Error:
            raise
        except (TypeError, ValueError) as error:
            raise ReferencePlaneAntipadGeometryV2Error("Native exact-grid source topology admission failed.") from error
        outer_mm, holes_mm = _ring_mm(topology.outer), [_ring_mm(item) for item in topology.cutouts]
        source_zone = {"zone_id": zone.id, "source_zone_id": zone.source_id, "net_id": zone.net_id,
                       "layer_id": antipad["layer_id"], "outer_ring_mm": outer_mm,
                       "source_hole_rings_mm": holes_mm, "canonical_winding": "outer_ccw_cutouts_cw"}
        hole = {"antipad_id": antipad["source_id"], "source_id": antipad["source_id"],
                "center_mm": [center[0] * GRID_MM, center[1] * GRID_MM],
                "radius_mm": radius * GRID_MM, "signal_clearance_mm": float(antipad["clearance_mm"])}
        z_min, z_max = float(land["z_min_mm"]), float(land["z_max_mm"])
        area = float(topology.copper_area_mm2) - math.pi * hole["radius_mm"] ** 2
        resolved = {"source_zone": source_zone, "antipad_holes": [hole],
                    "z_min_mm": z_min, "z_max_mm": z_max}
        regions.append({"region_id": f"reference-v2:{index}:{zone.id}", **resolved,
                        "source_zone_sha256": content_digest(source_zone),
                        "resolved_region_sha256": content_digest(resolved),
                        "exact_polygon_area_mm2": float(topology.copper_area_mm2),
                        "analytic_resolved_area_mm2": area,
                        "analytic_resolved_volume_mm3": area * (z_max - z_min)})
    return {
        "contract": CONTRACT,
        "source": {"design_contract": "spike/design-ir/v2", "design_sha256": content_digest(design.to_dict()),
                   "via_geometry_contract": VIA_GEOMETRY_CONTRACT, "via_geometry_sha256": content_digest(via_geometry),
                   "design_id": design.design_id, "via_id": via_geometry["via_id"],
                   "source_via_id": via_geometry["source_via_id"]},
        "topology_policy": {"coordinate_grid_mm": GRID_MM, "predicate": "exact_integer_or_fail_closed",
                            "curve_admission": "straight_segments_only", "maximum_total_points": MAX_TOTAL_POINTS},
        "regions": regions,
        "topology_audit": {"complete_source_zones_captured": True, "simple_outer_rings": len(regions),
                           "existing_source_cutouts": sum(len(item["source_zone"]["source_hole_rings_mm"])
                                                           for item in regions),
                           "explicit_antipad_holes": len(regions), "strict_separation_checked": True,
                           "discrete_watertightness_checked": False},
        "qualification": {"state": "general_straight_segment_plane_topology_only",
                          "mesh_topology_admitted": False, "native_mesh_handoff_ready": False,
                          "physics_convergence_performed": False, "capacitance_ready": False,
                          "si_ready": False, "solver_ready": False},
    }


def validate_reference_plane_antipad_geometry_v2(
    report: Mapping[str, Any], *, design: DesignIRV2, via_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    regenerated = build_reference_plane_antipad_geometry_v2(design, via_geometry=via_geometry)
    if dict(report) != regenerated:
        raise ReferencePlaneAntipadGeometryV2Error("General plane topology does not match deterministic regeneration.")
    return regenerated


__all__ = ["CONTRACT", "ERROR_CODE", "ReferencePlaneAntipadGeometryV2Error",
           "build_reference_plane_antipad_geometry_v2", "validate_reference_plane_antipad_geometry_v2"]
