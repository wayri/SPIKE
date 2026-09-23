"""Deterministic closed mesh for a complete convex source zone minus one antipad."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_geometry import CONTRACT as GEOMETRY_CONTRACT
from .via_transition_mesh import (
    MAX_SERIALIZED_BYTES, MAX_TRIANGLES, MAX_VERTICES, _audit, _triangle_distance_2d,
)


CONTRACT = "spike/pcb-reference-plane-antipad-mesh/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0008"
MIN_RADIAL_SEGMENTS = 8
MAX_RADIAL_SEGMENTS = 128


class ReferencePlaneAntipadMeshError(ValueError):
    """Raised when complete reference-plane geometry cannot form a closed mesh."""

    code = ERROR_CODE


def _cross(left: Sequence[float], right: Sequence[float]) -> float:
    return float(left[0]) * float(right[1]) - float(left[1]) * float(right[0])


def _subtract(left: Sequence[float], right: Sequence[float]) -> tuple[float, float]:
    return float(left[0]) - float(right[0]), float(left[1]) - float(right[1])


def _ray_boundary(center: Sequence[float], angle: float, ring: Sequence[Sequence[float]]) -> list[float]:
    direction = (math.cos(angle), math.sin(angle))
    candidates = []
    for index, left in enumerate(ring):
        right = ring[(index + 1) % len(ring)]
        edge = _subtract(right, left)
        denominator = _cross(direction, edge)
        if denominator == 0.0:
            continue
        offset = _subtract(left, center)
        distance = _cross(offset, edge) / denominator
        ratio = _cross(offset, direction) / denominator
        if distance > 0.0 and -1e-12 <= ratio <= 1.0 + 1e-12:
            candidates.append(distance)
    if not candidates:
        raise ReferencePlaneAntipadMeshError("A radial constraint did not intersect the convex source boundary.")
    distance = min(candidates)
    point = [float(center[0]) + distance * direction[0], float(center[1]) + distance * direction[1]]
    for vertex in ring:
        if math.hypot(point[0] - float(vertex[0]), point[1] - float(vertex[1])) <= 1e-10:
            return [float(vertex[0]), float(vertex[1])]
    return point


class _Builder:
    def __init__(self) -> None:
        self.vertices: list[list[float]] = []
        self.triangles: list[Dict[str, Any]] = []
        self._vertices: dict[tuple[float, float, float], int] = {}

    def vertex(self, point: Sequence[float], z_mm: float) -> int:
        key = (float(point[0]), float(point[1]), float(z_mm))
        if key not in self._vertices:
            if len(self.vertices) >= MAX_VERTICES:
                raise ReferencePlaneAntipadMeshError("Reference-plane mesh vertex budget exceeded.")
            self._vertices[key] = len(self.vertices)
            self.vertices.append(list(key))
        return self._vertices[key]

    def triangle(self, domain_id: str, indices: Sequence[int], role: str, sources: Sequence[str]) -> None:
        if len(self.triangles) >= MAX_TRIANGLES:
            raise ReferencePlaneAntipadMeshError("Reference-plane mesh triangle budget exceeded.")
        self.triangles.append({"id": f"triangle:{len(self.triangles)}", "domain_id": domain_id,
                               "vertex_indices": list(indices), "surface_role": role,
                               "source_ids": sorted(set(sources))})


def _angle(center: Sequence[float], point: Sequence[float]) -> float:
    return math.atan2(float(point[1]) - float(center[1]), float(point[0]) - float(center[0])) % (2.0 * math.pi)


def _contains_point(point: Sequence[float], triangle: Sequence[Sequence[float]]) -> bool:
    signs = []
    for index in range(3):
        left, right = triangle[index], triangle[(index + 1) % 3]
        signs.append(_cross(_subtract(right, left), _subtract(point, left)))
    return (all(value >= 0.0 for value in signs) or all(value <= 0.0 for value in signs))


def _build_region(builder: _Builder, region: Mapping[str, Any], radial_segments: int) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    domain_id = region["region_id"]
    source_zone = region["source_zone"]
    ring = source_zone["outer_ring_mm"]
    hole = region["antipad_holes"][0]
    center, exact_radius = hole["center_mm"], float(hole["radius_mm"])
    radius = exact_radius / math.cos(math.pi / radial_segments)
    z_min, z_max = float(region["z_min_mm"]), float(region["z_max_mm"])
    step = 2.0 * math.pi / radial_segments
    radial_angles = [index * step for index in range(radial_segments)]
    intersections = [_ray_boundary(center, angle, ring) for angle in radial_angles]
    original = sorted(((_angle(center, point), list(point)) for point in ring), key=lambda item: item[0])
    outer_points = sorted([*(item for item in intersections), *(list(point) for point in ring)],
                          key=lambda point: _angle(center, point))
    deduplicated = []
    for point in outer_points:
        if (not deduplicated or math.hypot(point[0] - deduplicated[-1][0],
                                           point[1] - deduplicated[-1][1]) > 1e-10):
            deduplicated.append(point)
    if (len(deduplicated) > 1 and math.hypot(deduplicated[0][0] - deduplicated[-1][0],
                                             deduplicated[0][1] - deduplicated[-1][1]) <= 1e-10):
        deduplicated.pop()
    hole_points = [[float(center[0]) + radius * math.cos(angle),
                    float(center[1]) + radius * math.sin(angle)] for angle in radial_angles]
    outer_bottom = [builder.vertex(point, z_min) for point in deduplicated]
    outer_top = [builder.vertex(point, z_max) for point in deduplicated]
    hole_bottom = [builder.vertex(point, z_min) for point in hole_points]
    hole_top = [builder.vertex(point, z_max) for point in hole_points]
    sources = [source_zone["zone_id"], source_zone["source_zone_id"], hole["source_id"]]
    for index in range(radial_segments):
        lower, upper = radial_angles[index], radial_angles[(index + 1) % radial_segments]
        if index == radial_segments - 1:
            middle = [point for angle_value, point in original if angle_value > lower or angle_value < upper]
        else:
            middle = [point for angle_value, point in original if lower < angle_value < upper]
        chain = [intersections[index], *middle, intersections[(index + 1) % radial_segments]]
        bottom_chain = [builder.vertex(point, z_min) for point in chain]
        top_chain = [builder.vertex(point, z_max) for point in chain]
        for position in range(len(chain) - 1):
            builder.triangle(domain_id, (hole_top[index], top_chain[position], top_chain[position + 1]),
                             "reference_zone_upper_face", sources)
            builder.triangle(domain_id, (hole_bottom[index], bottom_chain[position + 1], bottom_chain[position]),
                             "reference_zone_lower_face", sources)
        following = (index + 1) % radial_segments
        builder.triangle(domain_id, (hole_top[index], top_chain[-1], hole_top[following]),
                         "reference_zone_upper_face", sources)
        builder.triangle(domain_id, (hole_bottom[index], hole_bottom[following], bottom_chain[-1]),
                         "reference_zone_lower_face", sources)
    for index in range(len(deduplicated)):
        following = (index + 1) % len(deduplicated)
        builder.triangle(domain_id, (outer_bottom[index], outer_bottom[following], outer_top[following]),
                         "reference_zone_outer_boundary", sources)
        builder.triangle(domain_id, (outer_bottom[index], outer_top[following], outer_top[index]),
                         "reference_zone_outer_boundary", sources)
    for index in range(radial_segments):
        following = (index + 1) % radial_segments
        builder.triangle(domain_id, (hole_bottom[index], hole_top[following], hole_bottom[following]),
                         "antipad_void_boundary", sources)
        builder.triangle(domain_id, (hole_bottom[index], hole_top[index], hole_top[following]),
                         "antipad_void_boundary", sources)
    triangle_ids = [item["id"] for item in builder.triangles if item["domain_id"] == domain_id]
    domain = {"id": domain_id, "kind": "reference_plane_full_zone", "net_id": source_zone["net_id"],
              "layer_ids": [source_zone["layer_id"]], "source_ids": sorted(set(sources)),
              "triangle_ids": triangle_ids, "reference_zone_id": source_zone["zone_id"],
              "source_zone_sha256": region["source_zone_sha256"],
              "resolved_region_sha256": region["resolved_region_sha256"],
              "antipad_radius_mm": exact_radius}
    loops = [
        {"loop_id": f"{domain_id}:outer:lower", "domain_id": domain_id, "role": "source_outer",
         "z_mm": z_min, "vertex_indices": outer_bottom, "source_ids": sorted(set(sources[:2]))},
        {"loop_id": f"{domain_id}:antipad:lower", "domain_id": domain_id, "role": "antipad_hole",
         "z_mm": z_min, "vertex_indices": hole_bottom, "source_ids": [hole["source_id"]]},
    ]
    return domain, loops


def build_reference_plane_antipad_mesh(
    geometry: Mapping[str, Any], *, radial_segments: int = 32
) -> Dict[str, Any]:
    """Build a conservative watertight full-zone mesh without solver semantics."""

    if geometry.get("contract") != GEOMETRY_CONTRACT:
        raise ReferencePlaneAntipadMeshError("Reference-plane mesh requires exact full-zone geometry v1.")
    if (isinstance(radial_segments, bool) or not isinstance(radial_segments, int)
            or radial_segments % 4 or not MIN_RADIAL_SEGMENTS <= radial_segments <= MAX_RADIAL_SEGMENTS):
        raise ReferencePlaneAntipadMeshError("radial_segments must be a bounded integer multiple of four.")
    builder = _Builder()
    domains, loops = [], []
    for region in geometry["regions"]:
        domain, region_loops = _build_region(builder, region, radial_segments)
        domains.append(domain); loops.extend(region_loops)
    mesh: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {"geometry_contract": GEOMETRY_CONTRACT, "geometry_sha256": content_digest(geometry),
                   "design_id": geometry["source"]["design_id"], "via_id": geometry["source"]["via_id"],
                   "source_via_id": geometry["source"]["source_via_id"]},
        "center_mm": list(geometry["regions"][0]["antipad_holes"][0]["center_mm"]),
        "radial_segments": radial_segments,
        "tessellation": {"coordinate_tolerance_mm": 1e-9,
                         "antipad_boundary": "circumscribed",
                         "source_outer_boundary": "exact_constrained_segments"},
        "vertices_mm": builder.vertices,
        "triangles": builder.triangles, "domains": domains, "boundary_loops": loops,
        "resources": {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                      "actual_vertices": len(builder.vertices), "actual_triangles": len(builder.triangles),
                      "max_serialized_bytes": MAX_SERIALIZED_BYTES},
        "qualification": {"state": "full_reference_zone_geometry_mesh_only",
                          "native_handoff_ready": False, "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }
    audit = _audit(mesh)
    radii = {item["id"]: float(item["antipad_radius_mm"]) for item in domains}
    tolerance = float(mesh["tessellation"]["coordinate_tolerance_mm"])
    violations = 0
    for triangle in builder.triangles:
        points = [builder.vertices[index] for index in triangle["vertex_indices"]]
        if (_contains_point(mesh["center_mm"], points)
                or _triangle_distance_2d(tuple(mesh["center_mm"]), points)
                < radii[triangle["domain_id"]] - tolerance):
            violations += 1
    audit["reference_void_violations"] = violations
    audit["passed"] = audit["passed"] and violations == 0
    mesh["topology_audit"] = audit
    if not audit["passed"]:
        raise ReferencePlaneAntipadMeshError("Complete reference-plane mesh topology audit failed.")
    if len(json.dumps(mesh, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ReferencePlaneAntipadMeshError("Reference-plane mesh serialized-byte budget exceeded.")
    return mesh


def validate_reference_plane_antipad_mesh(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Regenerate and compare the complete mesh to reject stale topology claims."""

    try:
        regenerated = build_reference_plane_antipad_mesh(
            source_geometry, radial_segments=mesh["radial_segments"]
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReferencePlaneAntipadMeshError):
            raise
        raise ReferencePlaneAntipadMeshError("Malformed reference-plane mesh evidence.") from error
    if dict(mesh) != regenerated:
        raise ReferencePlaneAntipadMeshError("Reference-plane mesh does not match deterministic regeneration.")
    return regenerated


__all__ = ["CONTRACT", "ERROR_CODE", "ReferencePlaneAntipadMeshError",
           "build_reference_plane_antipad_mesh", "validate_reference_plane_antipad_mesh"]
