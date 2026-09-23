#include "geometry/planar_topology.hpp"

#include <algorithm>
#include <array>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace spike::geometry {
namespace {

using Edge = std::pair<std::uint32_t, std::uint32_t>;

Edge edge(std::uint32_t a, std::uint32_t b) {
  return a < b ? Edge{a, b} : Edge{b, a};
}

bool same(const QuantizedPoint2 &a, const QuantizedPoint2 &b) {
  return a.x == b.x && a.y == b.y;
}

bool on_segment(const QuantizedPoint2 &p, const QuantizedPoint2 &a,
                const QuantizedPoint2 &b) {
  return exact_quantized_orientation(a, b, p) == 0 &&
         p.x >= std::min(a.x, b.x) && p.x <= std::max(a.x, b.x) &&
         p.y >= std::min(a.y, b.y) && p.y <= std::max(a.y, b.y);
}

bool proper_intersection(const QuantizedPoint2 &a, const QuantizedPoint2 &b,
                         const QuantizedPoint2 &c, const QuantizedPoint2 &d) {
  const int ab_c = exact_quantized_orientation(a, b, c);
  const int ab_d = exact_quantized_orientation(a, b, d);
  const int cd_a = exact_quantized_orientation(c, d, a);
  const int cd_b = exact_quantized_orientation(c, d, b);
  return ab_c != 0 && ab_d != 0 && cd_a != 0 && cd_b != 0 &&
         ab_c != ab_d && cd_a != cd_b;
}

QuantizedTriangle triangle(std::uint32_t a, std::uint32_t b, std::uint32_t c,
                           const std::vector<QuantizedPoint2> &vertices) {
  const int orientation = exact_quantized_orientation(vertices[a], vertices[b], vertices[c]);
  if (orientation == 0)
    throw std::logic_error("constrained triangulation formed a degenerate face");
  if (orientation < 0) std::swap(b, c);
  std::array<std::uint32_t, 3> ids{a, b, c};
  const auto minimum = std::min_element(ids.begin(), ids.end());
  const auto offset = static_cast<std::size_t>(minimum - ids.begin());
  return {ids[offset], ids[(offset + 1) % 3], ids[(offset + 2) % 3]};
}

std::map<Edge, std::vector<std::size_t>> adjacency(
    const std::vector<QuantizedTriangle> &triangles) {
  std::map<Edge, std::vector<std::size_t>> result;
  for (std::size_t index = 0; index < triangles.size(); ++index) {
    const auto &item = triangles[index];
    result[edge(item.a, item.b)].push_back(index);
    result[edge(item.b, item.c)].push_back(index);
    result[edge(item.c, item.a)].push_back(index);
  }
  return result;
}

std::uint32_t opposite(const QuantizedTriangle &item, const Edge &shared) {
  for (const auto candidate : {item.a, item.b, item.c})
    if (candidate != shared.first && candidate != shared.second) return candidate;
  throw std::logic_error("triangle has no vertex opposite its edge");
}

bool inside_scaled(const std::vector<QuantizedPoint2> &ring,
                   std::int64_t x_numerator, std::int64_t y_numerator,
                   std::int64_t denominator) {
  int winding = 0;
  for (std::size_t index = 0; index < ring.size(); ++index) {
    const auto &a = ring[index], &b = ring[(index + 1) % ring.size()];
    const int turn = exact_quantized_orientation_scaled(
        a, b, x_numerator, y_numerator, denominator);
    const auto ax = a.x * denominator, ay = a.y * denominator;
    const auto bx = b.x * denominator, by = b.y * denominator;
    if (turn == 0 && x_numerator >= std::min(ax, bx) &&
        x_numerator <= std::max(ax, bx) && y_numerator >= std::min(ay, by) &&
        y_numerator <= std::max(ay, by))
      throw std::logic_error("triangle classification sample lies on a constraint");
    if (ay <= y_numerator && by > y_numerator && turn > 0) ++winding;
    if (ay > y_numerator && by <= y_numerator && turn < 0) --winding;
  }
  return winding != 0;
}

bool equivalent(const CanonicalPlanarRegion &left,
                const CanonicalPlanarRegion &right) {
  if (left.cutouts.size() != right.cutouts.size() ||
      left.outer.points.size() != right.outer.points.size()) return false;
  const auto equal_ring = [](const auto &a, const auto &b) {
    if (a.points.size() != b.points.size()) return false;
    for (std::size_t index = 0; index < a.points.size(); ++index)
      if (!same(a.points[index], b.points[index])) return false;
    return true;
  };
  if (!equal_ring(left.outer, right.outer)) return false;
  for (std::size_t index = 0; index < left.cutouts.size(); ++index)
    if (!equal_ring(left.cutouts[index], right.cutouts[index])) return false;
  return true;
}

} // namespace

