"""Deterministic geometry-quality and domain-convergence evidence for via meshes."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2_schema import content_digest
from .via_transition_geometry import CONTRACT as GEOMETRY_CONTRACT
from .via_transition_mesh import (
    CONTRACT as MESH_CONTRACT,
    MAX_RADIAL_SEGMENTS,
    MIN_RADIAL_SEGMENTS,
    build_via_transition_mesh,
    validate_via_transition_mesh,
)
from .via_transition_native_handoff import (
    CONTRACT as HANDOFF_CONTRACT,
    build_native_via_transition_handoff,
)


CONTRACT = "spike/pcb-via-transition-mesh-quality/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0006"
DEFAULT_LEVELS = (8, 16, 32, 64)

class ViaTransitionMeshQualityError(ValueError):
    """Raised when bounded geometry quality or convergence evidence fails."""

    code = ERROR_CODE


def _vector(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return tuple(float(right[index]) - float(left[index]) for index in range(3))  # type: ignore[return-value]


def _length(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _cross(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _triangle_metrics(points: Sequence[Sequence[float]]) -> tuple[float, float, float, float, float]:
    edges = [_length(_vector(points[index], points[(index + 1) % 3])) for index in range(3)]
    area = _length(_cross(_vector(points[0], points[1]), _vector(points[0], points[2]))) / 2.0
    if not area > 0.0 or any(not math.isfinite(value) or value <= 0.0 for value in edges):
        raise ViaTransitionMeshQualityError("Mesh quality contains a degenerate triangle.")
    angles = []
    for index in range(3):
        left = _vector(points[index], points[(index - 1) % 3])
        right = _vector(points[index], points[(index + 1) % 3])
        angles.append(math.degrees(math.atan2(_length(_cross(left, right)),
                                              sum(left[axis] * right[axis] for axis in range(3)))))
    longest = max(edges)
    longest_edge_to_altitude = longest * longest / (2.0 * area)
    return area, min(angles), longest_edge_to_altitude, min(edges), longest


def _point_segment_distance_2d(center: Sequence[float], left: Sequence[float], right: Sequence[float]) -> float:
    dx, dy = float(right[0]) - float(left[0]), float(right[1]) - float(left[1])
    scale = dx * dx + dy * dy
    ratio = 0.0 if scale <= 1e-30 else max(0.0, min(1.0, ((float(center[0]) - float(left[0])) * dx
                                                            + (float(center[1]) - float(left[1])) * dy) / scale))
    return math.hypot(float(center[0]) - float(left[0]) - ratio * dx,
                      float(center[1]) - float(left[1]) - ratio * dy)


def _relative_error(value: float, reference: float) -> float:
    return abs(value - reference) / max(abs(reference), 1e-18)


def _relative_change(left: float, right: float, floor: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), floor)


def _exact_domain_measures(geometry: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    inner_radius = float(geometry["drill_diameter_mm"]) / 2.0
    barrel_radius = inner_radius + float(geometry["plating_mm"])
    lands = sorted(geometry["lands"], key=lambda item: (float(item["z_min_mm"]), item["layer_id"]))
    elevations = sorted({float(item[key]) for item in lands for key in ("z_min_mm", "z_max_mm")})
    radii = []
    for lower, upper in zip(elevations, elevations[1:]):
        midpoint = (lower + upper) / 2.0
        radii.append(max([barrel_radius, *(float(item["outer_diameter_mm"]) / 2.0 for item in lands
                                            if float(item["z_min_mm"]) - 1e-12 <= midpoint
                                            <= float(item["z_max_mm"]) + 1e-12)]))
    signal_volume = sum(math.pi * (radius * radius - inner_radius * inner_radius) * (upper - lower)
                        for radius, lower, upper in zip(radii, elevations, elevations[1:]))
    signal_area = sum(2.0 * math.pi * radius * (upper - lower)
                      for radius, lower, upper in zip(radii, elevations, elevations[1:]))
    signal_area += 2.0 * math.pi * inner_radius * (elevations[-1] - elevations[0])
    signal_area += math.pi * (radii[0] ** 2 - inner_radius ** 2)
    signal_area += math.pi * (radii[-1] ** 2 - inner_radius ** 2)
    signal_area += sum(math.pi * abs(right * right - left * left) for left, right in zip(radii, radii[1:]))
    result: Dict[str, Dict[str, Any]] = {
        f"signal:{geometry['via_id']}": {
            "kind": "signal_via_conductor",
            "exact_surface_area_mm2": signal_area,
            "exact_volume_mm3": signal_volume,
        }
    }
    land_by_layer = {item["layer_id"]: item for item in lands}
    for index, antipad in enumerate(geometry["antipads"]):
        land = land_by_layer[antipad["layer_id"]]
        inner = float(antipad["diameter_mm"]) / 2.0
        outer = float(antipad["reference_patch_outer_diameter_mm"]) / 2.0
        height = float(land["z_max_mm"]) - float(land["z_min_mm"])
        result[f"reference:{index}:{antipad['reference_zone_id']}"] = {
            "kind": "reference_plane_local_patch",
            "exact_surface_area_mm2": 2.0 * math.pi * (outer + inner) * height
                                      + 2.0 * math.pi * (outer * outer - inner * inner),
            "exact_volume_mm3": math.pi * (outer * outer - inner * inner) * height,
        }
    return result


def _measure_mesh(mesh: Mapping[str, Any], exact: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    vertices = mesh["vertices_mm"]
    domains = {item["id"]: item for item in mesh["domains"]}
    domain_vertex_indexes = {identity: set() for identity in domains}
    for triangle in mesh["triangles"]:
        domain_vertex_indexes[triangle["domain_id"]].update(triangle["vertex_indices"])
    origins = {
        identity: tuple(math.fsum(float(vertices[index][axis]) for index in sorted(indexes)) / len(indexes)
                        for axis in range(3))
        for identity, indexes in domain_vertex_indexes.items()
    }
    aggregates = {identity: {"triangle_count": 0, "surface_areas": [], "volume_terms": [],
                             "minimum_triangle_area_mm2": math.inf, "minimum_triangle_angle_deg": math.inf,
                             "maximum_triangle_aspect_ratio": 0.0, "minimum_edge_length_mm": math.inf,
                             "maximum_edge_length_mm": 0.0, "reference_void_boundary_error_mm": 0.0,
                             "surface_roles": {}}
                  for identity in domains}
    center = mesh["center_mm"]
    for triangle in mesh["triangles"]:
        indexes = triangle["vertex_indices"]
        points = [vertices[index] for index in indexes]
        area, angle, aspect, shortest, longest = _triangle_metrics(points)
        record = aggregates[triangle["domain_id"]]
        record["triangle_count"] += 1
        record["surface_areas"].append(area)
        record["surface_roles"].setdefault(triangle["surface_role"], []).append(area)
        origin = origins[triangle["domain_id"]]
        first, second, third = (_vector(origin, point) for point in points)
        normal = _cross(_vector(first, second), _vector(first, third))
        record["volume_terms"].append(sum(first[axis] * normal[axis] for axis in range(3)) / 6.0)
        record["minimum_triangle_area_mm2"] = min(record["minimum_triangle_area_mm2"], area)
        record["minimum_triangle_angle_deg"] = min(record["minimum_triangle_angle_deg"], angle)
        record["maximum_triangle_aspect_ratio"] = max(record["maximum_triangle_aspect_ratio"], aspect)
        record["minimum_edge_length_mm"] = min(record["minimum_edge_length_mm"], shortest)
        record["maximum_edge_length_mm"] = max(record["maximum_edge_length_mm"], longest)
        domain = domains[triangle["domain_id"]]
        if (domain["kind"] in ("reference_plane_local_patch", "reference_plane_full_zone")
                and triangle["surface_role"] == "antipad_void_boundary"):
            distance = min(_point_segment_distance_2d(center, points[index], points[(index + 1) % 3])
                           for index in range(3))
            error = abs(distance - float(domain["antipad_radius_mm"]))
            record["reference_void_boundary_error_mm"] = max(record["reference_void_boundary_error_mm"], error)
    results = []
    for identity in sorted(domains):
        record = aggregates[identity]
        reference = exact[identity]
        surface_area = math.fsum(record.pop("surface_areas"))
        signed_volume = math.fsum(record.pop("volume_terms"))
        surface_roles = [{"surface_role": role, "triangle_count": len(areas),
                          "surface_area_mm2": math.fsum(areas)}
                         for role, areas in sorted(record.pop("surface_roles").items())]
        results.append({**record, "domain_id": identity, "kind": domains[identity]["kind"],
                        "surface_area_mm2": surface_area, "signed_volume_mm3": signed_volume,
                        "exact_surface_area_mm2": reference["exact_surface_area_mm2"],
                        "exact_volume_mm3": reference["exact_volume_mm3"],
                        "relative_surface_area_error": _relative_error(surface_area, reference["exact_surface_area_mm2"]),
                        "relative_volume_error": _relative_error(signed_volume, reference["exact_volume_mm3"]),
                        "surface_roles": surface_roles})
    return {
        "minimum_triangle_area_mm2": min(item["minimum_triangle_area_mm2"] for item in results),
        "minimum_triangle_angle_deg": min(item["minimum_triangle_angle_deg"] for item in results),
        "maximum_triangle_aspect_ratio": max(item["maximum_triangle_aspect_ratio"] for item in results),
        "minimum_edge_length_mm": min(item["minimum_edge_length_mm"] for item in results),
        "maximum_edge_length_mm": max(item["maximum_edge_length_mm"] for item in results),
        "maximum_reference_void_boundary_error_mm": max(item["reference_void_boundary_error_mm"] for item in results),
        "domains": results,
    }


def _levels(values: Sequence[int]) -> list[int]:
    result = list(values)
    if (not 4 <= len(result) <= 5
            or any(isinstance(value, bool) or not isinstance(value, int) or value % 4
                   or not MIN_RADIAL_SEGMENTS <= value <= MAX_RADIAL_SEGMENTS for value in result)
            or any(result[index + 1] != result[index] * 2 for index in range(len(result) - 1))):
        raise ViaTransitionMeshQualityError(
            "Convergence levels must contain four or five bounded doubling radial resolutions."
        )
    return result


def _native_handoff_passed(
    handoff: Mapping[str, Any], mesh: Mapping[str, Any], geometry: Mapping[str, Any]
) -> bool:
    source = handoff.get("source", {})
    native = handoff.get("native_validation", {})
    resources = handoff.get("resources", {})
    qualification = handoff.get("qualification", {})
    return (
        handoff.get("contract") == HANDOFF_CONTRACT
        and source.get("mesh_contract") == MESH_CONTRACT
        and source.get("mesh_sha256") == content_digest(mesh)
        and source.get("geometry_contract") == GEOMETRY_CONTRACT
        and source.get("geometry_sha256") == content_digest(geometry)
        and all(source.get(key) == mesh["source"][key]
                for key in ("design_id", "via_id", "source_via_id"))
        and native.get("status") == "passed"
        and all(native.get(key) is True for key in (
            "finite_vertices_checked", "compact_indices_checked", "closed_domains_checked",
            "domain_ownership_checked", "provenance_checked",
        ))
        and native.get("solver_entry_points_exposed") is False
        and native.get("vertex_count") == len(mesh["vertices_mm"])
        and native.get("triangle_count") == len(mesh["triangles"])
        and native.get("domain_count") == len(mesh["domains"])
        and resources.get("actual_vertices") == len(mesh["vertices_mm"])
        and resources.get("actual_triangles") == len(mesh["triangles"])
        and qualification == {
            "state": "geometry_handoff_only",
            "native_validation_passed": True,
            "capacitance_ready": False,
            "si_ready": False,
            "solver_ready": False,
        }
    )


def build_via_transition_mesh_quality(
    geometry: Mapping[str, Any], *, radial_levels: Sequence[int] = DEFAULT_LEVELS,
    maximum_terminal_relative_error: float = 0.005,
    maximum_terminal_relative_change: float = 0.01,
    maximum_terminal_normalized_radial_deviation: float = 0.00125,
    review_minimum_triangle_angle_deg: float = 0.25,
    review_maximum_triangle_aspect_ratio: float = 256.0,
) -> Dict[str, Any]:
    """Build geometry-only convergence evidence across native-admitted meshes."""

    levels = _levels(radial_levels)
    numeric_policy = (maximum_terminal_relative_error, maximum_terminal_relative_change,
                      maximum_terminal_normalized_radial_deviation,
                      review_minimum_triangle_angle_deg, review_maximum_triangle_aspect_ratio)
    if (any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or float(value) <= 0.0
            for value in numeric_policy) or review_minimum_triangle_angle_deg > 60.0
            or review_maximum_triangle_aspect_ratio < 1.0):
        raise ViaTransitionMeshQualityError("Mesh-quality thresholds must be finite, positive, and physically bounded.")
    if geometry.get("contract") != GEOMETRY_CONTRACT:
        raise ViaTransitionMeshQualityError("Mesh-quality evidence requires exact via-transition geometry v1.")
    try:
        initial_mesh = validate_via_transition_mesh(
            build_via_transition_mesh(geometry, radial_segments=levels[0]), source_geometry=geometry
        )
        exact = _exact_domain_measures(geometry)
        finest_requested_size = min(float(value) for value in geometry["refinement_sizes_mm"])
    except (KeyError, TypeError, ValueError) as error:
        raise ViaTransitionMeshQualityError(
            "Mesh-quality evidence requires a valid source-bound via-transition geometry."
        ) from error
    evidence_levels = []
    for radial_segments in levels:
        mesh = initial_mesh if radial_segments == levels[0] else validate_via_transition_mesh(
            build_via_transition_mesh(geometry, radial_segments=radial_segments), source_geometry=geometry
        )
        handoff = build_native_via_transition_handoff(mesh, source_geometry=geometry)
        quality = _measure_mesh(mesh, exact)
        coordinate_tolerance = float(mesh["tessellation"]["coordinate_tolerance_mm"])
        cosine = math.cos(math.pi / radial_segments)
        normalized_radial_deviation = max(1.0 - cosine, 1.0 / cosine - 1.0)
        land_by_layer = {item["layer_id"]: item for item in geometry["lands"]}
        clearance_margins = []
        for antipad in geometry["antipads"]:
            signal_radius = float(land_by_layer[antipad["layer_id"]]["outer_diameter_mm"]) / 2.0
            void_radius = float(antipad["diameter_mm"]) / 2.0
            clearance_margins.append(min(void_radius * (1.0 / cosine - 1.0),
                                         signal_radius * (1.0 - cosine)))
        conditioning_warnings = []
        if quality["minimum_triangle_angle_deg"] < float(review_minimum_triangle_angle_deg):
            conditioning_warnings.append("minimum_triangle_angle_below_review_threshold")
        if quality["maximum_triangle_aspect_ratio"] > float(review_maximum_triangle_aspect_ratio):
            conditioning_warnings.append("maximum_triangle_aspect_ratio_above_review_threshold")
        evidence_levels.append({
            "radial_segments": radial_segments,
            "mesh_contract": MESH_CONTRACT,
            "mesh_sha256": content_digest(mesh),
            "native_handoff_contract": HANDOFF_CONTRACT,
            "native_handoff_sha256": content_digest(handoff),
            "vertices": len(mesh["vertices_mm"]), "triangles": len(mesh["triangles"]),
            "domain_count": len(mesh["domains"]),
            "maximum_circle_radial_deviation_mm": float(mesh["tessellation"]["circle_approximation"]["max_radial_deviation_mm"]),
            "maximum_normalized_circle_radial_deviation": normalized_radial_deviation,
            "minimum_reference_clearance_margin_mm": min(clearance_margins),
            "coordinate_tolerance_mm": coordinate_tolerance,
            "topology_audit_passed": mesh["topology_audit"]["passed"],
            "native_admission_passed": _native_handoff_passed(handoff, mesh, geometry),
            "conditioning_warnings": conditioning_warnings,
            **quality,
        })
    counts_increase = all(
        evidence_levels[index + 1][key] > evidence_levels[index][key]
        for index in range(len(evidence_levels) - 1) for key in ("vertices", "triangles")
    )
    radial_deviation_decreases = all(
        evidence_levels[index + 1]["maximum_circle_radial_deviation_mm"]
        < evidence_levels[index]["maximum_circle_radial_deviation_mm"]
        for index in range(len(evidence_levels) - 1)
    )
    coarse, fine = evidence_levels[-2], evidence_levels[-1]
    coarse_domains = {item["domain_id"]: item for item in coarse["domains"]}
    terminal_changes = []
    for item in fine["domains"]:
        prior = coarse_domains[item["domain_id"]]
        terminal_changes.extend((
            _relative_change(item["surface_area_mm2"], prior["surface_area_mm2"],
                             32.0 * fine["coordinate_tolerance_mm"] ** 2),
            _relative_change(item["signed_volume_mm3"], prior["signed_volume_mm3"],
                             32.0 * fine["coordinate_tolerance_mm"] ** 3),
        ))
    max_terminal_error = max(max(item["relative_surface_area_error"], item["relative_volume_error"])
                             for item in fine["domains"])
    max_terminal_change = max(terminal_changes)
    exact_domains = _exact_domain_measures(geometry)
    level_domains = [{item["domain_id"]: item for item in level["domains"]}
                     for level in evidence_levels]
    volume_conservative_monotonic = all(
        all(level_domains[index + 1][identity]["signed_volume_mm3"]
            >= level_domains[index][identity]["signed_volume_mm3"]
            - 32.0 * evidence_levels[index]["coordinate_tolerance_mm"] ** 3
            for index in range(len(evidence_levels) - 1))
        and all(domains[identity]["signed_volume_mm3"]
                <= exact_domains[identity]["exact_volume_mm3"]
                + 32.0 * level["coordinate_tolerance_mm"] ** 3
                for domains, level in zip(level_domains, evidence_levels))
        for identity in exact_domains
    )
    quality_passed = all(
        item["minimum_triangle_area_mm2"] > 32.0 * item["coordinate_tolerance_mm"] ** 2
        and item["minimum_triangle_angle_deg"] > 0.0
        and math.isfinite(item["maximum_triangle_aspect_ratio"])
        and item["maximum_reference_void_boundary_error_mm"] <= 2.0 * item["coordinate_tolerance_mm"]
        and item["minimum_reference_clearance_margin_mm"] >= -2.0 * item["coordinate_tolerance_mm"]
        and all(domain["signed_volume_mm3"] > 32.0 * item["coordinate_tolerance_mm"] ** 3
                for domain in item["domains"])
        and item["topology_audit_passed"] and item["native_admission_passed"]
        for item in evidence_levels
    )
    convergence_passed = (
        counts_increase and radial_deviation_decreases and volume_conservative_monotonic and quality_passed
        and fine["maximum_circle_radial_deviation_mm"] <= finest_requested_size
        and fine["maximum_normalized_circle_radial_deviation"]
        <= float(maximum_terminal_normalized_radial_deviation)
        and max_terminal_error <= float(maximum_terminal_relative_error)
        and max_terminal_change <= float(maximum_terminal_relative_change)
    )
    if not convergence_passed:
        raise ViaTransitionMeshQualityError(
            "Via-transition geometry quality or terminal domain convergence failed the declared policy: "
            f"counts={counts_increase}, radial={radial_deviation_decreases}, "
            f"volume={volume_conservative_monotonic}, quality={quality_passed}, "
            f"terminal_error={max_terminal_error:.9g}, terminal_change={max_terminal_change:.9g}, "
            f"normalized_radial={fine['maximum_normalized_circle_radial_deviation']:.9g}."
        )
    report: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {"geometry_contract": GEOMETRY_CONTRACT, "geometry_sha256": content_digest(geometry),
                   "design_id": geometry["design_id"], "via_id": geometry["via_id"],
                   "source_via_id": geometry["source_via_id"]},
        "policy": {"radial_levels": levels,
                   "maximum_terminal_relative_error": float(maximum_terminal_relative_error),
                   "maximum_terminal_relative_change": float(maximum_terminal_relative_change),
                   "maximum_terminal_normalized_radial_deviation": float(maximum_terminal_normalized_radial_deviation),
                   "review_minimum_triangle_angle_deg": float(review_minimum_triangle_angle_deg),
                   "review_maximum_triangle_aspect_ratio": float(review_maximum_triangle_aspect_ratio),
                   "maximum_terminal_radial_deviation_mm": finest_requested_size},
        "levels": evidence_levels,
        "convergence": {"coarse_radial_segments": coarse["radial_segments"],
                        "fine_radial_segments": fine["radial_segments"],
                        "counts_strictly_increase": counts_increase,
                        "radial_deviation_strictly_decreases": radial_deviation_decreases,
                        "volumes_conservative_and_monotonic": volume_conservative_monotonic,
                        "maximum_terminal_relative_error": max_terminal_error,
                        "maximum_terminal_relative_change": max_terminal_change,
                        "terminal_radial_deviation_mm": fine["maximum_circle_radial_deviation_mm"],
                        "terminal_normalized_radial_deviation": fine["maximum_normalized_circle_radial_deviation"],
                        "all_levels_topology_validated": True, "all_levels_native_admitted": True,
                        "passed": True},
        "qualification": {"state": "geometry_domain_convergence_evidence",
                          "geometry_convergence_passed": True,
                          "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }
    return report


def validate_via_transition_mesh_quality(
    report: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Rebuild bounded evidence and reject any stale, forged, or promoted claim."""

    try:
        if report.get("contract") != CONTRACT:
            raise ViaTransitionMeshQualityError("Unexpected via-transition mesh-quality contract.")
        policy = report["policy"]
        regenerated = build_via_transition_mesh_quality(
            source_geometry,
            radial_levels=policy["radial_levels"],
            maximum_terminal_relative_error=policy["maximum_terminal_relative_error"],
            maximum_terminal_relative_change=policy["maximum_terminal_relative_change"],
            maximum_terminal_normalized_radial_deviation=(
                policy["maximum_terminal_normalized_radial_deviation"]
            ),
            review_minimum_triangle_angle_deg=policy["review_minimum_triangle_angle_deg"],
            review_maximum_triangle_aspect_ratio=policy["review_maximum_triangle_aspect_ratio"],
        )
    except ViaTransitionMeshQualityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ViaTransitionMeshQualityError("Malformed via-transition mesh-quality evidence.") from error
    if dict(report) != regenerated:
        raise ViaTransitionMeshQualityError(
            "Via-transition mesh-quality evidence does not match deterministic regeneration."
        )
    return regenerated


__all__ = ["CONTRACT", "DEFAULT_LEVELS", "ERROR_CODE", "ViaTransitionMeshQualityError",
           "build_via_transition_mesh_quality", "validate_via_transition_mesh_quality"]
