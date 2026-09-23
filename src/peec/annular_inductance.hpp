// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <cstddef>

namespace spike::peec::volume {

// Uniform axial volume current density, 1 / annular area amperes per square
// metre per branch ampere. Both operands MUST refer to the same straight axis
// and coordinate origin. Reversing endpoints reverses the current direction.
// This deliberately does not represent noncoaxial barrels or skin effect.
struct CoaxialAnnulus {
  double start_m = 0.0;
  double end_m = 0.0;
  double inner_radius_m = 0.0;
  double outer_radius_m = 0.0;
};

struct AnnularIntegrationOptions {
  double relative_tolerance = 1e-6;
  double absolute_tolerance_h = 1e-17;
  std::size_t max_evaluations = 2000000;
  std::size_t max_cells = 4096;
  double permeability_h_per_m = 1.2566370614359172954e-6;
};

struct AnnularIntegrationResult {
  double inductance_h = 0.0;
  // Adaptive rule difference plus roundoff indicator; NOT a certified bound.
  double estimated_error_h = 0.0;
  std::size_t evaluations = 0;
  bool converged = false;
};

// Same finite-volume integral for self, mutual, touching and overlapping
// coaxial annuli. No eigenvalue editing, diagonal repair or line self formula.
// Malformed input throws invalid_argument; resource exhaustion fails closed.
AnnularIntegrationResult coaxial_annular_inductance(
    const CoaxialAnnulus &first, const CoaxialAnnulus &second,
    const AnnularIntegrationOptions &options = {});

} // namespace spike::peec::volume
