// SPDX-License-Identifier: Apache-2.0
#include "cht.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>

static void require(bool pass,const char* message) {
    if(!pass) throw std::runtime_error(message); // Active under NDEBUG/Release.
}
static void verify_interfaces(const spike::airflow::ChtSettings& s,
                              const spike::airflow::ChtResult& r) {
    const int n=s.flow.n;
    for(int b=0;b<2;++b) {
        const auto& flux=b==0?r.interface_bottom_flux:r.interface_top_flux;
        const auto& face=b==0?r.interface_bottom_theta:r.interface_top_theta;
        const double kl=b==0?s.solid_k_ratio:1, ku=b==0?1:s.solid_k_ratio;
        for(int i=0;i<n;++i) {
            const int lower=(b==0?n/4-1:5*n/4-1)*n+i;
            const double from_lower=2*kl*(r.theta[lower]-face[i]);
            const double into_upper=2*ku*(face[i]-r.theta[lower+n]);
            require(std::abs(from_lower-flux[i])<1e-11,"lower interface Fourier flux mismatch");
            require(std::abs(into_upper-flux[i])<1e-11,"upper interface Fourier flux mismatch");
        }
        const double total=std::accumulate(flux.begin(),flux.end(),0.0);
        require(std::abs(total-r.hot_flux)<2e-6,"interface/global energy disagreement");
    }
}
int main() {
    using namespace spike::airflow;
    // Independent continuous solution: constant flux and series layer resistances.
    for(int n:{8,16,32}) for(double ratio:{.1,1.0,10.0}) {
        ChtSettings s;s.flow.n=n;s.flow.lid=0;s.solid_k_ratio=ratio;
        s.thermal_tolerance=1e-11;
        const auto r=solve_cht(s);
        require(r.converged,"layer conduction did not converge");
        const double q=1/(1+.5/ratio);
        double error=0;
        for(int j=0;j<3*n/2;++j) {
            const double y=(j+.5)/n-.25;
            const double resistance=y<0?(y+.25)/ratio:
                y<1?.25/ratio+y:.25/ratio+1+(y-1)/ratio;
            const double exact=1-q*resistance;
            for(int i=0;i<n;++i) error=std::max(error,std::abs(r.theta[j*n+i]-exact));
        }
        require(error<2e-7,"independent three-layer temperature oracle");
        require(std::abs(r.hot_flux-q)<2e-7,"independent three-layer flux oracle");
        require(r.balance_relative<=s.thermal_tolerance,"global energy residual");
        verify_interfaces(s,r);
        std::cout<<"rest n="<<n<<" ratio="<<ratio<<" theta_error="<<error
                 <<" heat="<<r.hot_flux<<" iterations="<<r.thermal_iterations<<'\n';
    }
    ChtSettings uniform;uniform.flow.n=8;uniform.hot_k=uniform.cold_k=321;
    uniform.peclet=5000;uniform.solid_k_ratio=1e5;
    const auto constant=solve_cht(uniform);
    require(constant.converged && constant.hot_flux==0 && constant.cold_flux==0,
            "constant absolute temperature not preserved");
    for(double t:constant.theta) require(t==0,"constant theta changed");
    for(double v:constant.flow.face_u) require(std::isfinite(v),"nonfinite accepted MAC field");

    std::vector<double> heats;
    for(int n:{8,16,32}) {
        ChtSettings s;s.flow.n=n;s.peclet=10;s.solid_k_ratio=1;
        const auto r=solve_cht(s);
        require(r.converged,"moving-lid CHT failed");
        require(r.theta_min>=0 && r.theta_max<=1,"temperature range");
        require(r.hot_flux>2.0/3,"advection did not affect heat transfer");
        require(r.thermal_residual<=s.thermal_tolerance,"thermal algebraic residual");
        verify_interfaces(s,r);
        double mass=0;
        for(int j=0;j<n;++j) for(int i=0;i<n;++i)
            mass=std::max(mass,n*std::abs(r.flow.face_u[j*(n+1)+i+1]-r.flow.face_u[j*(n+1)+i]
                     +r.flow.face_v[(j+1)*n+i]-r.flow.face_v[j*n+i]));
        require(mass<1e-8,"MAC flux not divergence free");
        heats.push_back(r.hot_flux);
        std::cout<<"moving n="<<n<<" heat="<<r.hot_flux<<" residual="<<r.thermal_residual
                 <<" balance="<<r.balance_relative<<" iterations="<<r.thermal_iterations<<'\n';
    }
    require(std::abs(heats[2]-heats[1])<std::abs(heats[1]-heats[0]),
            "moving-lid heat refinement failed to reduce differences");
    ChtSettings cap;cap.flow.n=8;cap.max_thermal_iterations=1;
    const auto thermal_failure=solve_cht(cap);
    require(!thermal_failure.converged && thermal_failure.theta.empty() &&
            thermal_failure.flow.face_u.empty(),"thermal cap admitted partial fields");
    cap.flow.max_steps=1;
    const auto flow_failure=solve_cht(cap);
    require(!flow_failure.converged && flow_failure.theta.empty() &&
            flow_failure.flow.face_v.empty(),"flow cap admitted partial fields");
    for(int kind=0;kind<8;++kind) {
        ChtSettings bad;bad.flow.n=8;
        if(kind==0) bad.peclet=std::numeric_limits<double>::quiet_NaN();
        if(kind==1) bad.solid_k_ratio=std::numeric_limits<double>::infinity();
        if(kind==2) bad.hot_k=std::numeric_limits<double>::infinity();
        if(kind==3) bad.flow.n=10;
        if(kind==4) bad.thermal_tolerance=0;
        if(kind==5) bad.peclet=5001;
        if(kind==6) bad.solid_k_ratio=100001;
        if(kind==7) bad.hot_k=bad.cold_k-1;
        bool rejected=false;
        try{solve_cht(bad);}catch(const std::invalid_argument&){rejected=true;}
        require(rejected,"invalid CHT setting admitted");
    }
}
