"""Generalized exact-grid plane mesh for straight or bounded-flattened regions."""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Dict, Mapping, Sequence

from python import spike_peec_native as native

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_geometry_v2 import CONTRACT as GEOMETRY_V2_CONTRACT
from .reference_plane_antipad_geometry_v3 import CONTRACT as GEOMETRY_V3_CONTRACT
from .via_transition_mesh import MAX_SERIALIZED_BYTES, MAX_TRIANGLES, MAX_VERTICES, _audit


CONTRACT = "spike/pcb-reference-plane-antipad-mesh/v2"
ERROR_CODE = "SPIKE-BE-MESH-E-0013"
GRID_MM = 0.000001
MIN_RADIAL_SEGMENTS = 8
MAX_RADIAL_SEGMENTS = 128
MAX_PLANAR_VERTICES = 4096
MAX_PLANAR_TRIANGLES = 8192
MAX_WORK_STEPS = 16777216
CANCELLATION_POLL_INTERVAL = 1024


class ReferencePlaneAntipadMeshV2Error(ValueError):
    code = ERROR_CODE


def _point(values: Sequence[float]) -> Any:
    item = native.PlanarPoint2()
    item.x, item.y = float(values[0]), float(values[1])
    return item


def _grid(values: Sequence[float]) -> tuple[int, int]:
    result = tuple(int(round(float(value) / GRID_MM)) for value in values)
    if any(abs(float(values[index]) / GRID_MM - result[index]) > 1e-6 for index in range(2)):
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh input contains an off-grid point.")
    return result  # type: ignore[return-value]


def _conservative_antipad_ring(
    center_mm: Sequence[float], radius_mm: float, radial_segments: int,
) -> tuple[list[list[float]], int]:
    center = _grid(center_mm)
    radius_grid = float(radius_mm) / GRID_MM
    radius = int(round(radius_grid))
    if abs(radius_grid - radius) > 1e-6 or radius <= 0:
        raise ReferencePlaneAntipadMeshV2Error("Antipad radius is off-grid or invalid.")
    base = radius / math.cos(math.pi / radial_segments)
    for inflation in range(33):
        candidate = []
        for index in range(radial_segments):
            angle = 2.0 * math.pi * index / radial_segments
            candidate.append((center[0] + int(round((base + inflation) * math.cos(angle))),
                              center[1] + int(round((base + inflation) * math.sin(angle)))))
        if len(set(candidate)) != radial_segments:
            continue
        conservative = True
        for index, first in enumerate(candidate):
            second = candidate[(index + 1) % radial_segments]
            dx, dy = second[0] - first[0], second[1] - first[1]
            px, py = center[0] - first[0], center[1] - first[1]
            length2 = dx * dx + dy * dy
            projection = px * dx + py * dy
            cross = dx * py - dy * px
            if (length2 <= 0 or not 0 <= projection <= length2
                    or cross * cross < radius * radius * length2):
                conservative = False
                break
        if conservative:
            return [[x * GRID_MM, y * GRID_MM] for x, y in candidate], inflation
    raise ReferencePlaneAntipadMeshV2Error(
        "A bounded exact-grid circumscribed antipad constraint could not be formed."
    )


class _Budget:
    def __init__(self, maximum: int, cancel_check: Callable[[], bool] | None) -> None:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_WORK_STEPS:
            raise ReferencePlaneAntipadMeshV2Error("maximum_work_steps is outside the production policy.")
        self.maximum = maximum
        self.actual = 0
        self.cancel_check = cancel_check
        self.poll()

    def poll(self) -> None:
        if self.cancel_check is not None and bool(self.cancel_check()):
            raise ReferencePlaneAntipadMeshV2Error("Generalized reference-plane meshing was cancelled.")

    def consume(self, amount: int = 1) -> None:
        self.actual += amount
        if self.actual > self.maximum:
            raise ReferencePlaneAntipadMeshV2Error("Generalized mesh deterministic work budget exceeded.")
        if self.actual % CANCELLATION_POLL_INTERVAL == 0:
            self.poll()


