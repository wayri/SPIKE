#include "geometry/planar_topology.hpp"

#include <cassert>
#include <cmath>
#include <stdexcept>

using spike::geometry::Point2;
using spike::geometry::canonicalize_simple_ring;
using spike::geometry::certified_orientation;
using spike::geometry::canonicalize_planar_region;
using spike::geometry::exact_quantized_incircle;
using spike::geometry::exact_quantized_orientation;
using spike::geometry::exact_quantized_orientation_scaled;
using spike::geometry::exact_quantized_twice_area;
using spike::geometry::triangulate_simple_planar_ring;
using spike::geometry::triangulate_constrained_planar_region;

template <typename Callable> void rejects(Callable &&callable) {
  bool failed = false;
  try { callable(); } catch (const std::invalid_argument &) { failed = true; }
  assert(failed);
}

int main() {
  const std::vector<Point2> concave{{4, 0}, {4, 4}, {2, 2}, {0, 4}, {0, 0}};
  const auto ring = canonicalize_simple_ring(concave);
  assert(ring.simple && !ring.input_reversed && ring.points.size() == 5);
  assert(ring.points[0].x == 0 && ring.points[0].y == 0);
  assert(std::abs(ring.signed_area - 12.0) < 1e-12);
  assert(certified_orientation({0, 0}, {2, 0}, {1, 1}) == 1);
  assert(certified_orientation({0, 0}, {1, 1}, {2, 2}) == 0);
  assert(exact_quantized_orientation({0, 0}, {10, 0}, {0, 10}) == 1);
  assert(exact_quantized_incircle({0, 0}, {10, 0}, {0, 10}, {5, 5}) == 1);
  assert(exact_quantized_incircle({0, 0}, {10, 0}, {0, 10}, {10, 10}) == 0);
  assert(exact_quantized_incircle({0, 0}, {10, 0}, {0, 10}, {11, 11}) == -1);
  assert(exact_quantized_incircle({0, 0}, {0, 10}, {10, 0}, {5, 5}) == 1);
  assert(exact_quantized_incircle(
      {-1000000000, -1000000000}, {1000000000, -1000000000},
      {1000000000, 1000000000}, {0, 0}) == 1);
  assert(exact_quantized_orientation_scaled({0, 0}, {10, 0}, 10, 2, 2) == 1);
  assert(exact_quantized_orientation_scaled({0, 0}, {10, 0}, 10, -2, 2) == -1);
  assert(exact_quantized_twice_area({
      {-1000000000, -1000000000}, {1000000000, -1000000000},
      {1000000000, 1000000000}, {-1000000000, 1000000000}}) ==
      8000000000000000000LL);
  rejects([] { exact_quantized_incircle(
      {0, 0}, {1000000001, 0}, {0, 10}, {1, 1}); });
  rejects([] { exact_quantized_orientation_scaled({0, 0}, {1, 0}, 0, 0, 0); });
  rejects([] { canonicalize_simple_ring({{0, 0}, {2, 2}, {0, 2}, {2, 0}}); });
  rejects([] { canonicalize_simple_ring({{0, 0}, {1, 0}, {1, 0}, {0, 1}}); });
  const auto region = canonicalize_planar_region(
      {{0, 0}, {8, 0}, {8, 8}, {4, 5}, {0, 8}},
      {{{1, 1}, {1, 2}, {2, 2}, {2, 1}},
       {{5, 1}, {5, 2}, {6, 2}, {6, 1}}});
  assert(region.topology_valid && region.cutouts.size() == 2);
  assert(std::abs(region.copper_area_mm2 - 50.0) < 1e-12);
  assert(region.outer.points.front().x == 0 && region.outer.points.front().y == 0);
  const auto concave_mesh = triangulate_simple_planar_ring(
      spike::geometry::canonicalize_quantized_ring(
          {{0, 0}, {6, 0}, {6, 2}, {2, 2}, {2, 6}, {0, 6}}));
  assert(concave_mesh.triangles.size() == 4 &&
         concave_mesh.twice_area_grid == 40000000000000LL);
  assert(concave_mesh.boundary_constraints_preserved && concave_mesh.exact_area_preserved);
  const auto collinear_mesh = triangulate_simple_planar_ring(
      spike::geometry::canonicalize_quantized_ring(
          {{0, 0}, {4, 0}, {8, 0}, {8, 6}, {0, 6}}));
  assert(collinear_mesh.triangles.size() == 3 && collinear_mesh.vertices.size() == 5 &&
         collinear_mesh.twice_area_grid == 96000000000000LL);
  const auto hole_region = canonicalize_planar_region(
      {{0, 0}, {10, 0}, {10, 10}, {0, 10}},
      {{{3, 3}, {3, 7}, {7, 7}, {7, 3}}});
  const auto hole_mesh = triangulate_constrained_planar_region(hole_region);
  assert(hole_mesh.vertices.size() == 8 && hole_mesh.triangles.size() == 8);
  assert(hole_mesh.twice_area_grid == 168000000000000LL);
  assert(hole_mesh.boundary_constraints_preserved && hole_mesh.exact_area_preserved &&
         hole_mesh.domain_classified && hole_mesh.locally_delaunay);
  assert(hole_mesh.boundary_loops.size() == 2);
  const auto two_hole_region = canonicalize_planar_region(
      {{0, 0}, {20, 0}, {20, 10}, {0, 10}},
      {{{2, 1}, {9.999, 1}, {9.999, 9}, {2, 9}},
       {{10.001, 1}, {18, 1}, {18, 9}, {10.001, 9}}});
  const auto two_hole_mesh = triangulate_constrained_planar_region(two_hole_region);
  assert(two_hole_mesh.vertices.size() == 12 && two_hole_mesh.triangles.size() == 14);
  assert(two_hole_mesh.twice_area_grid == 144032000000000LL);
  const auto hole_mesh_repeat = triangulate_constrained_planar_region(hole_region);
  assert(hole_mesh_repeat.work_steps == hole_mesh.work_steps &&
         hole_mesh_repeat.triangles.size() == hole_mesh.triangles.size());
  for (std::size_t i = 0; i < hole_mesh.triangles.size(); ++i)
    assert(std::tie(hole_mesh.triangles[i].a, hole_mesh.triangles[i].b,
                    hole_mesh.triangles[i].c) ==
           std::tie(hole_mesh_repeat.triangles[i].a, hole_mesh_repeat.triangles[i].b,
                    hole_mesh_repeat.triangles[i].c));
  rejects([&] { triangulate_constrained_planar_region(hole_region, 7); });
  rejects([&] { triangulate_constrained_planar_region(hole_region, 4096, 128, 7); });
  rejects([] { triangulate_simple_planar_ring(
      spike::geometry::canonicalize_quantized_ring({{0, 0}, {4, 0}, {4, 4}, {0, 4}}),
      3); });
  rejects([] { canonicalize_planar_region(
      {{0, 0}, {4, 0}, {4, 4}, {0, 4}},
      {{{3, 3}, {3, 5}, {5, 5}, {5, 3}}}); });
  rejects([] { canonicalize_planar_region(
      {{0, 0}, {6, 0}, {6, 6}, {0, 6}},
      {{{1, 1}, {1, 4}, {4, 4}, {4, 1}},
       {{3, 3}, {3, 5}, {5, 5}, {5, 3}}}); });
  rejects([] { spike::geometry::quantize_planar_point({0.0000004, 0.0}); });
}
