"""Regenerated geometry-convergence evidence for generalized plane mesh v2."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Mapping

from .design_ir_v2_schema import content_digest
from .generalized_reference_plane_native_handoff import (
    build_generalized_reference_plane_native_handoff,
)
from .reference_plane_antipad_geometry_v2 import CONTRACT as GEOMETRY_V2_CONTRACT
from .reference_plane_antipad_mesh_v2 import (
    CONTRACT as MESH_CONTRACT,
    MAX_WORK_STEPS,
    build_reference_plane_antipad_mesh_v2,
)


CONTRACT = "spike/pcb-reference-plane-antipad-mesh-quality/v2"
ERROR_CODE = "SPIKE-BE-MESH-E-0015"
RADIAL_LEVELS = (8, 16, 32, 64)
MAXIMUM_TERMINAL_RELATIVE_AREA_ERROR = 0.0015


class GeneralizedReferencePlaneMeshQualityError(ValueError):
    code = ERROR_CODE


def _triangle_quality(points: list[list[float]]) -> float:
    edges2 = []
    for index in range(3):
        first, second = points[index], points[(index + 1) % 3]
        edges2.append(sum((float(first[axis]) - float(second[axis])) ** 2 for axis in range(3)))
    left = [float(points[1][axis]) - float(points[0][axis]) for axis in range(3)]
    right = [float(points[2][axis]) - float(points[0][axis]) for axis in range(3)]
    cross = [left[1] * right[2] - left[2] * right[1],
             left[2] * right[0] - left[0] * right[2],
             left[0] * right[1] - left[1] * right[0]]
    twice_area = math.sqrt(sum(value * value for value in cross))
    denominator = sum(edges2)
    return 2.0 * math.sqrt(3.0) * twice_area / denominator if denominator > 0 else 0.0


def _analytic_area(region: Mapping[str, Any], geometry_contract: str) -> float:
    key = ("analytic_resolved_area_mm2" if geometry_contract == GEOMETRY_V2_CONTRACT
           else "analytic_flattened_resolved_area_mm2")
    value = float(region[key])
    if not math.isfinite(value) or not value > 0:
        raise GeneralizedReferencePlaneMeshQualityError("Analytic source area is invalid.")
    return value


def build_generalized_reference_plane_mesh_quality(
    geometry: Mapping[str, Any], *,
    cancel_check: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    geometry_contract = geometry.get("contract")
    levels = []
    errors_by_region: dict[str, list[float]] = {}
    total_work = 0
    for radial_segments in RADIAL_LEVELS:
        try:
            mesh = build_reference_plane_antipad_mesh_v2(
                geometry, radial_segments=radial_segments,
                maximum_work_steps=MAX_WORK_STEPS, cancel_check=cancel_check)
            handoff = build_generalized_reference_plane_native_handoff(
                mesh, source_geometry=geometry)
        except ValueError as error:
            if "cancelled" in str(error):
                raise GeneralizedReferencePlaneMeshQualityError(
                    "Generalized mesh quality evaluation was cancelled.") from error
            raise GeneralizedReferencePlaneMeshQualityError(
                "A generalized refinement level failed geometry or native admission."
            ) from error
        total_work += int(mesh["resources"]["actual_work_steps"])
        region_records = []
        for source_region, domain in zip(geometry["regions"], mesh["domains"]):
            analytic_area = _analytic_area(source_region, str(geometry_contract))
            discrete_area = float(domain["exact_discrete_area_mm2"])
            deficit = analytic_area - discrete_area
            relative = deficit / analytic_area
            if deficit < -1e-12 * max(1.0, analytic_area) or not math.isfinite(relative):
                raise GeneralizedReferencePlaneMeshQualityError(
                    "The discrete antipad void is not conservative relative to admitted geometry."
                )
            errors_by_region.setdefault(domain["id"], []).append(relative)
            region_records.append({
                "domain_id": domain["id"], "analytic_area_mm2": analytic_area,
                "discrete_area_mm2": discrete_area, "conservative_area_deficit_mm2": deficit,
                "relative_area_error": relative,
                "analytic_volume_mm3": analytic_area *
                    (float(source_region["z_max_mm"]) - float(source_region["z_min_mm"])),
                "discrete_volume_mm3": float(domain["exact_discrete_volume_mm3"]),
                "source_cutout_count": int(domain["source_cutout_count"]),
                "antipad_radial_inflation_grid_units":
                    int(domain["antipad_radial_inflation_grid_units"]),
            })
        qualities = [_triangle_quality([mesh["vertices_mm"][index]
                                        for index in triangle["vertex_indices"]])
                     for triangle in mesh["triangles"]
                     if triangle["surface_role"] == "reference_zone_upper_face"]
        if not qualities or min(qualities) <= 0 or not all(math.isfinite(item) for item in qualities):
            raise GeneralizedReferencePlaneMeshQualityError(
                "A generalized refinement level contains invalid triangle conditioning."
            )
        levels.append({
            "radial_segments": radial_segments,
            "mesh_sha256": content_digest(mesh), "native_handoff_sha256": content_digest(handoff),
            "vertex_count": len(mesh["vertices_mm"]), "triangle_count": len(mesh["triangles"]),
            "boundary_loop_count": len(mesh["boundary_loops"]),
            "work_steps": int(mesh["resources"]["actual_work_steps"]),
            "minimum_upper_face_triangle_quality": min(qualities),
            "regions": region_records,
            "native_admission_passed": True,
        })
    for identity, values in errors_by_region.items():
        if any(values[index + 1] > values[index] + 1e-12
               for index in range(len(values) - 1)):
            raise GeneralizedReferencePlaneMeshQualityError(
                f"Antipad geometry error is not monotonic for {identity}."
            )
        if values[-1] > MAXIMUM_TERMINAL_RELATIVE_AREA_ERROR:
            raise GeneralizedReferencePlaneMeshQualityError(
                f"Terminal antipad geometry error exceeds policy for {identity}."
            )
    return {
        "contract": CONTRACT,
        "source": {"mesh_contract": MESH_CONTRACT,
                   "geometry_contract": geometry_contract,
                   "geometry_sha256": content_digest(geometry),
                   "design_id": geometry["source"]["design_id"],
                   "via_id": geometry["source"]["via_id"]},
        "policy": {"radial_levels": list(RADIAL_LEVELS),
                   "maximum_terminal_relative_area_error":
                       MAXIMUM_TERMINAL_RELATIVE_AREA_ERROR,
                   "require_monotonic_conservative_area_error": True,
                   "triangle_quality_metric": "two_sqrt3_area_over_sum_edge_squared",
                   "source_curve_error_included": False},
        "levels": levels,
        "resources": {"maximum_work_steps_per_level": MAX_WORK_STEPS,
                      "actual_total_work_steps": total_work,
                      "cancellation_supported": True},
        "qualification": {"state": "generalized_plane_geometry_convergence_only",
                          "native_admission_all_levels": True,
                          "geometry_convergence_passed": True,
                          "mesh_quality_characterized": True,
                          "source_curve_convergence_performed": False,
                          "field_convergence_performed": False,
                          "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False,
                          "solver_ready": False},
    }


def validate_generalized_reference_plane_mesh_quality(
    report: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    regenerated = build_generalized_reference_plane_mesh_quality(source_geometry)
    if dict(report) != regenerated:
        raise GeneralizedReferencePlaneMeshQualityError(
            "Generalized mesh quality does not match deterministic regeneration."
        )
    return regenerated


__all__ = ["CONTRACT", "ERROR_CODE", "GeneralizedReferencePlaneMeshQualityError",
           "build_generalized_reference_plane_mesh_quality",
           "validate_generalized_reference_plane_mesh_quality"]
