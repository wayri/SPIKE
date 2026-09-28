// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "annular_inductance.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <queue>
#include <stdexcept>
#include <vector>

namespace spike::peec::volume {
namespace {
using Real = long double;
constexpr Real pi = 3.141592653589793238462643383279502884L;
constexpr Real x3[] = {-0.77459666924148337704L, 0, 0.77459666924148337704L};
constexpr Real w3[] = {0.55555555555555555556L, 0.88888888888888888889L,
                       0.55555555555555555556L};
constexpr Real x5[] = {-0.90617984593866399280L, -0.53846931010568309104L, 0,
                       0.53846931010568309104L, 0.90617984593866399280L};
constexpr Real w5[] = {0.23692688505618908751L, 0.47862867049936646804L,
                       0.56888888888888888889L, 0.47862867049936646804L,
                       0.23692688505618908751L};
constexpr std::size_t cell_cost = 27 + 125 + 3 * 45;

struct Value { Real value = 0, roundoff = 0; };
struct Domain {
  Real rlo, rhi, slo, shi;
  bool below_diagonal;
};
struct Geometry {
  std::array<Real, 4> z;
  Real factor;
};

// Independent derivation: F''(z) = 1/sqrt(z*z+rho*rho). Endpoint
// differencing integrates both longitudinal coordinates analytically. Rotation
// symmetry reduces two angles to 2*pi times their difference. Reflection gives
// another factor two and theta=pi*u*u softens the remaining logarithmic edge.
// Method lineage is the uniform-volume PEEC energy integral (Ruehli,
// DOI 10.1147/rd.165.0470); no external implementation was consulted/adapted.
Value integrand(const Domain &d, const Geometry &g, const std::array<Real,3> &u) {
  const Real r = d.rlo + (d.rhi-d.rlo)*u[0];
  const Real lo = d.below_diagonal ? d.slo : std::max(d.slo,r);
  const Real hi = d.below_diagonal ? std::min(d.shi,r) : d.shi;
  const Real s = lo + (hi-lo)*u[1];
  const Real theta = pi*u[2]*u[2];
  const Real rho = std::hypot(r-s, 2*std::sqrt(r*s)*std::sin(theta/2));
  const auto primitive = [rho](Real z) {
    return z*std::asinh(z/rho)-std::hypot(z,rho);
  };
  const Real a = primitive(g.z[0]), b = primitive(g.z[1]);
  const Real c = primitive(g.z[2]), e = primitive(g.z[3]);
  const Real jacobian = (d.rhi-d.rlo)*(hi-lo)*r*s*2*pi*u[2]*g.factor;
  const Real value = (a-b-c+e)*jacobian;
  const Real roundoff = 64*std::numeric_limits<Real>::epsilon()*
      (std::abs(a)+std::abs(b)+std::abs(c)+std::abs(e))*std::abs(jacobian);
  return {value,roundoff};
}
struct Cell {
  std::array<Real,3> lo{0,0,0}, hi{1,1,1};
  std::size_t domain = 0;
  int split = 0;
  Real value = 0, error = 0;
  bool operator<(const Cell &other) const { return error < other.error; }
};
Value rule(const Cell &cell, const Domain &domain, const Geometry &g,
           const std::array<int,3> &order) {
  Value result;
  for(int i=0;i<order[0];++i) for(int j=0;j<order[1];++j)
    for(int k=0;k<order[2];++k) {
      const int indices[] = {i,j,k};
      std::array<Real,3> u{}; Real weight=1;
      for(int d=0;d<3;++d) {
        const auto *x = order[d]==3 ? x3 : x5;
        const auto *w = order[d]==3 ? w3 : w5;
        const Real half = (cell.hi[d]-cell.lo[d])/2;
        u[d]=(cell.hi[d]+cell.lo[d])/2+half*x[indices[d]];
        weight*=half*w[indices[d]];
      }
      const auto value=integrand(domain,g,u);
      result.value+=weight*value.value;
      result.roundoff+=weight*value.roundoff;
    }
  return result;
}
void evaluate(Cell &cell,const Domain &domain,const Geometry &g) {
  const auto low=rule(cell,domain,g,{3,3,3});
  const auto high=rule(cell,domain,g,{5,5,5});
  Real largest=-1;
  for(int d=0;d<3;++d) {
    std::array<int,3> order{3,3,3};order[d]=5;
    const Real difference=std::abs(rule(cell,domain,g,order).value-low.value);
    if(difference>largest) {largest=difference;cell.split=d;}
  }
  cell.value=high.value;
  cell.error=4*std::max(largest,std::abs(high.value-low.value))+
      high.roundoff+low.roundoff;
}
void validate(const CoaxialAnnulus &a) {
  if(!std::isfinite(a.start_m)||!std::isfinite(a.end_m)||
      !std::isfinite(a.inner_radius_m)||!std::isfinite(a.outer_radius_m)||
      a.start_m==a.end_m||a.inner_radius_m<=0||
      a.outer_radius_m<=a.inner_radius_m)
    throw std::invalid_argument("Coaxial annulus requires finite distinct endpoints and 0 < inner < outer radius");
}
} // namespace

AnnularIntegrationResult coaxial_annular_inductance(
    const CoaxialAnnulus &first,const CoaxialAnnulus &second,
    const AnnularIntegrationOptions &options) {
  validate(first);validate(second);
  if(!std::isfinite(options.relative_tolerance)||options.relative_tolerance<=0||
      !std::isfinite(options.absolute_tolerance_h)||options.absolute_tolerance_h<0||
      !std::isfinite(options.permeability_h_per_m)||options.permeability_h_per_m<=0)
    throw std::invalid_argument("Invalid annular integration tolerance or permeability");
  const Real a=std::min(first.start_m,first.end_m);
  const Real b=std::max(first.start_m,first.end_m);
  const Real c=std::min(second.start_m,second.end_m);
  const Real d=std::max(second.start_m,second.end_m);
  const int sign=(first.end_m>first.start_m)==(second.end_m>second.start_m)?1:-1;
  const Real scale=std::max({b-a,d-c,Real(first.outer_radius_m),
                           Real(second.outer_radius_m),std::abs(a-c)});
  const Real ri=first.inner_radius_m/scale, ro=first.outer_radius_m/scale;
  const Real si=second.inner_radius_m/scale, so=second.outer_radius_m/scale;
  const Real area1=pi*(ro-ri)*(ro+ri), area2=pi*(so-si)*(so+si);
  Geometry g{{(b-c)/scale,(a-c)/scale,(b-d)/scale,(a-d)/scale},
             options.permeability_h_per_m*scale/(area1*area2)};
  // Split at every change in the radial intersection domain. The diagonal
  // r=s then lies only on subdomain boundaries, never through a cubature cell.
  std::vector<Real> knots{ri,ro};
  if(si>ri&&si<ro)knots.push_back(si);
  if(so>ri&&so<ro)knots.push_back(so);
  std::sort(knots.begin(),knots.end());
  std::vector<Domain> domains;
  for(std::size_t k=1;k<knots.size();++k) {
    const Real middle=(knots[k-1]+knots[k])/2;
    if(middle>si)domains.push_back({knots[k-1],knots[k],si,so,true});
    if(middle<so)domains.push_back({knots[k-1],knots[k],si,so,false});
  }
  AnnularIntegrationResult result;
  result.estimated_error_h=std::numeric_limits<double>::infinity();
  if(domains.size()>options.max_cells ||
      domains.size()>options.max_evaluations/cell_cost)return result;
  std::priority_queue<Cell> cells;
  Real value=0,error=0;
  for(std::size_t k=0;k<domains.size();++k) {
    Cell cell;cell.domain=k;evaluate(cell,domains[k],g);
    cells.push(cell);value+=cell.value;error+=cell.error;
    result.evaluations+=cell_cost;
  }
  const auto tolerance=[&]() {
    return std::max(Real(options.absolute_tolerance_h),
                    options.relative_tolerance*std::abs(value));
  };
  while(error>tolerance() && std::isfinite(value) && std::isfinite(error)) {
    if(cells.size()>=options.max_cells ||
        options.max_evaluations-result.evaluations<2*cell_cost)break;
    const Cell parent=cells.top();cells.pop();
    Cell left=parent,right=parent;
    const Real middle=(parent.lo[parent.split]+parent.hi[parent.split])/2;
    left.hi[parent.split]=middle;right.lo[parent.split]=middle;
    evaluate(left,domains[parent.domain],g);evaluate(right,domains[parent.domain],g);
    value+=left.value+right.value-parent.value;
    error=std::max(Real(0),error+left.error+right.error-parent.error);
    result.evaluations+=2*cell_cost;
    cells.push(left);cells.push(right);
  }
  result.inductance_h=static_cast<double>(sign*value);
  result.estimated_error_h=static_cast<double>(error);
  result.converged=std::isfinite(result.inductance_h)&&
      std::isfinite(result.estimated_error_h)&&value>=0&&error<=tolerance();
  return result;
}
AnnularIntegrationResult separated_annular_inductance(
    const CoaxialAnnulusVolume &first, const CoaxialAnnulusVolume &second,
    const AnnularIntegrationOptions &options) {
  // Clean-room derivation from the uniform-volume Coulomb energy integral.
  // Generating function: https://dlmf.nist.gov/18.12.E11 ; |P_n(x)| <= 1
  // on [-1,1]: https://dlmf.nist.gov/18.14.E1 (alpha=beta=0).
  // With delta = X-Y and D = |center1-center2|, each centrally symmetric
  // cylinder has zero odd moments. Thus only even Legendre degrees remain,
  // and the omitted n>=6 terms are bounded by q^6/(D*(1-q^2)), where
  // q=(enclosing_radius1+enclosing_radius2)/D. No external code was used.
  using V = std::array<Real,3>;
  const auto dot3=[](const V &a,const V &b) {
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  };
  const auto check=[&](const CoaxialAnnulusVolume &a) {
    validate({0,a.length_m,a.inner_radius_m,a.outer_radius_m});
    if(a.length_m<=0)throw std::invalid_argument("Invalid annulus length");
    for(int k=0;k<3;++k)
      if(!std::isfinite(a.center_m[k])||!std::isfinite(a.direction[k]))
        throw std::invalid_argument("Invalid annulus center or direction");
    const V u{a.direction[0],a.direction[1],a.direction[2]};
    if(std::abs(dot3(u,u)-1)>1e-10L)
      throw std::invalid_argument("Annulus direction must be unit length");
  };
  check(first);check(second);
  if(!std::isfinite(options.relative_tolerance)||options.relative_tolerance<=0||
      !std::isfinite(options.absolute_tolerance_h)||options.absolute_tolerance_h<0||
      !std::isfinite(options.permeability_h_per_m)||options.permeability_h_per_m<=0)
    throw std::invalid_argument("Invalid annular integration tolerance or permeability");
  AnnularIntegrationResult result;
  result.estimated_error_h=std::numeric_limits<double>::infinity();
  if(options.max_evaluations==0||options.max_cells==0)return result;
  V separation{},u{},v{};
  for(int k=0;k<3;++k) {
    separation[k]=Real(second.center_m[k])-first.center_m[k];
    u[k]=first.direction[k];v[k]=second.direction[k];
  }
  const Real distance=std::sqrt(dot3(separation,separation));
  if(!(distance>0)||!std::isfinite(distance))return result;
  // Admit unit axes only to arithmetic precision. Other approximately unit
  // descriptors remain unsupported here rather than silently rescaling them.
  const Real axis_error=std::abs(dot3(u,u)-1)+std::abs(dot3(v,v)-1);
  if(axis_error>64*std::numeric_limits<double>::epsilon())return result;
  const Real q=(std::hypot(Real(first.length_m)/2,Real(first.outer_radius_m))+
      std::hypot(Real(second.length_m)/2,Real(second.outer_radius_m)))/distance;
  if(!(q<=0.25L))return result;
  for(int k=0;k<3;++k)separation[k]/=distance;
  struct Moments { Real transverse, axial, trace, projection, radial4,
      projection4, projection_radial2; V covariance_projection; };
  const auto moments=[&](const CoaxialAnnulusVolume &a,const V &axis) {
    const Real ri=a.inner_radius_m/distance,ro=a.outer_radius_m/distance;
    const Real length=a.length_m/distance;
    const Real radial2=(ri*ri+ro*ro)/2;
    const Real radial4=(ri*ri*ri*ri+ri*ri*ro*ro+ro*ro*ro*ro)/3;
    const Real transverse=radial2/2,axial=length*length/12;
    const Real axial4=length*length*length*length/80;
    const Real c=dot3(axis,separation),c2=c*c,s2=1-c2;
    Moments m{transverse,axial,radial2+axial,
      transverse*s2+axial*c2,radial4+2*radial2*axial+axial4,
      3*radial4*s2*s2/8+6*transverse*axial*s2*c2+axial4*c2*c2,
      s2*(radial4/2+transverse*axial)+c2*(radial2*axial+axial4),{}};
    for(int k=0;k<3;++k)
      m.covariance_projection[k]=transverse*separation[k]+(axial-transverse)*c*axis[k];
    return m;
  };
  const auto a=moments(first,u),b=moments(second,v);
  const Real alignment=dot3(u,v);
  const Real covariance_trace=3*a.transverse*b.transverse+
      a.transverse*(b.axial-b.transverse)+b.transverse*(a.axial-a.transverse)+
      (a.axial-a.transverse)*(b.axial-b.transverse)*alignment*alignment;
  const Real r4=a.radial4+b.radial4+2*a.trace*b.trace+4*covariance_trace;
  const Real p4=a.projection4+b.projection4+6*a.projection*b.projection;
  const Real p2r2=a.projection_radial2+b.projection_radial2+
      a.projection*b.trace+b.projection*a.trace+
      4*dot3(a.covariance_projection,b.covariance_projection);
  const Real expansion=1+(3*(a.projection+b.projection)-a.trace-b.trace)/2+
      (35*p4-30*p2r2+3*r4)/8;
  // Area factors cancel: dV1*dV2/(A1*A2) = length1*length2 times
  // the expectation over uniform volumes. mu/(4*pi)*length1*length2/D is H.
  const Real factor=Real(options.permeability_h_per_m)/(4*pi)*
      first.length_m*(second.length_m/distance);
  if(!std::isfinite(factor)||factor<1024*std::numeric_limits<double>::min())return result;
  const Real q2=q*q;
  const Real remainder=q2*q2*q2/(1-q2);
  // q<=1/4 bounds all polynomial terms and keeps the sum away from zero.
  // The allowance covers input-axis deviation and intermediate/final rounding;
  // this is not a machine-certified interval enclosure.
  const Real roundoff=8192*std::numeric_limits<double>::epsilon()+16*axis_error;
  const Real value=factor*alignment*expansion;
  const Real error=std::abs(factor)*(std::abs(alignment)*remainder+roundoff);
  result.inductance_h=static_cast<double>(value);
  result.estimated_error_h=static_cast<double>(error);
  result.evaluations=1;
  result.converged=std::isfinite(result.inductance_h)&&
      std::isfinite(result.estimated_error_h)&&expansion>0&&
      error<=std::max(Real(options.absolute_tolerance_h),
                     options.relative_tolerance*std::abs(value));
  return result;
}
} // namespace spike::peec::volume
