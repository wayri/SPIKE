// SPDX-License-Identifier: Apache-2.0
#include "cavity.hpp"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <stdexcept>

namespace spike::airflow {
namespace {
double maximum(const std::vector<double>& a) {
    double m = 0;
    for (double x : a) {
        if (!std::isfinite(x)) throw std::runtime_error("non-finite native state");
        m = std::max(m, std::abs(x));
    }
    return m;
}
void zero_mean(std::vector<double>& a) {
    double mean = std::accumulate(a.begin(), a.end(), 0.0) / a.size();
    for (double& x : a) x -= mean;
}
double dot(const std::vector<double>& a, const std::vector<double>& b) {
    return std::inner_product(a.begin(), a.end(), b.begin(), 0.0);
}
}

std::vector<double> negative_laplacian(const std::vector<double>& p, int n) {
    if (n < 2 || p.size() != static_cast<size_t>(n*n))
        throw std::invalid_argument("invalid pressure grid");
    std::vector<double> out(p.size());
    for (int j=0; j<n; ++j) for (int i=0; i<n; ++i) {
        int k=j*n+i;
        double sum=0;
        if(i>0) sum += p[k]-p[k-1];
        if(i<n-1) sum += p[k]-p[k+1];
        if(j>0) sum += p[k]-p[k-n];
        if(j<n-1) sum += p[k]-p[k+n];
        out[k]=sum*n*n;
    }
    return out;
}

double solve_pressure(const std::vector<double>& rhs, int n,
                      std::vector<double>& p, double tolerance) {
    if(n<2 || rhs.size()!=static_cast<size_t>(n*n) || !std::isfinite(tolerance) || tolerance<=0)
        throw std::invalid_argument("invalid pressure solve");
    maximum(rhs);
    p.assign(rhs.size(),0);
    std::vector<double> r=rhs;
    // Closed wall flux makes the RHS compatible to roundoff. A material
    // compatibility defect is rejected rather than hidden by mean removal.
    double mean=std::accumulate(r.begin(),r.end(),0.0)/r.size();
    if(std::abs(mean)>1e-11*std::max(1.0,maximum(rhs)))
        throw std::runtime_error("incompatible closed-domain mass flux");
    zero_mean(r);
    std::vector<double> d=r;
    double rr=dot(r,r);
    for(int iteration=0; iteration<8*n*n; ++iteration) {
        if(maximum(r)<=tolerance) {
            zero_mean(p);
            auto ap=negative_laplacian(p,n);
            for(size_t k=0;k<r.size();++k) r[k]=rhs[k]-ap[k];
            const double actual=maximum(r);
            if(actual<=tolerance*4) return actual;
            d=r; zero_mean(d); rr=dot(d,d);
        }
        auto ad=negative_laplacian(d,n);
        const double denom=dot(d,ad);
        if(!(denom>0) || !std::isfinite(denom))
            throw std::runtime_error("pressure CG breakdown");
        double alpha=rr/denom;
        for(size_t k=0;k<p.size();++k) {p[k]+=alpha*d[k]; r[k]-=alpha*ad[k];}
        zero_mean(r);
        double next=dot(r,r);
        double beta=next/rr;
        for(size_t k=0;k<p.size();++k) d[k]=r[k]+beta*d[k];
        rr=next;
    }
    throw std::runtime_error("pressure solve failed to converge");
}

Result solve_cavity(const Settings& s) {
    if(s.n<8 || s.n>128 || s.n%2 || !std::isfinite(s.reynolds) || s.reynolds<1 || s.reynolds>400 ||
       s.max_steps<1 || s.max_steps>200000 || !std::isfinite(s.steady_tolerance) ||
       s.steady_tolerance<1e-10 || s.steady_tolerance>1e-3 || (s.lid!=0 && s.lid!=1))
        throw std::invalid_argument("unsupported cavity settings");
    const int n=s.n, stride=n+2;
    const double h=1.0/n, nu=1.0/s.reynolds;
    auto ix=[stride](int i,int j){return j*stride+i;};
    std::vector<double> u(stride*stride),v(u.size()),p(n*n),rhs(n*n),phi;
    Result result;
    int settled=0;
    for(int step=1;step<=s.max_steps;++step) {
        // u(i,j)=(i*h,(j-.5)*h), v(i,j)=((i-.5)*h,j*h).
        // Normal wall faces remain zero; odd reflection imposes tangential no slip.
        for(int i=0;i<=n;++i) {u[ix(i,0)]=-u[ix(i,1)];u[ix(i,n+1)]=2*s.lid-u[ix(i,n)];}
        for(int j=0;j<=n;++j) {v[ix(0,j)]=-v[ix(1,j)];v[ix(n+1,j)]=-v[ix(n,j)];}
        const double speed=std::max({1.0,maximum(u),maximum(v)});
        const double dt=std::min(.15*h*h/nu,.2*h/speed);
        auto us=u,vs=v;
        for(int j=1;j<=n;++j) for(int i=1;i<n;++i) {
            const int k=ix(i,j);
            const double east=.5*(u[k]+u[ix(i+1,j)]),west=.5*(u[k]+u[ix(i-1,j)]);
            const double north=.25*(u[k]+u[ix(i,j+1)])*(v[ix(i,j)]+v[ix(i+1,j)]);
            const double south=.25*(u[k]+u[ix(i,j-1)])*(v[ix(i,j-1)]+v[ix(i+1,j-1)]);
            const double lap=(u[ix(i+1,j)]+u[ix(i-1,j)]+u[ix(i,j+1)]+u[ix(i,j-1)]-4*u[k])/(h*h);
            us[k]=u[k]+dt*(-(east*east-west*west+north-south)/h+nu*lap-(p[(j-1)*n+i]-p[(j-1)*n+i-1])/h);
        }
        for(int j=1;j<n;++j) for(int i=1;i<=n;++i) {
            const int k=ix(i,j);
            const double north=.5*(v[k]+v[ix(i,j+1)]),south=.5*(v[k]+v[ix(i,j-1)]);
            const double east=.25*(v[k]+v[ix(i+1,j)])*(u[ix(i,j)]+u[ix(i,j+1)]);
            const double west=.25*(v[k]+v[ix(i-1,j)])*(u[ix(i-1,j)]+u[ix(i-1,j+1)]);
            const double lap=(v[ix(i+1,j)]+v[ix(i-1,j)]+v[ix(i,j+1)]+v[ix(i,j-1)]-4*v[k])/(h*h);
            vs[k]=v[k]+dt*(-(north*north-south*south+east-west)/h+nu*lap-(p[j*n+i-1]-p[(j-1)*n+i-1])/h);
        }
        for(int j=1;j<=n;++j) for(int i=1;i<=n;++i)
            rhs[(j-1)*n+i-1]=-(us[ix(i,j)]-us[ix(i-1,j)]+vs[ix(i,j)]-vs[ix(i,j-1)])/(h*dt);
        result.poisson_residual=solve_pressure(rhs,n,phi,1e-9);
        for(int j=1;j<=n;++j) for(int i=1;i<n;++i)
            us[ix(i,j)]-=dt*(phi[(j-1)*n+i]-phi[(j-1)*n+i-1])/h;
        for(int j=1;j<n;++j) for(int i=1;i<=n;++i)
            vs[ix(i,j)]-=dt*(phi[j*n+i-1]-phi[(j-1)*n+i-1])/h;
        double change=0,divergence=0;
        for(int j=1;j<=n;++j) for(int i=1;i<=n;++i) {
            change=std::max({change,std::abs(us[ix(i,j)]-u[ix(i,j)]),std::abs(vs[ix(i,j)]-v[ix(i,j)])});
            divergence=std::max(divergence,std::abs(us[ix(i,j)]-us[ix(i-1,j)]+vs[ix(i,j)]-vs[ix(i,j-1)])/h);
        }
        maximum(us);maximum(vs);
        for(size_t k=0;k<p.size();++k) p[k]+=phi[k];
        zero_mean(p);maximum(p);
        u.swap(us);v.swap(vs);
        result.steps=step;result.time+=dt;result.dt=dt;
        result.divergence=divergence;result.steady_rate=change/dt;
        if(divergence>1e-7) throw std::runtime_error("projection mass conservation failed");
        settled=(result.steady_rate<s.steady_tolerance)?settled+1:0;
        if(settled>=10) {result.converged=true;break;}
    }
    // Only converged fields can escape the solver's accepted-result boundary.
    if(result.converged) {
        result.u.resize(n*n);result.v.resize(n*n);result.pressure=p;
        for(int j=1;j<=n;++j) for(int i=1;i<=n;++i) {
            const int k=(j-1)*n+i-1;
            result.u[k]=.5*(u[ix(i,j)]+u[ix(i-1,j)]);
            result.v[k]=.5*(v[ix(i,j)]+v[ix(i,j-1)]);
        }
    }
    return result;
}
}
