// SPDX-License-Identifier: Apache-2.0
// Thin console transport for the original native equilibrium TCAD kernel.
#include "tcad_equilibrium.hpp"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {
double number(const std::string& text) {
  std::size_t used=0; const double value=std::stod(text,&used);
  if(used!=text.size() || !std::isfinite(value)) throw std::invalid_argument("expected a finite numeric argument");
  return value;
}
void array(std::ostream& out,const std::vector<double>& values) {
  out << '[';for(std::size_t i=0;i<values.size();++i){if(i)out<<',';out<<values[i];}out<<']';
}
std::string quoted(const std::string& value) {
  std::string out="\"";
  for(unsigned char c:value){if(c=='\\'||c=='\"')out+='\\';if(c>=32)out+=static_cast<char>(c);else out+=' ';}
  return out+'\"';
}
void field(std::ostream& out,const char* name,const std::vector<double>& values) {
  out<<",\n"<<quoted(name)<<':';array(out,values);
}
}

int main(int argc,char** argv) {
  try {
    spikes::tcad::Config config;
    config.length_m=2e-6;config.relative_permittivity=11.7;config.temperature_k=300;
    config.intrinsic_density_m3=1.45e16;config.grid_points=501;
    std::string profile="pn",doping_file,output;
    double density=1e22;
    for(int index=1;index<argc;++index) {
      const std::string option=argv[index];
      if(option=="--help") {
        std::cout<<"SPIKES TCAD: experimental 1D equilibrium Poisson-Boltzmann only\n"
          "--profile pn|uniform --density-m3 VALUE --length-m VALUE --grid N\n"
          "--epsilon-r VALUE --temperature-k VALUE --ni-m3 VALUE\n"
          "--doping-file FILE (one signed ND-NA density in m^-3 per grid node)\n"
          "--output FILE (new JSON file; refuses overwrites)\n"
          "No biased transport/I-V, process steps, quantum effects or physical qualification.\n";
        return 0;
      }
      if(index+1>=argc)throw std::invalid_argument("option requires a value");
      const std::string value=argv[++index];
      if(option=="--profile")profile=value;
      else if(option=="--density-m3")density=number(value);
      else if(option=="--length-m")config.length_m=number(value);
      else if(option=="--epsilon-r")config.relative_permittivity=number(value);
      else if(option=="--temperature-k")config.temperature_k=number(value);
      else if(option=="--ni-m3")config.intrinsic_density_m3=number(value);
      else if(option=="--grid"){
        const double count=number(value);
        if(count<3||count>100001||std::floor(count)!=count)throw std::invalid_argument("grid must be an integer in [3,100001]");
        config.grid_points=static_cast<int>(count);
      }
      else if(option=="--doping-file")doping_file=value;
      else if(option=="--output")output=value;
      else throw std::invalid_argument("unknown console option");
    }
    if(profile!="pn"&&profile!="uniform")throw std::invalid_argument("profile must be pn or uniform");
    if(density<0)throw std::invalid_argument("density-m3 must be nonnegative; use doping-file for signed values");
    config.net_doping_m3.resize(static_cast<std::size_t>(config.grid_points));
    if(doping_file.empty()) {
      for(int i=0;i<config.grid_points;++i)config.net_doping_m3[i]=
          profile=="uniform"?density:(2*i<config.grid_points-1?-density:(2*i>config.grid_points-1?density:0.));
    } else {
      if(std::filesystem::file_size(doping_file)>static_cast<std::uintmax_t>(config.grid_points)*129)
        throw std::invalid_argument("doping-file exceeds bounded input size");
      std::ifstream input(doping_file);if(!input)throw std::invalid_argument("cannot open doping-file");
      std::string token;
      for(double& value:config.net_doping_m3){if(!(input>>std::setw(129)>>token)||token.size()>128)throw std::invalid_argument("doping-file must contain exactly grid node densities");value=number(token);}
      if(input>>std::setw(129)>>token)throw std::invalid_argument("doping-file contains extra entries");
    }
    const auto result=spikes::tcad::solve(config);
    std::ostringstream json;json<<std::setprecision(17);
    json<<"{\n\"contract\":\"spikes/tcad-equilibrium/v1\",\"backend\":\"SPIKES C++\","
      "\"model_status\":\"experimental_unqualified\",\"converged\":"<<(result.converged?"true":"false")
      <<",\"status\":"<<quoted(result.status)<<",\"diagnostic\":"<<quoted(result.diagnostic)
      <<",\"accepted_iterations\":"<<result.accepted_iterations
      <<",\"temperature_k\":"<<config.temperature_k<<",\"relative_permittivity\":"<<config.relative_permittivity
      <<",\"intrinsic_density_m3\":"<<config.intrinsic_density_m3<<",\"length_m\":"<<config.length_m
      <<",\"grid_points\":"<<config.grid_points<<",\"thermal_voltage_v\":"<<result.thermal_voltage_v
      <<",\"residual_norm\":"<<result.residual_norm<<",\"residual_tolerance\":"<<config.residual_tolerance
      <<",\"residual_charge_c_per_m3\":"<<result.residual_charge_c_per_m3;
    field(json,"net_doping_m3",config.net_doping_m3);field(json,"x_m",result.x_m);
    field(json,"potential_v",result.potential_v);field(json,"electric_field_v_per_m",result.electric_field_v_per_m);
    field(json,"face_electric_field_v_per_m",result.face_electric_field_v_per_m);
    field(json,"electron_density_m3",result.electron_density_m3);field(json,"hole_density_m3",result.hole_density_m3);
    field(json,"charge_density_c_per_m3",result.charge_density_c_per_m3);field(json,"residual_history",result.residual_history);
    json<<",\"limitations\":[\"1D homogeneous material, isothermal, nondegenerate equilibrium only\","
      "\"No biased transport, current/I-V, process simulation, heterostructures, traps or quantum effects\","
      "\"Illustrative material inputs; no PDK or manufacturer qualification\"]\n}\n";
    if(output.empty())std::cout<<json.str();
    else {
      FILE* file=std::fopen(output.c_str(),"wx");if(!file)throw std::runtime_error("cannot create new output file (existing files are preserved)");
      const auto text=json.str();const bool written=std::fwrite(text.data(),1,text.size(),file)==text.size();
      const int closed=std::fclose(file);if(!written||closed!=0)throw std::runtime_error("output write failed");
    }
    return result.converged?0:3;
  } catch(const std::exception& error) {std::cerr<<"SPIKES TCAD error: "<<error.what()<<'\n';return 2;}
}