def _source_rings(region: Mapping[str, Any], geometry_contract: str) -> tuple[list, list]:
    source = region["source_zone"]
    if geometry_contract == GEOMETRY_V2_CONTRACT:
        return source["outer_ring_mm"], source["source_hole_rings_mm"]
    return source["flattened_outer_ring_mm"], source["flattened_source_hole_rings_mm"]


def _same_loop(points: set[tuple[int, int]], ring: Sequence[Sequence[float]]) -> bool:
    return points == {_grid(item) for item in ring}


def _build_region(
    region: Mapping[str, Any], geometry_contract: str, radial_segments: int,
    budget: _Budget, vertices: list[list[float]], triangles: list[Dict[str, Any]],
    loops: list[Dict[str, Any]],
) -> Dict[str, Any]:
    outer, source_holes = _source_rings(region, geometry_contract)
    antipad = region["antipad_holes"][0]
    antipad_ring, inflation_grid = _conservative_antipad_ring(
        antipad["center_mm"], float(antipad["radius_mm"]), radial_segments)
    try:
        topology = native.canonicalize_planar_region(
            [_point(item) for item in outer],
            [[_point(item) for item in ring] for ring in [*source_holes, antipad_ring]],
            GRID_MM, MAX_PLANAR_VERTICES,
        )
        remaining = budget.maximum - budget.actual
        planar = native.triangulate_constrained_planar_region(
            topology, maximum_vertices=MAX_PLANAR_VERTICES,
            maximum_holes=128, maximum_triangles=MAX_PLANAR_TRIANGLES,
            maximum_work_steps=remaining, cancel_check=budget.cancel_check,
        )
    except RuntimeError as error:
        message = str(error)
        if "cancelled" in message:
            raise ReferencePlaneAntipadMeshV2Error(
                "Generalized reference-plane meshing was cancelled."
            ) from error
        raise ReferencePlaneAntipadMeshV2Error(
            "Native constrained triangulation exceeded its admitted work."
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise ReferencePlaneAntipadMeshV2Error(
            "Native constrained-domain admission rejected the generalized plane."
        ) from error
    budget.consume(int(planar.work_steps))
    z_min, z_max = float(region["z_min_mm"]), float(region["z_max_mm"])
    if not math.isfinite(z_min) or not math.isfinite(z_max) or not z_max > z_min:
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh requires positive finite thickness.")
    vertex_offset = len(vertices)
    planar_vertices = list(planar.vertices)
    if vertex_offset + 2 * len(planar_vertices) > MAX_VERTICES:
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh vertex budget exceeded.")
    vertices.extend([[item.x * GRID_MM, item.y * GRID_MM, z_min] for item in planar_vertices])
    vertices.extend([[item.x * GRID_MM, item.y * GRID_MM, z_max] for item in planar_vertices])
    upper_offset = vertex_offset + len(planar_vertices)
    domain_id = f"mesh-v2:{region['region_id']}"
    source_zone = region["source_zone"]
    zone_sources = sorted({source_zone["zone_id"], source_zone["source_zone_id"]})
    source_ids = sorted({*zone_sources, antipad["source_id"]})

    def add(face: Sequence[int], role: str, role_sources: Sequence[str]) -> None:
        budget.consume()
        if len(triangles) >= MAX_TRIANGLES:
            raise ReferencePlaneAntipadMeshV2Error("Generalized mesh triangle budget exceeded.")
        triangles.append({"id": f"triangle:{len(triangles)}", "domain_id": domain_id,
                          "vertex_indices": list(face), "surface_role": role,
                          "source_ids": sorted(set(role_sources))})

    for item in planar.triangles:
        lower = [vertex_offset + item.a, vertex_offset + item.b, vertex_offset + item.c]
        upper = [upper_offset + item.a, upper_offset + item.b, upper_offset + item.c]
        add((lower[0], lower[2], lower[1]), "reference_zone_lower_face", source_ids)
        add(upper, "reference_zone_upper_face", source_ids)

    antipad_points = {_grid(item) for item in antipad_ring}
    source_cutouts = [set(_grid(item) for item in ring) for ring in source_holes]
    role_counts = {"source_outer": 0, "source_cutout": 0, "antipad_hole": 0}
    for loop_index, loop in enumerate(planar.boundary_loops):
        indices = list(loop)
        points = {(planar_vertices[index].x, planar_vertices[index].y) for index in indices}
        if loop_index == 0:
            role, wall_role, role_sources = "source_outer", "reference_zone_outer_boundary", zone_sources
        elif points == antipad_points:
            role, wall_role, role_sources = "antipad_hole", "antipad_void_boundary", [antipad["source_id"]]
        elif any(points == candidate for candidate in source_cutouts):
            role, wall_role, role_sources = "source_cutout", "source_cutout_boundary", zone_sources
        else:
            raise ReferencePlaneAntipadMeshV2Error("Native boundary loop cannot be bound to source provenance.")
        role_counts[role] += 1
        lower = [vertex_offset + index for index in indices]
        upper = [upper_offset + index for index in indices]
        for index, first in enumerate(indices):
            second = indices[(index + 1) % len(indices)]
            a, b = vertex_offset + first, vertex_offset + second
            at, bt = upper_offset + first, upper_offset + second
            add((a, b, bt), wall_role, role_sources)
            add((a, bt, at), wall_role, role_sources)
        for surface, z_mm, bound in (("lower", z_min, lower), ("upper", z_max, upper)):
            loops.append({"loop_id": f"{domain_id}:{role}:{role_counts[role]}:{surface}",
                          "domain_id": domain_id, "role": role, "surface": surface,
                          "z_mm": z_mm, "vertex_indices": bound,
                          "source_ids": sorted(set(role_sources))})

    triangle_ids = [item["id"] for item in triangles if item["domain_id"] == domain_id]
    exact_area_mm2 = int(planar.twice_area_grid) * GRID_MM * GRID_MM / 2.0
    domain = {"id": domain_id, "kind": "generalized_reference_plane",
              "net_id": source_zone["net_id"], "layer_ids": [source_zone["layer_id"]],
              "source_ids": source_ids, "triangle_ids": triangle_ids,
              "reference_zone_id": source_zone["zone_id"],
              "source_zone_sha256": region["source_zone_sha256"],
              "resolved_region_sha256": region["resolved_region_sha256"],
              "antipad_radius_mm": float(antipad["radius_mm"]),
              "exact_discrete_area_mm2": exact_area_mm2,
              "exact_discrete_volume_mm3": exact_area_mm2 * (z_max - z_min),
              "source_cutout_count": len(source_holes),
              "antipad_radial_inflation_grid_units": inflation_grid}
    if geometry_contract == GEOMETRY_V3_CONTRACT:
        domain["source_boundary_sha256"] = region["source_boundary_sha256"]
        domain["flattened_boundary_sha256"] = region["flattened_boundary_sha256"]
    return domain


def build_reference_plane_antipad_mesh_v2(
    geometry: Mapping[str, Any], *, radial_segments: int = 32,
    maximum_work_steps: int = MAX_WORK_STEPS,
    cancel_check: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    """Build a closed generalized geometry mesh without solver semantics."""

    geometry_contract = geometry.get("contract")
    if geometry_contract not in {GEOMETRY_V2_CONTRACT, GEOMETRY_V3_CONTRACT}:
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh requires geometry v2 or v3.")
    if geometry.get("qualification", {}).get("solver_ready") is not False:
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh input must remain solver-blocked.")
    if (isinstance(radial_segments, bool) or not isinstance(radial_segments, int)
            or radial_segments % 4 or not MIN_RADIAL_SEGMENTS <= radial_segments <= MAX_RADIAL_SEGMENTS):
        raise ReferencePlaneAntipadMeshV2Error(
            "radial_segments must be a bounded integer multiple of four."
        )
    budget = _Budget(maximum_work_steps, cancel_check)
    vertices: list[list[float]] = []
    triangles: list[Dict[str, Any]] = []
    loops: list[Dict[str, Any]] = []
    domains = [_build_region(region, geometry_contract, radial_segments, budget,
                             vertices, triangles, loops) for region in geometry["regions"]]
    curve_deviation = max((float(item.get("curve_tessellation", {}).get(
        "maximum_certified_curve_deviation_mm", 0.0)) for item in geometry["regions"]), default=0.0)
    mesh: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {"geometry_contract": geometry_contract,
                   "geometry_sha256": content_digest(geometry),
                   "design_id": geometry["source"]["design_id"],
                   "via_id": geometry["source"]["via_id"],
                   "source_via_id": geometry["source"]["source_via_id"]},
        "radial_segments": radial_segments,
        "tessellation": {"coordinate_grid_mm": GRID_MM, "coordinate_tolerance_mm": 1e-9,
                         "source_boundary": ("exact_straight_segments" if geometry_contract == GEOMETRY_V2_CONTRACT
                                             else "certified_bounded_flattened_segments"),
                         "maximum_source_curve_deviation_mm": curve_deviation,
                         "antipad_boundary": "exact_grid_circumscribed",
                         "planar_method": "exact_fixed_grid_constrained_delaunay_no_steiner"},
        "vertices_mm": vertices, "triangles": triangles,
        "domains": domains, "boundary_loops": loops,
        "resources": {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                      "max_planar_vertices_per_region": MAX_PLANAR_VERTICES,
                      "max_planar_triangles_per_region": MAX_PLANAR_TRIANGLES,
                      "maximum_work_steps": maximum_work_steps,
                      "actual_work_steps": budget.actual,
                      "cancellation_poll_interval": CANCELLATION_POLL_INTERVAL,
                      "actual_vertices": len(vertices), "actual_triangles": len(triangles),
                      "max_serialized_bytes": MAX_SERIALIZED_BYTES},
        "qualification": {"state": "generalized_reference_plane_geometry_mesh_only",
                          "mesh_topology_admitted": True,
                          "conservative_antipad_void_proven": True,
                          "conservative_source_copper_envelope_proven": geometry_contract == GEOMETRY_V2_CONTRACT,
                          "native_handoff_ready": False, "mesh_quality_performed": False,
                          "physics_convergence_performed": False, "capacitance_ready": False,
                          "si_ready": False, "solver_ready": False},
    }
    try:
        audit = _audit(mesh)
    except ValueError as error:
        raise ReferencePlaneAntipadMeshV2Error("Generalized closed-volume topology audit failed.") from error
    mesh["topology_audit"] = audit
    if not audit["passed"]:
        raise ReferencePlaneAntipadMeshV2Error("Generalized closed-volume topology audit failed.")
    encoded = json.dumps(mesh, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_SERIALIZED_BYTES:
        raise ReferencePlaneAntipadMeshV2Error("Generalized mesh serialized-byte budget exceeded.")
    return mesh


def validate_reference_plane_antipad_mesh_v2(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    try:
        regenerated = build_reference_plane_antipad_mesh_v2(
            source_geometry, radial_segments=mesh["radial_segments"],
            maximum_work_steps=mesh["resources"]["maximum_work_steps"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReferencePlaneAntipadMeshV2Error):
            raise
        raise ReferencePlaneAntipadMeshV2Error("Malformed generalized mesh evidence.") from error
    if dict(mesh) != regenerated:
        raise ReferencePlaneAntipadMeshV2Error(
            "Generalized mesh does not match deterministic regeneration."
        )
    return regenerated


__all__ = ["CONTRACT", "ERROR_CODE", "ReferencePlaneAntipadMeshV2Error",
           "build_reference_plane_antipad_mesh_v2", "validate_reference_plane_antipad_mesh_v2"]
