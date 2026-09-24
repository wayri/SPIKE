// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#include "peec/sparse_magnetic_energy.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace spike::peec::spectral;
namespace {
const double pi=std::acos(-1.0);
void require(bool condition,const char *message) {
  if(!condition)throw std::runtime_error(message);
}
bool close(double a,double b,double relative,double absolute=1e-24) {
  return std::abs(a-b)<=absolute+relative*std::max(std::abs(a),std::abs(b));
}
RectangularVolume cube() {
  RectangularVolume b;b.length_m=b.width_m=b.thickness_m=1e-3;return b;
}
StraightAnnularVolume annulus() {
  StraightAnnularVolume b;b.direction={1,0,0};b.length_m=1e-3;
  b.inner_radius_m=0.2e-3;b.outer_radius_m=0.3e-3;return b;
}
Options small() {
  Options o;o.radial_cutoff_per_m=12000;o.radial_panels=64;
  o.polar_order=20;o.azimuthal_panels=40;return o;
}
Result evaluate(const std::vector<Basis> &b,const std::vector<double> &i,
    const Options &o=small()) {
  auto r=prescribed_current_energy(b,i,o);
  require(r.evaluated,"Spectral evaluation failed");
  require(!r.finite_domain_quadrature_certified,"False quadrature certification");
  require(r.finite_domain_energy_j>=0,"Negative Gram energy");
  return r;
}
void transforms() {
  auto b=cube();const auto zero=fourier_basis(b,{0,0,0});
  require(close(zero[0].real(),b.length_m,1e-14)&&zero[1]==0.0&&zero[2]==0.0,"Rectangle zero mode");
  require(std::abs(fourier_basis(b,{2*pi/b.length_m,0,0})[0])<1e-18,"Rectangle sinc zero");
  const Vector k={800,500,-1200};const auto original=fourier_basis(b,k);
  b.center_m={0.003,-0.002,0.001};const auto shifted=fourier_basis(b,k);
  const std::complex<double> phase=std::polar(1.0,-(k[0]*b.center_m[0]+k[1]*b.center_m[1]+k[2]*b.center_m[2]));
  require(std::abs(shifted[0]-original[0]*phase)<1e-17,"Translation phase");
  b=cube();auto left=b,right=b;left.length_m=right.length_m=0.5e-3;
  left.center_m[0]=-0.25e-3;right.center_m[0]=0.25e-3;
  require(std::abs(fourier_basis(left,k)[0]+fourier_basis(right,k)[0]-original[0])<1e-17,"Touching rectangle partition");
  // Cyclic rotation is exact and does not require a numerical rotation oracle.
  auto rotated=b;rotated.direction={0,1,0};rotated.width_axis={0,0,1};
  require(std::abs(fourier_basis(rotated,{k[2],k[0],k[1]})[1]-original[0])<1e-17,"Rectangular rotation covariance");
  auto a=annulus();
  require(close(fourier_basis(a,{0,0,0})[0].real(),a.length_m,1e-14),"Annulus zero mode");
  // Independent spatial oracle: uniform midpoint sampling in r^2 and angle,
  // with analytic longitudinal sinc. No Bessel evaluation in the oracle.
  for(const double q:{1.0,1000.0,5000.0,15000.0}) {
    double sum=0;const int nr=512,nt=512;
    for(int ir=0;ir<nr;++ir) {
      const double r=std::sqrt(a.inner_radius_m*a.inner_radius_m+
          (ir+0.5)/nr*(a.outer_radius_m*a.outer_radius_m-a.inner_radius_m*a.inner_radius_m));
      for(int it=0;it<nt;++it)sum+=std::cos(q*r*std::cos(2*pi*(it+0.5)/nt));
    }
    const double expected=a.length_m*sum/(nr*nt);
    require(close(fourier_basis(a,{0,q,0})[0].real(),expected,2e-6,1e-12),"Annulus spatial transform oracle");
  }
  a.inner_radius_m=a.outer_radius_m*(1-1e-10);
  const auto thin=fourier_basis(a,{0,10,0});
  require(std::isfinite(thin[0].real())&&std::abs(thin[0].real())<=a.length_m,"Thin-wall small-wavevector stability");
  a=annulus();auto turned=a;turned.direction={0,1,0};
  require(std::abs(fourier_basis(a,k)[0]-fourier_basis(turned,{k[2],k[0],k[1]})[1])<1e-17,"Annular rotation covariance");
}
void cube_energy_and_tail() {
  // Independent real-space cube oracle from the Duffy-difference integral in
  // test_volume_inductance.cpp: L=1.8823126443896598e-10 H for a 1mm cube.
  const double exact=0.5*1.8823126443896598e-10;
  auto o=small();o.radial_cutoff_per_m=20000;o.radial_panels=160;
  o.polar_order=48;o.azimuthal_panels=96;
  const auto fine=evaluate({cube()},{1},o);
  o.radial_panels/=2;o.polar_order/=2;o.azimuthal_panels/=2;
  const auto coarse=evaluate({cube()},{1},o);
  const double drift=std::abs(fine.finite_domain_energy_j-coarse.finite_domain_energy_j);
  require(drift<2e-13,"Cube finite-domain quadrature refinement");
  require(std::abs(exact-fine.finite_domain_energy_j)<fine.radial_tail_bound_j+2e-13,"Cube reference versus tail and refinement");
  require(close(fine.radial_tail_bound_j,o.permeability_h_per_m*1000/(2*20000.0*20000),1e-14),"Parseval cube tail normalization");
  auto larger=cube();larger.length_m*=2;larger.width_m*=2;larger.thickness_m*=2;
  const auto base=evaluate({cube()},{1});auto scaled=small();scaled.radial_cutoff_per_m/=2;
  const auto twice=evaluate({larger},{1},scaled);
  require(close(twice.finite_domain_energy_j,2*base.finite_domain_energy_j,1e-13),"SI linear energy scaling");
  require(close(twice.radial_tail_bound_j,2*base.radial_tail_bound_j,1e-13),"SI tail scaling");
  require(close(evaluate({cube()},{3}).finite_domain_energy_j,9*base.finite_domain_energy_j,1e-13),"Quadratic current scaling");
  std::cout<<"cube W="<<fine.finite_domain_energy_j<<" J, exact="<<exact
      <<", radial tail bound="<<fine.radial_tail_bound_j<<", refinement drift="<<drift<<'\n';
}
// Independently integrate a separated rectangle/annulus pair in real space.
// Both currents are along x. Sample cylinder area uniformly using r^2. This
// deliberately slow reference has no singularity and no Fourier/Bessel calls.
double mixed_mutual_reference(int order) {
  const auto b=cube();auto a=annulus();a.center_m[1]=3e-3;
  double sum=0;const int angles=2*order;
  for(int x=0;x<order;++x)for(int y=0;y<order;++y)for(int z=0;z<order;++z) {
    const Vector p={b.length_m*((x+0.5)/order-0.5),b.width_m*((y+0.5)/order-0.5),b.thickness_m*((z+0.5)/order-0.5)};
    for(int l=0;l<order;++l)for(int r=0;r<order;++r)for(int t=0;t<angles;++t) {
      const double radius=std::sqrt(a.inner_radius_m*a.inner_radius_m+
          (r+0.5)/order*(a.outer_radius_m*a.outer_radius_m-a.inner_radius_m*a.inner_radius_m));
      const Vector q={a.length_m*((l+0.5)/order-0.5),a.center_m[1]+radius*std::cos(2*pi*(t+0.5)/angles),radius*std::sin(2*pi*(t+0.5)/angles)};
      sum+=1/std::sqrt((p[0]-q[0])*(p[0]-q[0])+(p[1]-q[1])*(p[1]-q[1])+(p[2]-q[2])*(p[2]-q[2]));
    }
  }
  return 1e-7*b.length_m*a.length_m*sum/(std::pow(double(order),5)*angles);
}
void mixed_and_gram() {
  auto b=cube();auto a=annulus();a.center_m[1]=3e-3;
  auto o=small();o.radial_cutoff_per_m=20000;o.radial_panels=160;o.polar_order=48;o.azimuthal_panels=96;
  const auto plus=evaluate({b,a},{1,1},o),minus=evaluate({b,a},{1,-1},o);
  const double mutual=(plus.finite_domain_energy_j-minus.finite_domain_energy_j)/2;
  const double reference=mixed_mutual_reference(12),coarse=mixed_mutual_reference(8);
  require(close(reference,coarse,2e-4),"Mixed real-space reference refinement");
  require(close(mutual,reference,0.025),"Mixed noncoaxial real-space mutual oracle");
  const auto reversed=evaluate({a,b},{1,1},o);
  require(close(plus.finite_domain_energy_j,reversed.finite_domain_energy_j,1e-14),"Mixed reciprocity");
  // Common positive-weight quadrature is a Gram form. Reconstruct its small
  // 3x3 matrix by polarization, check symmetry/Cauchy-Schwarz and all 27
  // {-1,0,1} current vectors against direct nonnegative energy.
  auto c=annulus();c.center_m={0,0.7e-3,0.5e-3};c.direction={0.6,0.8,0};
  const std::vector<Basis> bases={b,a,c};
  double matrix[3][3]{};
  for(int i=0;i<3;++i) {
    std::vector<double> currents(3);currents[i]=1;
    matrix[i][i]=2*evaluate(bases,currents).finite_domain_energy_j;
  }
  for(int i=0;i<3;++i)for(int j=0;j<i;++j) {
    std::vector<double> currents(3);currents[i]=currents[j]=1;
    matrix[i][j]=matrix[j][i]=evaluate(bases,currents).finite_domain_energy_j-
        (matrix[i][i]+matrix[j][j])/2;
    require(matrix[i][j]*matrix[i][j]<=matrix[i][i]*matrix[j][j]+1e-35,"Gram Cauchy-Schwarz");
  }
  for(int x=-1;x<=1;++x)for(int y=-1;y<=1;++y)for(int z=-1;z<=1;++z) {
    const std::vector<double> currents={double(x),double(y),double(z)};double quadratic=0;
    for(int i=0;i<3;++i)for(int j=0;j<3;++j)quadratic+=currents[i]*matrix[i][j]*currents[j]/2;
    const auto direct=evaluate(bases,currents);
    require(quadratic>=-1e-24&&close(quadratic,direct.finite_domain_energy_j,1e-12),"PSD quadratic/direct energy");
  }
  const auto cancellation=evaluate({b,b},{1,-1});
  require(cancellation.finite_domain_energy_j==0,"Duplicate opposite currents cancel");
  require(cancellation.radial_tail_bound_j>0,"Overlap-safe norm bound must not assume disjointness");
  auto opposite=b;opposite.direction={-1,0,0};
  require(evaluate({b,opposite},{1,1}).finite_domain_energy_j==0,"Reversed basis cancellation");
  auto left=b,right=b;left.length_m=right.length_m=b.length_m/2;
  left.center_m[0]=-b.length_m/4;right.center_m[0]=b.length_m/4;
  require(close(evaluate({left,right},{1,1}).finite_domain_energy_j,
      evaluate({b},{1}).finite_domain_energy_j,1e-13),"Touching partition energy");
  std::cout<<"mixed M="<<mutual<<" H, spatial reference="<<reference<<'\n';
}
void failures() {
  auto o=small();o.maximum_nodes=1;
  require(prescribed_current_energy({cube()},{1},o).failure_code=="SPECTRAL_NODE_LIMIT","Node cap");
  o=small();o.maximum_feature_evaluations=1;
  require(prescribed_current_energy({cube()},{1},o).failure_code=="SPECTRAL_WORK_LIMIT","Work cap");
  o=small();o.radial_panels=std::numeric_limits<std::size_t>::max();
  require(!prescribed_current_energy({cube()},{1},o).evaluated,"Overflow-safe node cap");
  o=small();o.radial_cutoff_per_m=std::numeric_limits<double>::max();
  require(prescribed_current_energy({cube()},{1},o).failure_code=="SPECTRAL_DYNAMIC_RANGE","Tail underflow rejected");
  int rejected=0;
  try {prescribed_current_energy({cube()},{std::numeric_limits<double>::quiet_NaN()});}catch(const std::invalid_argument &){++rejected;}
  try {auto b=cube();b.width_axis=b.direction;fourier_basis(b,{0,0,0});}catch(const std::invalid_argument &){++rejected;}
  try {auto a=annulus();a.inner_radius_m=a.outer_radius_m;fourier_basis(a,{0,0,0});}catch(const std::invalid_argument &){++rejected;}
  try {prescribed_current_energy({cube()},{1,2});}catch(const std::invalid_argument &){++rejected;}
  require(rejected==4,"Malformed spectral inputs rejected");
}
}
int main() {
  try {transforms();cube_energy_and_tail();mixed_and_gram();failures();}
  catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
  std::cout<<"Experimental spectral energy checks passed; finite-domain quadrature remains uncertified.\n";
}
