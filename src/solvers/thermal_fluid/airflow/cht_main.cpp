// SPDX-License-Identifier: Apache-2.0
#include "cht.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if(argc!=12) throw std::invalid_argument(
            "usage: spike_native_cht n Re lid Pe solid_k_ratio hotK coldK max_flow_steps steady_tol thermal_tol max_thermal_iterations");
        auto number=[](const char* arg){
            size_t end=0;const double v=std::stod(arg,&end);
            if(arg[end]!='\0' || !std::isfinite(v)) throw std::invalid_argument("invalid finite number");
            return v;
        };
        auto integer=[&](const char* arg,int low,int high){
            const double v=number(arg);
            if(v<low || v>high || v!=std::floor(v)) throw std::invalid_argument("invalid integer");
            return static_cast<int>(v);
        };
        spike::airflow::ChtSettings s;
        s.flow.n=integer(argv[1],8,64);s.flow.reynolds=number(argv[2]);
        s.flow.lid=number(argv[3]);s.peclet=number(argv[4]);s.solid_k_ratio=number(argv[5]);
        s.hot_k=number(argv[6]);s.cold_k=number(argv[7]);s.flow.max_steps=integer(argv[8],1,200000);
        s.flow.steady_tolerance=number(argv[9]);s.thermal_tolerance=number(argv[10]);
        s.max_thermal_iterations=integer(argv[11],1,200000);
        const auto r=spike::airflow::solve_cht(s);
        std::cout<<std::setprecision(17)<<"{\"schema\":\"spike-native-cht-v1\",\"status\":\""
                 <<(r.converged?"converged":"failed_to_converge")<<"\"";
        auto value=[](const char* name,auto v){std::cout<<",\""<<name<<"\":"<<v;};
        value("n",s.flow.n);value("rows",3*s.flow.n/2);value("reynolds",s.flow.reynolds);
        value("lid",s.flow.lid);value("peclet",s.peclet);value("solid_k_ratio",s.solid_k_ratio);
        value("hot_k",s.hot_k);value("cold_k",s.cold_k);value("max_flow_steps",s.flow.max_steps);
        value("steady_tolerance",s.flow.steady_tolerance);value("thermal_tolerance",s.thermal_tolerance);
        value("max_thermal_iterations",s.max_thermal_iterations);
        value("flow_steps",r.flow.steps);value("flow_time",r.flow.time);value("flow_dt",r.flow.dt);
        value("divergence_linf",r.flow.divergence);value("steady_rate_linf",r.flow.steady_rate);
        value("poisson_residual_linf",r.flow.poisson_residual);
        value("thermal_iterations",r.thermal_iterations);value("thermal_residual_linf",r.thermal_residual);
        value("hot_flux",r.hot_flux);value("cold_flux",r.cold_flux);
        value("balance_raw",r.balance_raw);value("balance_relative",r.balance_relative);
        value("theta_min",r.theta_min);value("theta_max",r.theta_max);
        auto array=[](const char* name,const std::vector<double>& a){
            std::cout<<",\""<<name<<"\":[";
            for(size_t i=0;i<a.size();++i){if(i)std::cout<<',';std::cout<<a[i];}
            std::cout<<']';
        };
        array("theta",r.theta);array("u",r.flow.u);array("v",r.flow.v);array("pressure",r.flow.pressure);
        array("face_u",r.flow.face_u);array("face_v",r.flow.face_v);
        array("interface_bottom_theta",r.interface_bottom_theta);array("interface_top_theta",r.interface_top_theta);
        array("interface_bottom_flux",r.interface_bottom_flux);array("interface_top_flux",r.interface_top_flux);
        std::cout<<"}\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<"native CHT: "<<e.what()<<'\n';return 2;}
}
