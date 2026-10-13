// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// Original switched-state equations and synthetic data; no external code used.
// Behavioral synchronous PWM buck, NOT a qualified transistor/SPICE compact model.
#include "spikes/transient_session.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
constexpr double vin = 12.0, target = 5.0, inductance = 100e-6, capacitance = 100e-6;
constexpr double winding = .2, alpha = .02, load = 5.0, capacity = .01, thermal_r = 10.0;
constexpr double period = 50e-6, ron = .02, roff = 1e6;
constexpr std::size_t cycles = 400;
using State = std::array<double, 4>; // current A, output V, rise K, PI integral V*s
using Ledger = std::array<double, 7>; // source, winding, load, high, low, ambient, BE loss: J

void require(bool condition, const std::string &message) {
  if (!condition) throw std::runtime_error(message);
}
void near(double actual, double expected, double tolerance, const std::string &message) {
  require(std::isfinite(actual) && std::isfinite(expected) && std::abs(actual - expected) <= tolerance,
          message + " actual=" + std::to_string(actual) + " expected=" + std::to_string(expected));
}
double command(const State &x) {
  return std::clamp(target / vin + .04 * (target - x[1]) + 10.0 * x[3], .05, .95);
}
double distance(const State &a, const State &b) {
  double sum = 0;
  for (std::size_t j = 0; j < a.size(); ++j) {
    const double delta = (a[j] - b[j]) * (j == 3 ? 10.0 : 1.0);
    sum += delta * delta;
  }
  return std::sqrt(sum); // normalizers: 1 A, 1 V, 1 K, 0.1 V*s
}

// Independent switched physical ODE. Eliminate the two conducting branches
// by KCL: Vsw=(Vin*g_high-i)/(g_high+g_low). Gate 0/1 V is 50 transition
// widths from threshold, so the native tanh switch reaches exactly Ron/Roff.
State derivative(const State &x, bool high, double coefficient) {
  const double gh = 1.0 / (high ? ron : roff), gl = 1.0 / (high ? roff : ron);
  const double vsw = (vin * gh - x[0]) / (gh + gl);
  const double r = winding * (1 + coefficient * x[2]);
  return {(vsw - r * x[0] - x[1]) / inductance,
          (x[0] - x[1] / load) / capacitance,
          (r * x[0] * x[0] - x[2] / thermal_r) / capacity, 0};
}
State shift(State x, const State &k, double h) {
  for (std::size_t j = 0; j < 3; ++j) x[j] += h * k[j];
  return x;
}
struct Oracle { State final{}; std::vector<State> endpoints; };
Oracle switched_oracle(double maximum_dt, double coefficient) {
  Oracle result;
  auto &x = result.final;
  for (std::size_t cycle = 0; cycle < cycles; ++cycle) {
    const double duty = command(x);
    x[3] += period * (target - x[1]); // identical once-per-cycle sampled PI
    for (const bool high : {true, false}) {
      const double duration = period * (high ? duty : 1 - duty);
      const auto steps = static_cast<std::size_t>(std::ceil(duration / maximum_dt));
      const double h = duration / static_cast<double>(steps);
      for (std::size_t n = 0; n < steps; ++n) {
        const auto a = derivative(x, high, coefficient);
        const auto b = derivative(shift(x, a, h / 2), high, coefficient);
        const auto c = derivative(shift(x, b, h / 2), high, coefficient);
        const auto d = derivative(shift(x, c, h), high, coefficient);
        for (std::size_t j = 0; j < 3; ++j) x[j] += h * (a[j] + 2*b[j] + 2*c[j] + d[j]) / 6;
      }
    }
    result.endpoints.push_back(x);
  }
  return result;
}

