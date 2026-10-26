// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <cstddef>
#include "volume_inductance.hpp"

namespace spike::peec::volume {

struct CoaxialAnnulusVolume {
  Vector center_m{};
  Vector direction{0.0, 0.0, 1.0};
  double length_m = 0.0;
  double inner_radius_m = 0.0;
  double outer_radius_m = 0.0;
};

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
  // Coaxial: adaptive rule difference plus roundoff indicator. Separated:
  // analytic truncation bound plus roundoff allowance. Neither is a
  // machine-certified floating-point error enclosure.
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

// Bounded far-field slice for finite annuli with arbitrary straight axes.
// Integrates the Legendre expansion through degree four using exact volume
// moments. The omitted series has an analytic bound; estimated_error_h also
// includes a conservative floating-point allowance (not interval arithmetic).
// Requires enclosing-sphere ratio <= 1/4 and the full error <= tolerance.
// Closer pairs, tight unattainable tolerances and work exhaustion fail closed.
AnnularIntegrationResult separated_annular_inductance(
    const CoaxialAnnulusVolume &first, const CoaxialAnnulusVolume &second,
    const AnnularIntegrationOptions &options = {});

} // namespace spike::peec::volume
