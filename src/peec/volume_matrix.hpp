// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#pragma once

#include "volume_inductance.hpp"
#include "annular_inductance.hpp"

#include <Eigen/Core>
#include <cstddef>
#include <limits>
#include <string>
#include <variant>
#include <vector>

namespace spike::peec::volume {

struct CoaxialAnnulusVolume {
  Vector center_m{};
  Vector direction{0.0, 0.0, 1.0};
  double length_m = 0.0;
  double inner_radius_m = 0.0;
  double outer_radius_m = 0.0;
};

using VolumeBasis = std::variant<RectangularVolume, CoaxialAnnulusVolume>;

struct MatrixIntegrationOptions {
  IntegrationOptions pair{};
  AnnularIntegrationOptions annular_pair{};
  std::size_t maximum_matrix_pairs = 4096;
  std::size_t maximum_total_potential_evaluations = 100000000;
};

struct MatrixIntegrationResult {
  Eigen::MatrixXd inductance_h;
  Eigen::MatrixXd estimated_error_h;
  Eigen::MatrixXd reciprocity_difference_h;
  std::size_t potential_evaluations = 0;
  std::size_t pair_count = 0;
  bool converged = false;
  std::string failure_code;
  std::size_t failure_pair_i = std::numeric_limits<std::size_t>::max();
  std::size_t failure_pair_j = std::numeric_limits<std::size_t>::max();
};

// Ordered finite-volume matrix assembly. No PSD projection, diagonal shift, or
// unconverged-pair substitution is performed. Unsupported mixed geometry and
// resource exhaustion return converged=false with the first failing pair.
MatrixIntegrationResult assemble_inductance_matrix(
    const std::vector<VolumeBasis> &bases,
    const MatrixIntegrationOptions &options = {});

class VolumeMatrixAssembler {
public:
  explicit VolumeMatrixAssembler(MatrixIntegrationOptions options = {})
      : options_(options) {}
  void add_rectangular(const RectangularVolume &basis);
  void add_coaxial_annulus(const CoaxialAnnulusVolume &basis);
  std::size_t basis_count() const noexcept { return bases_.size(); }
  void clear() noexcept { bases_.clear(); }
  MatrixIntegrationResult compute_inductance() const;

private:
  MatrixIntegrationOptions options_;
  std::vector<VolumeBasis> bases_;
};

} // namespace spike::peec::volume
