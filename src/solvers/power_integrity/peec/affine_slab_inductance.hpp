// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "affine_triangle_basis.hpp"

namespace spike::peec::affine {

struct SlabOptions {
  double absolute_tolerance_h = 1e-17;
  double relative_tolerance = 1e-6;
  double permeability_h_per_m = 1.2566370614359172954e-6;
  std::size_t maximum_evaluations = 500000;
  std::size_t maximum_cells = 4096;
};

struct SlabResult {
  double inductance_h = 0;
  // A posteriori cubature/roundoff estimate, NOT a conservative bound.
  double estimated_error_h = 0;
  std::size_t evaluations = 0;
  std::size_t displacement_regions = 0;
  bool converged = false;
};

// Isolated experimental candidate, not registered/bound to board extraction.
// Integrates the SAME supplied affine volume fields without support clipping
// or magnetic-only width changes. Both prisms must have identical z intervals.
// Analytic thickness integration and displacement-overlap polynomial moments
// reduce self, touching, overlapping and separated terms to 2D cubature.
// Quadrature estimates do not establish passivity or physical accuracy; retain
// independent energy, support, contact and mesh/integration refinement gates.
// Invalid/unsupported input throws; resource exhaustion returns converged=false.
SlabResult same_slab_mutual(const TrianglePrism& first,
                           const TrianglePrism& second,
                           const SlabOptions& options = {});

} // namespace spike::peec::affine
