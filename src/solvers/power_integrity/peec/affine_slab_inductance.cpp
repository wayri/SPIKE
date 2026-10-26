// SPDX-License-Identifier: Apache-2.0
// Independently derived displacement/thickness reduction; see
// docs/validation/PEEC_AFFINE_SLAB_KERNEL_20261019.md.
#include "affine_slab_inductance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <stdexcept>
#include <vector>

namespace spike::peec::affine {
namespace {
using Real = long double;
using P = std::array<Real,2>;
using V = std::array<Real,3>;
using Polygon = std::vector<P>;
P add(P a,P b) {return {a[0]+b[0],a[1]+b[1]};}
P sub(P a,P b) {return {a[0]-b[0],a[1]-b[1]};}
P mul(P a,Real s) {return {a[0]*s,a[1]*s};}
Real cross(P a,P b) {return a[0]*b[1]-a[1]*b[0];}
struct Field {std::array<P,3> p;std::array<V,3> b;};
Field field(const TrianglePrism& input,P origin) {
  Field f{};
  for(std::size_t i=0;i<3;++i) {
    f.p[i]=sub({input.vertices_m[i][0],input.vertices_m[i][1]},origin);
    for(std::size_t k=0;k<3;++k)f.b[i][k]=input.density_per_a[i][k];
  }
  return f;
}
V evaluate_field(const Field& f,P x) {
  const auto e1=sub(f.p[1],f.p[0]),e2=sub(f.p[2],f.p[0]),d=sub(x,f.p[0]);
  const Real det=cross(e1,e2),l1=cross(d,e2)/det,l2=cross(e1,d)/det;
  V value{};
  for(std::size_t k=0;k<3;++k)
    value[k]=(1-l1-l2)*f.b[0][k]+l1*f.b[1][k]+l2*f.b[2][k];
  return value;
}
Polygon clip(const Polygon& p,P origin,P direction,int sign) {
  Polygon out;
  if(p.empty())return out;
  auto previous=p.back();Real previous_side=sign*cross(direction,sub(previous,origin));
  for(const auto& current:p) {
    const Real side=sign*cross(direction,sub(current,origin));
    if((side>=0)!=(previous_side>=0)) {
      const Real t=previous_side/(previous_side-side);
      out.push_back(add(previous,mul(sub(current,previous),t)));
    }
    if(side>=0)out.push_back(current);
    previous=current;previous_side=side;
  }
  return out;
}
Real twice_area(const Polygon& p) {
  if(p.size()<3)return 0;
  Real result=0;
  for(std::size_t i=1;i+1<p.size();++i)
    result+=cross(sub(p[i],p[0]),sub(p[i+1],p[0]));
  return result;
}
Polygon difference_hull(const Field& a,const Field& b) {
  Polygon points;
  for(auto x:a.p)for(auto y:b.p)points.push_back(sub(x,y));
  std::sort(points.begin(),points.end());
  points.erase(std::unique(points.begin(),points.end()),points.end());
  Polygon hull;
  for(auto p:points) {
    while(hull.size()>1 && cross(sub(hull.back(),hull[hull.size()-2]),sub(p,hull.back()))<=0)
      hull.pop_back();
    hull.push_back(p);
  }
  const auto lower=hull.size();
  for(std::size_t i=points.size()-1;i-->0;) {
    const auto p=points[i];
    while(hull.size()>lower && cross(sub(hull.back(),hull[hull.size()-2]),sub(p,hull.back()))<=0)
      hull.pop_back();
    hull.push_back(p);
  }
  hull.pop_back();return hull;
}
std::vector<Polygon> displacement_partition(const Field& a,const Field& b) {
  std::vector<Polygon> regions{difference_hull(a,b)};
  const Real initial_area=twice_area(regions.front());
  // Overlap vertices change formulas only when an input vertex crosses a
  // translated opposite edge. Split on all 18 such lines before cubature.
  for(std::size_t edge=0;edge<3;++edge)for(std::size_t vertex=0;vertex<3;++vertex)
    for(int which=0;which<2;++which) {
      const P direction=which?sub(a.p[(edge+1)%3],a.p[edge]):sub(b.p[(edge+1)%3],b.p[edge]);
      const P origin=which?sub(a.p[edge],b.p[vertex]):sub(a.p[vertex],b.p[edge]);
      std::vector<Polygon> next;
      for(const auto& region:regions) {
        bool positive=false,negative=false;
        for(auto p:region) {
          const Real side=cross(direction,sub(p,origin));
          positive=positive||side>0;negative=negative||side<0;
        }
        if(positive && negative) {
          for(int sign:{-1,1}) {
            auto piece=clip(region,origin,direction,sign);
            if(twice_area(piece)>0)next.push_back(std::move(piece));
          }
        }else next.push_back(region);
      }
      if(next.size()>512)throw std::runtime_error("Affine slab displacement partition limit");
      regions=std::move(next);
    }
  Real retained_area=0;
  for(const auto& region:regions)retained_area+=twice_area(region);
  if(!(initial_area>0) || std::abs(retained_area-initial_area)>1e-11L*initial_area)
    throw std::runtime_error("Affine displacement partition changed integration area");
  return regions;
}
Real overlap_moment(const Field& a,const Field& b,P displacement) {
  Polygon overlap(a.p.begin(),a.p.end());
  for(std::size_t i=0;i<3 && !overlap.empty();++i)
    overlap=clip(overlap,add(b.p[i],displacement),sub(b.p[(i+1)%3],b.p[i]),1);
  Real integral=0;
  // Three symmetric barycentric samples integrate degree-two products exactly.
  for(std::size_t i=1;i+1<overlap.size();++i) {
    const std::array<P,3> triangle{overlap[0],overlap[i],overlap[i+1]};
    const Real area=cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]))/2;
    if(area<0)throw std::runtime_error("Inverted affine overlap moment triangle");
    for(std::size_t q=0;q<3;++q) {
      P point{};
      for(std::size_t j=0;j<3;++j)point=add(point,mul(triangle[j],j==q?2.0L/3:1.0L/6));
      const auto av=evaluate_field(a,point),bv=evaluate_field(b,sub(point,displacement));
      Real product=0;for(std::size_t k=0;k<3;++k)product+=av[k]*bv[k];
      integral+=area*product/3;
    }
  }
  return integral;
}
std::vector<std::pair<Real,Real>> gauss(int n) {
  std::vector<std::pair<Real,Real>> rule;
  for(int i=0;i<n;++i) {
    Real x=std::cos(std::acos(-1.0L)*(i+0.75L)/(n+0.5L)),d=0;
    for(int iteration=0;iteration<40;++iteration) {
      Real p=1,old=0;
      for(int k=1;k<=n;++k) {const Real next=((2*k-1)*x*p-(k-1)*old)/k;old=p;p=next;}
      d=n*(x*p-old)/(x*x-1);
      const Real delta=p/d;x-=delta;
      if(std::abs(delta)<4*std::numeric_limits<Real>::epsilon())break;
    }
    rule.push_back({(1+x)/2,1/((1-x*x)*d*d)});
  }
  return rule;
}
struct Sector {P origin,a,b;Real determinant;};
struct Cell {
  Sector sector;Real u0=0,u1=1,v0=0,v1=1,value=0,error=0;
  unsigned depth=0;
  bool operator<(const Cell& other)const{return error<other.error;}
};
Real integrand(const Field& a,const Field& b,Real thickness,const Sector& sector,Real u,Real v) {
  const P ray=add(mul(sub(sector.a,sector.origin),1-v),mul(sub(sector.b,sector.origin),v));
  const P d=add(sector.origin,mul(ray,u*u));
  const Real rho=std::hypot(d[0],d[1]);
  if(!(rho>0))throw std::runtime_error("Affine slab cubature encountered singular sample");
  // Exact double-z integral. Rationalization prevents far/thin cancellation.
  const Real kernel=2*(thickness*std::asinh(thickness/rho)-
      thickness*thickness/(std::hypot(rho,thickness)+rho));
  return 2*u*u*u*sector.determinant*kernel*overlap_moment(a,b,d);
}
void evaluate(Cell& cell,const Field& a,const Field& b,Real thickness,Real factor) {
  static const auto low=gauss(4),high=gauss(8);
  Real coarse=0,fine=0,magnitude=0;
  for(int level=0;level<2;++level) {
    const auto& rule=level?high:low;
    for(auto [x,wx]:rule)for(auto [y,wy]:rule) {
      const Real value=wx*wy*integrand(a,b,thickness,cell.sector,
          cell.u0+(cell.u1-cell.u0)*x,cell.v0+(cell.v1-cell.v0)*y);
      if(level) {fine+=value;magnitude+=std::abs(value);}else coarse+=value;
    }
  }
  const Real weight=factor*(cell.u1-cell.u0)*(cell.v1-cell.v0);
  cell.value=weight*fine;
  cell.error=weight*(8*std::abs(fine-coarse)+512*std::numeric_limits<double>::epsilon()*magnitude);
  if(!std::isfinite(cell.value)||!std::isfinite(cell.error))
    throw std::overflow_error("Affine slab quadrature overflow");
}
double output(Real value) {
  const double result=static_cast<double>(value);
  if(!std::isfinite(result)||(value!=0 && result==0))
    throw std::overflow_error("Affine slab result outside double range");
  return result;
}
} // namespace

