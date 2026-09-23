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
using FaceKey = std::tuple<std::size_t, std::size_t, std::size_t, std::size_t>;

void id(const std::string &value, const char *label) {
  if (value.empty() || value.size() > 512 ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return item < 0x20 || item == 0x7f;
      }))
    throw std::invalid_argument(std::string(label) + " is invalid");
}

void optional_id(const std::string &value, const char *label,
                 std::size_t maximum) {
  if (value.size() > maximum ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return item < 0x20 || item == 0x7f;
      }))
    throw std::invalid_argument(std::string(label) + " is invalid");
}

void digest(const std::string &value, const char *label) {
  if (value.size() != 64 ||
      std::any_of(value.begin(), value.end(), [](unsigned char item) {
        return !(item >= '0' && item <= '9') && !(item >= 'a' && item <= 'f');
      }))
    throw std::invalid_argument(std::string(label) + " is not lowercase SHA-256");
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

std::array<double, 3> subtract(const ReferencePlaneAntipadVertex &left,
                               const ReferencePlaneAntipadVertex &right) {
  return {left.x - right.x, left.y - right.y, left.z - right.z};
}
std::array<double, 3> cross(const std::array<double, 3> &left,
                            const std::array<double, 3> &right) {
  return {left[1] * right[2] - left[2] * right[1],
          left[2] * right[0] - left[0] * right[2],
          left[0] * right[1] - left[1] * right[0]};
}
} // namespace

