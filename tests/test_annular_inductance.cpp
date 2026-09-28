// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "peec/annular_inductance.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

using namespace spike::peec::volume;
namespace {
void require(bool ok,const char *message) {if(!ok)throw std::runtime_error(message);}
bool close(double a,double b,double relative) {
  return std::abs(a-b)<=relative*std::max(std::abs(a),std::abs(b));
}
double evaluated(const CoaxialAnnulus &a,const CoaxialAnnulus &b,
                 AnnularIntegrationOptions options={}) {
  const auto r=coaxial_annular_inductance(a,b,options);
  std::cout<<std::setprecision(15)<<"L="<<r.inductance_h<<" error="
    <<r.estimated_error_h<<" evaluations="<<r.evaluations
    <<" converged="<<r.converged<<'\n';
  require(r.converged,"Annular integral did not converge");
  return r.inductance_h;
}
// Independent fixed-order oracle: unpartitioned radial square, linear angle,
// no adaptive production integration or transformed domain. Converges more
// slowly near the self logarithm; retain two orders to quantify that drift.
double self_reference(const CoaxialAnnulus &a,int order) {
  using Real=long double;
  const Real pi=std::acos(-1.0L);
  std::vector<std::pair<Real,Real>> rule(static_cast<std::size_t>(order));
  for(int i=0;i<(order+1)/2;++i) {
    Real x=std::cos(pi*(i+.75L)/(order+.5L)),derivative=0;
    for(int iteration=0;iteration<40;++iteration) {
      Real p=1,previous=0;
      for(int k=1;k<=order;++k) {
        const Real next=((2*k-1)*x*p-(k-1)*previous)/k;
        previous=p;p=next;
      }
      derivative=order*(x*p-previous)/(x*x-1);
      const Real change=p/derivative;x-=change;
      if(std::abs(change)<4*std::numeric_limits<Real>::epsilon())break;
    }
    const Real weight=1/((1-x*x)*derivative*derivative);
    rule[static_cast<std::size_t>(i)]={(1-x)/2,weight};
    rule[static_cast<std::size_t>(order-1-i)]={(1+x)/2,weight};
  }
  const Real ri=a.inner_radius_m,dr=a.outer_radius_m-ri;
  const Real length=std::abs(Real(a.end_m)-a.start_m);
  const Real area=pi*dr*(a.outer_radius_m+ri);
  Real integral=0;
  for(const auto &[x,wx]:rule)for(const auto &[y,wy]:rule)
    for(const auto &[u,wu]:rule) {
      const Real r=ri+dr*x,s=ri+dr*y;
      const Real rho=std::hypot(r-s,2*std::sqrt(r*s)*std::sin(pi*u/2));
      const Real longitudinal=2*(length*std::asinh(length/rho)-
                                 std::hypot(length,rho)+rho);
      integral+=wx*wy*wu*r*s*longitudinal;
    }
  return static_cast<double>(integral*dr*dr*pi*4*pi*1e-7L/(area*area));
}

// Independent direct six-coordinate volume quadrature. No Legendre expansion,
// analytic moments, or production geometry transform is used by this oracle.
double separated_reference(const CoaxialAnnulusVolume &a,
                           const CoaxialAnnulusVolume &b,int angular_order) {
  struct Point { std::array<long double,3> x;long double w; };
  const auto nodes=[&](const CoaxialAnnulusVolume &v) {
    constexpr long double x[]={-.90617984593866399280L,-.53846931010568309104L,
        0,.53846931010568309104L,.90617984593866399280L};
    constexpr long double w[]={.23692688505618908751L,.47862867049936646804L,
        .56888888888888888889L,.47862867049936646804L,.23692688505618908751L};
    std::array<long double,3> e{},f{};
    int least=0;
    for(int k=1;k<3;++k)if(std::abs(v.direction[k])<std::abs(v.direction[least]))least=k;
    e[(least+1)%3]=v.direction[(least+2)%3];
    e[(least+2)%3]=-v.direction[(least+1)%3];
    const auto norm=std::sqrt(e[0]*e[0]+e[1]*e[1]+e[2]*e[2]);
    for(int k=0;k<3;++k)e[k]/=norm;
    for(int k=0;k<3;++k)f[k]=v.direction[(k+1)%3]*e[(k+2)%3]-v.direction[(k+2)%3]*e[(k+1)%3];
    std::vector<Point> points;
    for(int i=0;i<5;++i)for(int j=0;j<5;++j)for(int k=0;k<angular_order;++k) {
      const long double r=(v.outer_radius_m+v.inner_radius_m)/2+
          (v.outer_radius_m-v.inner_radius_m)*x[i]/2;
      const long double angle=2*std::acos(-1.0L)*(k+.25L)/angular_order;
      Point p{};p.w=w[i]*w[j]*r/(2*(v.outer_radius_m+v.inner_radius_m)*angular_order);
      // Radial normalized Gauss weight is w*r/(ro+ri); axial is w/2.
      for(int d=0;d<3;++d)p.x[d]=v.center_m[d]+r*(e[d]*std::cos(angle)+f[d]*std::sin(angle))+
          v.direction[d]*v.length_m*x[j]/2;
      points.push_back(p);
    }
    return points;
  };
  const auto first=nodes(a),second=nodes(b);
  long double sum=0,alignment=0;
  for(int k=0;k<3;++k)alignment+=static_cast<long double>(a.direction[k])*b.direction[k];
  for(const auto &p:first)for(const auto &q:second) {
    long double distance2=0;
    for(int k=0;k<3;++k)distance2+=(p.x[k]-q.x[k])*(p.x[k]-q.x[k]);
    sum+=p.w*q.w/std::sqrt(distance2);
  }
  return static_cast<double>(1e-7L*a.length_m*b.length_m*alignment*sum);
}
}
int main() {
  try {
    // Geometry-only regression extracted from pinned Marble v1.4.4. Oracle:
    // independent unsplit radial/angle Gauss rules, analytic longitudinal
    // integration, N=96/192 give self 20.6942715319/20.6942054861 pH and
    // adjacent mutual 11.7549511624/11.7549511472 pH. No matrix repair.
    const CoaxialAnnulus a{0,.140454e-3,.076e-3,.101e-3};
    auto b=a;b.start_m=a.end_m;b.end_m=2*a.end_m;
    const double self=evaluated(a,a), mutual=evaluated(a,b);
    require(close(self,20.6942054861e-12,1e-5),"Marble annular self oracle");
    require(close(mutual,11.7549511472e-12,2e-6),"Marble adjacent annulus oracle");
    AnnularIntegrationOptions tight;tight.relative_tolerance=1e-7;
    tight.absolute_tolerance_h=1e-19;tight.max_evaluations=4000000;
    const double refined=evaluated(a,a,tight);
    require(close(self,refined,2e-6),"Annular independent tolerance refinement");
    const double reference96=self_reference(a,96),reference192=self_reference(a,192);
    require(std::abs(reference192-refined)<std::abs(reference96-refined),
            "Independent annular oracle failed to refine");
    require(close(refined,reference192,2e-6),"Independent radial-angle self oracle");
    require(close(mutual,evaluated(b,a),1e-12),"Annular reciprocity");
    auto whole=a;whole.end_m=b.end_m;
    require(close(evaluated(whole,whole),2*self+2*mutual,3e-6),"Longitudinal subdivision");
    auto reverse=a;std::swap(reverse.start_m,reverse.end_m);
    require(close(evaluated(a,reverse),-self,1e-12),"Opposite current direction");
    auto overlap=a;overlap.start_m=a.end_m/2;overlap.end_m=1.5*a.end_m;
    const double overlap_l=evaluated(a,overlap);
    require(overlap_l>mutual&&overlap_l<self,"Overlapping volume energy");
    auto scaled=a;scaled.start_m*=1000;scaled.end_m*=1000;
    scaled.inner_radius_m*=1000;scaled.outer_radius_m*=1000;
    require(close(evaluated(scaled,scaled),1000*self,1e-12),"SI linear scaling");
    auto translated=a;translated.start_m+=1;translated.end_m+=1;
    require(close(evaluated(translated,translated),self,1e-10),"Translation invariance");
    auto other=a;other.inner_radius_m=.090e-3;other.outer_radius_m=.115e-3;
    require(close(evaluated(a,other),evaluated(other,a),3e-6),"Unequal overlapping radial supports");
    // The actual Marble barrel has eleven adjacent equal segments. Its Gram
    // matrix must admit positive-energy Cholesky pivots without modification.
    std::array<double,11> coupling{};coupling[0]=self;
    for(std::size_t k=1;k<coupling.size();++k) {
      auto segment=a;segment.start_m=static_cast<double>(k)*a.end_m;
      segment.end_m=static_cast<double>(k+1)*a.end_m;
      coupling[k]=evaluated(a,segment);
    }
    double series=0;
    std::array<std::array<double,11>,11> factor{};
    for(std::size_t i=0;i<11;++i)for(std::size_t j=0;j<=i;++j) {
      double entry=coupling[i-j];series+=i==j?entry:2*entry;
      for(std::size_t k=0;k<j;++k)entry-=factor[i][k]*factor[j][k];
      if(i==j) {require(entry>0,"Marble annular block has negative energy");
        factor[i][j]=std::sqrt(entry);}
      else factor[i][j]=entry/factor[j][j];
    }
    auto eleven=a;eleven.end_m=11*a.end_m;
    require(close(series,evaluated(eleven,eleven),3e-6),"Eleven-segment additivity");
    for(int bad=0;bad<4;++bad) {
      auto malformed=a;
      if(bad==0)malformed.inner_radius_m=0;
      if(bad==1)malformed.outer_radius_m=malformed.inner_radius_m;
      if(bad==2)malformed.end_m=malformed.start_m;
      if(bad==3)malformed.end_m=std::numeric_limits<double>::quiet_NaN();
      bool rejected=false;
      try {(void)coaxial_annular_inductance(malformed,a);}
      catch(const std::invalid_argument &) {rejected=true;}
      require(rejected,"Malformed annulus was accepted");
    }
    AnnularIntegrationOptions limited;limited.max_evaluations=1;
    require(!coaxial_annular_inductance(a,a,limited).converged,"Exhaustion accepted");
    limited.max_evaluations=2000000;limited.max_cells=1;
    require(!coaxial_annular_inductance(a,a,limited).converged,"Cell exhaustion accepted");
    CoaxialAnnulusVolume far_a;far_a.length_m=.14e-3;
    far_a.inner_radius_m=.076e-3;far_a.outer_radius_m=.101e-3;
    auto far_b=far_a;far_b.center_m={3e-3,1e-3,.7e-3};
    for(int orientation=0;orientation<3;++orientation) {
      if(orientation==1)far_b.direction={.6,0,.8};
      if(orientation==2)far_b.direction={-.6,0,-.8};
      const auto far=separated_annular_inductance(far_a,far_b);
      const auto oracle12=separated_reference(far_a,far_b,12);
      const auto oracle20=separated_reference(far_a,far_b,20);
      require(far.converged,"Separated annulus bound did not admit far pair");
      require(close(oracle12,oracle20,1e-12),"Independent direct oracle did not refine");
      require(std::abs(far.inductance_h-oracle20)<=far.estimated_error_h,
          "Separated annulus analytic remainder violated");
      const auto reciprocal=separated_annular_inductance(far_b,far_a);
      require(reciprocal.converged&&close(far.inductance_h,reciprocal.inductance_h,1e-14),
          "Separated annulus reciprocity");
      std::cout<<"far L="<<far.inductance_h<<" oracle="<<oracle20<<
          " bound="<<far.estimated_error_h<<'\n';
    }
    auto near_b=far_b;near_b.center_m={.2e-3,0,0};
    require(!separated_annular_inductance(far_a,near_b).converged,"Near pair admitted");
    // Close to the explicit q=1/4 admission ceiling, larger truncation is
    // allowed only when requested; compare all retained moments to direct
    // volume integration, not merely the asymptotic monopole.
    AnnularIntegrationOptions loose;loose.relative_tolerance=1e-3;
    auto edge=far_b;edge.center_m={1.01e-3,0,0};
    for(const auto &axis:std::vector<Vector>{{0,0,1},{.6,0,.8},{0,.8,.6},{.8,.6,0}}) {
      edge.direction=axis;
      const auto bounded=separated_annular_inductance(far_a,edge,loose);
      require(bounded.converged,"Permitted near-ceiling pair rejected");
      const auto reference=separated_reference(far_a,edge,20);
      require(std::abs(reference-bounded.inductance_h)<=bounded.estimated_error_h,
          "Near-ceiling multipole remainder violated");
      if(reference!=0)require(close(reference,separated_reference(far_a,edge,12),1e-10),
          "Near-ceiling independent quadrature drift");
    }
    auto malformed=far_a;malformed.inner_radius_m=0;
    bool malformed_rejected=false;
    try {(void)separated_annular_inductance(malformed,far_b);}
    catch(const std::invalid_argument &) {malformed_rejected=true;}
    require(malformed_rejected,"Invalid separated annulus admitted");
    AnnularIntegrationOptions strict;strict.relative_tolerance=1e-13;strict.absolute_tolerance_h=0;
    require(!separated_annular_inductance(far_a,far_b,strict).converged,"Unattainable tolerance admitted");
    strict.max_evaluations=0;
    require(!separated_annular_inductance(far_a,far_b,strict).converged,"Far pair work cap");
    auto scale_a=far_a,scale_b=far_b;
    for(auto *v:{&scale_a,&scale_b}) {
      v->length_m*=1000;v->inner_radius_m*=1000;v->outer_radius_m*=1000;
      for(auto &coordinate:v->center_m)coordinate*=1000;
    }
    require(close(separated_annular_inductance(scale_a,scale_b).inductance_h,
        1000*separated_annular_inductance(far_a,far_b).inductance_h,1e-12),"Far SI scaling");
    std::cout<<"Annular inductance checks passed\n";
    return 0;
  } catch(const std::exception &e) {
    std::cerr<<e.what()<<'\n';return 1;
  }
}
