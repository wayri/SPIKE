// SPDX-License-Identifier: Apache-2.0
#include "cht.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace spike::airflow {
namespace {
struct Row {
    double diagonal = 0, source = 0;
    std::array<int,4> neighbor{{-1,-1,-1,-1}};
    std::array<double,4> coefficient{};
};
void bounded(double value,double lower,double upper) {
    if(!std::isfinite(value) || value<lower || value>upper)
        throw std::invalid_argument("unsupported CHT setting");
}
}

ChtResult solve_cht(const ChtSettings& s) {
    const int n=s.flow.n;
    if(n<8 || n>64 || n%4 || s.max_thermal_iterations<1 ||
       s.max_thermal_iterations>200000)
        throw std::invalid_argument("unsupported CHT grid/iteration limit");
    bounded(s.peclet,0,5000);bounded(s.solid_k_ratio,.01,1e5);
    bounded(s.hot_k,1,10000);bounded(s.cold_k,1,10000);
    bounded(s.thermal_tolerance,1e-12,1e-4);
    if(s.hot_k<s.cold_k) throw std::invalid_argument("hot boundary below cold boundary");
    ChtResult r;
    r.flow=solve_cavity(s.flow);
    if(!r.flow.converged) return r;
    const int solid=n/4, rows=n+2*solid, count=n*rows;
    const double h=1.0/n, ks=s.solid_k_ratio;
    const double hot=(s.hot_k==s.cold_k)?0.0:1.0;
    auto conductivity=[&](int j){return j>=solid && j<solid+n ? 1.0 : ks;};
    std::vector<Row> stencil(count);
    for(int j=0;j<rows;++j) for(int i=0;i<n;++i) {
        const int p=j*n+i;
        auto& row=stencil[p];
        const std::array<int,4> ni{{i-1,i+1,i,i}}, nj{{j,j,j-1,j+1}};
        for(int d=0;d<4;++d) {
            if(ni[d]<0 || ni[d]>=n) continue; // Insulated vertical sides.
            if(nj[d]<0 || nj[d]>=rows) {
                row.diagonal+=2*ks;
                row.source+=2*ks*(nj[d]<0?hot:0);
                continue;
            }
            const double kp=conductivity(j),kn=conductivity(nj[d]);
            const double conductance=2*kp*kn/(kp+kn);
            double flux=0;
            if(j>=solid && j<solid+n && nj[d]>=solid && nj[d]<solid+n) {
                const int fj=j-solid;
                if(d==0) flux=-s.peclet*h*r.flow.face_u[fj*(n+1)+i];
                if(d==1) flux=s.peclet*h*r.flow.face_u[fj*(n+1)+i+1];
                if(d==2) flux=-s.peclet*h*r.flow.face_v[fj*n+i];
                if(d==3) flux=s.peclet*h*r.flow.face_v[(fj+1)*n+i];
            }
            row.neighbor[d]=nj[d]*n+ni[d];
            row.coefficient[d]=conductance+std::max(-flux,0.0);
            row.diagonal+=conductance+std::max(flux,0.0);
        }
    }
    std::vector<double> theta(count,hot*.5);
    auto balances=[&](){
        r.hot_flux=0;r.cold_flux=0;
        for(int i=0;i<n;++i) {
            r.hot_flux+=2*ks*(hot-theta[i]);
            r.cold_flux+=2*ks*theta[(rows-1)*n+i];
        }
        r.balance_raw=r.hot_flux-r.cold_flux;
        r.balance_relative=std::abs(r.balance_raw)/
            std::max({std::abs(r.hot_flux),std::abs(r.cold_flux),1e-30});
    };
    for(int iteration=1;iteration<=s.max_thermal_iterations;++iteration) {
        // Symmetric Gauss-Seidel traversals; bounded five-point storage, no fill.
        for(int pass=0;pass<2;++pass) for(int k=0;k<count;++k) {
            const int p=pass==0?k:count-1-k;
            const auto& row=stencil[p];
            double rhs=row.source;
            for(int d=0;d<4;++d) if(row.neighbor[d]>=0)
                rhs+=row.coefficient[d]*theta[row.neighbor[d]];
            theta[p]=rhs/row.diagonal;
            if(!std::isfinite(theta[p])) throw std::runtime_error("nonfinite thermal state");
        }
        r.thermal_iterations=iteration;r.thermal_residual=0;
        for(int p=0;p<count;++p) {
            const auto& row=stencil[p];
            double residual=row.diagonal*theta[p]-row.source;
            for(int d=0;d<4;++d) if(row.neighbor[d]>=0)
                residual-=row.coefficient[d]*theta[row.neighbor[d]];
            r.thermal_residual=std::max(r.thermal_residual,
                std::abs(residual)/std::max(1.0,row.diagonal));
        }
        balances();
        if(r.thermal_residual<=s.thermal_tolerance && r.balance_relative<=s.thermal_tolerance) {
            r.converged=true;break;
        }
    }
    if(!r.converged) {
        // No accepted fields, including flow, escape an incomplete coupled result.
        r.flow.u.clear();r.flow.v.clear();r.flow.pressure.clear();
        r.flow.face_u.clear();r.flow.face_v.clear();
        return r;
    }
    const auto limits=std::minmax_element(theta.begin(),theta.end());
    r.theta_min=*limits.first;r.theta_max=*limits.second;
    if(r.theta_min<-1e-8 || r.theta_max>hot+1e-8)
        throw std::runtime_error("thermal maximum principle failed");
    for(int i=0;i<n;++i) {
        for(int boundary=0;boundary<2;++boundary) {
            const int lower=(boundary==0?solid-1:solid+n-1)*n+i;
            const double kl=boundary==0?ks:1.0, ku=boundary==0?1.0:ks;
            const double flux=2*kl*ku/(kl+ku)*(theta[lower]-theta[lower+n]);
            const double face_temperature=theta[lower]-flux/(2*kl);
            auto& q=boundary==0?r.interface_bottom_flux:r.interface_top_flux;
            auto& t=boundary==0?r.interface_bottom_theta:r.interface_top_theta;
            q.push_back(flux);t.push_back(face_temperature);
        }
    }
    r.theta=std::move(theta);
    return r;
}
}
