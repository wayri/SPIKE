// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
// Standalone opt-in verification, no production registration:
// g++ -std=c++20 -O2 -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off
//   -I src src/peec/affine_triangle_basis.cpp tests/test_affine_triangle_basis.cpp
//   -o build/test_affine_triangle_basis
#include "peec/affine_triangle_basis.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

using namespace spike::peec::affine;
namespace {
void require(bool yes,const char* message) {
  if(!yes)throw std::runtime_error(message);
}
void near(double a,double b,double relative,const char* message) {
  require(std::abs(a-b)<=relative*std::max(std::abs(a),std::abs(b)),message);
}
template<class F> void rejects(F f,const char* message) {
  bool rejected=false;
  try {f();}catch(const std::invalid_argument&) {rejected=true;}
  require(rejected,message);
}
TrianglePrism triangle(double scale=1,double x=0) {
  return unit_face_basis({Point{x,0},Point{x+scale,0},Point{x,scale}},
                         0,0.1*scale,0);
}
TrianglePrism reverse(TrianglePrism p) {
  for(auto& v:p.density_per_a)for(double& x:v)x=-x;
  return p;
}
TrianglePrism rotate_translate(TrianglePrism p) {
  for(auto& v:p.vertices_m) v={7-v[1],-3+v[0]};
  for(auto& v:p.density_per_a) v={-v[1],v[0],v[2]};
  p.lower_z_m+=2;p.upper_z_m+=2;return p;
}
// Independent degree-two triangle quadrature, with barycentric nodes
// (2/3,1/6,1/6) and permutations; exact for the affine energy product.
double resistance_oracle(const TrianglePrism& a,const TrianglePrism& b,double sigma) {
  double sum=0;
  for(std::size_t i=0;i<3;++i) {
    Vector va{},vb{};
    for(std::size_t j=0;j<3;++j)for(std::size_t k=0;k<3;++k) {
      const double lambda=(j==i)?2.0/3:1.0/6;
      va[k]+=lambda*a.density_per_a[j][k];
      vb[k]+=lambda*b.density_per_a[j][k];
    }
    for(std::size_t k=0;k<3;++k)sum+=va[k]*vb[k]/3;
  }
  const auto& p=a.vertices_m;
  const double area=((p[1][0]-p[0][0])*(p[2][1]-p[0][1])-
                     (p[2][0]-p[0][0])*(p[1][1]-p[0][1]))/2;
  return sum*area*(a.upper_z_m-a.lower_z_m)/sigma;
}
void moments_and_flux() {
  const double size=1e-3,t=35e-6,sigma=5.8e7;
  const auto a=unit_face_basis({Point{0,0},Point{size,0},Point{0,size}},0,t,0);
  const auto b=unit_face_basis({Point{size,size},Point{0,size},Point{size,0}},0,t,0,-1);
  near(side_flux(a,0),1,2e-15,"Selected face unit flux");
  require(side_flux(a,1)==0 && side_flux(a,2)==0,"Exterior zero flux");
  near(side_flux(b,0),-1,2e-15,"Opposing divergence integral");
  near(side_flux(reverse(a),0),-1,2e-15,"Orientation reversal flux");
  const double r=local_resistance(a,a,sigma)+local_resistance(b,b,sigma);
  near(r,1/(3*sigma*t),3e-15,"Manufactured square pair exact resistance");
  near(r,0.0001642036124794745,3e-15,"Fixed SI resistance oracle");
  for(double u:{0.0,0.1,0.5,0.9,1.0}) {
    // Point (a*u,a*(1-u)) lies on the shared diagonal. The independently
    // specified fields are (x,y)/(a*a*t) and (a-x,a-y)/(a*a*t).
    const double lower_normal=(u+(1-u))/(size*t*std::sqrt(2.0));
    const double upper_normal=((1-u)+u)/(size*t*std::sqrt(2.0));
    near(lower_normal,upper_normal,2e-15,"Shared normal continuity oracle");
    // Evaluate the stored affine fields on the same shared edge.
    double stored_a=0,stored_b=0;
    for(std::size_t k=0;k<2;++k) {
      stored_a+=u*a.density_per_a[1][k]+(1-u)*a.density_per_a[2][k];
      stored_b+=(1-u)*b.density_per_a[1][k]+u*b.density_per_a[2][k];
    }
    near(stored_a/std::sqrt(2.0),lower_normal,3e-15,"Stored lower face field");
    near(stored_b/std::sqrt(2.0),upper_normal,3e-15,"Stored upper face field");
  }
  const auto integral=integrated_current(a);
  near(integral[0],size/6,2e-15,"Integrated affine current x");
  near(integral[1],size/6,2e-15,"Integrated affine current y");
  auto arbitrary=a; arbitrary.density_per_a={Vector{2,-3,1},Vector{-1,7,2},Vector{4,0,-5}};
  near(local_resistance(a,arbitrary,sigma),resistance_oracle(a,arbitrary,sigma),3e-15,
       "Independent mixed polynomial energy");
  near(local_resistance(arbitrary,arbitrary,sigma),resistance_oracle(arbitrary,arbitrary,sigma),3e-15,
       "Independent general affine energy");
  near(local_resistance(reverse(a),a,sigma),-local_resistance(a,a,sigma),3e-15,
       "Signed off-diagonal resistance");
  const auto transformed=rotate_translate(a);
  near(side_flux(transformed,0),1,2e-11,"Translated rotated flux");
  near(local_resistance(transformed,transformed,sigma),local_resistance(a,a,sigma),2e-11,
       "Translated rotated resistance");
  near(local_resistance(triangle(2),triangle(2),sigma),
       local_resistance(triangle(),triangle(),sigma)/2,3e-15,"SI resistance scaling");
  auto whole=triangle(),left=whole,right=whole;
  whole.density_per_a={Vector{1,2,-0.5},Vector{1,2,-0.5},Vector{1,2,-0.5}};
  left.density_per_a=right.density_per_a=whole.density_per_a;
  left.vertices_m[1]={0.5,0};right.vertices_m[0]={0.5,0};
  near(local_resistance(left,left,sigma)+local_resistance(right,right,sigma),
       local_resistance(whole,whole,sigma),3e-15,"Constant-field subdivision energy");
  for(std::size_t face=0;face<3;++face) {
    auto p=unit_face_basis({Point{0,0},Point{2,0},Point{0.3,1}},0,0.2,face);
    for(std::size_t side=0;side<3;++side)
      require(std::abs(side_flux(p,side)-(face==side?1:0))<3e-15,"All face fluxes");
  }
}

// Independent six-dimensional reference: tensor Gauss integration after
// Duffy mapping the triangle (u,(1-u)*v), including its Jacobian (1-u).
// This does not reuse production cell subdivision, bounds, or moments.
std::vector<std::pair<double,double>> gauss(int n) {
  std::vector<std::pair<double,double>> rule;
  for(int i=0;i<n;++i) {
    double x=std::cos(std::acos(-1.0)*(i+0.75)/(n+0.5)),d=0;
    for(int iteration=0;iteration<30;++iteration) {
      double p=1,previous=0;
      for(int k=1;k<=n;++k) {
        const double next=((2*k-1)*x*p-(k-1)*previous)/k;
        previous=p;p=next;
      }
      d=n*(x*p-previous)/(x*x-1);
      const double delta=p/d;x-=delta;if(std::abs(delta)<2e-16)break;
    }
    rule.push_back({(1+x)/2,1/((1-x*x)*d*d)});
  }
  return rule;
}
struct Sample {Vector position,current;double weight;};
std::vector<Sample> samples(const TrianglePrism& p,int order) {
  std::vector<Sample> out;const auto rule=gauss(order);const auto& v=p.vertices_m;
  const double determinant=(v[1][0]-v[0][0])*(v[2][1]-v[0][1])-
                           (v[1][1]-v[0][1])*(v[2][0]-v[0][0]);
  for(auto [u,wu]:rule)for(auto [w,ww]:rule)for(auto [z,wz]:rule) {
    const double lambda[]={1-u-(1-u)*w,u,(1-u)*w};Sample s{};
    for(std::size_t i=0;i<3;++i) {
      for(std::size_t k=0;k<2;++k)s.position[k]+=lambda[i]*v[i][k];
      for(std::size_t k=0;k<3;++k)s.current[k]+=lambda[i]*p.density_per_a[i][k];
    }
    s.position[2]=p.lower_z_m+z*(p.upper_z_m-p.lower_z_m);
    s.weight=wu*ww*wz*(1-u)*determinant*(p.upper_z_m-p.lower_z_m);out.push_back(s);
  }
  return out;
}
double mutual_oracle(const TrianglePrism& a,const TrianglePrism& b,int order) {
  const auto x=samples(a,order),y=samples(b,order);long double sum=0;
  for(const auto& i:x)for(const auto& j:y) {
    double distance2=0,numerator=0;
    for(std::size_t k=0;k<3;++k) {
      distance2+=std::pow(i.position[k]-j.position[k],2);
      numerator+=i.current[k]*j.current[k];
    }
    sum+=i.weight*j.weight*numerator/std::sqrt(distance2);
  }
  return static_cast<double>(sum*1e-7L);
}
void separated_integrals() {
  const auto a=triangle(),b=triangle(1,10);MutualOptions options;
  options.relative_tolerance=0.03;
  const double reference=mutual_oracle(a,b,8);
  near(reference,mutual_oracle(a,b,4),1e-9,"Independent reference refinement");
  const auto result=separated_mutual(a,b,options);
  require(result.status==MutualStatus::converged,"Separated integral admission");
  require(result.pair_evaluations>1,"Nontrivial adaptive refinement exercised");
  require(std::abs(result.inductance_h-reference)<=result.error_bound_estimate_h,
          "Independent reference within analytic error envelope");
  near(result.inductance_h,separated_mutual(b,a,options).inductance_h,1e-13,
       "Mutual reciprocity");
  near(separated_mutual(a,reverse(b),options).inductance_h,-result.inductance_h,1e-13,
       "Mutual orientation reversal");
  near(separated_mutual(rotate_translate(a),rotate_translate(b),options).inductance_h,
       result.inductance_h,1e-13,"Mutual rigid transform");
  near(separated_mutual(triangle(2),triangle(2,20),options).inductance_h,
       2*result.inductance_h,1e-13,"SI inductance scaling");
  options.max_pair_evaluations=1;
  const auto limited=separated_mutual(a,b,options);
  require(limited.status==MutualStatus::resource_limit && limited.pair_evaluations==1,
          "Evaluation budget explicit failure");
  require(result.error_bound_estimate_h<limited.error_bound_estimate_h,
          "Discretization envelope reduced by refinement");
  options.max_pair_evaluations=100;options.max_cells=1;
  require(separated_mutual(a,b,options).status==MutualStatus::resource_limit,
          "Memory budget explicit failure");
  const auto far=separated_mutual(a,triangle(1,1e6));
  require(far.status==MutualStatus::converged,"Far mutual admission");
  near(far.inductance_h,1e-7*(1.0/18)/1e6,2e-6,"Far integrated-current asymptote");
  auto mixed=b;
  mixed.density_per_a={Vector{-2,7,1},Vector{8,-3,0},Vector{1,4,-5}};
  MutualOptions mixed_options;mixed_options.relative_tolerance=0.1;
  const auto mixed_result=separated_mutual(a,mixed,mixed_options);
  require(mixed_result.status==MutualStatus::converged,"General affine mutual admission");
  const double mixed_reference=mutual_oracle(a,mixed,8);
  near(mixed_reference,mutual_oracle(a,mixed,4),1e-9,"General affine oracle refinement");
  require(std::abs(mixed_reference-mixed_result.inductance_h)<=mixed_result.error_bound_estimate_h,
          "Sign-changing affine numerator reference envelope");
  std::cout<<"affine far mutual="<<result.inductance_h<<" reference="<<reference
           <<" bound="<<result.error_bound_estimate_h<<" evaluations="<<result.pair_evaluations<<'\n';
}
void unsupported_and_invalid() {
  const auto p=triangle();
  for(const auto& q:{p,triangle(1,1),triangle(1,0.5)})
    require(separated_mutual(p,q).status==MutualStatus::unsupported_separation,
            "Self/touching/overlap must never be admitted");
  rejects([&]{local_resistance(p,triangle(1,2),1);},"Unsupported resistance overlap");
  rejects([&]{local_resistance(p,p,0);},"Zero conductivity");
  rejects([&]{unit_face_basis(p.vertices_m,0,1,3);},"Bad face");
  rejects([&]{unit_face_basis(p.vertices_m,0,1,0,0);},"Bad orientation sign");
  auto malformed=p;std::swap(malformed.vertices_m[1],malformed.vertices_m[2]);
  rejects([&]{integrated_current(malformed);},"Inverted geometry");
  malformed=p;malformed.vertices_m[2]=malformed.vertices_m[1];
  rejects([&]{integrated_current(malformed);},"Degenerate geometry");
  malformed=p;malformed.vertices_m[2]={1,1e-16};
  rejects([&]{integrated_current(malformed);},"Ill-conditioned geometry");
  malformed=p;malformed.upper_z_m=0;
  rejects([&]{integrated_current(malformed);},"Zero thickness");
  malformed=p;malformed.density_per_a[0][0]=std::numeric_limits<double>::quiet_NaN();
  rejects([&]{integrated_current(malformed);},"Nonfinite coefficients");
  MutualOptions options;options.max_cells=500001;
  rejects([&]{separated_mutual(p,triangle(1,10),options);},"Hard resource ceiling");
  options={};options.relative_tolerance=1;
  rejects([&]{separated_mutual(p,triangle(1,10),options);},"Invalid tolerance");
}
} // namespace
int main() {
  try {
    moments_and_flux();separated_integrals();unsupported_and_invalid();
    std::cout<<"Affine triangular-prism bounded-subset checks passed\n";
    return 0;
  }catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
