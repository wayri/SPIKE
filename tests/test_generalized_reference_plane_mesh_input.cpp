#include "peec/generalized_reference_plane_mesh_input.hpp"

#include <array>
#include <cassert>
#include <stdexcept>

using namespace spike::peec;
constexpr const char *kDigest =
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

GeneralizedReferencePlaneMeshInput valid_input() {
  GeneralizedReferencePlaneMeshInput input;
  input.contract = kGeneralizedReferencePlaneMeshContract;
  input.source_geometry_contract = kGeneralizedReferencePlaneGeometryV2Contract;
  input.source_geometry_sha256 = kDigest;
  input.design_id = "design"; input.via_id = "via"; input.source_via_id = "source-via";
  const std::array<std::array<double, 2>, 8> planar{{
      {{0, 0}}, {{0, 4}}, {{1, 1}}, {{1, 3}},
      {{3, 1}}, {{3, 3}}, {{4, 0}}, {{4, 4}}}};
  for (const auto &point : planar) input.vertices.push_back({point[0], point[1], 0});
  for (const auto &point : planar) input.vertices.push_back({point[0], point[1], 1});
  input.domains = {{"plane", "GND", "L1", {"zone", "antipad"}, "zone",
                    kDigest, kDigest, "", "", 0.5, 12.0, 12.0, 0}};
  const std::array<std::array<std::size_t, 3>, 8> faces{{
      {{0, 2, 3}}, {{0, 3, 1}}, {{0, 4, 2}}, {{0, 6, 4}},
      {{1, 3, 5}}, {{1, 5, 7}}, {{4, 6, 7}}, {{4, 7, 5}}}};
  const auto add = [&](std::size_t a, std::size_t b, std::size_t c,
                       const char *role, std::vector<std::string> sources) {
    input.triangles.push_back({"t" + std::to_string(input.triangles.size()),
                               a, b, c, 0, role, std::move(sources)});
  };
  for (const auto &face : faces) {
    add(face[0], face[2], face[1], "reference_zone_lower_face", {"zone", "antipad"});
    add(face[0] + 8, face[1] + 8, face[2] + 8,
        "reference_zone_upper_face", {"zone", "antipad"});
  }
  const auto wall = [&](const std::vector<std::size_t> &loop, const char *role,
                        std::vector<std::string> sources) {
    for (std::size_t index = 0; index < loop.size(); ++index) {
      const auto a = loop[index], b = loop[(index + 1) % loop.size()];
      add(a, b, b + 8, role, sources); add(a, b + 8, a + 8, role, sources);
    }
  };
  const std::vector<std::size_t> outer{0, 6, 7, 1}, hole{2, 3, 5, 4};
  wall(outer, "reference_zone_outer_boundary", {"zone"});
  wall(hole, "antipad_void_boundary", {"antipad"});
  input.loops = {
      {"outer-lower", 0, "source_outer", "lower", 0, outer, {"zone"}},
      {"outer-upper", 0, "source_outer", "upper", 1, {8, 14, 15, 9}, {"zone"}},
      {"hole-lower", 0, "antipad_hole", "lower", 0, hole, {"antipad"}},
      {"hole-upper", 0, "antipad_hole", "upper", 1, {10, 11, 13, 12}, {"antipad"}}};
  input.declared_vertex_count = input.vertices.size();
  input.declared_triangle_count = input.triangles.size();
  input.declared_domain_count = input.domains.size();
  input.declared_loop_count = input.loops.size();
  input.maximum_work_steps = 1000; input.actual_work_steps = 100;
  input.mesh_topology_admitted = true;
  input.conservative_source_copper_envelope_proven = true;
  return input;
}

template <typename Callable> void rejects(Callable &&callable) {
  bool failed = false;
  try { callable(); } catch (const std::invalid_argument &) { failed = true; }
  assert(failed);
}

int main() {
  const auto report = validate_generalized_reference_plane_mesh_input(valid_input(), kDigest);
  assert(report.vertex_count == 16 && report.domain_count == 1 && report.loop_count == 4);
  assert(report.finite_geometry && report.compact_indexing && report.closed_oriented_domains);
  assert(report.provenance_retained && report.complete_loop_coverage &&
         report.complete_surface_roles && report.source_curve_claim_honest && !report.solver_ready);
  auto input = valid_input(); input.solver_ready = true;
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
  input = valid_input(); input.conservative_source_copper_envelope_proven = false;
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
  input = valid_input(); input.loops.pop_back(); input.declared_loop_count--;
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
  input = valid_input(); input.loops[0].role = "source_cutout";
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
  input = valid_input(); input.domains[0].exact_discrete_volume_mm3 = 11.0;
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
  input = valid_input(); input.actual_work_steps = 1001;
  rejects([&] { validate_generalized_reference_plane_mesh_input(input, kDigest); });
}
