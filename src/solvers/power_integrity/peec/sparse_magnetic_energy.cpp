// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "sparse_magnetic_energy.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace spike::peec::spectral {
namespace {
using Real = long double;
using CV = std::array<std::complex<Real>, 3>;
const Real pi = std::acos(-1.0L);
Real dot(const Vector &a, const Vector &b) {
  Real sum=0; for(int k=0;k<3;++k) sum+=Real(a[k])*b[k]; return sum;
}
bool finite(const Vector &v) {
  return std::all_of(v.begin(),v.end(),[](double x){return std::isfinite(x);});
}
bool positive(double x) { return std::isfinite(x)&&x>0; }
bool unit(const Vector &v) { return finite(v)&&std::abs(dot(v,v)-1)<1e-12L; }
struct Prepared {
  Vector center{},direction{},width{},thickness{};
  Real length=0,area=0,w=0,t=0,inner=0,outer=0;
  bool annular=false;
};
Prepared prepare(const Basis &basis) {
  Prepared p;
  if(const auto *b=std::get_if<RectangularVolume>(&basis)) {
    if(!finite(b->center_m)||!unit(b->direction)||!unit(b->width_axis)||
        std::abs(dot(b->direction,b->width_axis))>1e-12L||
        !positive(b->length_m)||!positive(b->width_m)||!positive(b->thickness_m))
      throw std::invalid_argument("Invalid spectral rectangular basis");
    p.center=b->center_m;p.direction=b->direction;p.width=b->width_axis;
    p.length=b->length_m;p.w=b->width_m;p.t=b->thickness_m;p.area=p.w*p.t;
    for(int k=0;k<3;++k)p.thickness[k]=p.direction[(k+1)%3]*p.width[(k+2)%3]-
        p.direction[(k+2)%3]*p.width[(k+1)%3];
  } else {
    const auto &a=std::get<StraightAnnularVolume>(basis);
    if(!finite(a.center_m)||!unit(a.direction)||!positive(a.length_m)||
        !std::isfinite(a.inner_radius_m)||a.inner_radius_m<0||
        !positive(a.outer_radius_m)||a.outer_radius_m<=a.inner_radius_m)
      throw std::invalid_argument("Invalid spectral annular basis");
    p.center=a.center_m;p.direction=a.direction;p.length=a.length_m;
    p.inner=a.inner_radius_m;p.outer=a.outer_radius_m;p.annular=true;
    p.area=pi*(p.outer-p.inner)*(p.outer+p.inner);
  }
  if(!std::isfinite(p.area)||p.area<=0||!std::isfinite(p.length/p.area))
    throw std::invalid_argument("Spectral basis dynamic range exceeded");
  return p;
}
Real sinc(Real x) {
  if(std::abs(x)<1e-4L) {const Real x2=x*x;return 1-x2/6+x2*x2/120;}
  return std::sin(x)/x;
}
Real annular_factor(Real q,const Prepared &p) {
  const Real x=q*p.outer;
  if(x<=1) {
    // Entire Bessel series with (Ro^2-Ri^2) analytically cancelled. Stable
    // at q=0 and for a thin wall: sum_{j=0}^m (Ri/Ro)^(2j).
    const Real ratio=p.inner/p.outer,ratio2=ratio*ratio;
    Real sum=1,term=1,geometric=1,power=1;
    for(int m=1;m<=20;++m) {
      term*=-x*x/(4*Real(m)*(m+1));power*=ratio2;geometric+=power;
      const Real addition=term*geometric;sum+=addition;
      if(std::abs(addition)<std::numeric_limits<Real>::epsilon()*std::abs(sum))break;
    }
    return sum;
  }
  // Large arguments / extremely thin walls can suffer cancellation; the
  // finite-domain result intentionally carries no numerical certification.
  return 2*(p.outer*std::cyl_bessel_j(Real(1),q*p.outer)-
      p.inner*std::cyl_bessel_j(Real(1),q*p.inner))/
      (q*(p.outer-p.inner)*(p.outer+p.inner));
}
CV transform(const Prepared &p,const Vector &k) {
  const Real axial=dot(k,p.direction);
  Real shape=p.length*sinc(axial*p.length/2);
  if(p.annular) {
    // Cross product avoids cancellation in |k|^2-(k.direction)^2.
    Real transverse2=0;
    for(int d=0;d<3;++d) {
      const Real v=Real(k[(d+1)%3])*p.direction[(d+2)%3]-
          Real(k[(d+2)%3])*p.direction[(d+1)%3];transverse2+=v*v;
    }
    shape*=annular_factor(std::sqrt(transverse2),p);
  } else shape*=sinc(dot(k,p.width)*p.w/2)*sinc(dot(k,p.thickness)*p.t/2);
  const Real phase=-dot(k,p.center);
  const std::complex<Real> amplitude=shape*std::complex<Real>(std::cos(phase),std::sin(phase));
  CV result;for(int d=0;d<3;++d)result[d]=Real(p.direction[d])*amplitude;
  return result;
}
std::vector<std::pair<Real,Real>> polar_rule(std::size_t n) {
  std::vector<std::pair<Real,Real>> rule(n);
  for(std::size_t i=0;i<(n+1)/2;++i) {
    Real x=std::cos(pi*(Real(i)+0.75L)/(Real(n)+0.5L)),derivative=0;
    bool converged=false;
    for(int iteration=0;iteration<64;++iteration) {
      Real p=1,previous=0;
      for(std::size_t j=1;j<=n;++j) {
        const Real next=((2*Real(j)-1)*x*p-(Real(j)-1)*previous)/Real(j);
        previous=p;p=next;
      }
      derivative=Real(n)*(x*p-previous)/(x*x-1);
      const Real change=p/derivative;x-=change;
      if(std::abs(change)<=8*std::numeric_limits<Real>::epsilon()) {converged=true;break;}
    }
    if(!converged)throw std::runtime_error("Spectral polar rule failed");
    const Real weight=2/((1-x*x)*derivative*derivative);
    if(!std::isfinite(weight)||weight<=0)throw std::runtime_error("Invalid spectral weight");
    rule[i]={-x,weight};rule[n-1-i]={x,weight};
  }
  return rule;
}
}

