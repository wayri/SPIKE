#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace spike::peec {

inline constexpr std::size_t kReferencePlaneMaxVertices = 32768;
inline constexpr std::size_t kReferencePlaneMaxTriangles = 65536;
inline constexpr std::size_t kReferencePlaneMaxDomains = 64;
inline constexpr std::size_t kReferencePlaneMaxSources = 8;

inline constexpr const char *kReferencePlaneAntipadMeshContract =
    "spike/pcb-reference-plane-antipad-mesh/v1";
inline constexpr const char *kReferencePlaneAntipadGeometryContract =
    "spike/pcb-reference-plane-antipad-geometry/v1";

struct ReferencePlaneAntipadVertex { double x = 0.0, y = 0.0, z = 0.0; };

struct ReferencePlaneAntipadTriangle {
  std::string id;
  std::size_t a = 0, b = 0, c = 0, domain_index = 0;
  std::string surface_role;
  std::vector<std::string> source_ids;
};

struct ReferencePlaneAntipadDomain {
  std::string id, net_id, layer_id;
  std::vector<std::string> source_ids;
  std::string reference_zone_id, source_zone_sha256, resolved_region_sha256;
  double antipad_radius_mm = 0.0;
};

struct ReferencePlaneAntipadMeshInput {
  std::string contract, source_geometry_contract, source_geometry_sha256;
  std::string design_id, via_id, source_via_id;
  std::vector<ReferencePlaneAntipadVertex> vertices;
  std::vector<ReferencePlaneAntipadTriangle> triangles;
  std::vector<ReferencePlaneAntipadDomain> domains;
  std::size_t declared_vertex_count = 0, declared_triangle_count = 0,
              declared_domain_count = 0;
  bool solver_ready = false;
};

struct ReferencePlaneAntipadMeshValidation {
  std::string contract, source_geometry_contract, source_geometry_sha256;
  std::size_t vertex_count = 0, triangle_count = 0, domain_count = 0;
  bool finite_geometry = false, compact_indexing = false,
       closed_oriented_domains = false, provenance_retained = false,
       solver_ready = false;
};

ReferencePlaneAntipadMeshValidation validate_reference_plane_antipad_mesh_input(
    const ReferencePlaneAntipadMeshInput &input,
    const std::string &expected_geometry_sha256);

} // namespace spike::peec
