// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "volume_inductance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <stdexcept>
#include <vector>

namespace spike::peec::volume {
namespace {
// Independently derived rectangular Newton-potential primitive. Method lineage:
// Ruehli, DOI 10.1147/rd.165.0470 (finite-volume partial inductance), and
// Nagy et al., DOI 10.1007/s001900000116 (prism potential). No third-party
// implementation was consulted or adapted. The asinh primitive below differs
// from the usual logarithmic primitive by terms killed by corner differences.
using Real = long double;
using V = std::array<Real, 3>;
Real dot(const V &a, const V &b) {
  return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}
V cross(const V &a, const V &b) {
  return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
          a[0]*b[1]-a[1]*b[0]};
}
struct Box {
  V center, extent;
  std::array<V, 3> axes;
  Real volume() const { return extent[0]*extent[1]*extent[2]; }
};
Box make_box(const RectangularVolume &v, const Vector &origin, Real scale) {
  Box b;
  for (int k=0; k<3; ++k) {
    b.center[k]=(Real(v.center_m[k])-origin[k])/scale;
    b.axes[0][k]=v.direction[k];
    b.axes[1][k]=v.width_axis[k];
    if (!std::isfinite(b.center[k]) || !std::isfinite(b.axes[0][k]) ||
        !std::isfinite(b.axes[1][k]))
      throw std::invalid_argument("Nonfinite rectangular-volume geometry");
  }
  if (std::abs(dot(b.axes[0],b.axes[0])-1)>1e-10L ||
      std::abs(dot(b.axes[1],b.axes[1])-1)>1e-10L ||
      std::abs(dot(b.axes[0],b.axes[1]))>1e-10L)
    throw std::invalid_argument("Rectangular-volume axes must be orthonormal");
  b.axes[2]=cross(b.axes[0],b.axes[1]);
  b.extent={v.length_m/scale,v.width_m/scale,v.thickness_m/scale};
  for (Real e:b.extent)
    if (!std::isfinite(e) || e<=0)
      throw std::invalid_argument("Rectangular-volume dimensions must be positive");
  return b;
}
Real primitive(Real x, Real y, Real z) {
  if (x==0 || y==0 || z==0) return 0;
  const Real sign=((x<0)^(y<0)^(z<0)) ? -1 : 1;
  x=std::abs(x); y=std::abs(y); z=std::abs(z);
  const Real r=std::sqrt(x*x+y*y+z*z);
  return sign*(x*y*std::asinh(z/std::hypot(x,y)) +
      y*z*std::asinh(x/std::hypot(y,z)) +
      z*x*std::asinh(y/std::hypot(z,x)) -
      (x*x*std::atan2(y*z,x*r) + y*y*std::atan2(z*x,y*r) +
       z*z*std::atan2(x*y,z*r))/2);
}
struct Value { Real value=0, roundoff=0; };
Value potential(const Box &source, const V &point) {
  V delta;
  for(int k=0;k<3;++k) delta[k]=source.center[k]-point[k];
  V local{dot(delta,source.axes[0]),dot(delta,source.axes[1]),
          dot(delta,source.axes[2])};
  Real sum=0, magnitude=0;
  for(int mask=0;mask<8;++mask) {
    V corner; int sign=1;
    for(int k=0;k<3;++k) {
      const int s=(mask&(1<<k)) ? 1 : -1;
      corner[k]=local[k]+s*source.extent[k]/2; sign*=s;
    }
    const Real term=primitive(corner[0],corner[1],corner[2]);
    sum+=sign*term; magnitude+=std::abs(term);
  }
  // Conservative roundoff indicator (not an interval-arithmetic proof).
  return {sum/source.volume(), 64*std::numeric_limits<Real>::epsilon()*
          magnitude/source.volume()};
}
constexpr Real x3[]={-0.77459666924148337704L,0,0.77459666924148337704L};
constexpr Real w3[]={0.55555555555555555556L,0.88888888888888888889L,
                     0.55555555555555555556L};
constexpr Real x5[]={-0.90617984593866399280L,-0.53846931010568309104L,0,
                     0.53846931010568309104L,0.90617984593866399280L};
constexpr Real w5[]={0.23692688505618908751L,0.47862867049936646804L,
                     0.56888888888888888889L,0.47862867049936646804L,
                     0.23692688505618908751L};
struct Cell {
  V lower{-0.5L,-0.5L,-0.5L}, upper{0.5L,0.5L,0.5L};
  Real value=0, error=0;
  int split_axis=0;
  bool operator<(const Cell &other) const {return error<other.error;}
};
V point_at(const Box &box,const V &u) {
  V p=box.center;
  for(int d=0;d<3;++d)
    for(int k=0;k<3;++k) p[k]+=box.axes[d][k]*u[d]*box.extent[d];
  return p;
}
Value quadrature(const Box &source,const Box &target,const Cell &cell,
                 const std::array<int,3> &orders) {
  Value result;
  for(int i=0;i<orders[0];++i)
    for(int j=0;j<orders[1];++j)
      for(int k=0;k<orders[2];++k) {
        const int indexes[]={i,j,k}; V u; Real weight=1;
        for(int d=0;d<3;++d) {
          const Real *xs=orders[d]==3?x3:x5;
          const Real *ws=orders[d]==3?w3:w5;
          const Real half=(cell.upper[d]-cell.lower[d])/2;
          u[d]=(cell.upper[d]+cell.lower[d])/2+half*xs[indexes[d]];
          weight*=half*ws[indexes[d]];
        }
        const auto v=potential(source,point_at(target,u));
        result.value+=weight*v.value; result.roundoff+=weight*v.roundoff;
      }
  return result;
}
constexpr std::size_t cell_cost=27+125+3*45;
void evaluate(Cell &cell,const Box &source,const Box &target) {
  const auto low=quadrature(source,target,cell,{3,3,3});
  const auto high=quadrature(source,target,cell,{5,5,5});
  Real largest=-1;
  for(int d=0;d<3;++d) {
    std::array<int,3> orders{3,3,3}; orders[d]=5;
    const Real difference=std::abs(quadrature(source,target,cell,orders).value-
                                   low.value);
    if(difference>largest) {largest=difference; cell.split_axis=d;}
  }
  cell.value=high.value;
  // Safety factor covers observed asymptotic error, but is not certification.
  cell.error=4*std::max(std::abs(high.value-low.value),largest)+
             high.roundoff+low.roundoff;
}
struct Integral { Real value=0,error=0; bool converged=false; };
Integral integrate(const Box &source,const Box &target,
                   const IntegrationOptions &o,Real absolute_tolerance,
                   std::size_t &evaluations) {
  Integral total;
  if(o.max_potential_evaluations-evaluations<cell_cost) {
    total.error=std::numeric_limits<Real>::infinity(); return total;
  }
  Cell first; evaluate(first,source,target); evaluations+=cell_cost;
  total.value=first.value; total.error=first.error;
  std::priority_queue<Cell> cells; cells.push(first);
  while(true) {
    const Real tolerance=absolute_tolerance+o.relative_tolerance*std::abs(total.value);
    if(std::isfinite(total.value) && total.value>0 && total.error<=tolerance) {
      total.converged=true; return total;
    }
    if(cells.size()>=o.max_cells ||
       o.max_potential_evaluations-evaluations<2*cell_cost) return total;
    Cell parent=cells.top(); cells.pop();
    const int d=parent.split_axis;
    const Real midpoint=(parent.lower[d]+parent.upper[d])/2;
    if(midpoint==parent.lower[d] || midpoint==parent.upper[d]) return total;
    Cell left=parent,right=parent;
    left.upper[d]=midpoint; right.lower[d]=midpoint;
    evaluate(left,source,target); evaluate(right,source,target);
    evaluations+=2*cell_cost;
    total.value+=left.value+right.value-parent.value;
    total.error=std::max(Real(0),total.error+left.error+right.error-parent.error);
    cells.push(left);cells.push(right);
  }
}
} // namespace