SlabResult same_slab_mutual(const TrianglePrism& first,const TrianglePrism& second,
                           const SlabOptions& options) {
  // Reuse the established geometry/conditioning validation, not its integral.
  (void)integrated_current(first);(void)integrated_current(second);
  if(first.lower_z_m!=second.lower_z_m || first.upper_z_m!=second.upper_z_m)
    throw std::invalid_argument("Affine same-slab integral requires identical z intervals");
  if(!std::isfinite(options.absolute_tolerance_h)||options.absolute_tolerance_h<=0 ||
     !std::isfinite(options.relative_tolerance)||options.relative_tolerance<0 ||
     options.relative_tolerance>=1 || !std::isfinite(options.permeability_h_per_m)||
     options.permeability_h_per_m<=0 || options.maximum_evaluations<1 ||
     options.maximum_evaluations>10000000 || options.maximum_cells<1 || options.maximum_cells>65536)
    throw std::invalid_argument("Invalid affine slab tolerance or resource limits");
  const TrianglePrism* ap=&first;const TrianglePrism* bp=&second;
  if(bp->vertices_m<ap->vertices_m || (bp->vertices_m==ap->vertices_m && bp->density_per_a<ap->density_per_a))
    std::swap(ap,bp);
  const P origin{ap->vertices_m[0][0],ap->vertices_m[0][1]};
  const Field a=field(*ap,origin),b=field(*bp,origin);
  const auto regions=displacement_partition(a,b);
  const Real thickness=Real(first.upper_z_m)-first.lower_z_m;
  const Real factor=options.permeability_h_per_m/(4*std::acos(-1.0L));
  std::vector<Sector> sectors;
  for(const auto& region:regions) {
    P center{};bool contains_zero=true;
    for(std::size_t i=0;i<region.size();++i) {
      center=add(center,region[i]);
      if(cross(sub(region[(i+1)%region.size()],region[i]),mul(region[i],-1))<0)
        contains_zero=false;
    }
    center=contains_zero?P{}:mul(center,1.0L/region.size());
    for(std::size_t i=0;i<region.size();++i) {
      Sector sector{center,region[i],region[(i+1)%region.size()],0};
      sector.determinant=cross(sub(sector.a,center),sub(sector.b,center));
      if(sector.determinant>0)sectors.push_back(sector);
    }
  }
  SlabResult result;result.displacement_regions=regions.size();
  if(sectors.size()>options.maximum_cells || sectors.size()>options.maximum_evaluations/80) {
    result.estimated_error_h=std::numeric_limits<double>::max();return result;
  }
  std::priority_queue<Cell> queue;Real value=0,error=0;
  for(auto sector:sectors) {
    Cell cell{sector};evaluate(cell,a,b,thickness,factor);
    value+=cell.value;error+=cell.error;queue.push(cell);result.evaluations+=80;
  }
  while(true) {
    result.inductance_h=output(value);result.estimated_error_h=output(error);
    if(error<=options.absolute_tolerance_h+options.relative_tolerance*std::abs(value)) {
      result.converged=true;return result;
    }
    if(queue.size()>=options.maximum_cells || result.evaluations+160>options.maximum_evaluations)
      return result;
    const auto parent=queue.top();queue.pop();auto left=parent,right=parent;
    if(parent.depth%2==0) {left.u1=(parent.u0+parent.u1)/2;right.u0=left.u1;}
    else {left.v1=(parent.v0+parent.v1)/2;right.v0=left.v1;}
    if(left.u0==left.u1 || left.v0==left.v1 || right.u0==right.u1 || right.v0==right.v1)
      return result;
    ++left.depth;++right.depth;evaluate(left,a,b,thickness,factor);evaluate(right,a,b,thickness,factor);
    value+=left.value+right.value-parent.value;
    error=std::max(Real(0),error-parent.error)+left.error+right.error;
    queue.push(left);queue.push(right);result.evaluations+=160;
  }
}
} // namespace spike::peec::affine
