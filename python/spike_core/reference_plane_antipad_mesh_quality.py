"""Geometry-only convergence evidence for complete reference-plane antipad meshes."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_geometry import CONTRACT as GEOMETRY_CONTRACT
from .reference_plane_antipad_mesh import (
    CONTRACT as MESH_CONTRACT,
    build_reference_plane_antipad_mesh,
    validate_reference_plane_antipad_mesh,
)
from .reference_plane_antipad_native_handoff import (
    CONTRACT as HANDOFF_CONTRACT,
    build_native_reference_plane_antipad_handoff,
)
from .via_transition_mesh_quality import _levels, _measure_mesh, _relative_change


CONTRACT = "spike/pcb-reference-plane-antipad-mesh-quality/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0010"
DEFAULT_LEVELS = (8, 16, 32, 64)


class ReferencePlaneAntipadMeshQualityError(ValueError):
    """Raised when complete-zone geometry quality evidence fails."""

    code = ERROR_CODE


def _exact_measures(geometry: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for region in geometry["regions"]:
        ring = region["source_zone"]["outer_ring_mm"]
        perimeter = math.fsum(
            math.hypot(float(ring[(index + 1) % len(ring)][0]) - float(point[0]),
                       float(ring[(index + 1) % len(ring)][1]) - float(point[1]))
            for index, point in enumerate(ring)
        )
        height = float(region["z_max_mm"]) - float(region["z_min_mm"])
        radius = float(region["antipad_holes"][0]["radius_mm"])
        area = float(region["exact_area_mm2"])
        result[region["region_id"]] = {
            "kind": "reference_plane_full_zone",
            "exact_surface_area_mm2": 2.0 * area + (perimeter + 2.0 * math.pi * radius) * height,
            "exact_volume_mm3": float(region["exact_volume_mm3"]),
        }
    return result


def _discrete_measures(geometry: Mapping[str, Any], segments: int) -> Dict[str, tuple[float, float]]:
    result = {}
    for region in geometry["regions"]:
        ring, radius = region["source_zone"]["outer_ring_mm"], float(region["antipad_holes"][0]["radius_mm"])
        perimeter = math.fsum(math.hypot(float(ring[(i + 1) % len(ring)][0]) - float(p[0]),
                                        float(ring[(i + 1) % len(ring)][1]) - float(p[1]))
                                for i, p in enumerate(ring))
        polygon_area = float(region["exact_area_mm2"]) + math.pi * radius * radius
        tangent = math.tan(math.pi / segments)
        resolved_area = polygon_area - segments * radius * radius * tangent
        height = float(region["z_max_mm"]) - float(region["z_min_mm"])
        result[region["region_id"]] = (
            2.0 * resolved_area + height * (perimeter + 2.0 * segments * radius * tangent),
            resolved_area * height,
        )
    return result


def _native_passed(handoff: Mapping[str, Any], mesh: Mapping[str, Any],
                   geometry: Mapping[str, Any]) -> bool:
    source, native = handoff.get("source", {}), handoff.get("native_validation", {})
    return (
        handoff.get("contract") == HANDOFF_CONTRACT
        and source.get("mesh_contract") == MESH_CONTRACT
        and source.get("mesh_sha256") == content_digest(mesh)
        and source.get("geometry_contract") == GEOMETRY_CONTRACT
        and source.get("geometry_sha256") == content_digest(geometry)
        and native.get("status") == "passed"
        and all(native.get(key) is True for key in (
            "finite_vertices_checked", "compact_indices_checked", "closed_domains_checked",
            "domain_ownership_checked", "provenance_checked"))
        and native.get("solver_entry_points_exposed") is False
        and native.get("vertex_count") == len(mesh["vertices_mm"])
        and native.get("triangle_count") == len(mesh["triangles"])
        and native.get("domain_count") == len(mesh["domains"])
        and handoff.get("qualification") == {
            "state": "full_reference_zone_geometry_handoff_only",
            "native_validation_passed": True,
            "physics_convergence_performed": False,
            "capacitance_ready": False, "si_ready": False, "solver_ready": False,
        }
    )


def build_reference_plane_antipad_mesh_quality(
    geometry: Mapping[str, Any], *, radial_levels: Sequence[int] = DEFAULT_LEVELS,
    maximum_terminal_relative_error: float = 0.005,
    maximum_terminal_relative_change: float = 0.01,
    maximum_terminal_normalized_radial_deviation: float = 0.00125,
) -> Dict[str, Any]:
    """Regenerate four native-admitted levels and qualify geometry convergence only."""

    try:
        levels = _levels(radial_levels)
    except ValueError as error:
        raise ReferencePlaneAntipadMeshQualityError(str(error)) from error
    thresholds = (maximum_terminal_relative_error, maximum_terminal_relative_change,
                  maximum_terminal_normalized_radial_deviation)
    if (geometry.get("contract") != GEOMETRY_CONTRACT
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(float(value)) or not 0.0 < float(value) <= 1.0
                   for value in thresholds)):
        raise ReferencePlaneAntipadMeshQualityError(
            "Full-zone quality evidence requires valid geometry and bounded positive thresholds."
        )
    try:
        exact = _exact_measures(geometry)
        evidence = []
        for segments in levels:
            mesh = validate_reference_plane_antipad_mesh(
                build_reference_plane_antipad_mesh(geometry, radial_segments=segments),
                source_geometry=geometry,
            )
            handoff = build_native_reference_plane_antipad_handoff(mesh, source_geometry=geometry)
            quality = _measure_mesh(mesh, exact)
            discrete = _discrete_measures(geometry, segments)
            for domain in quality["domains"]:
                expected_surface, expected_volume = discrete[domain["domain_id"]]
                domain["analytic_discrete_surface_area_mm2"] = expected_surface
                domain["analytic_discrete_volume_mm3"] = expected_volume
                domain["relative_discrete_surface_discrepancy"] = abs(
                    domain["surface_area_mm2"] - expected_surface) / expected_surface
                domain["relative_discrete_volume_discrepancy"] = abs(
                    domain["signed_volume_mm3"] - expected_volume) / expected_volume
            normalized = 1.0 / math.cos(math.pi / segments) - 1.0
            maximum_radius = max(float(item["antipad_holes"][0]["radius_mm"])
                                 for item in geometry["regions"])
            radial_error = maximum_radius * normalized
            clearance = min(float(item["minimum_antipad_to_outer_boundary_mm"])
                            for item in geometry["regions"]) - radial_error
            evidence.append({
                "radial_segments": segments, "mesh_contract": MESH_CONTRACT,
                "mesh_sha256": content_digest(mesh), "native_handoff_contract": HANDOFF_CONTRACT,
                "native_handoff_sha256": content_digest(handoff),
                "vertices": len(mesh["vertices_mm"]), "triangles": len(mesh["triangles"]),
                "domain_count": len(mesh["domains"]),
                "maximum_antipad_radial_deviation_mm": radial_error,
                "maximum_normalized_antipad_radial_deviation": normalized,
                "minimum_outer_boundary_clearance_margin_mm": clearance,
                "coordinate_tolerance_mm": float(mesh["tessellation"]["coordinate_tolerance_mm"]),
                "topology_audit_passed": mesh["topology_audit"]["passed"],
                "native_admission_passed": _native_passed(handoff, mesh, geometry),
                **quality,
            })
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReferencePlaneAntipadMeshQualityError):
            raise
        raise ReferencePlaneAntipadMeshQualityError(
            "Full-zone quality evidence could not regenerate native-admitted meshes."
        ) from error
    counts = all(evidence[index + 1][key] > evidence[index][key]
                 for index in range(len(evidence) - 1) for key in ("vertices", "triangles"))
    radial = all(evidence[index + 1]["maximum_antipad_radial_deviation_mm"]
                 < evidence[index]["maximum_antipad_radial_deviation_mm"]
                 for index in range(len(evidence) - 1))
    domain_levels = [{item["domain_id"]: item for item in level["domains"]} for level in evidence]
    volumes = all(
        all(domain_levels[index + 1][identity]["signed_volume_mm3"]
            >= domain_levels[index][identity]["signed_volume_mm3"]
            - 32.0 * evidence[index]["coordinate_tolerance_mm"] ** 3
            for index in range(len(evidence) - 1))
        and all(domains[identity]["signed_volume_mm3"] <= exact[identity]["exact_volume_mm3"]
                + 32.0 * level["coordinate_tolerance_mm"] ** 3
                for domains, level in zip(domain_levels, evidence))
        for identity in exact
    )
    surface_errors_nonincreasing = all(
        all(domain_levels[index + 1][identity]["relative_surface_area_error"]
            <= domain_levels[index][identity]["relative_surface_area_error"] + 1e-15
            for index in range(len(evidence) - 1)) for identity in exact)
    coarse, fine = evidence[-2], evidence[-1]
    changes = []
    for item in fine["domains"]:
        prior = domain_levels[-2][item["domain_id"]]
        changes.extend((
            _relative_change(item["surface_area_mm2"], prior["surface_area_mm2"], 1e-18),
            _relative_change(item["signed_volume_mm3"], prior["signed_volume_mm3"], 1e-18),
        ))
    terminal_error = max(max(item["relative_surface_area_error"], item["relative_volume_error"])
                         for item in fine["domains"])
    terminal_change = max(changes)
    quality = all(level["topology_audit_passed"] and level["native_admission_passed"]
                  and level["minimum_triangle_area_mm2"] > 32.0 * level["coordinate_tolerance_mm"] ** 2
                  and level["minimum_triangle_angle_deg"] > 0.0
                  and math.isfinite(level["maximum_triangle_aspect_ratio"])
                  and level["minimum_outer_boundary_clearance_margin_mm"] >= 2.0 * level["coordinate_tolerance_mm"]
                  and all(domain["relative_discrete_surface_discrepancy"] <= 1e-12
                          and domain["relative_discrete_volume_discrepancy"] <= 1e-12
                          for domain in level["domains"])
                  for level in evidence)
    passed = (counts and radial and volumes and surface_errors_nonincreasing and quality
              and terminal_error <= float(maximum_terminal_relative_error)
              and terminal_change <= float(maximum_terminal_relative_change)
              and fine["maximum_normalized_antipad_radial_deviation"]
              <= float(maximum_terminal_normalized_radial_deviation))
    if not passed:
        raise ReferencePlaneAntipadMeshQualityError(
            "Full-zone geometry quality or terminal convergence failed: "
            f"counts={counts}, radial={radial}, volumes={volumes}, "
            f"surface_errors={surface_errors_nonincreasing}, quality={quality}, "
            f"terminal_error={terminal_error:.9g}, terminal_change={terminal_change:.9g}."
        )
    return {
        "contract": CONTRACT,
        "source": {"geometry_contract": GEOMETRY_CONTRACT,
                   "geometry_sha256": content_digest(geometry), **geometry["source"]},
        "policy": {"radial_levels": levels,
                   "maximum_terminal_relative_error": float(maximum_terminal_relative_error),
                   "maximum_terminal_relative_change": float(maximum_terminal_relative_change),
                   "maximum_terminal_normalized_radial_deviation": float(maximum_terminal_normalized_radial_deviation)},
        "levels": evidence,
        "convergence": {"coarse_radial_segments": coarse["radial_segments"],
                        "fine_radial_segments": fine["radial_segments"],
                        "counts_strictly_increase": True,
                        "radial_deviation_strictly_decreases": True,
                        "volumes_conservative_and_monotonic": True,
                        "surface_errors_nonincreasing": True,
                        "maximum_terminal_relative_error": terminal_error,
                        "maximum_terminal_relative_change": terminal_change,
                        "terminal_normalized_radial_deviation": fine["maximum_normalized_antipad_radial_deviation"],
                        "all_levels_topology_validated": True,
                        "all_levels_native_admitted": True, "passed": True},
        "qualification": {"state": "full_reference_zone_geometry_domain_convergence_evidence",
                          "geometry_convergence_passed": True,
                          "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }


def validate_reference_plane_antipad_mesh_quality(
    report: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Regenerate the complete report to reject stale or promoted evidence."""

    try:
        policy = report["policy"]
        regenerated = build_reference_plane_antipad_mesh_quality(
            source_geometry, radial_levels=policy["radial_levels"],
            maximum_terminal_relative_error=policy["maximum_terminal_relative_error"],
            maximum_terminal_relative_change=policy["maximum_terminal_relative_change"],
            maximum_terminal_normalized_radial_deviation=policy["maximum_terminal_normalized_radial_deviation"],
        )
    except ReferencePlaneAntipadMeshQualityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ReferencePlaneAntipadMeshQualityError("Malformed full-zone quality evidence.") from error
    if dict(report) != regenerated:
        raise ReferencePlaneAntipadMeshQualityError(
            "Full-zone mesh-quality evidence does not match deterministic regeneration."
        )
    return regenerated


__all__ = ["CONTRACT", "DEFAULT_LEVELS", "ERROR_CODE",
           "ReferencePlaneAntipadMeshQualityError",
           "build_reference_plane_antipad_mesh_quality",
           "validate_reference_plane_antipad_mesh_quality"]
