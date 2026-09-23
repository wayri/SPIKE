// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#include "affine_triangle_basis.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace spike::peec::affine {
namespace {
// Independent derivation from barycentric polynomial moments and the
// finite-volume Coulomb energy stated in PEEC_CONFORMING_BASIS_BLOCKER.md.
// No external implementation or test data consulted or adapted.
// E[lambda_i lambda_j]=(1+delta_ij)/12. For disjoint cells, replace 1/r by
// its centroid value K0. The numerator's integral is exactly B_i dot B_j.
// The absolute remainder is bounded by max|K-K0| V_i V_j max|b_i| max|b_j|.
// Convexity bounds |b| by vertex norms, and AABBs bound all pair distances.
using Real = long double;
using V = std::array<Real, 3>;
Real dot(const V& a, const V& b) {
  return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
}
V add(const V& a, const V& b) {
  return {a[0]+b[0], a[1]+b[1], a[2]+b[2]};
}
V mul(const V& a, Real s) { return {a[0]*s,a[1]*s,a[2]*s}; }
Real norm(const V& a) { return std::sqrt(dot(a,a)); }
struct Cell { std::array<V,3> p,b; Real lo,hi; };
Real twice_area(const Cell& c) {
  return (c.p[1][0]-c.p[0][0])*(c.p[2][1]-c.p[0][1])-
         (c.p[1][1]-c.p[0][1])*(c.p[2][0]-c.p[0][0]);
}
Real volume(const Cell& c) { return twice_area(c)*(c.hi-c.lo)/2; }
V centroid(const Cell& c) {
  V result=mul(add(add(c.p[0],c.p[1]),c.p[2]),1.0L/3);
  result[2]=(c.lo+c.hi)/2; return result;
}
V moment(const Cell& c) {
  return mul(add(add(c.b[0],c.b[1]),c.b[2]),volume(c)/3);
}
Cell checked(const TrianglePrism& p) {
  Cell c{}; c.lo=p.lower_z_m; c.hi=p.upper_z_m;
  for(std::size_t i=0;i<3;++i) {
    for(std::size_t k=0;k<2;++k) c.p[i][k]=p.vertices_m[i][k];
    for(std::size_t k=0;k<3;++k) c.b[i][k]=p.density_per_a[i][k];
    for(Real v:c.p[i]) if(!std::isfinite(v))
      throw std::invalid_argument("Nonfinite affine-prism vertex");
    for(Real v:c.b[i]) if(!std::isfinite(v))
      throw std::invalid_argument("Nonfinite affine-prism current density");
  }
  constexpr Real floor=256*std::numeric_limits<double>::epsilon();
  Real longest2=0, coordinate_scale=0;
  for(std::size_t i=0;i<3;++i) {
    const V edge=add(c.p[i],mul(c.p[(i+1)%3],-1));
    longest2=std::max(longest2,dot(edge,edge));
    coordinate_scale=std::max(coordinate_scale,norm(c.p[i]));
  }
  if(!std::isfinite(c.lo)||!std::isfinite(c.hi)||!(c.hi>c.lo)||
     c.hi-c.lo<=floor*std::max(std::abs(c.lo),std::abs(c.hi)) ||
     !(twice_area(c)>floor*longest2) ||
     std::sqrt(longest2)<=floor*coordinate_scale ||
     !std::isfinite(volume(c)) || !(volume(c)>0))
    throw std::invalid_argument("Degenerate, inverted or ill-conditioned affine prism");
  return c;
}
double finite_double(Real value) {
  const double result=static_cast<double>(value);
  if(!std::isfinite(result) || (value!=0 && result==0))
    throw std::overflow_error("Affine-prism result outside double range");
  return result;
}
struct Bounds { V lo,hi; };
Bounds bounds(const Cell& c) {
  Bounds b{c.p[0],c.p[0]};
  for(const auto& p:c.p) for(std::size_t k=0;k<2;++k) {
    b.lo[k]=std::min(b.lo[k],p[k]); b.hi[k]=std::max(b.hi[k],p[k]);
  }
  b.lo[2]=c.lo;b.hi[2]=c.hi;return b;
}
Real distance_lower(const Cell& a, const Cell& b) {
  const auto x=bounds(a), y=bounds(b); V delta{};
  for(std::size_t k=0;k<3;++k)
    delta[k]=std::max({Real(0),x.lo[k]-y.hi[k],y.lo[k]-x.hi[k]});
  return norm(delta);
}
struct Pair {
  Cell a,b; Real value=0,error=0;
  bool operator<(const Pair& other) const { return error<other.error; }
};
Pair evaluate(const Cell& a,const Cell& b,Real factor) {
  Pair result{a,b};const auto x=bounds(a),y=bounds(b);V far{};
  for(std::size_t k=0;k<3;++k)
    far[k]=std::max(std::abs(x.lo[k]-y.hi[k]),std::abs(x.hi[k]-y.lo[k]));
  const Real lower=distance_lower(a,b), upper=norm(far);
  const Real k0=1/norm(add(centroid(a),mul(centroid(b),-1)));
  Real am=0,bm=0;
  for(std::size_t i=0;i<3;++i) {
    am=std::max(am,norm(a.b[i]));bm=std::max(bm,norm(b.b[i]));
  }
  const Real magnitude=volume(a)*volume(b)*am*bm;
  result.value=factor*dot(moment(a),moment(b))*k0;
  result.error=factor*magnitude*(std::max(1/lower-k0,k0-1/upper)+
      256*std::numeric_limits<double>::epsilon()/lower);
  if(!std::isfinite(result.value)||!std::isfinite(result.error))
    throw std::overflow_error("Affine-prism mutual arithmetic overflow");
  return result;
}
Real diameter(const Cell& c) {
  const auto b=bounds(c);return norm(add(b.hi,mul(b.lo,-1)));
}
std::pair<Cell,Cell> split(const Cell& c) {
  std::size_t edge=0; Real length=0;
  for(std::size_t i=0;i<3;++i) {
    const Real candidate=norm(add(c.p[i],mul(c.p[(i+1)%3],-1)));
    if(candidate>length) {length=candidate;edge=i;}
  }
  Cell a=c,b=c;
  if(c.hi-c.lo>length) {a.hi=(c.lo+c.hi)/2;b.lo=a.hi;}
  else {
    const auto i=edge,j=(edge+1)%3,k=(edge+2)%3;
    const V p=mul(add(c.p[i],c.p[j]),0.5L), v=mul(add(c.b[i],c.b[j]),0.5L);
    a.p={c.p[i],p,c.p[k]};a.b={c.b[i],v,c.b[k]};
    b.p={p,c.p[j],c.p[k]};b.b={v,c.b[j],c.b[k]};
  }
  return {a,b};
}
} // namespace

