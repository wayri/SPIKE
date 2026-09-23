#include "peec/generalized_reference_plane_mesh_input.hpp"

#include "peec/reference_plane_antipad_mesh_input.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace spike::peec {
namespace {
using Edge = std::pair<std::size_t, std::size_t>;
using EdgeKey = std::tuple<std::size_t, std::size_t, std::size_t>;
using RoleEdge = std::tuple<std::size_t, std::size_t, std::size_t, std::string>;
using FaceKey = std::tuple<std::size_t, std::size_t, std::size_t, std::size_t>;

void id(const std::string &value, const char *label, std::size_t maximum = 512) {
  if (value.empty() || value.size() > maximum ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return item < 0x20 || item == 0x7f;
      })) throw std::invalid_argument(std::string(label) + " is invalid");
}

void digest(const std::string &value, const char *label, bool optional = false) {
  if (optional && value.empty()) return;
  if (value.size() != 64 ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return !(item >= '0' && item <= '9') && !(item >= 'a' && item <= 'f');
      })) throw std::invalid_argument(std::string(label) + " is not lowercase SHA-256");
}

void sources(const std::vector<std::string> &values, const char *label) {
  if (values.empty() || values.size() > kReferencePlaneMaxSources)
    throw std::invalid_argument(std::string(label) + " is empty or over budget");
  std::set<std::string> unique;
  for (const auto &value : values) {
    id(value, label);
    if (!unique.insert(value).second)
      throw std::invalid_argument(std::string(label) + " has duplicates");
  }
}

void subset(const std::vector<std::string> &part,
            const std::vector<std::string> &whole, const char *label) {
  sources(part, label);
  const std::set<std::string> admitted(whole.begin(), whole.end());
  if (std::any_of(part.begin(), part.end(), [&](const auto &item) {
        return !admitted.contains(item);
      })) throw std::invalid_argument(std::string(label) + " is not domain-owned");
}

std::array<double, 3> subtract(const GeneralizedReferencePlaneVertex &left,
                               const GeneralizedReferencePlaneVertex &right) {
  return {left.x - right.x, left.y - right.y, left.z - right.z};
}

std::array<double, 3> cross(const std::array<double, 3> &left,
                            const std::array<double, 3> &right) {
  return {left[1] * right[2] - left[2] * right[1],
          left[2] * right[0] - left[0] * right[2],
          left[0] * right[1] - left[1] * right[0]};
}

Edge edge(std::size_t a, std::size_t b) {
  return a < b ? Edge{a, b} : Edge{b, a};
}
} // namespace

