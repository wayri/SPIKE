"""Deterministic conservative surface mesh for one admitted circular via transition."""

from __future__ import annotations

from collections import defaultdict
import json
import math
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2_schema import content_digest
from .via_transition_geometry import CONTRACT as GEOMETRY_CONTRACT


CONTRACT = "spike/pcb-via-transition-mesh/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0004"
MIN_RADIAL_SEGMENTS = 8
MAX_RADIAL_SEGMENTS = 128
MAX_VERTICES = 32768
MAX_TRIANGLES = 65536
MAX_SERIALIZED_BYTES = 8 * 1024 * 1024


class ViaTransitionMeshError(ValueError):
    """Raised before an invalid or non-watertight transition mesh is retained."""

    code = ERROR_CODE


def _cross(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _subtract(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _segment_distance_2d(point: tuple[float, float], left: Sequence[float], right: Sequence[float]) -> float:
    dx, dy = right[0] - left[0], right[1] - left[1]
    scale = dx * dx + dy * dy
    ratio = 0.0 if scale <= 1e-30 else max(0.0, min(1.0, ((point[0] - left[0]) * dx + (point[1] - left[1]) * dy) / scale))
    return math.hypot(point[0] - left[0] - ratio * dx, point[1] - left[1] - ratio * dy)


def _triangle_distance_2d(center: tuple[float, float], points: Sequence[Sequence[float]]) -> float:
    signs = []
    for index, left in enumerate(points):
        right = points[(index + 1) % 3]
        cross = (right[0] - left[0]) * (center[1] - left[1]) - (right[1] - left[1]) * (center[0] - left[0])
        if abs(cross) > 1e-15:
            signs.append(cross > 0)
    if signs and all(value == signs[0] for value in signs):
        return 0.0
    return min(_segment_distance_2d(center, points[index], points[(index + 1) % 3]) for index in range(3))


class _MeshBuilder:
    def __init__(self, center: Sequence[float], segments: int) -> None:
        self.center = (float(center[0]), float(center[1]))
        self.segments = segments
        self.vertices: list[list[float]] = []
        self.triangles: list[Dict[str, Any]] = []
        self.domains: list[Dict[str, Any]] = []
        self._rings: dict[tuple[str, float, float], list[int]] = {}

    def domain(self, identity: str, kind: str, net_id: str, layer_ids: Sequence[str], source_ids: Sequence[str], **extra: Any) -> None:
        if any(item["id"] == identity for item in self.domains):
            raise ViaTransitionMeshError("Mesh domain identities must be unique.")
        self.domains.append({"id": identity, "kind": kind, "net_id": net_id, "layer_ids": list(layer_ids),
                             "source_ids": sorted(set(source_ids)), "triangle_ids": [], **extra})

    def ring(self, domain_id: str, radius: float, z_mm: float) -> list[int]:
        key = (domain_id, float(radius), float(z_mm))
        if key in self._rings:
            return self._rings[key]
        if radius <= 0 or not math.isfinite(radius) or not math.isfinite(z_mm):
            raise ViaTransitionMeshError("Mesh rings require finite positive radii and elevations.")
        if len(self.vertices) + self.segments > MAX_VERTICES:
            raise ViaTransitionMeshError("Via-transition mesh vertex budget exceeded before allocation.")
        result = []
        for index in range(self.segments):
            angle = 2.0 * math.pi * index / self.segments
            result.append(len(self.vertices))
            self.vertices.append([self.center[0] + radius * math.cos(angle), self.center[1] + radius * math.sin(angle), z_mm])
        self._rings[key] = result
        return result

    def triangle(self, domain_id: str, indices: Sequence[int], role: str, source_ids: Sequence[str]) -> None:
        if len(self.triangles) >= MAX_TRIANGLES:
            raise ViaTransitionMeshError("Via-transition mesh triangle budget exceeded before allocation.")
        identity = f"triangle:{len(self.triangles)}"
        self.triangles.append({"id": identity, "domain_id": domain_id, "vertex_indices": list(indices),
                               "surface_role": role, "source_ids": sorted(set(source_ids))})
        next(item for item in self.domains if item["id"] == domain_id)["triangle_ids"].append(identity)

    def wall(self, domain_id: str, bottom: Sequence[int], top: Sequence[int], role: str,
             source_ids: Sequence[str], *, inward: bool = False) -> None:
        for index in range(self.segments):
            following = (index + 1) % self.segments
            faces = ((bottom[index], top[following], bottom[following]), (bottom[index], top[index], top[following])) if inward else (
                (bottom[index], bottom[following], top[following]), (bottom[index], top[following], top[index]))
            for face in faces:
                self.triangle(domain_id, face, role, source_ids)

    def annulus(self, domain_id: str, inner: Sequence[int], outer: Sequence[int], role: str,
                source_ids: Sequence[str], *, normal_up: bool) -> None:
        for index in range(self.segments):
            following = (index + 1) % self.segments
            faces = [(inner[index], outer[index], outer[following]), (inner[index], outer[following], inner[following])]
            if not normal_up:
                faces = [(face[0], face[2], face[1]) for face in faces]
            for face in faces:
                self.triangle(domain_id, face, role, source_ids)

    def annular_cylinder(self, domain_id: str, inner_radius: float, outer_radius: float, z_min: float, z_max: float,
                         source_ids: Sequence[str], inner_role: str, outer_role: str) -> None:
        if not z_max > z_min or not outer_radius > inner_radius:
            raise ViaTransitionMeshError("Annular mesh volumes require positive radial and axial extent.")
        inner_bottom, inner_top = self.ring(domain_id, inner_radius, z_min), self.ring(domain_id, inner_radius, z_max)
        outer_bottom, outer_top = self.ring(domain_id, outer_radius, z_min), self.ring(domain_id, outer_radius, z_max)
        self.wall(domain_id, outer_bottom, outer_top, outer_role, source_ids)
        self.wall(domain_id, inner_bottom, inner_top, inner_role, source_ids, inward=True)
        self.annulus(domain_id, inner_bottom, outer_bottom, "lower_face", source_ids, normal_up=False)
        self.annulus(domain_id, inner_top, outer_top, "upper_face", source_ids, normal_up=True)


def _signal_domain(builder: _MeshBuilder, geometry: Mapping[str, Any], inner_radius: float) -> None:
    lands = sorted(geometry["lands"], key=lambda item: (float(item["z_min_mm"]), item["layer_id"]))
    source_ids = [geometry["source_via_id"], *(item["source_profile_id"] for item in lands)]
    domain_id = f"signal:{geometry['via_id']}"
    builder.domain(domain_id, "signal_via_conductor", geometry["net_id"], geometry["span"]["ordered_layer_ids"], source_ids)
    barrel_radius = float(geometry["drill_diameter_mm"]) / 2.0 + float(geometry["plating_mm"])
    elevations = sorted({float(item[key]) for item in lands for key in ("z_min_mm", "z_max_mm")})
    if len(elevations) < 2:
        raise ViaTransitionMeshError("Signal transition has no finite axial extent.")
    exact_radii = []
    for lower, upper in zip(elevations, elevations[1:]):
        midpoint = (lower + upper) / 2.0
        radius = max([barrel_radius, *(float(item["outer_diameter_mm"]) / 2.0 for item in lands
                                       if float(item["z_min_mm"]) - 1e-12 <= midpoint <= float(item["z_max_mm"]) + 1e-12)])
        exact_radii.append(radius)
    if inner_radius >= min(exact_radii) - 1e-12:
        raise ViaTransitionMeshError("Requested radial resolution consumes the conservative plated-barrel mesh.")
    outer_rings: list[tuple[list[int], list[int]]] = []
    for index, radius in enumerate(exact_radii):
        bottom = builder.ring(domain_id, radius, elevations[index])
        top = builder.ring(domain_id, radius, elevations[index + 1])
        builder.wall(domain_id, bottom, top, "signal_outer_boundary", source_ids)
        outer_rings.append((bottom, top))
    for index in range(len(exact_radii) - 1):
        left, right = exact_radii[index], exact_radii[index + 1]
        if math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12):
            continue
        small = builder.ring(domain_id, min(left, right), elevations[index + 1])
        large = builder.ring(domain_id, max(left, right), elevations[index + 1])
        builder.annulus(domain_id, small, large, "signal_land_shoulder", source_ids, normal_up=left > right)
    inner_bottom = builder.ring(domain_id, inner_radius, elevations[0])
    inner_top = builder.ring(domain_id, inner_radius, elevations[-1])
    builder.wall(domain_id, inner_bottom, inner_top, "drill_void_boundary", source_ids, inward=True)
    builder.annulus(domain_id, inner_bottom, outer_rings[0][0], "signal_lower_face", source_ids, normal_up=False)
    builder.annulus(domain_id, inner_top, outer_rings[-1][1], "signal_upper_face", source_ids, normal_up=True)


def _audit(mesh: Mapping[str, Any]) -> Dict[str, Any]:
    tolerance = float(mesh["tessellation"]["coordinate_tolerance_mm"])
    vertices = mesh["vertices_mm"]
    triangles = mesh["triangles"]
    if not isinstance(vertices, list) or not isinstance(triangles, list) or len(vertices) > MAX_VERTICES or len(triangles) > MAX_TRIANGLES:
        raise ViaTransitionMeshError("Mesh arrays are missing or exceed their resource budget.")
    for point in vertices:
        if (not isinstance(point, list) or len(point) != 3 or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                                                 or not math.isfinite(float(value)) for value in point)):
            raise ViaTransitionMeshError("Mesh vertices must be finite three-dimensional coordinates.")
    domains = {item["id"]: item for item in mesh["domains"]}
    if len(domains) != len(mesh["domains"]):
        raise ViaTransitionMeshError("Mesh domain identities must be unique.")
    domain_triangles: dict[str, list[str]] = defaultdict(list)
    edges: dict[tuple[str, int, int], list[tuple[int, int]]] = defaultdict(list)
    faces: set[tuple[str, int, int, int]] = set()
    used: set[int] = set()
    signed_volume: dict[str, float] = defaultdict(float)
    zero_area = duplicate = nonmanifold = orientation = void_violations = 0
    ids: set[str] = set()
    for triangle in triangles:
        identity, domain_id, indexes = triangle.get("id"), triangle.get("domain_id"), triangle.get("vertex_indices")
        if not isinstance(identity, str) or identity in ids or domain_id not in domains or not isinstance(indexes, list) or len(indexes) != 3:
            raise ViaTransitionMeshError("Mesh triangle identity, domain, or index arity is invalid.")
        ids.add(identity); domain_triangles[domain_id].append(identity)
        if any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(vertices) for index in indexes):
            raise ViaTransitionMeshError("Mesh triangle index is outside the compact vertex array.")
        used.update(indexes)
        key = (domain_id, *sorted(indexes))
        if key in faces:
            duplicate += 1
        faces.add(key)
        points = [vertices[index] for index in indexes]
        normal = _cross(_subtract(points[1], points[0]), _subtract(points[2], points[0]))
        if math.sqrt(sum(value * value for value in normal)) <= tolerance * tolerance:
            zero_area += 1
        signed_volume[domain_id] += sum(points[0][axis] * normal[axis] for axis in range(3)) / 6.0
        for left, right in zip(indexes, indexes[1:] + indexes[:1]):
            edges[(domain_id, min(left, right), max(left, right))].append((left, right))
        domain = domains[domain_id]
        if domain["kind"] == "reference_plane_local_patch":
            center = tuple(float(value) for value in mesh["center_mm"])
            if _triangle_distance_2d(center, points) < float(domain["antipad_radius_mm"]) - tolerance:
                void_violations += 1
    for occurrences in edges.values():
        if len(occurrences) != 2:
            nonmanifold += 1
        elif occurrences[0] == occurrences[1]:
            orientation += 1
        elif occurrences[0] != (occurrences[1][1], occurrences[1][0]):
            orientation += 1
    for identity, domain in domains.items():
        if domain["triangle_ids"] != domain_triangles.get(identity, []) or signed_volume[identity] <= tolerance ** 3:
            raise ViaTransitionMeshError("Mesh domain ownership or outward orientation is invalid.")
    unused = len(vertices) - len(used)
    return {"zero_area_triangles": zero_area, "duplicate_triangles": duplicate,
            "nonmanifold_or_boundary_edges": nonmanifold, "orientation_mismatches": orientation,
            "unused_vertices": unused, "reference_void_violations": void_violations,
            "closed_domains": len(domains),
            "passed": all(value == 0 for value in (zero_area, duplicate, nonmanifold, orientation, unused, void_violations))}


