"""Fail-closed typed native admission for a validated via-transition mesh."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .design_ir_v2_schema import content_digest
from .via_transition_geometry import CONTRACT as GEOMETRY_CONTRACT
from .via_transition_mesh import (
    CONTRACT as MESH_CONTRACT,
    MAX_SERIALIZED_BYTES,
    MAX_TRIANGLES,
    MAX_VERTICES,
    validate_via_transition_mesh,
)


CONTRACT = "spike/native-via-transition-handoff/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0005"


class ViaTransitionNativeHandoffError(ValueError):
    """Raised when geometry cannot cross the native validation boundary."""

    code = ERROR_CODE


def _require_native_api(native: Any) -> Any:
    required = (
        "ViaTransitionVertex",
        "ViaTransitionTriangle",
        "ViaTransitionDomain",
        "ViaTransitionMeshInput",
        "validate_via_transition_mesh_input",
    )
    if any(not hasattr(native, name) for name in required):
        raise ViaTransitionNativeHandoffError(
            "The native extension does not expose the required typed via-transition validator."
        )
    return native


def _load_native() -> Any:
    try:
        from python import spike_peec_native as native
    except ImportError:
        try:
            import spike_peec_native as native  # type: ignore[no-redef]
        except ImportError as error:
            raise ViaTransitionNativeHandoffError(
                "The native via-transition validator is unavailable."
            ) from error
    return _require_native_api(native)


def build_native_via_transition_handoff(
    mesh: Mapping[str, Any], *, source_geometry: Mapping[str, Any]
) -> Dict[str, Any]:
    """Validate and bind geometry natively without admitting it to a solver."""

    validated = validate_via_transition_mesh(mesh, source_geometry=source_geometry)
    expected_geometry_digest = content_digest(source_geometry)
    source = validated["source"]
    if source["geometry_sha256"] != expected_geometry_digest:
        raise ViaTransitionNativeHandoffError(
            "The mesh does not identify the independently supplied source geometry."
        )

    native = _require_native_api(_load_native())
    native_input = native.ViaTransitionMeshInput()
    native_input.contract = validated["contract"]
    native_input.source_geometry_contract = source["geometry_contract"]
    native_input.source_geometry_sha256 = source["geometry_sha256"]
    native_input.design_id = source["design_id"]
    native_input.via_id = source["via_id"]
    native_input.source_via_id = source["source_via_id"]

    vertices = []
    for point in validated["vertices_mm"]:
        vertex = native.ViaTransitionVertex()
        vertex.x, vertex.y, vertex.z = (float(value) for value in point)
        vertices.append(vertex)
    native_input.vertices = vertices

    domain_indexes = {domain["id"]: index for index, domain in enumerate(validated["domains"])}
    domains = []
    for source_domain in validated["domains"]:
        domain = native.ViaTransitionDomain()
        domain.id = source_domain["id"]
        domain.kind = source_domain["kind"]
        domain.net_id = source_domain["net_id"]
        domain.layer_ids = source_domain["layer_ids"]
        domain.source_ids = source_domain["source_ids"]
        domains.append(domain)
    native_input.domains = domains

    triangles = []
    for source_triangle in validated["triangles"]:
        triangle = native.ViaTransitionTriangle()
        triangle.id = source_triangle["id"]
        triangle.a, triangle.b, triangle.c = source_triangle["vertex_indices"]
        triangle.domain_index = domain_indexes[source_triangle["domain_id"]]
        triangle.surface_role = source_triangle["surface_role"]
        triangle.source_ids = source_triangle["source_ids"]
        triangles.append(triangle)
    native_input.triangles = triangles
    native_input.declared_vertex_count = len(vertices)
    native_input.declared_triangle_count = len(triangles)
    native_input.declared_domain_count = len(domains)
    native_input.solver_ready = False

    try:
        report = native.validate_via_transition_mesh_input(
            native_input, expected_geometry_digest
        )
    except Exception as error:
        raise ViaTransitionNativeHandoffError(
            "Native via-transition geometry admission failed."
        ) from error
    if (
        report.contract != MESH_CONTRACT
        or report.source_geometry_contract != GEOMETRY_CONTRACT
        or report.source_geometry_sha256 != expected_geometry_digest
        or int(report.vertex_count) != len(vertices)
        or int(report.triangle_count) != len(triangles)
        or int(report.domain_count) != len(domains)
        or not all(
            (
                report.finite_geometry,
                report.compact_indexing,
                report.closed_oriented_domains,
                report.provenance_retained,
            )
        )
        or report.solver_ready
    ):
        raise ViaTransitionNativeHandoffError(
            "Native validation returned inconsistent or physics-promoted evidence."
        )

    result: Dict[str, Any] = {
        "contract": CONTRACT,
        "source": {
            "mesh_contract": MESH_CONTRACT,
            "mesh_sha256": content_digest(validated),
            "geometry_contract": GEOMETRY_CONTRACT,
            "geometry_sha256": expected_geometry_digest,
            "design_id": source["design_id"],
            "via_id": source["via_id"],
            "source_via_id": source["source_via_id"],
        },
        "native_validation": {
            "status": "passed",
            "finite_vertices_checked": bool(report.finite_geometry),
            "compact_indices_checked": bool(report.compact_indexing),
            "closed_domains_checked": bool(report.closed_oriented_domains),
            "domain_ownership_checked": True,
            "provenance_checked": bool(report.provenance_retained),
            "solver_entry_points_exposed": False,
            "vertex_count": int(report.vertex_count),
            "triangle_count": int(report.triangle_count),
            "domain_count": int(report.domain_count),
        },
        "resources": {
            "max_vertices": MAX_VERTICES,
            "max_triangles": MAX_TRIANGLES,
            "actual_vertices": len(vertices),
            "actual_triangles": len(triangles),
            "max_serialized_bytes": MAX_SERIALIZED_BYTES,
        },
        "qualification": {
            "state": "geometry_handoff_only",
            "native_validation_passed": True,
            "capacitance_ready": False,
            "si_ready": False,
            "solver_ready": False,
        },
    }
    return result


__all__ = [
    "CONTRACT",
    "ERROR_CODE",
    "ViaTransitionNativeHandoffError",
    "build_native_via_transition_handoff",
]