spikes::Circuit circuit(double coefficient, bool reversed = false) {
  spikes::Circuit model;
  model.add_voltage_source("Vin", reversed ? "0" : "vin", reversed ? "vin" : "0", reversed ? -vin : vin);
  model.add_voltage_source("Vgh", reversed ? "0" : "gh", reversed ? "gh" : "0", 0);
  model.add_voltage_source("Vgl", reversed ? "0" : "gl", reversed ? "gl" : "0", reversed ? -1 : 1);
  spikes::VoltageControlledSwitchModel sw;
  sw.on_resistance_ohm = ron; sw.off_resistance_ohm = roff;
  sw.threshold_voltage_v = .5; sw.transition_voltage_v = .01;
  model.add_voltage_controlled_switch("Sh", "vin", "sw", "gh", "0", sw);
  model.add_voltage_controlled_switch("Sl", "sw", "0", "gl", "0", sw);
  spikes::ElectrothermalResistorModel copper;
  copper.resistance_ohm = winding; copper.temperature_coefficient_per_k = coefficient;
  copper.ambient_temperature_k = 300; copper.minimum_temperature_k = 300;
  copper.maximum_temperature_k = 400; copper.thermal_resistance_k_per_w = thermal_r;
  copper.thermal_capacitance_j_per_k = capacity;
  model.add_electrothermal_resistor("Rw", "sw", "coil", "theta", copper);
  model.add_inductor("L", "coil", "out", inductance, 0);
  model.add_capacitor("C", "out", "0", capacitance, 0);
  model.add_resistor("Rload", "out", "0", load);
  return model;
}
spikes::TransientOptions settings(bool sparse = false) {
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::backward_euler;
  options.max_steps = 2; // each session call is one event-contained BE interval
  options.nonlinear.absolute_tolerance = 1e-13;
  options.nonlinear.relative_tolerance = 1e-12;
  if (sparse) options.sparse_linear_threshold = 1;
  return options;
}

struct NativeRun {
  spikes::TransientSession session;
  State x{};
  Ledger energy{};
  double maximum_dt, coefficient;
  bool reversed;
  double max_electrical_error = 0, max_thermal_error = 0;
  double minimum_duty = 1, maximum_duty = 0;
  std::size_t edge_count = 0;
  NativeRun(double dt, double a, bool reverse = false, bool sparse = false)
      : session(circuit(a, reverse), settings(sparse)), maximum_dt(dt), coefficient(a), reversed(reverse) {}

  void step(double h, bool high) {
    const bool accepted = session.step(h);
    require(accepted, "PWM native step failed: " + session.message());
    State next{session.element_current("L"), session.node_voltage("out"), session.node_voltage("theta"), x[3]};
    for (const double value : next) require(std::isfinite(value), "nonfinite PWM state");
    require(next[2] >= 0 && next[2] <= 100, "winding material temperature envelope");
    const double gh = 1.0 / (high ? ron : roff), gl = 1.0 / (high ? roff : ron);
    near(session.node_voltage("sw"), (vin*gh-next[0])/(gh+gl), 1e-8, "finite-switch KCL oracle");
    near(session.node_voltage("gh"), high ? 1 : 0, 1e-12, "high gate command");
    near(session.node_voltage("gl"), high ? 0 : 1, 1e-12, "low gate command");
    const double source = -session.element_power("Vin"), heat = session.element_power("Rw");
    const double pload = session.element_power("Rload"), ph = session.element_power("Sh"), pl = session.element_power("Sl");
    require(heat >= 0 && pload >= 0 && ph >= 0 && pl >= 0, "negative dissipative power");
    near(session.element_power("Vgh"), 0, 1e-12, "ideal high gate has no physical drive loss model");
    near(session.element_power("Vgl"), 0, 1e-12, "ideal low gate has no physical drive loss model");
    near(heat, winding*(1+coefficient*next[2])*next[0]*next[0], 1e-8, "temperature-dependent winding loss");
    near(-source+heat+pload+ph+pl+session.element_power("L")+session.element_power("C"),
         0, 2e-8, "complete nine-element electrical power ledger");
    const double stored = .5*inductance*(next[0]*next[0]-x[0]*x[0]) + .5*capacitance*(next[1]*next[1]-x[1]*x[1]);
    const double defect = .5*inductance*std::pow(next[0]-x[0],2) + .5*capacitance*std::pow(next[1]-x[1],2);
    const double electrical_error = h*(source-heat-pload-ph-pl)-stored-defect;
    const double thermal_error = h*(heat-next[2]/thermal_r)-capacity*(next[2]-x[2]);
    near(electrical_error, 0, 5e-10, "PWM per-step electrical/BE energy");
    near(thermal_error, 0, 5e-10, "PWM per-step physical thermal energy");
    max_electrical_error = std::max(max_electrical_error, std::abs(electrical_error));
    max_thermal_error = std::max(max_thermal_error, std::abs(thermal_error));
    const Ledger change{h*source,h*heat,h*pload,h*ph,h*pl,h*next[2]/thermal_r,defect};
    for (std::size_t j=0;j<energy.size();++j) energy[j]+=change[j];
    x=next;
  }

