// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "peec/volume_inductance.hpp"
#include <Eigen/Eigenvalues>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

using namespace spike::peec::volume;
namespace {
void require(bool condition,const char *message) {
  if(!condition) throw std::runtime_error(message);
}
bool close(double actual,double expected,double relative) {
  return std::abs(actual-expected)<=relative*std::abs(expected);
}
RectangularVolume box(double l=1e-3,double w=1e-3,double t=1e-3) {
  RectangularVolume b;b.length_m=l;b.width_m=w;b.thickness_m=t;return b;
}
double evaluated(const RectangularVolume &a,const RectangularVolume &b,
                 IntegrationOptions options={}) {
  const auto r=rectangular_inductance(a,b,options);
  std::cout<<std::setprecision(14)<<"L="<<r.inductance_h<<" error="
      <<r.estimated_error_h<<" evaluations="<<r.potential_evaluations
      <<" converged="<<r.converged<<std::endl;
  require(r.converged,"Volume integration did not converge");
  return r.inductance_h;
}
// Independent reference: transform the six-dimensional self integral to the
// difference box, then split its unit cube into three Duffy pyramids. Integrate
// the radial polynomial exactly: Q(s,t)=1/6-(s+t)/12+st/20. No prism potential
// or production quadrature is reused. The cube oracle also has a fixed value.
std::vector<std::pair<long double,long double>> gauss(int n) {
  std::vector<std::pair<long double,long double>> rule(n);
  for(int i=0;i<(n+1)/2;++i) {
    long double x=std::cos(std::acos(-1.0L)*(i+0.75L)/(n+0.5L)),derivative=0;
    for(int iteration=0;iteration<30;++iteration) {
      long double p=1,previous=0;
      for(int k=1;k<=n;++k) {
        const long double next=((2*k-1)*x*p-(k-1)*previous)/k;
        previous=p;p=next;
      }
      derivative=n*(x*p-previous)/(x*x-1);
      const long double change=p/derivative;x-=change;
      if(std::abs(change)<1e-19L)break;
    }
    const long double weight=1/((1-x*x)*derivative*derivative);
    rule[i]={(1-x)/2,weight};rule[n-1-i]={(1+x)/2,weight};
  }
  return rule;
}
double self_reference(const RectangularVolume &b,int order=160) {
  const auto rule=gauss(order);long double sum=0;
  const long double a=b.length_m,w=b.width_m,t=b.thickness_m;
  for(const auto &[s,ws]:rule)for(const auto &[u,wu]:rule) {
    const long double q=1.0L/6-(s+u)/12+s*u/20;
    sum+=ws*wu*q*(1/std::sqrt(a*a+w*w*s*s+t*t*u*u)+
        1/std::sqrt(w*w+a*a*s*s+t*t*u*u)+
        1/std::sqrt(t*t+a*a*s*s+w*w*u*u));
  }
  return static_cast<double>(1e-7L*8*a*a*sum);
}
void analytic_cases() {
  const auto cube=box();
  const double cube_expected=1.8823126443896598e-10;
  require(close(self_reference(cube),cube_expected,1e-13),"Duffy cube oracle");
  require(close(evaluated(cube,cube),cube_expected,2e-6),"Unit cube value");
  for(const auto &b:{box(0.140454e-3,0.556062e-3,0.035e-3),
                     box(10e-3,0.5e-3,0.035e-3)}) {
    const double reference=self_reference(b);
    require(close(reference,self_reference(b,240),2e-9),"Duffy oracle refinement");
    require(close(evaluated(b,b),reference,2e-6),"Aspect-ratio self value");
  }
  auto larger=box(2e-3,2e-3,2e-3);
  require(close(evaluated(larger,larger),2*cube_expected,2e-6),"SI linear scaling");
}
void partition_and_overlap() {
  auto whole=box(2e-3,1e-3,0.5e-3),left=whole,right=whole;
  left.length_m=right.length_m=whole.length_m/2;
  left.center_m[0]=-whole.length_m/4;right.center_m[0]=whole.length_m/4;
  const double full=evaluated(whole,whole);
  const double ll=evaluated(left,left),rr=evaluated(right,right);
  const double lr=evaluated(left,right);
  require(close(full,ll+rr+2*lr,3e-6),"Longitudinal subdivision invariance");
  auto overlap=whole;overlap.center_m[0]=whole.length_m/4;
  const double mutual=evaluated(whole,overlap);
  require(mutual>0 && mutual<full,"Overlap Cauchy-Schwarz energy");
  auto opposite=whole;opposite.direction[0]=-1;
  require(close(evaluated(whole,opposite),-full,2e-6),"Opposite duplicate basis");
  require(close(evaluated(whole,whole),full,1e-14),"Identical duplicate basis");
  const double matrix[3][3]={{full,mutual,-full},{mutual,full,-mutual},
                             {-full,-mutual,full}};
  for(int i=-2;i<=2;++i)for(int j=-2;j<=2;++j)for(int k=-2;k<=2;++k) {
    const double currents[]={double(i),double(j),double(k)};double energy=0;
    for(int p=0;p<3;++p)for(int q=0;q<3;++q)
      energy+=currents[p]*matrix[p][q]*currents[q];
    require(energy>=-1e-22,"Overlapping/duplicate basis positive energy");
  }
}
void orientation_and_far_field() {
  const double root=std::sqrt(0.5);
  auto a=box(2e-3,1e-3,0.5e-3),b=a;b.center_m={0,2e-3,0};
  const double unrotated=evaluated(a,b);
  a.direction=b.direction={root,root,0};
  a.width_axis=b.width_axis={-root,root,0};
  b.center_m={-2e-3*root,2e-3*root,0};
  require(close(evaluated(a,b),unrotated,2e-6),"Common rotation invariance");
  auto perpendicular=a;perpendicular.direction={-root,root,0};
  perpendicular.width_axis={root,root,0};
  require(evaluated(a,perpendicular)==0,"Orthogonal uniform currents");
  auto cube=box(),distant=cube;distant.center_m={0,0.1,0};
  require(close(evaluated(cube,distant),1e-12,1e-6),"Far-field volume mutual");
}
void rotated_overlap_and_refinement() {
  auto a=box(2e-3,1e-3,0.5e-3),b=a,opposite=a;
  const double root=std::sqrt(0.5);
  b.direction={root,root,0};b.width_axis={-root,root,0};
  b.center_m={0.25e-3,0.1e-3,0.05e-3};
  opposite.direction={-1,0,0};
  IntegrationOptions coarse,fine;
  coarse.relative_tolerance=1e-4;
  fine.max_potential_evaluations=1000000;
  const auto low=rectangular_inductance(a,b,coarse);
  const auto high=rectangular_inductance(a,b,fine);
  std::cout<<"Rotated overlap coarse="<<low.inductance_h<<" coarse_error="
           <<low.estimated_error_h<<" coarse_converged="<<low.converged
           <<" fine="<<high.inductance_h<<" fine_error="
           <<high.estimated_error_h<<" fine_converged="<<high.converged
           <<" evaluations="<<high.potential_evaluations<<std::endl;
  require(low.converged && high.converged,"Rotated overlap refinement convergence");
  require(high.estimated_error_h<low.estimated_error_h,
          "Refinement reduces estimated error");
  require(std::abs(high.inductance_h-low.inductance_h)<=
          high.estimated_error_h+low.estimated_error_h,"Refinement difference");
  const RectangularVolume volumes[]={a,b,opposite};
  Eigen::Matrix3d matrix;
  for(int i=0;i<3;++i)for(int j=0;j<=i;++j) {
    matrix(i,j)=evaluated(volumes[i],volumes[j],fine);
    matrix(j,i)=matrix(i,j);
  }
  const Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d> eigen(matrix);
  require(eigen.info()==Eigen::Success,"Volume matrix eigensolver");
  const double minimum=eigen.eigenvalues().minCoeff();
  std::cout<<"Rotated overlap matrix min_eigenvalue="<<minimum<<std::endl;
  require(minimum>=-1e-20,"Assembled overlapping-volume matrix PSD");
  auto shifted_a=a,shifted_b=b;
  for(int k=0;k<3;++k) {
    shifted_a.center_m[k]+=0.125;shifted_b.center_m[k]+=0.125;
  }
  require(close(evaluated(shifted_a,shifted_b,fine),high.inductance_h,2e-6),
          "Translation invariance");
  for(double &value:b.width_axis)value=-value;
  require(close(evaluated(a,b,fine),high.inductance_h,2e-6),
          "Width and thickness axis sign invariance");
}
void resource_and_input_failure() {
  auto cube=box();IntegrationOptions limited;
  limited.max_potential_evaluations=1;
  const auto failure=rectangular_inductance(cube,cube,limited);
  require(!failure.converged && failure.potential_evaluations==0,
          "Resource cap must fail closed");
  cube.width_m=std::numeric_limits<double>::quiet_NaN();bool rejected=false;
  try{rectangular_inductance(cube,box());}catch(const std::invalid_argument&){rejected=true;}
  require(rejected,"Nonfinite geometry rejection");
  cube=box();cube.width_axis={1,0,0};rejected=false;
  try{rectangular_inductance(cube,box());}catch(const std::invalid_argument&){rejected=true;}
  require(rejected,"Nonorthogonal geometry rejection");
  auto distant=box();distant.center_m={1e300,0,0};
  limited.max_potential_evaluations=574;
  require(!rectangular_inductance(box(),distant,limited).converged,
          "Extreme separation must not falsely converge");
  auto huge=box(1e10,1e10,1e10);limited.relative_tolerance=0.5;
  limited.permeability_h_per_m=1e308;
  require(!rectangular_inductance(huge,huge,limited).converged,
          "Nonfinite SI output must not falsely converge");
}
}
int main() {
  try {
    analytic_cases();partition_and_overlap();orientation_and_far_field();
    rotated_overlap_and_refinement();resource_and_input_failure();
    std::cout<<"Experimental finite rectangular-volume checks passed\n";return 0;
  } catch(const std::exception &error) {
    std::cerr<<error.what()<<'\n';return 1;
  }
}
