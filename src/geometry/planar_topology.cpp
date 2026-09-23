#include "geometry/planar_topology.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <tuple>
#include <map>
#include <set>
#ifdef _MSC_VER
#include <intrin.h>
#endif

namespace spike::geometry {
namespace {

constexpr std::int64_t kMaximumGridCoordinate = 1000000000;

struct Unsigned256 {
  std::array<std::uint64_t, 4> limb{};
};

struct Signed256 {
  int sign = 0;
  Unsigned256 magnitude{};
};

std::uint64_t magnitude(std::int64_t value) {
  return value < 0 ? std::uint64_t(-(value + 1)) + 1 : std::uint64_t(value);
}

Unsigned256 multiply64(std::uint64_t left, std::uint64_t right) {
  Unsigned256 result;
#ifdef _MSC_VER
  result.limb[0] = _umul128(left, right, &result.limb[1]);
#else
  const unsigned __int128 product = static_cast<unsigned __int128>(left) * right;
  result.limb[0] = static_cast<std::uint64_t>(product);
  result.limb[1] = static_cast<std::uint64_t>(product >> 64);
#endif
  return result;
}

int compare(const Unsigned256 &left, const Unsigned256 &right) {
  for (std::size_t index = left.limb.size(); index-- > 0;)
    if (left.limb[index] != right.limb[index])
      return left.limb[index] < right.limb[index] ? -1 : 1;
  return 0;
}

Unsigned256 add(const Unsigned256 &left, const Unsigned256 &right) {
  Unsigned256 result;
  std::uint64_t carry = 0;
  for (std::size_t index = 0; index < result.limb.size(); ++index) {
    const auto first = left.limb[index] + carry;
    const bool first_overflow = first < left.limb[index];
    const auto second = first + right.limb[index];
    const bool second_overflow = second < first;
    result.limb[index] = second;
    carry = first_overflow || second_overflow;
  }
  if (carry) throw std::overflow_error("fixed-grid predicate accumulator overflow");
  return result;
}

Unsigned256 subtract(const Unsigned256 &left, const Unsigned256 &right) {
  Unsigned256 result;
  std::uint64_t borrow = 0;
  for (std::size_t index = 0; index < result.limb.size(); ++index) {
    const auto first = left.limb[index] - borrow;
    const bool first_borrow = first > left.limb[index];
    const auto second = first - right.limb[index];
    const bool second_borrow = second > first;
    result.limb[index] = second;
    borrow = first_borrow || second_borrow;
  }
  if (borrow) throw std::logic_error("invalid fixed-grid magnitude subtraction");
  return result;
}

bool zero(const Unsigned256 &value) {
  return std::all_of(value.limb.begin(), value.limb.end(),
                     [](std::uint64_t item) { return item == 0; });
}

Signed256 add_signed(const Signed256 &left, const Signed256 &right) {
  if (left.sign == 0) return right;
  if (right.sign == 0) return left;
  if (left.sign == right.sign) return {left.sign, add(left.magnitude, right.magnitude)};
  const int ordering = compare(left.magnitude, right.magnitude);
  if (ordering == 0) return {};
  return ordering > 0 ? Signed256{left.sign, subtract(left.magnitude, right.magnitude)}
                      : Signed256{right.sign, subtract(right.magnitude, left.magnitude)};
}

Signed256 product(std::uint64_t unsigned_value, std::int64_t signed_value) {
  if (unsigned_value == 0 || signed_value == 0) return {};
  return {signed_value < 0 ? -1 : 1, multiply64(unsigned_value, magnitude(signed_value))};
}

Signed256 product_signed(std::int64_t left, std::int64_t right) {
  if (left == 0 || right == 0) return {};
  return {(left < 0) == (right < 0) ? 1 : -1,
          multiply64(magnitude(left), magnitude(right))};
}

Signed256 negate(Signed256 value) {
  value.sign = -value.sign;
  return value;
}

std::int64_t bounded_int64(const Signed256 &value, const char *message) {
  if (value.magnitude.limb[1] != 0 || value.magnitude.limb[2] != 0 ||
      value.magnitude.limb[3] != 0 ||
      value.magnitude.limb[0] > std::uint64_t(std::numeric_limits<std::int64_t>::max()))
    throw std::overflow_error(message);
  return value.sign * static_cast<std::int64_t>(value.magnitude.limb[0]);
}

void require_grid_domain(const QuantizedPoint2 &point) {
  if (point.x < -kMaximumGridCoordinate || point.x > kMaximumGridCoordinate ||
      point.y < -kMaximumGridCoordinate || point.y > kMaximumGridCoordinate)
    throw std::invalid_argument("quantized point exceeds the exact predicate range");
}

bool same(const Point2 &a, const Point2 &b) { return a.x == b.x && a.y == b.y; }

bool on_box(const Point2 &point, const Point2 &a, const Point2 &b) {
  return point.x >= std::min(a.x, b.x) && point.x <= std::max(a.x, b.x) &&
         point.y >= std::min(a.y, b.y) && point.y <= std::max(a.y, b.y);
}

bool segments_intersect(const Point2 &a, const Point2 &b, const Point2 &c,
                        const Point2 &d) {
  if (same(a, c) || same(a, d) || same(b, c) || same(b, d))
    return true;
  const int ab_c = certified_orientation(a, b, c);
  const int ab_d = certified_orientation(a, b, d);
  const int cd_a = certified_orientation(c, d, a);
  const int cd_b = certified_orientation(c, d, b);
  if ((ab_c == 0 && on_box(c, a, b)) || (ab_d == 0 && on_box(d, a, b)) ||
      (cd_a == 0 && on_box(a, c, d)) || (cd_b == 0 && on_box(b, c, d)))
    return true;
  return ab_c != ab_d && cd_a != cd_b;
}

long double area2(const std::vector<Point2> &points) {
  long double sum = 0.0L;
  for (std::size_t index = 0; index < points.size(); ++index) {
    const auto &next = points[(index + 1) % points.size()];
    sum += static_cast<long double>(points[index].x) * next.y -
           static_cast<long double>(next.x) * points[index].y;
  }
  return sum;
}

bool same(const QuantizedPoint2 &a, const QuantizedPoint2 &b) {
  return a.x == b.x && a.y == b.y;
}

std::int64_t exact_orientation_value(const QuantizedPoint2 &a,
                                     const QuantizedPoint2 &b,
                                     const QuantizedPoint2 &c) {
  const std::int64_t abx = b.x - a.x, aby = b.y - a.y;
  const std::int64_t acx = c.x - a.x, acy = c.y - a.y;
  return abx * acy - aby * acx;
}

bool on_box(const QuantizedPoint2 &p, const QuantizedPoint2 &a,
            const QuantizedPoint2 &b) {
  return p.x >= std::min(a.x, b.x) && p.x <= std::max(a.x, b.x) &&
         p.y >= std::min(a.y, b.y) && p.y <= std::max(a.y, b.y);
}

bool segments_intersect(const QuantizedPoint2 &a, const QuantizedPoint2 &b,
                        const QuantizedPoint2 &c, const QuantizedPoint2 &d) {
  const int ab_c = exact_quantized_orientation(a, b, c), ab_d = exact_quantized_orientation(a, b, d);
  const int cd_a = exact_quantized_orientation(c, d, a), cd_b = exact_quantized_orientation(c, d, b);
  if ((ab_c == 0 && on_box(c, a, b)) || (ab_d == 0 && on_box(d, a, b)) ||
      (cd_a == 0 && on_box(a, c, d)) || (cd_b == 0 && on_box(b, c, d))) return true;
  return ab_c != ab_d && cd_a != cd_b;
}

bool point_inside(const QuantizedPoint2 &point,
                  const std::vector<QuantizedPoint2> &ring) {
  int winding = 0;
  for (std::size_t i = 0; i < ring.size(); ++i) {
    const auto &a = ring[i], &b = ring[(i + 1) % ring.size()];
    const int turn = exact_quantized_orientation(a, b, point);
    if (turn == 0 && on_box(point, a, b))
      throw std::invalid_argument("planar rings touch at a boundary");
    if (a.y <= point.y && b.y > point.y && turn > 0) ++winding;
    if (a.y > point.y && b.y <= point.y && turn < 0) --winding;
  }
  return winding != 0;
}

bool rings_intersect(const std::vector<QuantizedPoint2> &left,
                     const std::vector<QuantizedPoint2> &right) {
  for (std::size_t i = 0; i < left.size(); ++i)
    for (std::size_t j = 0; j < right.size(); ++j)
      if (segments_intersect(left[i], left[(i + 1) % left.size()],
                             right[j], right[(j + 1) % right.size()])) return true;
  return false;
}

} // namespace

int exact_quantized_orientation(const QuantizedPoint2 &a,
                                const QuantizedPoint2 &b,
                                const QuantizedPoint2 &c) {
  require_grid_domain(a); require_grid_domain(b); require_grid_domain(c);
  const auto value = exact_orientation_value(a, b, c);
  return value > 0 ? 1 : value < 0 ? -1 : 0;
}

int exact_quantized_incircle(const QuantizedPoint2 &a,
                             const QuantizedPoint2 &b,
                             const QuantizedPoint2 &c,
                             const QuantizedPoint2 &d) {
  require_grid_domain(a); require_grid_domain(b); require_grid_domain(c); require_grid_domain(d);
  const std::int64_t ax = a.x - d.x, ay = a.y - d.y;
  const std::int64_t bx = b.x - d.x, by = b.y - d.y;
  const std::int64_t cx = c.x - d.x, cy = c.y - d.y;
  const auto lift = [](std::int64_t x, std::int64_t y) {
    return magnitude(x) * magnitude(x) + magnitude(y) * magnitude(y);
  };
  const std::int64_t bc = bx * cy - by * cx;
  const std::int64_t ca = cx * ay - cy * ax;
  const std::int64_t ab = ax * by - ay * bx;
  auto determinant = add_signed(product(lift(ax, ay), bc), product(lift(bx, by), ca));
  determinant = add_signed(determinant, product(lift(cx, cy), ab));
  if (zero(determinant.magnitude)) return 0;
  const int orientation = exact_quantized_orientation(a, b, c);
  if (orientation == 0) throw std::invalid_argument("incircle requires a non-collinear triangle");
  return determinant.sign * orientation;
}

int exact_quantized_orientation_scaled(const QuantizedPoint2 &a,
                                       const QuantizedPoint2 &b,
                                       std::int64_t point_x_numerator,
                                       std::int64_t point_y_numerator,
                                       std::int64_t positive_denominator) {
  require_grid_domain(a); require_grid_domain(b);
  if (positive_denominator <= 0 || positive_denominator > 16)
    throw std::invalid_argument("scaled fixed-grid predicate denominator is invalid");
  const auto px = point_x_numerator - a.x * positive_denominator;
  const auto py = point_y_numerator - a.y * positive_denominator;
  const auto dx = b.x - a.x, dy = b.y - a.y;
  auto determinant = add_signed(product_signed(dx, py), negate(product_signed(dy, px)));
  return determinant.sign;
}

std::int64_t exact_quantized_twice_area(
    const std::vector<QuantizedPoint2> &ring) {
  if (ring.size() < 3 || ring.size() > 65536)
    throw std::invalid_argument("exact area requires a bounded ring");
  Signed256 total;
  for (std::size_t index = 0; index < ring.size(); ++index) {
    const auto &first = ring[index], &second = ring[(index + 1) % ring.size()];
    require_grid_domain(first);
    total = add_signed(total, product_signed(first.x, second.y));
    total = add_signed(total, negate(product_signed(second.x, first.y)));
  }
  if (total.sign == 0) throw std::invalid_argument("exact ring area is zero");
  return bounded_int64(total, "exact ring area exceeds the bounded return range");
}

int certified_orientation(const Point2 &a, const Point2 &b, const Point2 &c) {
  for (const double value : {a.x, a.y, b.x, b.y, c.x, c.y})
    if (!std::isfinite(value))
      throw std::invalid_argument("planar predicate requires finite coordinates");
  const double left_x = a.x - c.x, left_y = a.y - c.y;
  const double right_x = b.x - c.x, right_y = b.y - c.y;
  const double positive = left_x * right_y;
  const double negative = left_y * right_x;
  const double determinant = positive - negative;
  const double bound = 8.0 * std::numeric_limits<double>::epsilon() *
                       (std::abs(positive) + std::abs(negative));
  if (determinant > bound) return 1;
  if (determinant < -bound) return -1;
  const long double exactish =
      (static_cast<long double>(a.x) - c.x) *
          (static_cast<long double>(b.y) - c.y) -
      (static_cast<long double>(a.y) - c.y) *
          (static_cast<long double>(b.x) - c.x);
  if (exactish == 0.0L) return 0;
  throw std::invalid_argument(
      "planar orientation is collinear or numerically unresolved");
}

CanonicalRing canonicalize_simple_ring(const std::vector<Point2> &input,
                                       std::size_t maximum_points) {
  if (input.size() < 3 || input.size() > maximum_points || maximum_points > 65536)
    throw std::invalid_argument("planar ring is outside the point budget");
  std::vector<Point2> points = input;
  for (std::size_t index = 0; index < points.size(); ++index) {
    if (!std::isfinite(points[index].x) || !std::isfinite(points[index].y) ||
        same(points[index], points[(index + 1) % points.size()]))
      throw std::invalid_argument("planar ring has invalid or duplicate coordinates");
    for (std::size_t other = index + 1; other < points.size(); ++other)
      if (same(points[index], points[other]))
        throw std::invalid_argument("planar ring repeats a vertex");
  }
  for (std::size_t index = 0; index < points.size(); ++index) {
    for (std::size_t other = index + 1; other < points.size(); ++other) {
      if (other == index + 1 || (index == 0 && other == points.size() - 1)) continue;
      if (segments_intersect(points[index], points[(index + 1) % points.size()],
                             points[other], points[(other + 1) % points.size()]))
        throw std::invalid_argument("planar ring is self-intersecting");
    }
  }
  const long double twice_area = area2(points);
  if (!std::isfinite(static_cast<double>(twice_area)) || twice_area == 0.0L)
    throw std::invalid_argument("planar ring has zero or invalid area");
  const bool reversed = twice_area < 0.0L;
  if (reversed) std::reverse(points.begin(), points.end());
  const auto start = std::min_element(points.begin(), points.end(),
      [](const Point2 &left, const Point2 &right) {
        return left.x < right.x || (left.x == right.x && left.y < right.y);
      });
  std::rotate(points.begin(), start, points.end());
  return {points, static_cast<double>(std::abs(twice_area) / 2.0L), reversed, true};
}

QuantizedPoint2 quantize_planar_point(const Point2 &point,
                                     double coordinate_grid_mm) {
  if (!std::isfinite(point.x) || !std::isfinite(point.y) ||
      coordinate_grid_mm != 0.000001)
    throw std::invalid_argument("planar v2 requires finite points on the fixed 1 nm grid");
  const auto convert = [coordinate_grid_mm](double value) {
    const double scaled = value / coordinate_grid_mm;
    const double rounded = std::nearbyint(scaled);
    if (!std::isfinite(scaled) || std::abs(rounded) > kMaximumGridCoordinate ||
        std::abs(scaled - rounded) > 1e-6)
      throw std::invalid_argument("planar coordinate is off-grid or outside the exact predicate range");
    return static_cast<std::int64_t>(rounded);
  };
  return {convert(point.x), convert(point.y)};
}

CanonicalQuantizedRing canonicalize_quantized_ring(
    const std::vector<Point2> &input, bool clockwise, double coordinate_grid_mm,
    std::size_t maximum_points) {
  if (input.size() < 3 || input.size() > maximum_points || maximum_points > 65536)
    throw std::invalid_argument("quantized planar ring is outside the point budget");
  std::vector<QuantizedPoint2> points;
  points.reserve(input.size());
  for (const auto &point : input) points.push_back(quantize_planar_point(point, coordinate_grid_mm));
  for (std::size_t i = 0; i < points.size(); ++i) {
    if (same(points[i], points[(i + 1) % points.size()]))
      throw std::invalid_argument("quantization collapsed a planar edge");
    for (std::size_t j = i + 1; j < points.size(); ++j)
      if (same(points[i], points[j])) throw std::invalid_argument("quantized ring repeats a vertex");
  }
  for (std::size_t i = 0; i < points.size(); ++i)
    for (std::size_t j = i + 1; j < points.size(); ++j) {
      if (j == i + 1 || (i == 0 && j == points.size() - 1)) continue;
      if (segments_intersect(points[i], points[(i + 1) % points.size()],
                             points[j], points[(j + 1) % points.size()]))
        throw std::invalid_argument("quantized ring is self-intersecting");
    }
  const std::int64_t twice_area = exact_quantized_twice_area(points);
  const bool is_clockwise = twice_area < 0.0L;
  const bool reversed = is_clockwise != clockwise;
  if (reversed) std::reverse(points.begin(), points.end());
  const auto start = std::min_element(points.begin(), points.end(),
      [](const auto &left, const auto &right) {
        return left.x < right.x || (left.x == right.x && left.y < right.y);
      });
  std::rotate(points.begin(), start, points.end());
  const double scale = coordinate_grid_mm;
  return {points, std::abs(static_cast<double>(twice_area)) * scale * scale / 2.0,
          reversed, true};
}

CanonicalPlanarRegion canonicalize_planar_region(
    const std::vector<Point2> &outer,
    const std::vector<std::vector<Point2>> &cutouts,
    double coordinate_grid_mm, std::size_t maximum_total_points) {
  if (cutouts.size() > 128 || maximum_total_points > 65536)
    throw std::invalid_argument("planar cutout or point budget exceeded");
  std::size_t total = outer.size();
  for (const auto &ring : cutouts) total += ring.size();
  if (total > maximum_total_points)
    throw std::invalid_argument("planar region total point budget exceeded");
  auto canonical_outer = canonicalize_quantized_ring(
      outer, false, coordinate_grid_mm, maximum_total_points);
  std::vector<CanonicalQuantizedRing> canonical_cutouts;
  for (const auto &cutout : cutouts) {
    auto ring = canonicalize_quantized_ring(cutout, true, coordinate_grid_mm,
                                            maximum_total_points);
    if (rings_intersect(canonical_outer.points, ring.points) ||
        !point_inside(ring.points.front(), canonical_outer.points))
      throw std::invalid_argument("planar cutout is not strictly inside the outer ring");
    for (const auto &prior : canonical_cutouts) {
      if (rings_intersect(prior.points, ring.points) ||
          point_inside(ring.points.front(), prior.points) ||
          point_inside(prior.points.front(), ring.points))
        throw std::invalid_argument("planar cutouts intersect, touch, or nest");
    }
    canonical_cutouts.push_back(std::move(ring));
  }
  std::sort(canonical_cutouts.begin(), canonical_cutouts.end(), [](const auto &a, const auto &b) {
    return std::tie(a.points.front().x, a.points.front().y) <
           std::tie(b.points.front().x, b.points.front().y);
  });
  double area = canonical_outer.area_mm2;
  for (const auto &cutout : canonical_cutouts) area -= cutout.area_mm2;
  if (!(area > 0.0) || !std::isfinite(area))
    throw std::invalid_argument("planar region has no positive copper area");
  return {canonical_outer, canonical_cutouts, area, coordinate_grid_mm, true};
}

SimplePlanarTriangulation triangulate_simple_planar_ring(
    const CanonicalQuantizedRing &ring, std::size_t maximum_points,
    std::size_t maximum_triangles, std::size_t maximum_work_steps) {
  const std::size_t count = ring.points.size();
  if (!ring.simple || count < 3 || count > maximum_points || maximum_points > 4096 ||
      count - 2 > maximum_triangles || maximum_triangles > 8192 ||
      maximum_work_steps == 0 || maximum_work_steps > 16777216)
    throw std::invalid_argument("simple triangulation input or resource policy is invalid");
  std::vector<Point2> reconstructed;
  reconstructed.reserve(count);
  for (const auto &point : ring.points)
    reconstructed.push_back({point.x * 0.000001, point.y * 0.000001});
  const auto admitted = canonicalize_quantized_ring(reconstructed, false, 0.000001, maximum_points);
  if (admitted.points.size() != ring.points.size())
    throw std::invalid_argument("simple triangulation ring is not canonical");
  for (std::size_t index = 0; index < count; ++index)
    if (!same(admitted.points[index], ring.points[index]))
      throw std::invalid_argument("simple triangulation ring is not canonical");
  if (exact_quantized_twice_area(ring.points) <= 0)
    throw std::invalid_argument("simple triangulation requires a canonical counter-clockwise ring");

  std::vector<std::uint32_t> active(count);
  for (std::uint32_t index = 0; index < count; ++index) active[index] = index;
  std::vector<QuantizedTriangle> triangles;
  std::size_t work_steps = 0;
  const auto consume = [&]() {
    if (++work_steps > maximum_work_steps)
      throw std::runtime_error("simple triangulation exceeded its deterministic work budget");
  };
  const auto in_triangle = [&](std::uint32_t point_index, std::uint32_t a,
                               std::uint32_t b, std::uint32_t c) {
    const auto &point = ring.points[point_index];
    return exact_quantized_orientation(ring.points[a], ring.points[b], point) >= 0 &&
           exact_quantized_orientation(ring.points[b], ring.points[c], point) >= 0 &&
           exact_quantized_orientation(ring.points[c], ring.points[a], point) >= 0;
  };
  while (active.size() > 3) {
    bool clipped = false;
    for (std::size_t position = 0; position < active.size(); ++position) {
      consume();
      const auto previous = active[(position + active.size() - 1) % active.size()];
      const auto current = active[position];
      const auto next = active[(position + 1) % active.size()];
      if (exact_quantized_orientation(ring.points[previous], ring.points[current],
                                      ring.points[next]) <= 0) continue;
      bool occupied = false;
      for (const auto candidate : active) {
        if (candidate == previous || candidate == current || candidate == next) continue;
        consume();
        if (in_triangle(candidate, previous, current, next)) {
          occupied = true;
          break;
        }
      }
      if (occupied) continue;
      triangles.push_back({previous, current, next});
      active.erase(active.begin() + static_cast<std::ptrdiff_t>(position));
      clipped = true;
      break;
    }
    if (!clipped)
      throw std::invalid_argument("simple exact ear triangulation could not make progress");
  }
  if (exact_quantized_orientation(ring.points[active[0]], ring.points[active[1]],
                                  ring.points[active[2]]) <= 0)
    throw std::invalid_argument("simple triangulation ended with a degenerate face");
  triangles.push_back({active[0], active[1], active[2]});

  for (auto &triangle : triangles) {
    const std::array<std::uint32_t, 3> values{triangle.a, triangle.b, triangle.c};
    const auto minimum = std::min_element(values.begin(), values.end());
    const auto offset = static_cast<std::size_t>(minimum - values.begin());
    triangle = {values[offset], values[(offset + 1) % 3], values[(offset + 2) % 3]};
  }
  std::sort(triangles.begin(), triangles.end(), [](const auto &left, const auto &right) {
    return std::tie(left.a, left.b, left.c) < std::tie(right.a, right.b, right.c);
  });
  for (std::size_t index = 1; index < triangles.size(); ++index)
    if (std::tie(triangles[index - 1].a, triangles[index - 1].b, triangles[index - 1].c) ==
        std::tie(triangles[index].a, triangles[index].b, triangles[index].c))
      throw std::logic_error("simple triangulation emitted duplicate triangles");

  using Edge = std::pair<std::uint32_t, std::uint32_t>;
  std::map<Edge, std::size_t> incidence;
  std::set<Edge> boundary;
  std::set<std::uint32_t> used;
  std::int64_t triangle_area = 0;
  for (const auto &triangle : triangles) {
    if (triangle.a >= count || triangle.b >= count || triangle.c >= count ||
        triangle.a == triangle.b || triangle.b == triangle.c || triangle.c == triangle.a)
      throw std::logic_error("simple triangulation emitted an invalid triangle");
    const std::array<std::uint32_t, 3> ids{triangle.a, triangle.b, triangle.c};
    const auto area = exact_quantized_twice_area(
        {ring.points[triangle.a], ring.points[triangle.b], ring.points[triangle.c]});
    if (area <= 0 || triangle_area > std::numeric_limits<std::int64_t>::max() - area)
      throw std::overflow_error("simple triangulation area audit overflow");
    triangle_area += area;
    used.insert(ids.begin(), ids.end());
    for (std::size_t edge = 0; edge < 3; ++edge) {
      auto first = ids[edge], second = ids[(edge + 1) % 3];
      if (second < first) std::swap(first, second);
      ++incidence[{first, second}];
    }
  }
  for (std::uint32_t index = 0; index < count; ++index) {
    auto first = index, second = static_cast<std::uint32_t>((index + 1) % count);
    if (second < first) std::swap(first, second);
    boundary.insert({first, second});
    if (incidence[{first, second}] != 1)
      throw std::logic_error("simple triangulation did not preserve a boundary constraint");
  }
  for (const auto &[edge, edge_count] : incidence)
    if ((boundary.contains(edge) && edge_count != 1) ||
        (!boundary.contains(edge) && edge_count != 2))
      throw std::logic_error("simple triangulation edge incidence is invalid");
  const auto source_area = exact_quantized_twice_area(ring.points);
  if (triangles.size() != count - 2 || used.size() != count || triangle_area != source_area)
    throw std::logic_error("simple triangulation failed exact coverage audit");
  return {ring.points, triangles, source_area, work_steps, true, true};
}

} // namespace spike::geometry