GeneralizedReferencePlaneMeshValidation
validate_generalized_reference_plane_mesh_input(
    const GeneralizedReferencePlaneMeshInput &input,
    const std::string &expected_geometry_sha256) {
  const bool geometry_v2 =
      input.source_geometry_contract == kGeneralizedReferencePlaneGeometryV2Contract;
  const bool geometry_v3 =
      input.source_geometry_contract == kGeneralizedReferencePlaneGeometryV3Contract;
  if (input.contract != kGeneralizedReferencePlaneMeshContract ||
      (!geometry_v2 && !geometry_v3))
    throw std::invalid_argument("unsupported generalized reference-plane contract");
  if (!input.mesh_topology_admitted || input.native_handoff_ready ||
      input.mesh_quality_performed || input.solver_ready ||
      input.conservative_source_copper_envelope_proven != geometry_v2)
    throw std::invalid_argument("generalized mesh qualification claims are invalid");
  digest(input.source_geometry_sha256, "source geometry digest");
  digest(expected_geometry_sha256, "expected geometry digest");
  if (input.source_geometry_sha256 != expected_geometry_sha256)
    throw std::invalid_argument("source geometry digest mismatch");
  id(input.design_id, "design_id"); id(input.via_id, "via_id");
  if (!input.source_via_id.empty()) id(input.source_via_id, "source_via_id", 256);
  if (input.vertices.empty() || input.vertices.size() > kReferencePlaneMaxVertices ||
      input.triangles.empty() || input.triangles.size() > kReferencePlaneMaxTriangles ||
      input.domains.empty() || input.domains.size() > kReferencePlaneMaxDomains ||
      input.loops.empty() || input.loops.size() > 16384)
    throw std::invalid_argument("generalized native arrays exceed bounds");
  if (input.declared_vertex_count != input.vertices.size() ||
      input.declared_triangle_count != input.triangles.size() ||
      input.declared_domain_count != input.domains.size() ||
      input.declared_loop_count != input.loops.size() ||
      input.maximum_work_steps == 0 || input.maximum_work_steps > 16777216 ||
      input.actual_work_steps == 0 || input.actual_work_steps > input.maximum_work_steps)
    throw std::invalid_argument("generalized declared resource accounting is invalid");

  std::set<std::string> domain_ids;
  for (const auto &domain : input.domains) {
    id(domain.id, "domain id"); id(domain.net_id, "domain net_id");
    id(domain.layer_id, "domain layer_id"); id(domain.reference_zone_id, "zone id");
    sources(domain.source_ids, "domain source ids");
    if (!std::set<std::string>(domain.source_ids.begin(), domain.source_ids.end())
             .contains(domain.reference_zone_id))
      throw std::invalid_argument("reference zone is absent from domain provenance");
    digest(domain.source_zone_sha256, "source zone digest");
    digest(domain.resolved_region_sha256, "resolved region digest");
    digest(domain.source_boundary_sha256, "source boundary digest", geometry_v2);
    digest(domain.flattened_boundary_sha256, "flattened boundary digest", geometry_v2);
    if (!domain_ids.insert(domain.id).second || domain.source_cutout_count > 128 ||
        !(domain.antipad_radius_mm > 0.0) ||
        !(domain.exact_discrete_area_mm2 > 0.0) ||
        !(domain.exact_discrete_volume_mm3 > 0.0) ||
        !std::isfinite(domain.antipad_radius_mm) ||
        !std::isfinite(domain.exact_discrete_area_mm2) ||
        !std::isfinite(domain.exact_discrete_volume_mm3))
      throw std::invalid_argument("generalized domain is invalid");
  }
  for (const auto &vertex : input.vertices)
    if (!std::isfinite(vertex.x) || !std::isfinite(vertex.y) || !std::isfinite(vertex.z))
      throw std::invalid_argument("generalized vertex is non-finite");

  const std::set<std::string> roles{
      "reference_zone_upper_face", "reference_zone_lower_face",
      "reference_zone_outer_boundary", "source_cutout_boundary",
      "antipad_void_boundary"};
  const auto unassigned = std::numeric_limits<std::size_t>::max();
  std::vector<std::size_t> owners(input.vertices.size(), unassigned);
  std::vector<double> volumes(input.domains.size(), 0.0);
  std::vector<std::set<std::string>> roles_by_domain(input.domains.size());
  std::map<EdgeKey, std::vector<Edge>> edges;
  std::set<RoleEdge> role_edges;
  std::set<FaceKey> faces;
  std::set<std::string> triangle_ids;
  for (const auto &triangle : input.triangles) {
    id(triangle.id, "triangle id");
    if (!triangle_ids.insert(triangle.id).second || !roles.contains(triangle.surface_role) ||
        triangle.domain_index >= input.domains.size() ||
        triangle.a >= input.vertices.size() || triangle.b >= input.vertices.size() ||
        triangle.c >= input.vertices.size() || triangle.a == triangle.b ||
        triangle.b == triangle.c || triangle.a == triangle.c)
      throw std::invalid_argument("generalized triangle is invalid");
    subset(triangle.source_ids, input.domains[triangle.domain_index].source_ids,
           "triangle source ids");
    roles_by_domain[triangle.domain_index].insert(triangle.surface_role);
    std::array<std::size_t, 3> sorted{triangle.a, triangle.b, triangle.c};
    std::sort(sorted.begin(), sorted.end());
    if (!faces.insert({triangle.domain_index, sorted[0], sorted[1], sorted[2]}).second)
      throw std::invalid_argument("duplicate generalized triangle");
    const auto &first = input.vertices[triangle.a];
    const auto normal = cross(subtract(input.vertices[triangle.b], first),
                              subtract(input.vertices[triangle.c], first));
    const double magnitude = normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2];
    if (!(magnitude > 1e-24) || !std::isfinite(magnitude))
      throw std::invalid_argument("degenerate generalized triangle");
    volumes[triangle.domain_index] +=
        (first.x * normal[0] + first.y * normal[1] + first.z * normal[2]) / 6.0;
    for (const auto [left, right] :
         {Edge{triangle.a, triangle.b}, Edge{triangle.b, triangle.c}, Edge{triangle.c, triangle.a}}) {
      const auto normalized = edge(left, right);
      edges[{triangle.domain_index, normalized.first, normalized.second}].push_back({left, right});
      role_edges.insert({triangle.domain_index, normalized.first, normalized.second,
                         triangle.surface_role});
    }
    for (const auto index : {triangle.a, triangle.b, triangle.c}) {
      if (owners[index] != unassigned && owners[index] != triangle.domain_index)
        throw std::invalid_argument("vertex is shared across generalized domains");
      owners[index] = triangle.domain_index;
    }
  }
  if (std::any_of(owners.begin(), owners.end(),
                  [unassigned](auto value) { return value == unassigned; }))
    throw std::invalid_argument("unused generalized vertex");
  for (const auto &[key, occurrences] : edges) {
    (void)key;
    if (occurrences.size() != 2 || occurrences[0].first != occurrences[1].second ||
        occurrences[0].second != occurrences[1].first)
      throw std::invalid_argument("generalized domains are not closed and oriented");
  }
  if (std::any_of(volumes.begin(), volumes.end(),
                  [](double value) { return !(value > 1e-24) || !std::isfinite(value); }))
    throw std::invalid_argument("generalized domain volume is invalid");

  std::vector<std::set<double>> z_levels(input.domains.size());
  for (std::size_t index = 0; index < input.vertices.size(); ++index)
    z_levels[owners[index]].insert(input.vertices[index].z);
  for (std::size_t index = 0; index < input.domains.size(); ++index) {
    if (z_levels[index].size() != 2)
      throw std::invalid_argument("generalized extrusion must have exactly two elevations");
    const double thickness = *z_levels[index].rbegin() - *z_levels[index].begin();
    const double declared = input.domains[index].exact_discrete_volume_mm3;
    const double from_area = input.domains[index].exact_discrete_area_mm2 * thickness;
    const double scale = std::max({1.0, std::abs(declared), std::abs(from_area),
                                  std::abs(volumes[index])});
    if (!(thickness > 0.0) || std::abs(declared - from_area) > 1e-12 * scale ||
        std::abs(declared - volumes[index]) > 1e-12 * scale)
      throw std::invalid_argument("generalized exact area and volume claims are inconsistent");
  }

  using LoopKey = std::pair<std::string, std::string>;
  std::set<std::string> loop_ids;
  std::vector<std::map<LoopKey, std::size_t>> loop_counts(input.domains.size());
  using Projection = std::vector<std::pair<double, double>>;
  std::vector<std::map<std::string, std::multiset<Projection>>> lower(input.domains.size()),
      upper(input.domains.size());
  const std::map<std::string, std::string> wall_role{
      {"source_outer", "reference_zone_outer_boundary"},
      {"source_cutout", "source_cutout_boundary"},
      {"antipad_hole", "antipad_void_boundary"}};
  for (const auto &loop : input.loops) {
    id(loop.id, "loop id");
    if (!loop_ids.insert(loop.id).second || loop.domain_index >= input.domains.size() ||
        !wall_role.contains(loop.role) ||
        (loop.surface != "lower" && loop.surface != "upper") ||
        !std::isfinite(loop.z_mm) || loop.vertex_indices.size() < 3 ||
        loop.vertex_indices.size() > 4096)
      throw std::invalid_argument("generalized boundary loop is invalid");
    subset(loop.source_ids, input.domains[loop.domain_index].source_ids,
           "loop source ids");
    std::set<std::size_t> unique;
    Projection projection;
    for (const auto index : loop.vertex_indices) {
      if (index >= input.vertices.size() || owners[index] != loop.domain_index ||
          !unique.insert(index).second || input.vertices[index].z != loop.z_mm ||
          loop.z_mm != (loop.surface == "lower" ? *z_levels[loop.domain_index].begin()
                                                 : *z_levels[loop.domain_index].rbegin()))
        throw std::invalid_argument("generalized loop vertex is invalid");
      projection.push_back({input.vertices[index].x, input.vertices[index].y});
    }
    for (std::size_t index = 0; index < loop.vertex_indices.size(); ++index) {
      const auto normalized = edge(loop.vertex_indices[index],
          loop.vertex_indices[(index + 1) % loop.vertex_indices.size()]);
      if (!role_edges.contains({loop.domain_index, normalized.first, normalized.second,
                                wall_role.at(loop.role)}))
        throw std::invalid_argument("loop edge is absent from its declared wall role");
    }
    ++loop_counts[loop.domain_index][{loop.role, loop.surface}];
    (loop.surface == "lower" ? lower : upper)[loop.domain_index][loop.role].insert(projection);
  }
  for (std::size_t index = 0; index < input.domains.size(); ++index) {
    const auto cutouts = input.domains[index].source_cutout_count;
    for (const auto &role : {std::string("source_outer"), std::string("antipad_hole")})
      if (loop_counts[index][{role, "lower"}] != 1 ||
          loop_counts[index][{role, "upper"}] != 1)
        throw std::invalid_argument("required generalized loops are incomplete");
    if (loop_counts[index][{"source_cutout", "lower"}] != cutouts ||
        loop_counts[index][{"source_cutout", "upper"}] != cutouts ||
        lower[index] != upper[index])
      throw std::invalid_argument("generalized cutout loop coverage is incomplete");
    std::set<std::string> expected{
        "reference_zone_upper_face", "reference_zone_lower_face",
        "reference_zone_outer_boundary", "antipad_void_boundary"};
    if (cutouts > 0) expected.insert("source_cutout_boundary");
    if (roles_by_domain[index] != expected)
      throw std::invalid_argument("generalized domain surface roles are incomplete");
  }
  return {input.contract, input.source_geometry_contract, input.source_geometry_sha256,
          input.vertices.size(), input.triangles.size(), input.domains.size(),
          input.loops.size(), true, true, true, true, true, true, true, false};
}

} // namespace spike::peec