def validate_via_transition_mesh(mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    if mesh.get("contract") != CONTRACT or mesh.get("source", {}).get("geometry_contract") != GEOMETRY_CONTRACT:
        raise ViaTransitionMeshError("Via-transition mesh contract or source contract is invalid.")
    if source_geometry is not None and (source_geometry.get("contract") != GEOMETRY_CONTRACT
                                        or mesh["source"]["geometry_sha256"] != content_digest(source_geometry)):
        raise ViaTransitionMeshError("Via-transition mesh source geometry digest does not match.")
    audit = _audit(mesh)
    if not audit["passed"] or mesh.get("topology_audit") != audit:
        raise ViaTransitionMeshError("Via-transition discrete topology audit failed.")
    resources = mesh.get("resources", {})
    if resources != {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                     "actual_vertices": len(mesh["vertices_mm"]), "actual_triangles": len(mesh["triangles"]),
                     "max_serialized_bytes": MAX_SERIALIZED_BYTES}:
        raise ViaTransitionMeshError("Via-transition mesh resource accounting is invalid.")
    encoded = json.dumps(mesh, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_SERIALIZED_BYTES:
        raise ViaTransitionMeshError("Via-transition mesh serialized resource budget exceeded.")
    return dict(mesh)


def build_via_transition_mesh(
    geometry: Mapping[str, Any], *, radial_segments: int = 24, coordinate_tolerance_mm: float = 1e-9,
) -> Dict[str, Any]:
    """Mesh a source-admitted transition without enabling a numerical solver."""
    if geometry.get("contract") != GEOMETRY_CONTRACT or geometry.get("qualification", {}).get("solver_ready") is not False:
        raise ViaTransitionMeshError("Mesh input must be solver-blocked via-transition geometry v1.")
    if (isinstance(radial_segments, bool) or not isinstance(radial_segments, int)
            or not MIN_RADIAL_SEGMENTS <= radial_segments <= MAX_RADIAL_SEGMENTS or radial_segments % 4):
        raise ViaTransitionMeshError("radial_segments must be divisible by four and within 8..128.")
    if (isinstance(coordinate_tolerance_mm, bool) or not math.isfinite(float(coordinate_tolerance_mm))
            or not 0 < coordinate_tolerance_mm <= 1e-6):
        raise ViaTransitionMeshError("coordinate_tolerance_mm must be finite, positive, and no larger than 1e-6 mm.")
    center = geometry.get("center_mm")
    if not isinstance(center, list) or len(center) != 2 or any(not math.isfinite(float(value)) for value in center):
        raise ViaTransitionMeshError("Via-transition mesh requires a finite source center.")
    cosine = math.cos(math.pi / radial_segments)
    builder = _MeshBuilder(center, radial_segments)
    drill_radius = float(geometry["drill_diameter_mm"]) / 2.0
    _signal_domain(builder, geometry, drill_radius / cosine)
    exact_radii = [drill_radius, drill_radius + float(geometry["plating_mm"]),
                   *(float(item["outer_diameter_mm"]) / 2.0 for item in geometry["lands"])]
    land_by_layer = {item["layer_id"]: item for item in geometry["lands"]}
    for index, antipad in enumerate(geometry["antipads"]):
        land = land_by_layer.get(antipad["layer_id"])
        if land is None:
            raise ViaTransitionMeshError("Antipad layer does not resolve to an admitted land volume.")
        inner_exact = float(antipad["diameter_mm"]) / 2.0
        outer_exact = float(antipad["reference_patch_outer_diameter_mm"]) / 2.0
        inner_mesh = inner_exact / cosine
        if inner_mesh >= outer_exact - coordinate_tolerance_mm:
            raise ViaTransitionMeshError("Requested radial resolution consumes the local reference-plane patch.")
        domain_id = f"reference:{index}:{antipad['reference_zone_id']}"
        sources = [antipad["source_id"], antipad["reference_zone_id"], land["source_profile_id"]]
        builder.domain(domain_id, "reference_plane_local_patch", antipad["reference_net_id"], [antipad["layer_id"]], sources,
                       antipad_radius_mm=inner_exact, reference_zone_id=antipad["reference_zone_id"],
                       qualification="source_contained_local_patch_not_full_plane")
        builder.annular_cylinder(domain_id, inner_mesh, outer_exact, float(land["z_min_mm"]), float(land["z_max_mm"]),
                                 sources, "antipad_void_boundary", "local_patch_truncation")
        exact_radii.extend((inner_exact, outer_exact))
    max_deviation = max([radius * (1.0 - cosine) for radius in exact_radii]
                        + [radius * (1.0 / cosine - 1.0) for radius in exact_radii])
    mesh: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {"geometry_contract": GEOMETRY_CONTRACT, "geometry_sha256": content_digest(geometry),
                   "design_id": geometry["design_id"], "via_id": geometry["via_id"], "source_via_id": geometry["source_via_id"]},
        "center_mm": [float(center[0]), float(center[1])],
        "tessellation": {"radial_segments": radial_segments, "coordinate_tolerance_mm": float(coordinate_tolerance_mm),
                         "circle_approximation": {"source_is_exact_circle": True,
                                                  "outer_boundaries": "inscribed",
                                                  "drill_and_antipad_void_boundaries": "circumscribed",
                                                  "max_radial_deviation_mm": max_deviation}},
        "vertices_mm": builder.vertices, "triangles": builder.triangles, "domains": builder.domains,
        "boundary_loops": [],
        "resources": {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                      "actual_vertices": len(builder.vertices), "actual_triangles": len(builder.triangles),
                      "max_serialized_bytes": MAX_SERIALIZED_BYTES},
        "topology_audit": {},
        "qualification": {"geometry_state": "conservative_discrete_circular_approximation",
                          "reference_plane_state": "source_contained_local_patch_not_full_plane",
                          "refinement_state": "tessellation_not_convergence_proof",
                          "discrete_watertightness_checked": True, "native_handoff_ready": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }
    mesh["topology_audit"] = _audit(mesh)
    return validate_via_transition_mesh(mesh, source_geometry=geometry)


__all__ = ["CONTRACT", "ERROR_CODE", "ViaTransitionMeshError", "build_via_transition_mesh", "validate_via_transition_mesh"]
