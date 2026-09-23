#include "peec/via_transition_mesh_input.hpp"

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

using DirectedEdge = std::pair<std::size_t, std::size_t>;
using EdgeKey = std::tuple<std::size_t, std::size_t, std::size_t>;
using FaceKey = std::tuple<std::size_t, std::size_t, std::size_t, std::size_t>;

void require_id(const std::string &value, const char *label) {
  if (value.empty() || value.size() > 512 ||
      std::any_of(value.begin(), value.end(),
                  [](unsigned char item) { return item < 0x20 || item == 0x7f; })) {
    throw std::invalid_argument(std::string(label) +
                                " must be a bounded non-control identity");
  }
}

void require_digest(const std::string &value) {
  if (value.size() != 64 ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return !(item >= '0' && item <= '9') && !(item >= 'a' && item <= 'f');
      })) {
    throw std::invalid_argument(
        "source_geometry_sha256 must be a lowercase SHA-256 digest");
  }
}

void require_unique_ids(const std::vector<std::string> &values,
                        const char *label) {
  if (values.empty() || values.size() > 64) {
    throw std::invalid_argument(std::string(label) +
                                " must be non-empty and bounded");
  }
  std::set<std::string> unique;
  for (const auto &value : values) {
    require_id(value, label);
    if (!unique.insert(value).second) {
      throw std::invalid_argument(std::string(label) +
                                  " must not contain duplicates");
    }
  }
}

std::array<double, 3> subtract(const ViaTransitionVertex &left,
                               const ViaTransitionVertex &right) {
  return {left.x - right.x, left.y - right.y, left.z - right.z};
}

std::array<double, 3> cross(const std::array<double, 3> &left,
                            const std::array<double, 3> &right) {
  return {left[1] * right[2] - left[2] * right[1],
          left[2] * right[0] - left[0] * right[2],
          left[0] * right[1] - left[1] * right[0]};
}

} // namespace

