"""Solver-isolated native admission for generalized reference-plane mesh v2."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_mesh_v2 import (
    CONTRACT as MESH_CONTRACT,
    validate_reference_plane_antipad_mesh_v2,
)
from .via_transition_mesh import MAX_SERIALIZED_BYTES, MAX_TRIANGLES, MAX_VERTICES


CONTRACT = "spike/native-reference-plane-antipad-handoff/v2"
ERROR_CODE = "SPIKE-BE-MESH-E-0014"


class GeneralizedReferencePlaneNativeHandoffError(ValueError):
    code = ERROR_CODE


def _native() -> Any:
    try:
        from python import spike_peec_native as native
    except ImportError:
        try:
            import spike_peec_native as native  # type: ignore[no-redef]
        except ImportError as error:
            raise GeneralizedReferencePlaneNativeHandoffError(
                "The generalized native plane validator is unavailable."
            ) from error
    required = ("GeneralizedReferencePlaneVertex", "GeneralizedReferencePlaneTriangle",
                "GeneralizedReferencePlaneDomain", "GeneralizedReferencePlaneLoop",
                "GeneralizedReferencePlaneMeshInput",
                "validate_generalized_reference_plane_mesh_input")
    if any(not hasattr(native, name) for name in required):
        raise GeneralizedReferencePlaneNativeHandoffError(
            "The native extension lacks generalized plane admission."
        )
    return native


def build_generalized_reference_plane_native_handoff(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    try:
        validated = validate_reference_plane_antipad_mesh_v2(
            mesh, source_geometry=source_geometry)
    except (KeyError, TypeError, ValueError) as error:
        raise GeneralizedReferencePlaneNativeHandoffError(
            "Generalized mesh failed deterministic validation before native admission."
        ) from error
    expected_digest = content_digest(source_geometry)
    native = _native()
    native_input = native.GeneralizedReferencePlaneMeshInput()
    native_input.contract = MESH_CONTRACT
    native_input.source_geometry_contract = validated["source"]["geometry_contract"]
    native_input.source_geometry_sha256 = expected_digest
    native_input.design_id = validated["source"]["design_id"]
    native_input.via_id = validated["source"]["via_id"]
    native_input.source_via_id = validated["source"]["source_via_id"]
    vertices = []
    for source in validated["vertices_mm"]:
        item = native.GeneralizedReferencePlaneVertex()
        item.x, item.y, item.z = (float(value) for value in source)
        vertices.append(item)
    native_input.vertices = vertices
    domain_indexes = {source["id"]: index for index, source in enumerate(validated["domains"])}
    domains = []
    for source in validated["domains"]:
        item = native.GeneralizedReferencePlaneDomain()
        item.id, item.net_id, item.layer_id = source["id"], source["net_id"], source["layer_ids"][0]
        item.source_ids = source["source_ids"]
        item.reference_zone_id = source["reference_zone_id"]
        item.source_zone_sha256 = source["source_zone_sha256"]
        item.resolved_region_sha256 = source["resolved_region_sha256"]
        item.source_boundary_sha256 = source.get("source_boundary_sha256", "")
        item.flattened_boundary_sha256 = source.get("flattened_boundary_sha256", "")
        item.antipad_radius_mm = float(source["antipad_radius_mm"])
        item.exact_discrete_area_mm2 = float(source["exact_discrete_area_mm2"])
        item.exact_discrete_volume_mm3 = float(source["exact_discrete_volume_mm3"])
        item.source_cutout_count = int(source["source_cutout_count"])
        domains.append(item)
    native_input.domains = domains
    triangles = []
    for source in validated["triangles"]:
        item = native.GeneralizedReferencePlaneTriangle()
        item.id = source["id"]
        item.a, item.b, item.c = source["vertex_indices"]
        item.domain_index = domain_indexes[source["domain_id"]]
        item.surface_role, item.source_ids = source["surface_role"], source["source_ids"]
        triangles.append(item)
    native_input.triangles = triangles
    loops = []
    for source in validated["boundary_loops"]:
        item = native.GeneralizedReferencePlaneLoop()
        item.id, item.domain_index = source["loop_id"], domain_indexes[source["domain_id"]]
        item.role, item.surface, item.z_mm = source["role"], source["surface"], float(source["z_mm"])
        item.vertex_indices, item.source_ids = source["vertex_indices"], source["source_ids"]
        loops.append(item)
    native_input.loops = loops
    native_input.declared_vertex_count = len(vertices)
    native_input.declared_triangle_count = len(triangles)
    native_input.declared_domain_count = len(domains)
    native_input.declared_loop_count = len(loops)
    native_input.maximum_work_steps = validated["resources"]["maximum_work_steps"]
    native_input.actual_work_steps = validated["resources"]["actual_work_steps"]
    qualification = validated["qualification"]
    native_input.mesh_topology_admitted = qualification["mesh_topology_admitted"]
    native_input.conservative_source_copper_envelope_proven = \
        qualification["conservative_source_copper_envelope_proven"]
    native_input.native_handoff_ready = qualification["native_handoff_ready"]
    native_input.mesh_quality_performed = qualification["mesh_quality_performed"]
    native_input.solver_ready = qualification["solver_ready"]
    try:
        report = native.validate_generalized_reference_plane_mesh_input(
            native_input, expected_digest)
    except Exception as error:
        raise GeneralizedReferencePlaneNativeHandoffError(
            "Generalized native plane admission failed."
        ) from error
    checks = (report.finite_geometry, report.compact_indexing,
              report.closed_oriented_domains, report.provenance_retained,
              report.complete_loop_coverage, report.complete_surface_roles,
              report.source_curve_claim_honest)
    if (report.contract != MESH_CONTRACT
            or report.source_geometry_contract != validated["source"]["geometry_contract"]
            or report.source_geometry_sha256 != expected_digest
            or int(report.vertex_count) != len(vertices)
            or int(report.triangle_count) != len(triangles)
            or int(report.domain_count) != len(domains)
            or int(report.loop_count) != len(loops)
            or not all(checks) or report.solver_ready):
        raise GeneralizedReferencePlaneNativeHandoffError(
            "Native admission returned inconsistent or promoted evidence."
        )
    return {
        "contract": CONTRACT,
        "source": {"mesh_contract": MESH_CONTRACT, "mesh_sha256": content_digest(validated),
                   "geometry_contract": validated["source"]["geometry_contract"],
                   "geometry_sha256": expected_digest,
                   "design_id": validated["source"]["design_id"],
                   "via_id": validated["source"]["via_id"],
                   "source_via_id": validated["source"]["source_via_id"]},
        "native_validation": {"status": "passed", "finite_vertices_checked": True,
                              "compact_indices_checked": True, "closed_domains_checked": True,
                              "domain_ownership_checked": True, "provenance_checked": True,
                              "complete_loop_coverage_checked": True,
                              "complete_surface_roles_checked": True,
                              "source_curve_claim_checked": True,
                              "solver_entry_points_exposed": False,
                              "vertex_count": len(vertices), "triangle_count": len(triangles),
                              "domain_count": len(domains), "loop_count": len(loops)},
        "resources": {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                      "actual_vertices": len(vertices), "actual_triangles": len(triangles),
                      "actual_loops": len(loops),
                      "maximum_work_steps": validated["resources"]["maximum_work_steps"],
                      "actual_work_steps": validated["resources"]["actual_work_steps"],
                      "max_serialized_bytes": MAX_SERIALIZED_BYTES},
        "qualification": {"state": "generalized_reference_plane_native_geometry_only",
                          "native_validation_passed": True,
                          "mesh_quality_performed": False,
                          "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False,
                          "solver_ready": False},
    }


__all__ = ["CONTRACT", "ERROR_CODE", "GeneralizedReferencePlaneNativeHandoffError",
           "build_generalized_reference_plane_native_handoff"]
