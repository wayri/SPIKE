#include "peec/via_transition_mesh_input.hpp"

#include <cassert>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>

namespace {

using spike::peec::ViaTransitionDomain;
using spike::peec::ViaTransitionMeshInput;
using spike::peec::ViaTransitionTriangle;
using spike::peec::ViaTransitionVertex;
using spike::peec::kViaTransitionGeometryContract;
using spike::peec::kViaTransitionMeshContract;
using spike::peec::validate_via_transition_mesh_input;

constexpr const char *kDigest =
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

ViaTransitionMeshInput valid_input() {
  ViaTransitionMeshInput input;
  input.contract = kViaTransitionMeshContract;
  input.source_geometry_contract = kViaTransitionGeometryContract;
  input.source_geometry_sha256 = kDigest;
  input.design_id = "design-1";
  input.via_id = "via-1";
  input.source_via_id = "source-via-1";
  // Two disjoint outward-oriented tetrahedra: a signal conductor and one
  // local reference-patch domain.  They deliberately share no vertices.
  input.vertices = {{0.0, 0.0, 0.0}, {1.0, 0.0, 0.0},
                    {0.0, 1.0, 0.0}, {0.0, 0.0, 1.0},
                    {3.0, 0.0, 0.0}, {4.0, 0.0, 0.0},
                    {3.0, 1.0, 0.0}, {3.0, 0.0, 1.0}};
  input.domains = {
      ViaTransitionDomain{"signal", "signal_via_conductor", "SIG",
                          {"L1", "L2"}, {"via-source", "land-source"}},
      ViaTransitionDomain{"reference", "reference_plane_local_patch", "GND",
                          {"L2"}, {"zone-source"}},
  };
  const auto face = [](std::string id, std::size_t a, std::size_t b,
                       std::size_t c, std::size_t domain_index,
                       std::vector<std::string> source_ids) {
    return ViaTransitionTriangle{std::move(id), a, b, c, domain_index,
                                 "lower_face", std::move(source_ids)};
  };
  input.triangles = {
      face("t0", 0, 2, 1, 0, {"via-source"}),
      face("t1", 0, 1, 3, 0, {"via-source"}),
      face("t2", 0, 3, 2, 0, {"land-source"}),
      face("t3", 1, 2, 3, 0, {"land-source"}),
      face("t4", 4, 6, 5, 1, {"zone-source"}),
      face("t5", 4, 5, 7, 1, {"zone-source"}),
      face("t6", 4, 7, 6, 1, {"zone-source"}),
      face("t7", 5, 6, 7, 1, {"zone-source"}),
  };
  input.declared_vertex_count = input.vertices.size();
  input.declared_triangle_count = input.triangles.size();
  input.declared_domain_count = input.domains.size();
  return input;
}

void sync_counts(ViaTransitionMeshInput &input) {
  input.declared_vertex_count = input.vertices.size();
  input.declared_triangle_count = input.triangles.size();
  input.declared_domain_count = input.domains.size();
}

template <typename Callable> void requires_invalid_argument(Callable &&callable) {
  bool rejected = false;
  try {
    callable();
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

void admits_closed_two_domain_mesh_without_solver_promotion() {
  const auto report = validate_via_transition_mesh_input(valid_input(), kDigest);
  assert(report.contract == kViaTransitionMeshContract);
  assert(report.source_geometry_contract == kViaTransitionGeometryContract);
  assert(report.source_geometry_sha256 == kDigest);
  assert(report.vertex_count == 8);
  assert(report.triangle_count == 8);
  assert(report.domain_count == 2);
  assert(report.finite_geometry);
  assert(report.compact_indexing);
  assert(report.closed_oriented_domains);
  assert(report.provenance_retained);
  assert(!report.solver_ready);
}

void rejects_invalid_digest_and_solver_promotion() {
  auto input = valid_input();
  input.source_geometry_sha256 = "ABCDEF";
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  const std::string different_digest(64, 'f');
  requires_invalid_argument([&input, &different_digest] {
    validate_via_transition_mesh_input(input, different_digest);
  });

  input = valid_input();
  input.solver_ready = true;
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });
}

void rejects_open_reversed_and_duplicate_domain_surfaces() {
  auto input = valid_input();
  input.triangles.pop_back();
  sync_counts(input);
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  std::swap(input.triangles[3].b, input.triangles[3].c);
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  input.triangles.push_back(input.triangles.front());
  input.triangles.back().id = "duplicate-face";
  sync_counts(input);
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });
}

void rejects_unused_and_cross_domain_vertices() {
  auto input = valid_input();
  input.vertices.push_back({9.0, 9.0, 9.0});
  sync_counts(input);
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  input.triangles[4].domain_index = 0;
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });
}

void rejects_invalid_provenance() {
  auto input = valid_input();
  input.domains[1].source_ids.clear();
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  input.domains[0].id = "";
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });

  input = valid_input();
  input.triangles[0].source_ids = {"unowned-source"};
  requires_invalid_argument([&input] { validate_via_transition_mesh_input(input, kDigest); });
}

} // namespace

int main() {
  admits_closed_two_domain_mesh_without_solver_promotion();
  rejects_invalid_digest_and_solver_promotion();
  rejects_open_reversed_and_duplicate_domain_surfaces();
  rejects_unused_and_cross_domain_vertices();
  rejects_invalid_provenance();
  std::cout << "Native via-transition mesh handoff tests passed\n";
  return 0;
}
