// SPDX-License-Identifier: MIT
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
  MatrixIntegrationOptions work_limited=options;
  work_limited.maximum_total_potential_evaluations=1;
  require(!assemble_inductance_matrix({rectangle()},work_limited).converged,
          "total work cap");
}
