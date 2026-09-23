"""Source-bound ownership overlay for generalized reference-plane meshes."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Any, Dict, Mapping, Sequence

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_geometry_v2 import CONTRACT as GEOMETRY_V2_CONTRACT
from .reference_plane_antipad_geometry_v3 import CONTRACT as GEOMETRY_V3_CONTRACT
from .reference_plane_antipad_mesh_v2 import (
    CONTRACT as MESH_CONTRACT,
    GRID_MM,
    validate_reference_plane_antipad_mesh_v2,
)


CONTRACT = "spike/pcb-reference-plane-mesh-ownership/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0014"


class ReferencePlaneMeshOwnershipError(ValueError):
    code = ERROR_CODE


def _grid(value: Any) -> int:
    number = float(value)
    scaled = number / GRID_MM
    rounded = round(scaled)
    if not isfinite(number) or abs(scaled - rounded) > 1e-6:
        raise ReferencePlaneMeshOwnershipError(
            "Ownership overlay encountered a vertex outside the exact mesh grid."
        )
    return int(rounded)


def _ring(values: Sequence[Sequence[float]]) -> list[tuple[int, int]]:
    return [(_grid(item[0]), _grid(item[1])) for item in values]


def _relation(
    x_numerator: int, y_numerator: int, denominator: int,
    ring: Sequence[tuple[int, int]],
) -> int:
    """Return -1 outside, 0 on boundary, or 1 inside using integer predicates."""

    winding = 0
    for index, first in enumerate(ring):
        second = ring[(index + 1) % len(ring)]
        cross = ((second[0] - first[0]) * (y_numerator - first[1] * denominator)
                 - (second[1] - first[1]) * (x_numerator - first[0] * denominator))
        if (cross == 0
                and min(first[0], second[0]) * denominator <= x_numerator
                <= max(first[0], second[0]) * denominator
                and min(first[1], second[1]) * denominator <= y_numerator
                <= max(first[1], second[1]) * denominator):
            return 0
        first_y, second_y = first[1] * denominator, second[1] * denominator
        if first_y <= y_numerator < second_y and cross > 0:
            winding += 1
        elif second_y <= y_numerator < first_y and cross < 0:
            winding -= 1
    return 1 if winding else -1


def _inside_admitted_region(
    x_numerator: int, y_numerator: int, denominator: int,
    outer: Sequence[tuple[int, int]], holes: Sequence[Sequence[tuple[int, int]]],
    antipad_center: tuple[int, int], antipad_radius: int,
) -> bool:
    if _relation(x_numerator, y_numerator, denominator, outer) < 0:
        return False
    if any(_relation(x_numerator, y_numerator, denominator, hole) > 0 for hole in holes):
        return False
    dx = x_numerator - antipad_center[0] * denominator
    dy = y_numerator - antipad_center[1] * denominator
    return dx * dx + dy * dy >= (antipad_radius * denominator) ** 2


def build_reference_plane_mesh_ownership_overlay(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Prove ownership for every supplied domain; never claim full-board coverage."""

    try:
        validated = validate_reference_plane_antipad_mesh_v2(
            mesh, source_geometry=source_geometry
        )
        geometry_contract = str(source_geometry["contract"])
        curved = geometry_contract == GEOMETRY_V3_CONTRACT
        if geometry_contract not in {GEOMETRY_V2_CONTRACT, GEOMETRY_V3_CONTRACT}:
            raise KeyError("geometry contract")
        vertices = [tuple(_grid(value) for value in item) for item in validated["vertices_mm"]]
        regions = {str(item["resolved_region_sha256"]): item
                   for item in source_geometry["regions"]}
        if len(regions) != len(source_geometry["regions"]):
            raise ReferencePlaneMeshOwnershipError(
                "Ownership overlay source regions are duplicated."
            )
        triangles_by_domain: Dict[str, list[Mapping[str, Any]]] = {}
        for triangle in validated["triangles"]:
            triangles_by_domain.setdefault(str(triangle["domain_id"]), []).append(triangle)
        loops_by_domain: Counter[str] = Counter(
            str(item["domain_id"]) for item in validated["boundary_loops"]
        )
        seen_owners: set[tuple[str, str]] = set()
        domain_reports = []
        checked_references = 0
        for domain in validated["domains"]:
            region = regions.get(str(domain["resolved_region_sha256"]))
            if region is None:
                raise ReferencePlaneMeshOwnershipError(
                    "A mesh domain has no digest-bound source region owner."
                )
            source_zone = region["source_zone"]
            outer_key = "flattened_outer_ring_mm" if curved else "outer_ring_mm"
            holes_key = "flattened_source_hole_rings_mm" if curved else "source_hole_rings_mm"
            owner_key = (str(source_zone["zone_id"]), str(source_zone["layer_id"]))
            if owner_key in seen_owners:
                raise ReferencePlaneMeshOwnershipError(
                    "Overlapping duplicate zone/layer domain ownership is unsupported."
                )
            seen_owners.add(owner_key)
            expected_sources = {
                str(source_zone["zone_id"]), str(source_zone["source_zone_id"]),
                *(str(item["source_id"]) for item in region["antipad_holes"]),
            }
            if (domain["reference_zone_id"] != source_zone["zone_id"]
                    or domain["net_id"] != source_zone["net_id"]
                    or domain["layer_ids"] != [source_zone["layer_id"]]
                    or domain["source_zone_sha256"] != region["source_zone_sha256"]
                    or set(domain["source_ids"]) != expected_sources):
                raise ReferencePlaneMeshOwnershipError(
                    "Mesh domain identity or provenance escapes its source owner."
                )
            outer = _ring(source_zone[outer_key])
            holes = [_ring(item) for item in source_zone[holes_key]]
            antipads = region["antipad_holes"]
            if len(antipads) != 1:
                raise ReferencePlaneMeshOwnershipError(
                    "Ownership overlay v1 requires exactly one admitted antipad per region."
                )
            center = (_grid(antipads[0]["center_mm"][0]), _grid(antipads[0]["center_mm"][1]))
            radius = _grid(antipads[0]["radius_mm"])
            z_min, z_max = _grid(region["z_min_mm"]), _grid(region["z_max_mm"])
            triangles = triangles_by_domain.get(str(domain["id"]), [])
            declared_ids = set(domain["triangle_ids"])
            actual_ids = {str(item["id"]) for item in triangles}
            if declared_ids != actual_ids or not triangles:
                raise ReferencePlaneMeshOwnershipError(
                    "Mesh domain triangle ownership is incomplete."
                )
            for triangle in triangles:
                if not set(triangle["source_ids"]).issubset(expected_sources):
                    raise ReferencePlaneMeshOwnershipError(
                        "Triangle provenance escapes its source owner."
                    )
                points = [vertices[int(index)] for index in triangle["vertex_indices"]]
                for x_value, y_value, z_value in points:
                    if (not z_min <= z_value <= z_max
                            or not _inside_admitted_region(
                                x_value, y_value, 1, outer, holes, center, radius
                            )):
                        raise ReferencePlaneMeshOwnershipError(
                            "Triangle geometry escapes its admitted source region."
                        )
                if triangle["surface_role"] in {
                    "reference_zone_lower_face", "reference_zone_upper_face"
                }:
                    if not _inside_admitted_region(
                        sum(item[0] for item in points), sum(item[1] for item in points),
                        3, outer, holes, center, radius,
                    ):
                        raise ReferencePlaneMeshOwnershipError(
                            "A planar triangle crosses an excluded source void."
                        )
                checked_references += 3
            for loop in validated["boundary_loops"]:
                if (loop["domain_id"] == domain["id"]
                        and not set(loop["source_ids"]).issubset(expected_sources)):
                    raise ReferencePlaneMeshOwnershipError(
                        "Boundary-loop provenance escapes its source owner."
                    )
            domain_reports.append({
                "domain_id": domain["id"], "reference_zone_id": source_zone["zone_id"],
                "source_zone_id": source_zone["source_zone_id"],
                "net_id": source_zone["net_id"], "layer_id": source_zone["layer_id"],
                "source_zone_sha256": region["source_zone_sha256"],
                "resolved_region_sha256": region["resolved_region_sha256"],
                "triangle_count": len(triangles),
                "vertex_reference_count": 3 * len(triangles),
                "boundary_loop_count": loops_by_domain[str(domain["id"])],
                "source_cutout_count": len(holes), "antipad_count": 1,
                "xy_containment_checked": True, "z_containment_checked": True,
                "provenance_checked": True,
            })
        if set(triangles_by_domain) != {str(item["id"]) for item in validated["domains"]}:
            raise ReferencePlaneMeshOwnershipError("Orphan mesh triangles are unsupported.")
    except ReferencePlaneMeshOwnershipError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ReferencePlaneMeshOwnershipError(
            "Generalized ownership overlay validation failed."
        ) from error
    return {
        "contract": CONTRACT,
        "source": {
            "mesh_contract": MESH_CONTRACT, "mesh_sha256": content_digest(validated),
            "geometry_contract": geometry_contract,
            "geometry_sha256": content_digest(source_geometry),
            "design_id": validated["source"]["design_id"],
            "via_id": validated["source"]["via_id"],
            "source_via_id": validated["source"]["source_via_id"],
        },
        "domains": domain_reports,
        "summary": {
            "status": "passed", "checked_domains": len(domain_reports),
            "checked_triangles": len(validated["triangles"]),
            "checked_vertex_references": checked_references,
            "checked_boundary_loops": len(validated["boundary_loops"]),
            "duplicate_owner_count": 0, "orphan_triangle_count": 0,
        },
        "qualification": {
            "state": "admitted_source_region_ownership_overlay_only",
            "all_supplied_domains_owned": True,
            "complete_board_copper_coverage": False,
            "source_curve_copper_envelope_proven": not curved,
            "native_geometric_overlay_verified": False,
            "physics_convergence_performed": False,
            "solver_ready": False,
        },
    }


def validate_reference_plane_mesh_ownership_overlay(
    report: Mapping[str, Any], *, mesh: Mapping[str, Any],
    source_geometry: Mapping[str, Any],
) -> Dict[str, Any]:
    regenerated = build_reference_plane_mesh_ownership_overlay(
        mesh, source_geometry=source_geometry
    )
    if dict(report) != regenerated:
        raise ReferencePlaneMeshOwnershipError(
            "Ownership overlay does not match deterministic regeneration."
        )
    return regenerated


__all__ = [
    "CONTRACT", "ERROR_CODE", "ReferencePlaneMeshOwnershipError",
    "build_reference_plane_mesh_ownership_overlay",
    "validate_reference_plane_mesh_ownership_overlay",
]
