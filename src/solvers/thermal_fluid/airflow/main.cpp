// SPDX-License-Identifier: Apache-2.0
#include "cavity.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if(argc!=5) throw std::invalid_argument("usage: spike_native_airflow n Re max_steps steady_tolerance");
        auto number=[](const char* arg){size_t end=0;double v=std::stod(arg,&end);if(arg[end]!='\0' || !std::isfinite(v)) throw std::invalid_argument("invalid number");return v;};
        spike::airflow::Settings s;
        double n=number(argv[1]),steps=number(argv[3]);
        if(n<8 || n>128 || steps<1 || steps>200000 || n!=static_cast<int>(n) || steps!=static_cast<int>(steps)) throw std::invalid_argument("invalid integer setting");
        s.n=static_cast<int>(n);s.reynolds=number(argv[2]);s.max_steps=static_cast<int>(steps);s.steady_tolerance=number(argv[4]);
        auto r=spike::airflow::solve_cavity(s);
        std::cout<<std::setprecision(17)<<"{\"schema\":\"spike-native-cavity-v1\",\"status\":\""<<(r.converged?"converged":"failed_to_converge")
          <<"\",\"n\":"<<s.n<<",\"reynolds\":"<<s.reynolds<<",\"steps\":"<<r.steps<<",\"time\":"<<r.time
          <<",\"dt\":"<<r.dt<<",\"divergence_linf\":"<<r.divergence<<",\"steady_rate_linf\":"<<r.steady_rate
          <<",\"poisson_residual_linf\":"<<r.poisson_residual;
        auto array=[](const char* name,const std::vector<double>& a){std::cout<<",\""<<name<<"\":[";for(size_t i=0;i<a.size();++i){if(i)std::cout<<',';std::cout<<a[i];}std::cout<<']';};
        array("u",r.u);array("v",r.v);array("pressure",r.pressure);
        std::cout<<"}\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<"native airflow: "<<e.what()<<'\n';return 2;}
}