ViaTransitionMeshValidation
validate_via_transition_mesh_input(
    const ViaTransitionMeshInput &input,
    const std::string &expected_geometry_sha256) {
  if (input.contract != kViaTransitionMeshContract) {
    throw std::invalid_argument("unsupported via-transition mesh contract");
  }
  if (input.source_geometry_contract != kViaTransitionGeometryContract) {
    throw std::invalid_argument("unsupported via-transition geometry contract");
  }
  if (input.solver_ready) {
    throw std::invalid_argument(
        "native via-transition handoff cannot be marked solver-ready");
  }
  require_digest(input.source_geometry_sha256);
  require_digest(expected_geometry_sha256);
  if (input.source_geometry_sha256 != expected_geometry_sha256) {
    throw std::invalid_argument(
        "source geometry digest does not match independently expected digest");
  }
  require_id(input.design_id, "design_id");
  require_id(input.via_id, "via_id");
  require_id(input.source_via_id, "source_via_id");
  if (input.vertices.empty() ||
      input.vertices.size() > kMaxViaTransitionVertices ||
      input.triangles.empty() ||
      input.triangles.size() > kMaxViaTransitionTriangles ||
      input.domains.size() < 2 ||
      input.domains.size() > kMaxViaTransitionDomains) {
    throw std::invalid_argument("native via-transition arrays exceed bounds");
  }
  if (input.declared_vertex_count != input.vertices.size() ||
      input.declared_triangle_count != input.triangles.size() ||
      input.declared_domain_count != input.domains.size()) {
    throw std::invalid_argument(
        "native via-transition declared resource counts do not match arrays");
  }

  std::set<std::string> domain_ids;
  std::size_t signal_domains = 0;
  for (const auto &domain : input.domains) {
    require_id(domain.id, "domain id");
    require_id(domain.net_id, "domain net_id");
    require_unique_ids(domain.layer_ids, "domain layer_ids");
    require_unique_ids(domain.source_ids, "domain source_ids");
    if (!domain_ids.insert(domain.id).second) {
      throw std::invalid_argument("native domain identities must be unique");
    }
    if (domain.kind == "signal_via_conductor") {
      ++signal_domains;
    } else if (domain.kind != "reference_plane_local_patch") {
      throw std::invalid_argument("native via-transition domain kind is invalid");
    }
  }
  if (signal_domains != 1) {
    throw std::invalid_argument(
        "native handoff requires exactly one signal-conductor domain");
  }

  for (const auto &vertex : input.vertices) {
    if (!std::isfinite(vertex.x) || !std::isfinite(vertex.y) ||
        !std::isfinite(vertex.z)) {
      throw std::invalid_argument("native handoff vertex is non-finite");
    }
  }

  const auto unassigned = std::numeric_limits<std::size_t>::max();
  std::vector<std::size_t> vertex_domains(input.vertices.size(), unassigned);
  std::vector<double> signed_volumes(input.domains.size(), 0.0);
  std::map<EdgeKey, std::vector<DirectedEdge>> edges;
  std::set<FaceKey> faces;
  std::set<std::string> triangle_ids;
  const std::set<std::string> surface_roles{
      "signal_outer_boundary", "signal_land_shoulder",
      "drill_void_boundary", "signal_lower_face", "signal_upper_face",
      "antipad_void_boundary", "local_patch_truncation", "lower_face",
      "upper_face"};
  for (const auto &triangle : input.triangles) {
    require_id(triangle.id, "triangle id");
    require_id(triangle.surface_role, "triangle surface_role");
    require_unique_ids(triangle.source_ids, "triangle source_ids");
    if (!triangle_ids.insert(triangle.id).second) {
      throw std::invalid_argument("native triangle identities must be unique");
    }
    if (!surface_roles.contains(triangle.surface_role)) {
      throw std::invalid_argument("native triangle surface role is invalid");
    }
    if (triangle.domain_index >= input.domains.size() ||
        triangle.a >= input.vertices.size() ||
        triangle.b >= input.vertices.size() ||
        triangle.c >= input.vertices.size() || triangle.a == triangle.b ||
        triangle.b == triangle.c || triangle.a == triangle.c) {
      throw std::invalid_argument(
          "native handoff triangle has invalid compact indices");
    }
    const auto &domain_sources = input.domains[triangle.domain_index].source_ids;
    if (std::any_of(triangle.source_ids.begin(), triangle.source_ids.end(),
                    [&domain_sources](const std::string &source_id) {
                      return std::find(domain_sources.begin(),
                                       domain_sources.end(),
                                       source_id) == domain_sources.end();
                    })) {
      throw std::invalid_argument(
          "native triangle source identity is not owned by its domain");
    }
    std::array<std::size_t, 3> sorted{triangle.a, triangle.b, triangle.c};
    std::sort(sorted.begin(), sorted.end());
    if (!faces
             .insert({triangle.domain_index, sorted[0], sorted[1], sorted[2]})
             .second) {
      throw std::invalid_argument("native handoff has a duplicate triangle");
    }
    const auto &first = input.vertices[triangle.a];
    const auto &second = input.vertices[triangle.b];
    const auto &third = input.vertices[triangle.c];
    const auto normal = cross(subtract(second, first), subtract(third, first));
    const double normal_squared = normal[0] * normal[0] +
                                  normal[1] * normal[1] +
                                  normal[2] * normal[2];
    if (!(normal_squared > 1e-24) || !std::isfinite(normal_squared)) {
      throw std::invalid_argument(
          "native handoff contains a degenerate triangle");
    }
    signed_volumes[triangle.domain_index] +=
        (first.x * normal[0] + first.y * normal[1] +
         first.z * normal[2]) /
        6.0;
    const std::array<DirectedEdge, 3> directed{
        DirectedEdge{triangle.a, triangle.b},
        DirectedEdge{triangle.b, triangle.c},
        DirectedEdge{triangle.c, triangle.a}};
    for (const auto &[left, right] : directed) {
      edges[{triangle.domain_index, std::min(left, right),
             std::max(left, right)}]
          .push_back({left, right});
    }
    for (const auto index : {triangle.a, triangle.b, triangle.c}) {
      if (vertex_domains[index] != unassigned &&
          vertex_domains[index] != triangle.domain_index) {
        throw std::invalid_argument(
            "native handoff vertex is shared across material domains");
      }
      vertex_domains[index] = triangle.domain_index;
    }
  }
  if (std::any_of(vertex_domains.begin(), vertex_domains.end(),
                  [unassigned](std::size_t item) { return item == unassigned; })) {
    throw std::invalid_argument("native handoff contains an unused vertex");
  }
  for (const auto &[key, occurrences] : edges) {
    (void)key;
    if (occurrences.size() != 2 ||
        occurrences[0].first != occurrences[1].second ||
        occurrences[0].second != occurrences[1].first) {
      throw std::invalid_argument(
          "native handoff domains are not closed and consistently oriented");
    }
  }
  if (std::any_of(signed_volumes.begin(), signed_volumes.end(),
                  [](double value) {
                    return !(value > 1e-24) || !std::isfinite(value);
                  })) {
    throw std::invalid_argument(
        "native handoff domain volume is not finite and outward-oriented");
  }

  return {input.contract,
          input.source_geometry_contract,
          input.source_geometry_sha256,
          input.vertices.size(),
          input.triangles.size(),
          input.domains.size(),
          true,
          true,
          true,
          true,
          false};
}

} // namespace spike::peec
