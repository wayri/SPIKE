#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace spike::peec {

inline constexpr const char *kGeneralizedReferencePlaneMeshContract =
    "spike/pcb-reference-plane-antipad-mesh/v2";
inline constexpr const char *kGeneralizedReferencePlaneGeometryV2Contract =
    "spike/pcb-reference-plane-antipad-geometry/v2";
inline constexpr const char *kGeneralizedReferencePlaneGeometryV3Contract =
    "spike/pcb-reference-plane-antipad-geometry/v3";

struct GeneralizedReferencePlaneVertex { double x = 0.0, y = 0.0, z = 0.0; };

struct GeneralizedReferencePlaneTriangle {
  std::string id;
  std::size_t a = 0, b = 0, c = 0, domain_index = 0;
  std::string surface_role;
  std::vector<std::string> source_ids;
};

struct GeneralizedReferencePlaneDomain {
  std::string id, net_id, layer_id;
  std::vector<std::string> source_ids;
  std::string reference_zone_id, source_zone_sha256, resolved_region_sha256;
  std::string source_boundary_sha256, flattened_boundary_sha256;
  double antipad_radius_mm = 0.0;
  double exact_discrete_area_mm2 = 0.0, exact_discrete_volume_mm3 = 0.0;
  std::size_t source_cutout_count = 0;
};

struct GeneralizedReferencePlaneLoop {
  std::string id;
  std::size_t domain_index = 0;
  std::string role, surface;
  double z_mm = 0.0;
  std::vector<std::size_t> vertex_indices;
  std::vector<std::string> source_ids;
};

struct GeneralizedReferencePlaneMeshInput {
  std::string contract, source_geometry_contract, source_geometry_sha256;
  std::string design_id, via_id, source_via_id;
  std::vector<GeneralizedReferencePlaneVertex> vertices;
  std::vector<GeneralizedReferencePlaneTriangle> triangles;
  std::vector<GeneralizedReferencePlaneDomain> domains;
  std::vector<GeneralizedReferencePlaneLoop> loops;
  std::size_t declared_vertex_count = 0, declared_triangle_count = 0,
              declared_domain_count = 0, declared_loop_count = 0;
  std::size_t maximum_work_steps = 0, actual_work_steps = 0;
  bool mesh_topology_admitted = false;
  bool conservative_source_copper_envelope_proven = false;
  bool native_handoff_ready = false, mesh_quality_performed = false,
       solver_ready = false;
};

struct GeneralizedReferencePlaneMeshValidation {
  std::string contract, source_geometry_contract, source_geometry_sha256;
  std::size_t vertex_count = 0, triangle_count = 0, domain_count = 0,
              loop_count = 0;
  bool finite_geometry = false, compact_indexing = false,
       closed_oriented_domains = false, provenance_retained = false,
       complete_loop_coverage = false, complete_surface_roles = false,
       source_curve_claim_honest = false, solver_ready = false;
};

GeneralizedReferencePlaneMeshValidation
validate_generalized_reference_plane_mesh_input(
    const GeneralizedReferencePlaneMeshInput &input,
    const std::string &expected_geometry_sha256);

} // namespace spike::peec