  void cycle(std::size_t index) {
    const double duty=command(x);
    minimum_duty=std::min(minimum_duty,duty); maximum_duty=std::max(maximum_duty,duty);
    x[3]+=period*(target-x[1]);
    for (const bool high : {true,false}) {
      session.set_source_value("Vgh",high ? (reversed ? -1 : 1) : 0);
      session.set_source_value("Vgl",high ? 0 : (reversed ? -1 : 1));
      ++edge_count; // caller-controlled exact edge, never an averaged voltage source
      const double duration=period*(high ? duty : 1-duty);
      const auto steps=static_cast<std::size_t>(std::ceil(duration/maximum_dt));
      const double h=duration/static_cast<double>(steps);
      for(std::size_t n=0;n<steps;++n) step(h,high);
      const double expected=period*(static_cast<double>(index)+(high ? duty : 1.0));
      near(session.time_s(),expected,2e-12,"PWM gate edge time");
    }
  }

  void report() const {
    const double stored=.5*inductance*x[0]*x[0]+.5*capacitance*x[1]*x[1];
    near(energy[0]-energy[1]-energy[2]-energy[3]-energy[4]-stored-energy[6],0,1e-9,"PWM electrical cumulative energy");
    near(energy[1]-energy[5]-capacity*x[2],0,1e-9,"PWM thermal cumulative energy");
    near(energy[0]-energy[2]-energy[3]-energy[4]-energy[5]-capacity*x[2]-stored-energy[6],0,1e-9,"PWM combined energy");
    require(edge_count==2*cycles,"missing PWM events");
    require(minimum_duty>.05 && maximum_duty<.95,"unexpected PI saturation");
    require(std::abs(x[1]-target)<.035,"20ms end-of-cycle tracking exceeds 35mV");
    std::cout<<"PWM_RESULT dt_s="<<maximum_dt<<" alpha="<<coefficient<<" current_a="<<x[0]
      <<" voltage_v="<<x[1]<<" rise_k="<<x[2]<<" integral_v_s="<<x[3]
      <<" source_j="<<energy[0]<<" winding_j="<<energy[1]<<" load_j="<<energy[2]
      <<" high_switch_j="<<energy[3]<<" low_switch_j="<<energy[4]<<" ambient_j="<<energy[5]
      <<" numerical_j="<<energy[6]<<" electrical_storage_j="<<stored<<" thermal_storage_j="<<capacity*x[2]
      <<" max_electrical_error_j="<<max_electrical_error<<" max_thermal_error_j="<<max_thermal_error
      <<" edges="<<edge_count<<" steps="<<session.step_index()<<'\n';
  }
};

State run_native(double dt,double coefficient,bool replay) {
  NativeRun run(dt,coefficient);
  for(std::size_t c=0;c<cycles/2;++c) run.cycle(c);
  const auto checkpoint=run.session.checkpoint();
  const auto saved_x=run.x; const auto saved_energy=run.energy; const auto saved_edges=run.edge_count;
  if(replay) {
    // Check source controls themselves restore, without overwriting them with
    // the next cycle's commands. Native and controller checkpoints are distinct.
    require(run.session.step(dt),"checkpoint low-state probe");
    const double low_current=run.session.element_current("L");
    const double low_temperature=run.session.node_voltage("theta");
    run.session.restore(checkpoint);
    run.session.set_source_value("Vgh",1); run.session.set_source_value("Vgl",0);
    require(run.session.step(dt),"checkpoint changed-control probe");
    require(run.session.element_current("L")>low_current+.01,"changed gate did not affect native state");
    run.session.restore(checkpoint);
    require(run.session.step(dt),"checkpoint restored-control probe");
    near(run.session.node_voltage("gh"),0,1e-12,"restored high gate source");
    near(run.session.node_voltage("gl"),1,1e-12,"restored low gate source");
    near(run.session.element_current("L"),low_current,2e-9,"restored control electrical response");
    near(run.session.node_voltage("theta"),low_temperature,2e-9,"restored control thermal response");
    run.session.restore(checkpoint);
  }
  for(std::size_t c=cycles/2;c<cycles;++c) run.cycle(c);
  const auto first_x=run.x; const auto first_energy=run.energy;
  const auto first_steps=run.session.step_index();
  if(replay) {
    run.session.restore(checkpoint); run.x=saved_x; run.energy=saved_energy; run.edge_count=saved_edges;
    for(std::size_t c=cycles/2;c<cycles;++c) run.cycle(c);
    require(run.session.step_index()==first_steps,"checkpoint step count");
    for(std::size_t j=0;j<run.x.size();++j) near(run.x[j],first_x[j],2e-9,"PWM controller+native checkpoint replay");
    for(std::size_t j=0;j<run.energy.size();++j) near(run.energy[j],first_energy[j],1e-9,"PWM ledger checkpoint replay");
    std::cout<<"PWM_CHECKPOINT native_and_sampled_controller_replay=passed\n";
  }
  run.report(); return run.x;
}

