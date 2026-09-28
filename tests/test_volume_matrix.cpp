// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "peec/volume_matrix.hpp"
#include <cmath>
#include <Eigen/Eigenvalues>
#include <stdexcept>

using namespace spike::peec::volume;
namespace {
void require(bool value, const char *message) { if (!value) throw std::runtime_error(message); }
RectangularVolume rectangle(double x=0) {
  RectangularVolume v; v.center_m={x,0,0}; v.length_m=2e-3;
  v.width_m=1e-3; v.thickness_m=0.5e-3; return v;
}
}
int main() {
  MatrixIntegrationOptions options; options.pair.max_potential_evaluations=1000000;
  VolumeMatrixAssembler matrix(options);
  matrix.add_rectangular(rectangle());
  matrix.add_rectangular(rectangle(0.5e-3)); // Marble-style overlapping bases.
  const auto overlap=matrix.compute_inductance();
  require(overlap.converged && overlap.inductance_h.rows()==2,"overlap matrix");
  require(overlap.inductance_h.isApprox(overlap.inductance_h.transpose(),1e-20),"symmetry");
  Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> eig(overlap.inductance_h);
  require(eig.eigenvalues().minCoeff()>=-1e-20,"overlap energy");
  MatrixIntegrationOptions capped; capped.maximum_matrix_pairs=2;
  require(!assemble_inductance_matrix({rectangle(),rectangle()},capped).converged,"pair cap");
  CoaxialAnnulusVolume annulus; annulus.length_m=1e-3;
  annulus.inner_radius_m=0.15e-3; annulus.outer_radius_m=0.175e-3;
  auto perpendicular_rectangle=rectangle(); perpendicular_rectangle.direction={1,0,0};
  require(assemble_inductance_matrix({perpendicular_rectangle,annulus},options).converged,
          "perpendicular mixed pair is exactly zero");
  const auto annular=assemble_inductance_matrix({annulus},options);
  require(annular.converged && annular.inductance_h(0,0)>0,"annular self");
  auto orthogonal=annulus;orthogonal.direction={1,0,0};
  const auto zero=assemble_inductance_matrix({annulus,orthogonal},options);
  require(zero.converged&&zero.inductance_h(0,1)==0&&zero.estimated_error_h(0,1)==0,
          "exact perpendicular overlapping annuli");
  auto distant=annulus;distant.center_m={.020,0,0};
  const auto far=assemble_inductance_matrix({annulus,distant},options);
  require(far.converged&&far.inductance_h(0,1)>0,"bounded noncoaxial annuli");
  Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> far_eigen(far.inductance_h);
  require(far_eigen.eigenvalues().minCoeff()>0,"far annuli energy");
  auto close_annulus=annulus;close_annulus.center_m={.4e-3,0,0};
  const auto unsupported=assemble_inductance_matrix({annulus,close_annulus},options);
  require(!unsupported.converged&&unsupported.failure_code=="VOLUME_MATRIX_NONCOAXIAL_ANNULI",
          "close noncoaxial annuli remain unsupported");
  // Both geometries passed the former absolute 1 pm offset and dot-product
  // angular tolerances, incorrectly using the singular coaxial integral.
  auto offset=annulus;offset.center_m={5e-13,0,0};
  auto skew=annulus;skew.direction={1e-6,0,std::sqrt(1-1e-12)};
  for(const auto &almost: {offset,skew}) {
    const auto rejected=assemble_inductance_matrix({annulus,almost},options);
    require(!rejected.converged&&rejected.failure_code=="VOLUME_MATRIX_NONCOAXIAL_ANNULI",
            "genuinely offset/skew overlapping annuli were treated as coaxial");
  }
  auto small=annulus;small.length_m*=1e-6;small.inner_radius_m*=1e-6;
  small.outer_radius_m*=1e-6;
  auto small_offset=small;small_offset.center_m={5e-19,0,0};
  const auto small_rejected=assemble_inductance_matrix({small,small_offset},options);
  require(!small_rejected.converged&&small_rejected.failure_code=="VOLUME_MATRIX_NONCOAXIAL_ANNULI",
          "coaxial admission must scale with geometry");
  auto rotated=annulus;rotated.direction={.6,.8,0};
  auto rotated_adjacent=rotated;rotated_adjacent.center_m={.6e-3,.8e-3,0};
  require(assemble_inductance_matrix({rotated,rotated_adjacent},options).converged,
          "arithmetic-precision rotated coaxial pair rejected");
  MatrixIntegrationOptions work_limited=options;
  work_limited.maximum_total_potential_evaluations=1;
  require(!assemble_inductance_matrix({rectangle()},work_limited).converged,
          "total work cap");
}