TrianglePrism unit_face_basis(const std::array<Point,3>& vertices,
                             double lo,double hi,std::size_t opposite,int sign) {
  if(opposite>=3 || (sign!=1 && sign!=-1))
    throw std::invalid_argument("Invalid affine face index or orientation");
  TrianglePrism p{vertices,lo,hi,{}};const auto c=checked(p);
  const Real factor=sign/(twice_area(c)*(c.hi-c.lo));
  for(std::size_t i=0;i<3;++i)for(std::size_t k=0;k<2;++k)
    p.density_per_a[i][k]=finite_double(factor*(c.p[i][k]-c.p[opposite][k]));
  return p;
}
double side_flux(const TrianglePrism& piece,std::size_t opposite) {
  if(opposite>=3)throw std::invalid_argument("Invalid affine face index");
  const auto c=checked(piece);const auto i=(opposite+1)%3,j=(opposite+2)%3;
  const V edge=add(c.p[j],mul(c.p[i],-1)),mean=mul(add(c.b[i],c.b[j]),0.5L);
  return finite_double((c.hi-c.lo)*(edge[1]*mean[0]-edge[0]*mean[1]));
}
Vector integrated_current(const TrianglePrism& piece) {
  const V v=moment(checked(piece));
  return {finite_double(v[0]),finite_double(v[1]),finite_double(v[2])};
}
double local_resistance(const TrianglePrism& first,const TrianglePrism& second,
                        double sigma) {
  const auto a=checked(first),b=checked(second);
  if(!(sigma>0)||!std::isfinite(sigma))
    throw std::invalid_argument("Conductivity must be finite and positive");
  if(first.vertices_m!=second.vertices_m || first.lower_z_m!=second.lower_z_m ||
     first.upper_z_m!=second.upper_z_m)
    throw std::invalid_argument("Local affine resistance requires identical ordered support");
  Real diagonal=0;V sa{},sb{};
  for(std::size_t i=0;i<3;++i) {
    diagonal+=dot(a.b[i],b.b[i]);sa=add(sa,a.b[i]);sb=add(sb,b.b[i]);
  }
  return finite_double(volume(a)*(dot(sa,sb)+diagonal)/(12*sigma));
}
MutualResult separated_mutual(const TrianglePrism& first,const TrianglePrism& second,
                             const MutualOptions& o) {
  auto a=checked(first),b=checked(second);
  // Canonical geometry ordering makes reciprocal calls share the same adaptive
  // subdivision, including equal-diameter ties. Coefficient signs do not enter.
  if(b.p<a.p || (b.p==a.p && (b.lo<a.lo || (b.lo==a.lo && b.hi<a.hi))))
    std::swap(a,b);
  if(!std::isfinite(o.absolute_tolerance_h)||o.absolute_tolerance_h<=0 ||
     !std::isfinite(o.relative_tolerance)||o.relative_tolerance<0 ||
     o.relative_tolerance>=1 || !std::isfinite(o.permeability_h_per_m)||
     o.permeability_h_per_m<=0 || o.max_pair_evaluations<1 || o.max_cells<1 ||
     o.max_pair_evaluations>1000000 || o.max_cells>500000)
    throw std::invalid_argument("Invalid affine mutual tolerance or resource budget");
  MutualResult result;
  if(!(distance_lower(a,b)>0)) return result;
  const Real factor=o.permeability_h_per_m/(4*std::acos(-1.0L));
  std::priority_queue<Pair> queue;queue.push(evaluate(a,b,factor));
  Real value=queue.top().value,error=queue.top().error;
  result.pair_evaluations=1;
  for(;;) {
    result.inductance_h=finite_double(value);
    result.error_bound_estimate_h=finite_double(error);
    // Relative error is tested against a lower bound on |true value|.
    const Real target=o.absolute_tolerance_h+
        o.relative_tolerance*std::max(Real(0),std::abs(value)-error);
    if(error<=target) {result.status=MutualStatus::converged;return result;}
    if(queue.size()>=o.max_cells || result.pair_evaluations+2>o.max_pair_evaluations) {
      result.status=MutualStatus::resource_limit;return result;
    }
    const auto parent=queue.top();queue.pop();Pair x,y;
    if(diameter(parent.a)>=diameter(parent.b)) {
      const auto children=split(parent.a);
      x=evaluate(children.first,parent.b,factor);y=evaluate(children.second,parent.b,factor);
    } else {
      const auto children=split(parent.b);
      x=evaluate(parent.a,children.first,factor);y=evaluate(parent.a,children.second,factor);
    }
    value+=x.value+y.value-parent.value;
    error=std::max(Real(0),error-parent.error)+x.error+y.error;
    queue.push(x);queue.push(y);result.pair_evaluations+=2;
  }
}
} // namespace spike::peec::affine