IntegrationResult rectangular_inductance(const RectangularVolume &a,
    const RectangularVolume &b,const IntegrationOptions &o) {
  if(!std::isfinite(o.relative_tolerance) || o.relative_tolerance<=0 ||
     !std::isfinite(o.absolute_tolerance_h) || o.absolute_tolerance_h<0 ||
     !std::isfinite(o.permeability_h_per_m) || o.permeability_h_per_m<=0 ||
     o.max_cells<1)
    throw std::invalid_argument("Invalid finite-volume integration options");
  const Real scale=std::max({a.length_m,a.width_m,a.thickness_m,
                             b.length_m,b.width_m,b.thickness_m});
  if(!std::isfinite(scale) || scale<=0)
    throw std::invalid_argument("Invalid finite-volume geometry scale");
  const Box first=make_box(a,a.center_m,scale),second=make_box(b,a.center_m,scale);
  IntegrationResult result;
  const Real orientation=dot(first.axes[0],second.axes[0]);
  if(orientation==0) {result.converged=true;return result;}
  const Real factor=o.permeability_h_per_m/(4*std::acos(Real(-1)))*scale*
                    first.extent[0]*second.extent[0]*orientation;
  const Real tolerance=o.absolute_tolerance_h/std::abs(factor);
  // Split the total work budget evenly, so reciprocity is never omitted.
  auto half=o; half.max_potential_evaluations=o.max_potential_evaluations/2;
  // Reserve half the requested error budget for the separately measured
  // reciprocity discrepancy instead of spending it twice on directed integrals.
  half.relative_tolerance=o.relative_tolerance/2;
  std::size_t used_first=0,used_second=0;
  const auto forward=integrate(first,second,half,tolerance/2,used_first);
  const auto reverse=integrate(second,first,half,tolerance/2,used_second);
  result.potential_evaluations=used_first+used_second;
  result.inductance_h=static_cast<double>(factor*(forward.value+reverse.value)/2);
  result.reciprocity_difference_h=static_cast<double>(std::abs(factor)*
                                       std::abs(forward.value-reverse.value));
  result.estimated_error_h=static_cast<double>(std::abs(factor)*
      ((forward.error+reverse.error)/2+std::abs(forward.value-reverse.value)/2));
  result.converged=forward.converged && reverse.converged &&
      std::isfinite(result.inductance_h) &&
      std::isfinite(result.estimated_error_h) &&
      std::isfinite(result.reciprocity_difference_h) &&
      result.estimated_error_h<=o.absolute_tolerance_h+
                               o.relative_tolerance*std::abs(result.inductance_h);
  return result;
}
} // namespace spike::peec::volume