FourierVector fourier_basis(const Basis &basis,const Vector &wavevector) {
  if(!finite(wavevector))throw std::invalid_argument("Invalid spectral wavevector");
  const auto value=transform(prepare(basis),wavevector);
  FourierVector result;
  for(int d=0;d<3;++d) {
    result[d]={double(value[d].real()),double(value[d].imag())};
    if(!std::isfinite(result[d].real())||!std::isfinite(result[d].imag()))
      throw std::invalid_argument("Spectral transform dynamic range exceeded");
  }
  return result;
}

Result prescribed_current_energy(const std::vector<Basis> &bases,
    const std::vector<double> &currents,const Options &o) {
  if(bases.empty()||bases.size()!=currents.size()||!positive(o.radial_cutoff_per_m)||
      !positive(o.permeability_h_per_m)||o.radial_panels==0||o.polar_order==0||
      o.polar_order>512||o.azimuthal_panels==0)
    throw std::invalid_argument("Invalid spectral energy input/options");
  Result result;
  std::size_t count=1;
  for(auto size:{o.radial_panels,o.polar_order,o.azimuthal_panels}) {
    if(count>o.maximum_nodes/size) {result.failure_code="SPECTRAL_NODE_LIMIT";return result;}
    count*=size;
  }
  if(count>o.maximum_feature_evaluations/bases.size()) {
    result.failure_code="SPECTRAL_WORK_LIMIT";return result;
  }
  std::vector<Prepared> prepared;prepared.reserve(bases.size());
  Real norm_bound=0;
  for(std::size_t i=0;i<bases.size();++i) {
    if(!std::isfinite(currents[i]))throw std::invalid_argument("Invalid spectral current");
    prepared.push_back(prepare(bases[i]));
    norm_bound+=std::abs(Real(currents[i]))*std::sqrt(prepared.back().length/prepared.back().area);
  }
  const Real cutoff=o.radial_cutoff_per_m,mu=o.permeability_h_per_m;
  result.current_l2_squared_bound_a2_per_m=double(norm_bound*norm_bound);
  result.radial_tail_bound_j=double(mu/2*(norm_bound/cutoff)*(norm_bound/cutoff));
  if(!std::isfinite(result.current_l2_squared_bound_a2_per_m)||
      !std::isfinite(result.radial_tail_bound_j)||
      (norm_bound>0&&(result.current_l2_squared_bound_a2_per_m==0||result.radial_tail_bound_j==0))) {
    result.failure_code="SPECTRAL_DYNAMIC_RANGE";return result;
  }
  const auto polar=polar_rule(o.polar_order);
  const Real dr=cutoff/Real(o.radial_panels),dphi=2*pi/Real(o.azimuthal_panels);
  Real sum=0;
  for(std::size_t ir=0;ir<o.radial_panels;++ir) {
    const Real radius=(Real(ir)+0.5L)*dr;
    for(const auto &[z,weight]:polar) {
      const Real rho=std::sqrt(std::max(Real(0),1-z*z));
      for(std::size_t ia=0;ia<o.azimuthal_panels;++ia) {
        const Real phi=(Real(ia)+0.5L)*dphi;
        Vector k={double(radius*rho*std::cos(phi)),double(radius*rho*std::sin(phi)),double(radius*z)};
        CV total{};
        for(std::size_t i=0;i<prepared.size();++i) {
          const auto feature=transform(prepared[i],k);
          for(int d=0;d<3;++d)total[d]+=Real(currents[i])*feature[d];
        }
        Real squared=0;for(const auto &value:total)squared+=std::norm(value);
        sum+=weight*squared;
      }
    }
  }
  result.finite_domain_energy_j=double(mu/(16*pi*pi*pi)*dr*dphi*sum);
  result.nodes=count;result.feature_evaluations=count*bases.size();
  if(!std::isfinite(result.finite_domain_energy_j)) {
    result.failure_code="SPECTRAL_DYNAMIC_RANGE";return result;
  }
  result.evaluated=true;return result;
}
} // namespace spike::peec::spectral
