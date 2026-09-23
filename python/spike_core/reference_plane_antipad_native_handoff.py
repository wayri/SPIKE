"""Strict native admission for a complete reference-plane antipad mesh."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .design_ir_v2_schema import content_digest
from .reference_plane_antipad_geometry import CONTRACT as GEOMETRY_CONTRACT
from .reference_plane_antipad_mesh import (
    CONTRACT as MESH_CONTRACT,
    validate_reference_plane_antipad_mesh,
)
from .via_transition_mesh import MAX_SERIALIZED_BYTES, MAX_TRIANGLES, MAX_VERTICES


CONTRACT = "spike/native-reference-plane-antipad-handoff/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0009"


class ReferencePlaneAntipadNativeHandoffError(ValueError):
    """Raised when full-zone geometry cannot cross native admission."""

    code = ERROR_CODE


def _require_native_api(native: Any) -> Any:
    required = ("ReferencePlaneAntipadVertex", "ReferencePlaneAntipadTriangle",
                "ReferencePlaneAntipadDomain", "ReferencePlaneAntipadMeshInput",
                "validate_reference_plane_antipad_mesh_input")
    if any(not hasattr(native, name) for name in required):
        raise ReferencePlaneAntipadNativeHandoffError(
            "The native extension lacks the typed reference-plane admission API."
        )
    return native


def _native() -> Any:
    try:
        from python import spike_peec_native as native
    except ImportError:
        try:
            import spike_peec_native as native  # type: ignore[no-redef]
        except ImportError as error:
            raise ReferencePlaneAntipadNativeHandoffError(
                "The native reference-plane validator is unavailable."
            ) from error
    return _require_native_api(native)


def build_native_reference_plane_antipad_handoff(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Admit exact source-bound topology natively without exposing a solver."""

    validated = validate_reference_plane_antipad_mesh(mesh, source_geometry=source_geometry)
    expected_digest = content_digest(source_geometry)
    native = _require_native_api(_native())
    native_input = native.ReferencePlaneAntipadMeshInput()
    native_input.contract = MESH_CONTRACT
    native_input.source_geometry_contract = GEOMETRY_CONTRACT
    native_input.source_geometry_sha256 = expected_digest
    native_input.design_id = validated["source"]["design_id"]
    native_input.via_id = validated["source"]["via_id"]
    native_input.source_via_id = validated["source"]["source_via_id"]
    vertices = []
    for point in validated["vertices_mm"]:
        item = native.ReferencePlaneAntipadVertex()
        item.x, item.y, item.z = (float(value) for value in point)
        vertices.append(item)
    native_input.vertices = vertices
    domain_indexes = {item["id"]: index for index, item in enumerate(validated["domains"])}
    domains = []
    for source in validated["domains"]:
        item = native.ReferencePlaneAntipadDomain()
        item.id, item.net_id, item.layer_id = source["id"], source["net_id"], source["layer_ids"][0]
        item.source_ids = source["source_ids"]
        item.reference_zone_id = source["reference_zone_id"]
        item.source_zone_sha256 = source["source_zone_sha256"]
        item.resolved_region_sha256 = source["resolved_region_sha256"]
        item.antipad_radius_mm = float(source["antipad_radius_mm"])
        domains.append(item)
    native_input.domains = domains
    triangles = []
    for source in validated["triangles"]:
        item = native.ReferencePlaneAntipadTriangle()
        item.id = source["id"]
        item.a, item.b, item.c = source["vertex_indices"]
        item.domain_index = domain_indexes[source["domain_id"]]
        item.surface_role, item.source_ids = source["surface_role"], source["source_ids"]
        triangles.append(item)
    native_input.triangles = triangles
    native_input.declared_vertex_count = len(vertices)
    native_input.declared_triangle_count = len(triangles)
    native_input.declared_domain_count = len(domains)
    native_input.solver_ready = False
    try:
        report = native.validate_reference_plane_antipad_mesh_input(native_input, expected_digest)
    except Exception as error:
        raise ReferencePlaneAntipadNativeHandoffError(
            "Native reference-plane geometry admission failed."
        ) from error
    if (report.contract != MESH_CONTRACT or report.source_geometry_contract != GEOMETRY_CONTRACT
            or report.source_geometry_sha256 != expected_digest
            or int(report.vertex_count) != len(vertices) or int(report.triangle_count) != len(triangles)
            or int(report.domain_count) != len(domains)
            or not all((report.finite_geometry, report.compact_indexing,
                        report.closed_oriented_domains, report.provenance_retained))
            or report.solver_ready):
        raise ReferencePlaneAntipadNativeHandoffError(
            "Native admission returned inconsistent or physics-promoted evidence."
        )
    return {
        "contract": CONTRACT,
        "source": {"mesh_contract": MESH_CONTRACT, "mesh_sha256": content_digest(validated),
                   "geometry_contract": GEOMETRY_CONTRACT, "geometry_sha256": expected_digest,
                   "design_id": validated["source"]["design_id"],
                   "via_id": validated["source"]["via_id"],
                   "source_via_id": validated["source"]["source_via_id"]},
        "native_validation": {"status": "passed", "finite_vertices_checked": True,
                              "compact_indices_checked": True, "closed_domains_checked": True,
                              "domain_ownership_checked": True, "provenance_checked": True,
                              "solver_entry_points_exposed": False,
                              "vertex_count": len(vertices), "triangle_count": len(triangles),
                              "domain_count": len(domains)},
        "resources": {"max_vertices": MAX_VERTICES, "max_triangles": MAX_TRIANGLES,
                      "actual_vertices": len(vertices), "actual_triangles": len(triangles),
                      "max_serialized_bytes": MAX_SERIALIZED_BYTES},
        "qualification": {"state": "full_reference_zone_geometry_handoff_only",
                          "native_validation_passed": True,
                          "physics_convergence_performed": False,
                          "capacitance_ready": False, "si_ready": False, "solver_ready": False},
    }


__all__ = ["CONTRACT", "ERROR_CODE", "ReferencePlaneAntipadNativeHandoffError",
           "build_native_reference_plane_antipad_handoff"]
