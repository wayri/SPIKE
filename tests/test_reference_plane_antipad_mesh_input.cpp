#include "peec/reference_plane_antipad_mesh_input.hpp"

#include <cassert>
#include <iostream>
#include <stdexcept>
#include <utility>

using namespace spike::peec;
constexpr const char *kDigest =
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

ReferencePlaneAntipadMeshInput valid_input() {
  ReferencePlaneAntipadMeshInput input;
  input.contract = kReferencePlaneAntipadMeshContract;
  input.source_geometry_contract = kReferencePlaneAntipadGeometryContract;
  input.source_geometry_sha256 = kDigest;
  input.design_id = "design"; input.via_id = "via"; input.source_via_id = "source-via";
  input.vertices = {{0, 0, 0}, {1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
  input.domains = {{"plane", "GND", "L1", {"zone", "antipad"}, "zone",
                    kDigest, kDigest, 0.45}};
  const auto face = [](const char *name, std::size_t a, std::size_t b,
                       std::size_t c, const char *role) {
    return ReferencePlaneAntipadTriangle{name, a, b, c, 0, role,
                                         {"zone", "antipad"}};
  };
  input.triangles = {
      face("t0", 0, 2, 1, "reference_zone_lower_face"),
      face("t1", 0, 1, 3, "reference_zone_outer_boundary"),
      face("t2", 0, 3, 2, "antipad_void_boundary"),
      face("t3", 1, 2, 3, "reference_zone_upper_face")};
  input.declared_vertex_count = 4; input.declared_triangle_count = 4;
  input.declared_domain_count = 1;
  return input;
}

template <typename Callable> void rejects(Callable &&callable) {
  bool failed = false;
  try { callable(); } catch (const std::invalid_argument &) { failed = true; }
  assert(failed);
}

int main() {
  const auto report = validate_reference_plane_antipad_mesh_input(valid_input(), kDigest);
  assert(report.vertex_count == 4 && report.triangle_count == 4 && report.domain_count == 1);
  assert(report.finite_geometry && report.compact_indexing && report.closed_oriented_domains);
  assert(report.provenance_retained && !report.solver_ready);

  auto input = valid_input(); input.solver_ready = true;
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.source_geometry_sha256 = "bad";
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.triangles.pop_back(); input.declared_triangle_count = 3;
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); std::swap(input.triangles[3].b, input.triangles[3].c);
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.triangles[0].source_ids = {"foreign"};
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.domains[0].antipad_radius_mm = 0.0;
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.source_via_id = "bad\nidentity";
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.triangles[0].surface_role = "reference_zone_upper_face";
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  input = valid_input(); input.vertices.push_back({9, 9, 9}); input.declared_vertex_count = 5;
  rejects([&] { validate_reference_plane_antipad_mesh_input(input, kDigest); });
  std::cout << "Native reference-plane antipad admission tests passed\n";
}