ReferencePlaneAntipadMeshValidation validate_reference_plane_antipad_mesh_input(
    const ReferencePlaneAntipadMeshInput &input,
    const std::string &expected_geometry_sha256) {
  if (input.contract != kReferencePlaneAntipadMeshContract ||
      input.source_geometry_contract != kReferencePlaneAntipadGeometryContract)
    throw std::invalid_argument("unsupported reference-plane contract");
  if (input.solver_ready)
    throw std::invalid_argument("geometry admission cannot be solver-ready");
  digest(input.source_geometry_sha256, "source geometry digest");
  digest(expected_geometry_sha256, "expected geometry digest");
  if (input.source_geometry_sha256 != expected_geometry_sha256)
    throw std::invalid_argument("source geometry digest mismatch");
  id(input.design_id, "design_id"); id(input.via_id, "via_id");
  optional_id(input.source_via_id, "source_via_id", 256);
  if (input.vertices.empty() || input.vertices.size() > kReferencePlaneMaxVertices ||
      input.triangles.empty() || input.triangles.size() > kReferencePlaneMaxTriangles ||
      input.domains.empty() || input.domains.size() > kReferencePlaneMaxDomains)
    throw std::invalid_argument("native reference-plane arrays exceed bounds");
  if (input.declared_vertex_count != input.vertices.size() ||
      input.declared_triangle_count != input.triangles.size() ||
      input.declared_domain_count != input.domains.size())
    throw std::invalid_argument("declared resource counts do not match arrays");

  std::set<std::string> domain_ids;
  for (const auto &domain : input.domains) {
    id(domain.id, "domain id"); id(domain.net_id, "domain net_id");
    id(domain.layer_id, "domain layer_id"); id(domain.reference_zone_id, "zone id");
    sources(domain.source_ids, "domain source ids");
    if (std::find(domain.source_ids.begin(), domain.source_ids.end(),
                  domain.reference_zone_id) == domain.source_ids.end())
      throw std::invalid_argument("reference zone is absent from domain provenance");
    digest(domain.source_zone_sha256, "source zone digest");
    digest(domain.resolved_region_sha256, "resolved region digest");
    if (!domain_ids.insert(domain.id).second ||
        !(domain.antipad_radius_mm > 0.0) || !std::isfinite(domain.antipad_radius_mm))
      throw std::invalid_argument("native reference-plane domain is invalid");
  }
  for (const auto &vertex : input.vertices)
    if (!std::isfinite(vertex.x) || !std::isfinite(vertex.y) || !std::isfinite(vertex.z))
      throw std::invalid_argument("native reference-plane vertex is non-finite");

  const std::set<std::string> roles{
      "reference_zone_upper_face", "reference_zone_lower_face",
      "reference_zone_outer_boundary", "antipad_void_boundary"};
  const auto unassigned = std::numeric_limits<std::size_t>::max();
  std::vector<std::size_t> owners(input.vertices.size(), unassigned);
  std::vector<double> volumes(input.domains.size(), 0.0);
  std::vector<std::set<std::string>> roles_by_domain(input.domains.size());
  std::map<EdgeKey, std::vector<Edge>> edges;
  std::set<FaceKey> faces;
  std::set<std::string> triangle_ids;
  for (const auto &triangle : input.triangles) {
    id(triangle.id, "triangle id"); sources(triangle.source_ids, "triangle source ids");
    if (!triangle_ids.insert(triangle.id).second || !roles.contains(triangle.surface_role) ||
        triangle.domain_index >= input.domains.size() ||
        triangle.a >= input.vertices.size() || triangle.b >= input.vertices.size() ||
        triangle.c >= input.vertices.size() || triangle.a == triangle.b ||
        triangle.b == triangle.c || triangle.a == triangle.c)
      throw std::invalid_argument("native reference-plane triangle is invalid");
    const auto &domain_sources = input.domains[triangle.domain_index].source_ids;
    if (std::set<std::string>(triangle.source_ids.begin(), triangle.source_ids.end()) !=
        std::set<std::string>(domain_sources.begin(), domain_sources.end()))
      throw std::invalid_argument("triangle provenance is not owned by its domain");
    roles_by_domain[triangle.domain_index].insert(triangle.surface_role);
    std::array<std::size_t, 3> sorted{triangle.a, triangle.b, triangle.c};
    std::sort(sorted.begin(), sorted.end());
    if (!faces.insert({triangle.domain_index, sorted[0], sorted[1], sorted[2]}).second)
      throw std::invalid_argument("duplicate native reference-plane triangle");
    const auto &first = input.vertices[triangle.a];
    const auto normal = cross(subtract(input.vertices[triangle.b], first),
                              subtract(input.vertices[triangle.c], first));
    const double magnitude = normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2];
    if (!(magnitude > 1e-24) || !std::isfinite(magnitude))
      throw std::invalid_argument("degenerate native reference-plane triangle");
    volumes[triangle.domain_index] +=
        (first.x * normal[0] + first.y * normal[1] + first.z * normal[2]) / 6.0;
    for (const auto [left, right] :
         {Edge{triangle.a, triangle.b}, Edge{triangle.b, triangle.c}, Edge{triangle.c, triangle.a}})
      edges[{triangle.domain_index, std::min(left, right), std::max(left, right)}].push_back({left, right});
    for (const auto index : {triangle.a, triangle.b, triangle.c}) {
      if (owners[index] != unassigned && owners[index] != triangle.domain_index)
        throw std::invalid_argument("vertex is shared across reference-plane domains");
      owners[index] = triangle.domain_index;
    }
  }
  if (std::any_of(owners.begin(), owners.end(), [unassigned](auto value) { return value == unassigned; }))
    throw std::invalid_argument("unused native reference-plane vertex");
  for (const auto &[key, occurrences] : edges) {
    (void)key;
    if (occurrences.size() != 2 || occurrences[0].first != occurrences[1].second ||
        occurrences[0].second != occurrences[1].first)
      throw std::invalid_argument("reference-plane domains are not closed and oriented");
  }
  if (std::any_of(volumes.begin(), volumes.end(),
                  [](double value) { return !(value > 1e-24) || !std::isfinite(value); }))
    throw std::invalid_argument("reference-plane domain volume is invalid");
  if (std::any_of(roles_by_domain.begin(), roles_by_domain.end(),
                  [&roles](const auto &seen) { return seen != roles; }))
    throw std::invalid_argument("reference-plane domain surface roles are incomplete");
  return {input.contract, input.source_geometry_contract, input.source_geometry_sha256,
          input.vertices.size(), input.triangles.size(), input.domains.size(),
          true, true, true, true, false};
}
} // namespace spike::peec