void benchmark() {
  {
    // Seeding the independent gate can make the residual identically zero
    // while duplicate zero-volt branches still have indeterminate currents.
    // A predictor must not turn that singular circuit into a completed solve.
    spikes::Circuit singular;
    singular.add_voltage_source("Vgate","gate","0",1);
    singular.add_voltage_source("V1","n","0",0);
    singular.add_voltage_source("V2","n","0",0);
    singular.add_voltage_controlled_switch("S","n","0","gate","0");
    auto options=settings(); options.time_step_s=1e-6; options.stop_time_s=1e-6;
    const auto rejected=spikes::solve_transient(singular,options);
    require(!rejected.converged() && rejected.points().empty(),
            "source predictor must not admit singular zero-residual voltage branches");
  }
  for(const double duplicate_voltage : {vin,vin+1}) {
    auto duplicated=circuit(alpha);
    duplicated.add_voltage_source("Vparallel","vin","0",duplicate_voltage);
    auto options=settings(); options.time_step_s=1e-6; options.stop_time_s=1e-6;
    const auto rejected=spikes::solve_transient(duplicated,options);
    require(!rejected.converged() && rejected.points().empty(),
            "parallel redundant/conflicting source constraints must fail closed");
  }
  std::cout<<"PWM_PARALLEL_SOURCE_CONSTRAINTS rejected=passed\n";
  NativeRun ordinary(2e-6,alpha), reversed(2e-6,alpha,true), sparse(2e-6,alpha,false,true);
  for(std::size_t c=0;c<4;++c) {
    ordinary.cycle(c); reversed.cycle(c); sparse.cycle(c);
    require(distance(ordinary.x,reversed.x)<2e-9,"reversed grounded-source predictor changes physics");
    require(distance(ordinary.x,sparse.x)<2e-9,"sparse switch predictor changes physics");
    for(std::size_t j=0;j<ordinary.energy.size();++j) {
      near(ordinary.energy[j],reversed.energy[j],1e-9,"reversed source energy ledger");
      near(ordinary.energy[j],sparse.energy[j],1e-9,"sparse source energy ledger");
    }
  }
  require(sparse.session.diagnostics().sparse_numeric_factorizations > 0,
          "sparse predictor regression did not execute sparse backend");
  std::cout<<"PWM_SPARSE_DENSE_SWITCH_PREDICTOR equivalent=passed\n";
  std::cout<<"PWM_REVERSED_GROUNDED_SOURCES equivalent=passed\n";
  const auto reference=switched_oracle(1e-7,alpha), finer=switched_oracle(5e-8,alpha);
  for(std::size_t c=0;c<cycles;++c)
    require(distance(reference.endpoints[c],finer.endpoints[c])<1e-8,"switched RK4 oracle unresolved");
  std::cout<<"PWM_ORACLE current_a="<<reference.final[0]<<" voltage_v="<<reference.final[1]
           <<" rise_k="<<reference.final[2]<<" integral_v_s="<<reference.final[3]<<'\n';
  const std::array<double,3> steps{2e-6,1e-6,.5e-6};
  std::array<double,3> errors{}; State fine{};
  for(std::size_t j=0;j<steps.size();++j) {
    fine=run_native(steps[j],alpha,j==2); errors[j]=distance(fine,reference.final);
    std::cout<<"PWM_REFINEMENT dt_s="<<steps[j]<<" normalized_endpoint_error="<<errors[j]<<'\n';
    // Independent scalar sampled-BE precheck predicts ratios .58267,.54072.
    if(j>0) require(errors[j]/errors[j-1]>.4 && errors[j]/errors[j-1]<.7,"PWM first-order refinement trend");
  }
  require(errors.back()<.0025,"PWM finest-step error exceeds predeclared oracle gate");
  const auto cold=run_native(.5e-6,0,false);
  require(fine[2]>cold[2]+.002 && fine[1]<cold[1]-.0001,"winding electrothermal feedback absent");
}
} // namespace

int main() {
  std::cout<<std::setprecision(13);
  try { benchmark(); }
  catch(const std::exception &error) {
    std::cerr<<"Native PWM electrothermal reference FAILED: "<<error.what()<<'\n'; return 1;
  }
  std::cout<<"Native PWM electrothermal reference PASSED: finite behavioral switches, sampled PI, winding-only thermal feedback. "
             "No deadtime, gate charge, transistor switching loss, semiconductor thermal or hardware qualification; human numerical review required.\n";
  return 0;
}
