// SPDX-License-Identifier: Apache-2.0
#include "cavity.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

static void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
int main() {
    using namespace spike::airflow;
    constexpr double pi=3.14159265358979323846;
    double prior_error=0;
    for(int n:{8,16,32,64}) {
        std::vector<double> p(n*n),rhs(n*n),solved;
        for(int j=0;j<n;++j) for(int i=0;i<n;++i) {
            int k=j*n+i;
            p[k]=std::cos(pi*(i+.5)/n)*std::cos(2*pi*(j+.5)/n);
            rhs[k]=5*pi*pi*p[k];
        }
        auto ap=negative_laplacian(p,n);
        double operator_error=0;
        for(size_t k=0;k<p.size();++k)operator_error=std::max(operator_error,std::abs(ap[k]-rhs[k]));
        if(prior_error)require(prior_error/operator_error>3.6,"pressure operator lost second order convergence");
        prior_error=operator_error;
        const double residual=solve_pressure(rhs,n,solved,1e-9);
        require(residual<4e-9,"pressure solve residual");
        const double eigenvalue=4*n*n*(std::pow(std::sin(pi/(2*n)),2)+std::pow(std::sin(pi/n),2));
        for(size_t k=0;k<p.size();++k)
            require(std::abs(solved[k]-rhs[k]/eigenvalue)<1e-10,"independent discrete cosine oracle");
        std::cout<<"n="<<n<<" laplacian_error="<<operator_error<<" pressure_residual="<<residual<<'\n';
    }
    bool rejected=false;
    try {std::vector<double> p;solve_pressure(std::vector<double>(64,1),8,p,1e-9);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"incompatible pressure RHS admitted");
    Settings quiet;quiet.n=8;quiet.lid=0;
    auto zero=solve_cavity(quiet);
    require(zero.converged && zero.divergence==0 && zero.steady_rate==0,"rest state not preserved");
    Settings short_run;short_run.n=8;short_run.max_steps=1;
    auto partial=solve_cavity(short_run);
    require(!partial.converged && partial.u.empty() && partial.pressure.empty(),"unconverged fields admitted");
    std::vector<double> center;
    for(int n:{16,32,64}) {
        Settings s;s.n=n;
        auto result=solve_cavity(s);
        require(result.converged,"cavity failed to converge");
        require(result.divergence<1e-8,"cavity mass residual");
        const double uc=.25*(result.u[(n/2-1)*n+n/2-1]+result.u[(n/2-1)*n+n/2]+result.u[(n/2)*n+n/2-1]+result.u[(n/2)*n+n/2]);
        require(uc<-.15 && uc>-.3,"lid recirculation direction/magnitude");
        center.push_back(uc);
        std::cout<<"cavity n="<<n<<" steps="<<result.steps<<" center_u="<<uc<<" divergence="<<result.divergence<<" steady_rate="<<result.steady_rate<<'\n';
    }
    require(std::abs(center[2]-center[1])<std::abs(center[1]-center[0])*.6,"cavity refinement not reducing center velocity change");
    return 0;
}
