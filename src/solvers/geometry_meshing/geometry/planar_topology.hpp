#pragma once

#include <string>
#include <array>
#include <cstdint>
#include <functional>
#include <vector>

namespace spike::geometry {

struct Point2 {
  double x = 0.0;
  double y = 0.0;
};

struct CanonicalRing {
  std::vector<Point2> points;
  double signed_area = 0.0;
  bool input_reversed = false;
  bool simple = false;
};

struct QuantizedPoint2 { std::int64_t x = 0, y = 0; };

// Exact fixed-grid predicates used by topology and the constrained-mesh
// kernel. The incircle implementation uses an internal signed 256-bit
// accumulator and does not depend on platform floating-point behavior.
int exact_quantized_orientation(const QuantizedPoint2 &a,
                                const QuantizedPoint2 &b,
                                const QuantizedPoint2 &c);
int exact_quantized_incircle(const QuantizedPoint2 &a,
                             const QuantizedPoint2 &b,
                             const QuantizedPoint2 &c,
                             const QuantizedPoint2 &d);
int exact_quantized_orientation_scaled(const QuantizedPoint2 &a,
                                       const QuantizedPoint2 &b,
                                       std::int64_t point_x_numerator,
                                       std::int64_t point_y_numerator,
                                       std::int64_t positive_denominator);
std::int64_t exact_quantized_twice_area(
    const std::vector<QuantizedPoint2> &ring);

struct CanonicalQuantizedRing {
  std::vector<QuantizedPoint2> points;
  double area_mm2 = 0.0;
  bool input_reversed = false;
  bool simple = false;
};

struct CanonicalPlanarRegion {
  CanonicalQuantizedRing outer;
  std::vector<CanonicalQuantizedRing> cutouts;
  double copper_area_mm2 = 0.0;
  double coordinate_grid_mm = 0.000001;
  bool topology_valid = false;
};

struct QuantizedTriangle {
  std::uint32_t a = 0, b = 0, c = 0;
};

struct SimplePlanarTriangulation {
  std::vector<QuantizedPoint2> vertices;
  std::vector<QuantizedTriangle> triangles;
  std::int64_t twice_area_grid = 0;
  std::size_t work_steps = 0;
  bool boundary_constraints_preserved = false;
  bool exact_area_preserved = false;
};

struct ConstrainedPlanarTriangulation {
  std::vector<QuantizedPoint2> vertices;
  std::vector<QuantizedTriangle> triangles;
  std::vector<std::vector<std::uint32_t>> boundary_loops;
  std::int64_t twice_area_grid = 0;
  std::size_t work_steps = 0;
  bool boundary_constraints_preserved = false;
  bool exact_area_preserved = false;
  bool domain_classified = false;
  bool locally_delaunay = false;
};

// Returns -1 or +1 only when the floating-point error bound certifies the
// sign, and zero for an exactly represented collinearity. Other unresolved
// near-degeneracies fail closed.
int certified_orientation(const Point2 &a, const Point2 &b, const Point2 &c);

CanonicalRing canonicalize_simple_ring(const std::vector<Point2> &input,
                                       std::size_t maximum_points = 4096);

QuantizedPoint2 quantize_planar_point(const Point2 &point,
                                     double coordinate_grid_mm = 0.000001);
CanonicalQuantizedRing canonicalize_quantized_ring(
    const std::vector<Point2> &input, bool clockwise = false,
    double coordinate_grid_mm = 0.000001, std::size_t maximum_points = 4096);
CanonicalPlanarRegion canonicalize_planar_region(
    const std::vector<Point2> &outer,
    const std::vector<std::vector<Point2>> &cutouts,
    double coordinate_grid_mm = 0.000001, std::size_t maximum_total_points = 16384);
SimplePlanarTriangulation triangulate_simple_planar_ring(
    const CanonicalQuantizedRing &ring, std::size_t maximum_points = 4096,
    std::size_t maximum_triangles = 8192,
    std::size_t maximum_work_steps = 16777216);
ConstrainedPlanarTriangulation triangulate_constrained_planar_region(
    const CanonicalPlanarRegion &region, std::size_t maximum_vertices = 4096,
    std::size_t maximum_holes = 128, std::size_t maximum_triangles = 8192,
    std::size_t maximum_work_steps = 16777216,
    const std::function<bool()> &cancellation_requested = {});

} // namespace spike::geometry
