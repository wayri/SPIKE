// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <array>
#include <cstddef>

namespace spike::peec::volume {

using Vector = std::array<double, 3>;

// Experimental uniform-volume current basis. All positions/dimensions use SI.
// direction and width_axis are orthonormal; thickness follows their cross product.
// Current density per ampere is direction / (width_m * thickness_m).
struct RectangularVolume {
  Vector center_m{};
  Vector direction{1.0, 0.0, 0.0};
  Vector width_axis{0.0, 1.0, 0.0};
  double length_m = 0.0;
  double width_m = 0.0;
  double thickness_m = 0.0;
};

struct IntegrationOptions {
  double relative_tolerance = 1e-6;
  double absolute_tolerance_h = 1e-17;
  std::size_t max_potential_evaluations = 500000;
  std::size_t max_cells = 2048;
  double permeability_h_per_m = 1.2566370614359172954e-6;
};

struct IntegrationResult {
  double inductance_h = 0.0;
  // A posteriori quadrature/roundoff estimate, NOT a certified error bound.
  double estimated_error_h = 0.0;
  double reciprocity_difference_h = 0.0;
  std::size_t potential_evaluations = 0;
  bool converged = false;
};

// Same finite-volume Coulomb integral for self, mutual, touching and overlapping
// rectangular bases. No line approximation, singular-point skipping, diagonal
// shift, or PSD projection. A converged quadrature estimate does not certify a
// whole matrix: the caller must retain energy/passivity and refinement checks.
// Throws invalid_argument for malformed input. Resource exhaustion returns
// converged=false and must not be treated as a usable production result.
IntegrationResult rectangular_inductance(
    const RectangularVolume &first, const RectangularVolume &second,
    const IntegrationOptions &options = {});

} // namespace spike::peec::volume
