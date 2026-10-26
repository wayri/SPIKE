// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <array>
#include <cstddef>

namespace spike::peec::affine {

using Point = std::array<double, 2>;
using Vector = std::array<double, 3>;

// Experimental, isolated verification interface; not bound to the extractor.
// SI coordinates, CCW planar vertices, positive z thickness. The current
// density per ampere (1/m^2) is barycentric interpolation of the three vertex
// vectors, constant in z. This is exactly an affine planar vector field.
struct TrianglePrism {
  std::array<Point, 3> vertices_m{};
  double lower_z_m = 0;
  double upper_z_m = 0;
  std::array<Vector, 3> density_per_a{};
};

// b = sign * (r - opposite_vertex)/(2*A*t), sign must be +/-1.
TrianglePrism unit_face_basis(const std::array<Point, 3>& vertices_m,
                             double lower_z_m, double upper_z_m,
                             std::size_t opposite_vertex, int sign = 1);

// Exact polynomial moments, subject to floating-point roundoff. The selected
// side is opposite the indexed vertex; positive flux points out of the prism.
double side_flux(const TrianglePrism& piece, std::size_t opposite_vertex);
Vector integrated_current(const TrianglePrism& piece); // metres

// Integral b_i dot b_j / sigma in ohms. Supports identical ordered prisms
// ONLY; it does not approximate a polygon overlap or assemble multiple pieces.
double local_resistance(const TrianglePrism& first, const TrianglePrism& second,
                        double conductivity_s_per_m);

enum class MutualStatus { converged, resource_limit, unsupported_separation };
struct MutualOptions {
  double absolute_tolerance_h = 1e-17;
  double relative_tolerance = 1e-3;
  double permeability_h_per_m = 1.2566370614359172954e-6;
  std::size_t max_pair_evaluations = 32767;
  std::size_t max_cells = 16384;
};
struct MutualResult {
  double inductance_h = 0;
  // Conservative analytic discretization bound plus roundoff INDICATOR;
  // floating-point operations are not outward-rounded interval arithmetic.
  double error_bound_estimate_h = 0;
  std::size_t pair_evaluations = 0;
  MutualStatus status = MutualStatus::unsupported_separation;
};

// Finite-volume Coulomb mutual integral of these same affine current fields.
// Admits only prisms whose axis-aligned boxes have strictly positive distance.
// Self/touching/overlapping boxes explicitly return unsupported_separation,
// never an inferred zero. No singular quadrature, annuli, matrix assembly,
// passivity repair, contact model, or board convergence is implemented here.
// Invalid/ill-conditioned input throws; exhausted budgets return resource_limit.
MutualResult separated_mutual(const TrianglePrism& first,
                             const TrianglePrism& second,
                             const MutualOptions& options = {});

// Experimental all-pair extension, including self, touching and overlapping
// supports. Integrable singular cells use analytic finite potential envelopes,
// never a sampled singularity or softening length. Adaptive subdivision is
// convergent in exact arithmetic; practical tolerances can exhaust the caps.
// Admission covers integration only, not mesh, contact or physical validity.
MutualResult mutual(const TrianglePrism& first, const TrianglePrism& second,
                    const MutualOptions& options = {});

} // namespace spike::peec::affine
