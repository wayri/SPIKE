// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#include "volume_matrix.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace spike::peec::volume {
namespace {
double dot(const Vector &a, const Vector &b) {
  return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}
bool perpendicular(const Vector &a, const Vector &b) {
  return std::abs(dot(a, b)) <= 1e-15;
}
double norm2(const Vector &a) { return dot(a,a); }
Vector subtract(const Vector &a,const Vector &b) {
  return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};
}
bool unit(const Vector &a) { return std::abs(norm2(a)-1.0)<=1e-10; }
bool finite_vector(const Vector &a) {
  return std::isfinite(a[0])&&std::isfinite(a[1])&&std::isfinite(a[2]);
}
bool valid(const RectangularVolume &a) {
  return finite_vector(a.center_m)&&unit(a.direction)&&unit(a.width_axis)&&
      std::abs(dot(a.direction,a.width_axis))<=1e-10&&
      std::isfinite(a.length_m)&&a.length_m>0&&std::isfinite(a.width_m)&&a.width_m>0&&
      std::isfinite(a.thickness_m)&&a.thickness_m>0;
}
bool valid(const CoaxialAnnulusVolume &a) {
  return finite_vector(a.center_m)&&unit(a.direction)&&std::isfinite(a.length_m)&&a.length_m>0&&
      std::isfinite(a.inner_radius_m)&&a.inner_radius_m>0&&
      std::isfinite(a.outer_radius_m)&&a.outer_radius_m>a.inner_radius_m;
}
void fail(MatrixIntegrationResult &result, std::size_t i, std::size_t j,
          const char *code) {
  result.failure_pair_i = i;
  result.failure_pair_j = j;
  result.failure_code = code;
}
} // namespace

MatrixIntegrationResult assemble_inductance_matrix(
    const std::vector<VolumeBasis> &bases,
    const MatrixIntegrationOptions &options) {
  MatrixIntegrationResult result;
  const std::size_t n = bases.size();
  if (n == 0) {
    result.failure_code = "VOLUME_MATRIX_EMPTY";
    return result;
  }
  if (options.maximum_total_potential_evaluations == 0) {
    result.failure_code = "VOLUME_MATRIX_TOTAL_WORK_LIMIT";
    return result;
  }
  if (n > std::numeric_limits<std::size_t>::max() / (n + 1) ||
      n * (n + 1) / 2 > options.maximum_matrix_pairs) {
    result.failure_code = "VOLUME_MATRIX_PAIR_LIMIT";
    return result;
  }
  result.inductance_h = Eigen::MatrixXd::Zero(n, n);
  result.estimated_error_h = Eigen::MatrixXd::Zero(n, n);
  result.reciprocity_difference_h = Eigen::MatrixXd::Zero(n, n);
  for (std::size_t i = 0; i < n; ++i) {
    for (std::size_t j = 0; j <= i; ++j) {
      ++result.pair_count;
      try {
      if (const auto *a = std::get_if<RectangularVolume>(&bases[i])) {
        if(!valid(*a)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
        if (const auto *b = std::get_if<RectangularVolume>(&bases[j])) {
          if(!valid(*b)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
          auto pair_options=options.pair;
          pair_options.max_potential_evaluations=std::min(
              pair_options.max_potential_evaluations,
              options.maximum_total_potential_evaluations-result.potential_evaluations);
          const auto pair = rectangular_inductance(*a, *b, pair_options);
          result.potential_evaluations += pair.potential_evaluations;
          if (result.potential_evaluations > options.maximum_total_potential_evaluations) {
            fail(result, i, j, "VOLUME_MATRIX_TOTAL_WORK_LIMIT"); return result;
          }
          if (!pair.converged) {
            fail(result, i, j, "VOLUME_MATRIX_PAIR_NOT_CONVERGED");
            return result;
          }
          result.inductance_h(i,j)=result.inductance_h(j,i)=pair.inductance_h;
          result.estimated_error_h(i,j)=result.estimated_error_h(j,i)=pair.estimated_error_h;
          result.reciprocity_difference_h(i,j)=result.reciprocity_difference_h(j,i)=pair.reciprocity_difference_h;
          continue;
        }
        const auto &b = std::get<CoaxialAnnulusVolume>(bases[j]);
        if(!valid(b)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
        if (perpendicular(a->direction, b.direction)) continue;
        fail(result, i, j, "VOLUME_MATRIX_RECT_ANNULUS_UNSUPPORTED");
        return result;
      }
      const auto &a = std::get<CoaxialAnnulusVolume>(bases[i]);
      if(!valid(a)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
      if (const auto *b = std::get_if<RectangularVolume>(&bases[j])) {
        if(!valid(*b)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
        if (perpendicular(a.direction, b->direction)) continue;
        fail(result, i, j, "VOLUME_MATRIX_RECT_ANNULUS_UNSUPPORTED");
        return result;
      }
      const auto &b=std::get<CoaxialAnnulusVolume>(bases[j]);
      if(!valid(b)){fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;}
      if (!unit(a.direction)||!unit(b.direction)) {
        fail(result,i,j,"VOLUME_MATRIX_INVALID_ANNULUS_AXIS");return result;
      }
      const double alignment=dot(a.direction,b.direction);
      if (std::abs(std::abs(alignment)-1.0)>1e-10) {
        fail(result,i,j,"VOLUME_MATRIX_NONCOAXIAL_ANNULI");return result;
      }
      const auto delta=subtract(b.center_m,a.center_m);
      const double axial=dot(delta,a.direction);
      const Vector transverse={delta[0]-axial*a.direction[0],
          delta[1]-axial*a.direction[1],delta[2]-axial*a.direction[2]};
      if (norm2(transverse)>1e-24) {
        fail(result,i,j,"VOLUME_MATRIX_NONCOAXIAL_ANNULI");return result;
      }
      CoaxialAnnulus first{-a.length_m/2,a.length_m/2,
                            a.inner_radius_m,a.outer_radius_m};
      const double signed_length=alignment*b.length_m;
      CoaxialAnnulus second{axial-signed_length/2,axial+signed_length/2,
                             b.inner_radius_m,b.outer_radius_m};
      auto pair_options=options.annular_pair;
      pair_options.max_evaluations=std::min(pair_options.max_evaluations,
          options.maximum_total_potential_evaluations-result.potential_evaluations);
      const auto pair=coaxial_annular_inductance(first,second,pair_options);
      result.potential_evaluations+=pair.evaluations;
      if (result.potential_evaluations>options.maximum_total_potential_evaluations) {
        fail(result,i,j,"VOLUME_MATRIX_TOTAL_WORK_LIMIT");return result;
      }
      if(!pair.converged) {fail(result,i,j,"VOLUME_MATRIX_PAIR_NOT_CONVERGED");return result;}
      result.inductance_h(i,j)=result.inductance_h(j,i)=pair.inductance_h;
      result.estimated_error_h(i,j)=result.estimated_error_h(j,i)=pair.estimated_error_h;
      continue;
      } catch (const std::invalid_argument &) {
        fail(result,i,j,"VOLUME_MATRIX_INVALID_BASIS");return result;
      }
    }
  }
  result.converged = true;
  return result;
}

void VolumeMatrixAssembler::add_rectangular(const RectangularVolume &basis) {
  bases_.emplace_back(basis);
}
void VolumeMatrixAssembler::add_coaxial_annulus(const CoaxialAnnulusVolume &basis) {
  bases_.emplace_back(basis);
}
MatrixIntegrationResult VolumeMatrixAssembler::compute_inductance() const {
  return assemble_inductance_matrix(bases_, options_);
}
} // namespace spike::peec::volume