ConstrainedPlanarTriangulation triangulate_constrained_planar_region(
    const CanonicalPlanarRegion &region, std::size_t maximum_vertices,
    std::size_t maximum_holes, std::size_t maximum_triangles,
    std::size_t maximum_work_steps,
    const std::function<bool()> &cancellation_requested) {
  if (!region.topology_valid || region.coordinate_grid_mm != 0.000001 ||
      maximum_vertices < 3 || maximum_vertices > 4096 || maximum_holes > 128 ||
      region.cutouts.size() > maximum_holes || maximum_triangles == 0 ||
      maximum_triangles > 8192 || maximum_work_steps == 0 ||
      maximum_work_steps > 16777216)
    throw std::invalid_argument("constrained triangulation input or resource policy is invalid");

  std::vector<Point2> outer;
  std::vector<std::vector<Point2>> cutouts;
  for (const auto &point : region.outer.points)
    outer.push_back({point.x * 0.000001, point.y * 0.000001});
  for (const auto &source : region.cutouts) {
    std::vector<Point2> ring;
    for (const auto &point : source.points)
      ring.push_back({point.x * 0.000001, point.y * 0.000001});
    cutouts.push_back(std::move(ring));
  }
  const auto admitted = canonicalize_planar_region(
      outer, cutouts, 0.000001, maximum_vertices);
  if (!equivalent(region, admitted))
    throw std::invalid_argument("constrained triangulation region is not canonical");

  std::vector<QuantizedPoint2> vertices = region.outer.points;
  for (const auto &ring : region.cutouts)
    vertices.insert(vertices.end(), ring.points.begin(), ring.points.end());
  if (vertices.size() > maximum_vertices)
    throw std::invalid_argument("constrained triangulation vertex budget exceeded");
  std::sort(vertices.begin(), vertices.end(), [](const auto &a, const auto &b) {
    return std::tie(a.x, a.y) < std::tie(b.x, b.y);
  });
  if (std::adjacent_find(vertices.begin(), vertices.end(), same) != vertices.end())
    throw std::invalid_argument("constrained triangulation has duplicate vertices");

  const auto vertex_index = [&](const QuantizedPoint2 &point) {
    const auto found = std::lower_bound(vertices.begin(), vertices.end(), point,
        [](const auto &a, const auto &b) { return std::tie(a.x, a.y) < std::tie(b.x, b.y); });
    if (found == vertices.end() || !same(*found, point))
      throw std::logic_error("canonical region vertex table is incomplete");
    return static_cast<std::uint32_t>(found - vertices.begin());
  };

  std::vector<std::vector<std::uint32_t>> loops;
  const auto add_loop = [&](const auto &ring) {
    std::vector<std::uint32_t> indices;
    for (const auto &point : ring.points) indices.push_back(vertex_index(point));
    loops.push_back(std::move(indices));
  };
  add_loop(region.outer);
  for (const auto &ring : region.cutouts) add_loop(ring);
  std::set<Edge> constraints;
  for (const auto &loop : loops)
    for (std::size_t index = 0; index < loop.size(); ++index)
      constraints.insert(edge(loop[index], loop[(index + 1) % loop.size()]));

  const std::size_t expected_triangles = vertices.size() + 2 * region.cutouts.size() - 2;
  if (expected_triangles > maximum_triangles)
    throw std::invalid_argument("constrained triangulation triangle budget exceeded");
  std::size_t work_steps = 0;
  if (cancellation_requested && cancellation_requested())
    throw std::runtime_error("constrained triangulation was cancelled");
  const auto consume = [&]() {
    if (++work_steps > maximum_work_steps)
      throw std::runtime_error("constrained triangulation exceeded its deterministic work budget");
    if (cancellation_requested && work_steps % 1024 == 0 && cancellation_requested())
      throw std::runtime_error("constrained triangulation was cancelled");
  };

  std::vector<std::uint32_t> hull;
  for (std::uint32_t index = 0; index < vertices.size(); ++index) {
    while (hull.size() >= 2 && exact_quantized_orientation(
        vertices[hull[hull.size() - 2]], vertices[hull.back()], vertices[index]) <= 0) {
      consume(); hull.pop_back();
    }
    hull.push_back(index);
  }
  const auto lower_size = hull.size();
  for (std::size_t reverse = vertices.size() - 1; reverse-- > 0;) {
    const auto index = static_cast<std::uint32_t>(reverse);
    while (hull.size() > lower_size && exact_quantized_orientation(
        vertices[hull[hull.size() - 2]], vertices[hull.back()], vertices[index]) <= 0) {
      consume(); hull.pop_back();
    }
    hull.push_back(index);
  }
  if (!hull.empty()) hull.pop_back();
  if (hull.size() < 3)
    throw std::invalid_argument("constrained triangulation point set has no area");

  std::vector<QuantizedTriangle> triangles;
  for (std::size_t index = 1; index + 1 < hull.size(); ++index)
    triangles.push_back(triangle(hull[0], hull[index], hull[index + 1], vertices));
  std::set<std::uint32_t> hull_vertices(hull.begin(), hull.end());

  for (std::uint32_t point = 0; point < vertices.size(); ++point) {
    if (hull_vertices.contains(point)) continue;
    const auto graph = adjacency(triangles);
    bool inserted = false;
    for (const auto &[candidate, incident] : graph) {
      consume();
      if (!on_segment(vertices[point], vertices[candidate.first], vertices[candidate.second]) ||
          point == candidate.first || point == candidate.second) continue;
      std::vector<QuantizedTriangle> updated;
      for (std::size_t index = 0; index < triangles.size(); ++index)
        if (std::find(incident.begin(), incident.end(), index) == incident.end())
          updated.push_back(triangles[index]);
      for (const auto index : incident) {
        const auto third = opposite(triangles[index], candidate);
        updated.push_back(triangle(candidate.first, point, third, vertices));
        updated.push_back(triangle(point, candidate.second, third, vertices));
      }
      triangles = std::move(updated); inserted = true; break;
    }
    if (inserted) continue;
    for (std::size_t index = 0; index < triangles.size(); ++index) {
      consume();
      const auto &item = triangles[index];
      const int first = exact_quantized_orientation(vertices[item.a], vertices[item.b], vertices[point]);
      const int second = exact_quantized_orientation(vertices[item.b], vertices[item.c], vertices[point]);
      const int third = exact_quantized_orientation(vertices[item.c], vertices[item.a], vertices[point]);
      if (first <= 0 || second <= 0 || third <= 0) continue;
      const auto old = item;
      triangles[index] = triangle(old.a, old.b, point, vertices);
      triangles.push_back(triangle(old.b, old.c, point, vertices));
      triangles.push_back(triangle(old.c, old.a, point, vertices));
      inserted = true; break;
    }
    if (!inserted)
      throw std::logic_error("constrained triangulation could not insert a source vertex");
  }

  for (const auto &constraint : constraints) {
    while (true) {
      const auto graph = adjacency(triangles);
      if (graph.contains(constraint)) break;
      bool flipped = false;
      for (const auto &[candidate, incident] : graph) {
        consume();
        if (incident.size() != 2 || constraints.contains(candidate) ||
            !proper_intersection(vertices[constraint.first], vertices[constraint.second],
                                 vertices[candidate.first], vertices[candidate.second])) continue;
        const auto first = opposite(triangles[incident[0]], candidate);
        const auto second = opposite(triangles[incident[1]], candidate);
        if (!proper_intersection(vertices[first], vertices[second],
                                 vertices[candidate.first], vertices[candidate.second]) ||
            graph.contains(edge(first, second))) continue;
        triangles[incident[0]] = triangle(first, second, candidate.first, vertices);
        triangles[incident[1]] = triangle(second, first, candidate.second, vertices);
        flipped = true; break;
      }
      if (!flipped)
        throw std::logic_error("exact constraint recovery could not make progress");
    }
  }

  while (true) {
    const auto graph = adjacency(triangles);
    bool flipped = false;
    for (const auto &[candidate, incident] : graph) {
      consume();
      if (incident.size() != 2 || constraints.contains(candidate)) continue;
      const auto first = opposite(triangles[incident[0]], candidate);
      const auto second = opposite(triangles[incident[1]], candidate);
      if (!proper_intersection(vertices[first], vertices[second],
                               vertices[candidate.first], vertices[candidate.second])) continue;
      const int incircle = exact_quantized_incircle(
          vertices[candidate.first], vertices[candidate.second], vertices[first], vertices[second]);
      const auto replacement = edge(first, second);
      if (incircle < 0 || (incircle == 0 && !(replacement < candidate))) continue;
      if (graph.contains(replacement))
        throw std::logic_error("Delaunay legalization would duplicate an edge");
      triangles[incident[0]] = triangle(first, second, candidate.first, vertices);
      triangles[incident[1]] = triangle(second, first, candidate.second, vertices);
      flipped = true; break;
    }
    if (!flipped) break;
  }

  std::vector<QuantizedTriangle> domain;
  for (const auto &item : triangles) {
    consume();
    const auto x = vertices[item.a].x + vertices[item.b].x + vertices[item.c].x;
    const auto y = vertices[item.a].y + vertices[item.b].y + vertices[item.c].y;
    bool included = inside_scaled(region.outer.points, x, y, 3);
    for (const auto &hole : region.cutouts)
      if (included && inside_scaled(hole.points, x, y, 3)) included = false;
    if (included) domain.push_back(item);
  }
  std::sort(domain.begin(), domain.end(), [](const auto &a, const auto &b) {
    return std::tie(a.a, a.b, a.c) < std::tie(b.a, b.b, b.c);
  });
  if (domain.size() != expected_triangles)
    throw std::logic_error("constrained triangulation failed the Euler face-count audit");

  const auto graph = adjacency(domain);
  std::set<std::uint32_t> used;
  std::int64_t area_sum = 0;
  for (const auto &item : domain) {
    consume();
    used.insert(item.a); used.insert(item.b); used.insert(item.c);
    const auto value = exact_quantized_twice_area(
        {vertices[item.a], vertices[item.b], vertices[item.c]});
    if (value <= 0 || area_sum > std::numeric_limits<std::int64_t>::max() - value)
      throw std::overflow_error("constrained triangulation area audit overflow");
    area_sum += value;
  }
  for (const auto &[candidate, incident] : graph) {
    consume();
    const auto expected = constraints.contains(candidate) ? 1u : 2u;
    if (incident.size() != expected)
      throw std::logic_error("constrained triangulation edge incidence is invalid");
    if (incident.size() == 2 && !constraints.contains(candidate)) {
      const auto first = opposite(domain[incident[0]], candidate);
      const auto second = opposite(domain[incident[1]], candidate);
      if (proper_intersection(vertices[first], vertices[second],
                              vertices[candidate.first], vertices[candidate.second])) {
        const int incircle = exact_quantized_incircle(
            vertices[candidate.first], vertices[candidate.second], vertices[first], vertices[second]);
        if (incircle > 0 || (incircle == 0 && edge(first, second) < candidate))
          throw std::logic_error("constrained triangulation is not deterministically locally Delaunay");
      }
    }
  }
  std::int64_t source_area = exact_quantized_twice_area(region.outer.points);
  for (const auto &hole : region.cutouts) {
    const auto hole_area = exact_quantized_twice_area(hole.points);
    if (hole_area >= 0 || source_area < -hole_area)
      throw std::logic_error("canonical cutout orientation or area is invalid");
    source_area += hole_area;
  }
  const std::size_t expected_edges = 2 * vertices.size() + 3 * region.cutouts.size() - 3;
  if (used.size() != vertices.size() || graph.size() != expected_edges ||
      area_sum != source_area)
    throw std::logic_error("constrained triangulation failed exact coverage audit");
  return {vertices, domain, loops, source_area, work_steps, true, true, true, true};
}

} // namespace spike::geometry
