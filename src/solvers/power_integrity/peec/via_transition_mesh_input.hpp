#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace spike::peec {

inline constexpr const char *kViaTransitionMeshContract =
    "spike/pcb-via-transition-mesh/v1";
inline constexpr const char *kViaTransitionGeometryContract =
    "spike/pcb-via-transition-geometry/v1";
inline constexpr std::size_t kMaxViaTransitionVertices = 32768;
inline constexpr std::size_t kMaxViaTransitionTriangles = 65536;
inline constexpr std::size_t kMaxViaTransitionDomains = 65;

struct ViaTransitionVertex {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
};

struct ViaTransitionTriangle {
  std::string id;
  std::size_t a = 0;
  std::size_t b = 0;
  std::size_t c = 0;
  std::size_t domain_index = 0;
  std::string surface_role;
  std::vector<std::string> source_ids;
};

struct ViaTransitionDomain {
  std::string id;
  std::string kind;
  std::string net_id;
  std::vector<std::string> layer_ids;
  std::vector<std::string> source_ids;
};

struct ViaTransitionMeshInput {
  std::string contract;
  std::string source_geometry_contract;
  std::string source_geometry_sha256;
  std::string design_id;
  std::string via_id;
  std::string source_via_id;
  std::vector<ViaTransitionVertex> vertices;
  std::vector<ViaTransitionTriangle> triangles;
  std::vector<ViaTransitionDomain> domains;
  std::size_t declared_vertex_count = 0;
  std::size_t declared_triangle_count = 0;
  std::size_t declared_domain_count = 0;
  bool solver_ready = false;
};

struct ViaTransitionMeshValidation {
  std::string contract;
  std::string source_geometry_contract;
  std::string source_geometry_sha256;
  std::size_t vertex_count = 0;
  std::size_t triangle_count = 0;
  std::size_t domain_count = 0;
  bool finite_geometry = false;
  bool compact_indexing = false;
  bool closed_oriented_domains = false;
  bool provenance_retained = false;
  bool solver_ready = false;
};

ViaTransitionMeshValidation
validate_via_transition_mesh_input(const ViaTransitionMeshInput &input,
                                   const std::string &expected_geometry_sha256);

} // namespace spike::peec
