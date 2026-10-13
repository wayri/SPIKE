// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// Independent synthetic analytical fixture; not a physical device qualification.
#include "spikes/transient_session.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using Method = spikes::TransientIntegrationMethod;
constexpr double resistance = 2.0; // ohm at ambient
constexpr double alpha = 0.02; // 1/K
constexpr double capacity = 2.0; // J/K
constexpr double thermal_resistance = 1.0; // K/W to explicit fixed ambient
constexpr double ambient = 300.0; // K
constexpr double end_time = 2.0; // s
// Tight algebraic tolerances, not claims of physical prediction accuracy.
constexpr double temperature_tolerance = 2.0e-9; // K
constexpr double power_tolerance = 2.0e-9; // W
constexpr double energy_tolerance = 4.0e-9; // J over this two-second fixture

void require(bool condition, const std::string &message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void near(double actual, double expected, double tolerance,
          const std::string &message) {
  require(std::isfinite(actual) && std::isfinite(expected) &&
              std::abs(actual - expected) <= tolerance,
          message + ": actual=" + std::to_string(actual) +
              ", expected=" + std::to_string(expected));
}

spikes::Circuit circuit(double coefficient = alpha) {
  spikes::Circuit result;
  // Positive source current flows from ground into the resistor's positive pin.
  result.add_current_source("I", "0", "rail", 1.0);
  spikes::ElectrothermalResistorModel model;
  model.resistance_ohm = resistance;
  model.temperature_coefficient_per_k = coefficient;
  model.ambient_temperature_k = ambient;
  model.thermal_resistance_k_per_w = thermal_resistance;
  model.thermal_capacitance_j_per_k = capacity;
  model.minimum_temperature_k = 290.0;
  model.maximum_temperature_k = 400.0;
  // The device's thermal-node voltage is rise above ambient, not absolute K.
  result.add_electrothermal_resistor("R", "rail", "0", "theta", model);
  return result;
}

spikes::TransientOptions options(double dt, Method method) {
  spikes::TransientOptions result;
  result.time_step_s = dt;
  result.stop_time_s = end_time;
  result.max_steps = 100;
  result.initialize_from_operating_point = false; // theta(0)=0, not hot OP
  result.integration_method = method;
  result.adaptive_time_step = false;
  result.nonlinear.absolute_tolerance = 1.0e-13;
  result.nonlinear.relative_tolerance = 1.0e-12;
  return result;
}

const spikes::ElementOperatingPoint &element(const spikes::TransientPoint &point,
                                              std::string_view id) {
  const auto found = std::find_if(point.elements.begin(), point.elements.end(),
                                [id](const auto &row) { return row.id == id; });
  require(found != point.elements.end(), "missing element " + std::string(id));
  return *found;
}

double exact_temperature(double time, double coefficient = alpha) {
  // Constant I=1: C theta' = P0 - (1/Rth - alpha P0) theta.
  const double conductance = 1.0 / thermal_resistance - coefficient * resistance;
  return resistance / conductance * -std::expm1(-conductance * time / capacity);
}

struct Evidence {
  double continuous_error_k{};
  double maximum_discrete_error_k{};
  double maximum_balance_w{};
  double cumulative_balance_j{};
};

Evidence check_batch(double dt, Method method) {
  const auto solved = spikes::solve_transient(circuit(), options(dt, method));
  require(solved.converged(), "native solve failed: " + solved.message());
  const auto count = static_cast<std::size_t>(std::lround(end_time / dt));
  require(solved.points().size() == count, "unexpected saved sample count");
  const auto &diagnostics = solved.diagnostics();
  require(diagnostics.completed_steps == count, "unexpected accepted step count");
  require(diagnostics.total_newton_iterations > 0, "coupled Newton solve not executed");
  if (method == Method::bdf2) {
    require(diagnostics.backward_euler_steps == 1 && diagnostics.bdf2_steps == count - 1,
            "BDF2 must start once with BE then preserve two-step history");
  } else {
    require(diagnostics.backward_euler_steps == count && diagnostics.bdf2_steps == 0,
            "BE method accounting mismatch");
  }

  Evidence evidence;
  double previous = 0.0, older = 0.0;
  double expected_previous = 0.0, expected_older = 0.0;
  double deposited_energy = 0.0, rejected_energy = 0.0;
  for (std::size_t index = 0; index < count; ++index) {
    const auto &point = solved.points()[index];
    const double theta = point.node_voltage("theta");
    const double time = (index + 1) * dt;
    near(point.time_s, time, 2.0e-14, "sample time");
    const bool bdf = method == Method::bdf2 && index > 0;
    // Independently solved scalar recurrences; no native stamps reused.
    const double expected = bdf
        ? (2.0 * expected_previous - 0.5 * expected_older + dt) / (1.5 + 0.48 * dt)
        : (expected_previous + dt) / (1.0 + 0.48 * dt);
    near(theta, expected, temperature_tolerance, "coupled discrete temperature");
    if (method == Method::backward_euler) {
      const double closed_be = (2.0 / 0.96) *
          (1.0 - std::pow(1.0 + 0.48 * dt, -static_cast<double>(index + 1)));
      near(theta, closed_be, temperature_tolerance, "closed BE temperature");
    }
    evidence.maximum_discrete_error_k = std::max(evidence.maximum_discrete_error_k,
                                                std::abs(theta - expected));
    const auto &resistor = element(point, "R");
    const auto &source = element(point, "I");
    const double expected_power = resistance * (1.0 + alpha * theta);
    near(resistor.current_a, 1.0, power_tolerance, "resistor current direction");
    near(source.current_a, 1.0, power_tolerance, "source current direction");
    near(resistor.voltage_v, expected_power, power_tolerance, "temperature updates resistance");
    near(source.voltage_v, -resistor.voltage_v, power_tolerance, "source voltage polarity");
    near(resistor.power_w, expected_power, power_tolerance, "Joule power");
    require(source.power_w < 0 && resistor.power_w > 0, "source/loss power signs");
    near(source.power_w + resistor.power_w, 0.0, power_tolerance, "electrical energy ledger");

    const double storage_rate = capacity / dt *
        (bdf ? 1.5 * theta - 2.0 * previous + 0.5 * older : theta - previous);
    const double heat_to_ambient = theta / thermal_resistance;
    const double balance = storage_rate + heat_to_ambient - resistor.power_w;
    near(balance, 0.0, power_tolerance, "discrete thermal nodal balance");
    evidence.maximum_balance_w = std::max(evidence.maximum_balance_w, std::abs(balance));
    if (method == Method::backward_euler) {
      // BE end-point heat quadrature telescopes to actual stored energy.
      // Do not call the BDF2 companion history physical stored energy.
      deposited_energy += dt * resistor.power_w;
      rejected_energy += dt * heat_to_ambient;
      evidence.cumulative_balance_j = capacity * theta + rejected_energy - deposited_energy;
      near(evidence.cumulative_balance_j, 0.0, energy_tolerance, "cumulative BE thermal energy");
    }
    older = previous;
    previous = theta;
    expected_older = expected_previous;
    expected_previous = expected;
  }
  evidence.continuous_error_k = std::abs(previous - exact_temperature(end_time));
  require(previous > 0, "temperature must rise above explicit ambient");
  std::cout << (method == Method::bdf2 ? "BDF2" : "BE") << " dt_s=" << dt
            << " final_rise_k=" << previous
            << " continuous_error_k=" << evidence.continuous_error_k
            << " discrete_error_k=" << evidence.maximum_discrete_error_k
            << " thermal_balance_w=" << evidence.maximum_balance_w;
  if (method == Method::backward_euler) {
    std::cout << " cumulative_balance_j=" << evidence.cumulative_balance_j;
  }
  std::cout << '\n';
  return evidence;
}

void refinement_and_feedback() {
  for (const auto method : {Method::backward_euler, Method::bdf2}) {
    std::array<double, 3> errors{};
    const std::array<double, 3> steps{0.2, 0.1, 0.05};
    for (std::size_t index = 0; index < steps.size(); ++index) {
      errors[index] = check_batch(steps[index], method).continuous_error_k;
    }
    for (std::size_t index = 1; index < errors.size(); ++index) {
      const double ratio = errors[index] / errors[index - 1];
      // Predeclared order gates for this smooth, bounded constant-step case.
      require(method == Method::bdf2 ? ratio > 0.15 && ratio < 0.35
                                    : ratio > 0.4 && ratio < 0.55,
              "time refinement failed expected integration order");
      std::cout << (method == Method::bdf2 ? "BDF2" : "BE")
                << " refinement_ratio=" << ratio << '\n';
    }
  }
  const auto cold = spikes::solve_transient(circuit(0.0), options(0.05, Method::backward_euler));
  const auto coupled = spikes::solve_transient(circuit(), options(0.05, Method::backward_euler));
  require(cold.converged() && coupled.converged(), "feedback comparison failed");
  near(cold.points().back().node_voltage("theta"),
       2.0 * (1.0 - std::pow(1.025, -40.0)), temperature_tolerance, "zero-alpha oracle");
  const double difference = coupled.points().back().node_voltage("theta") -
                            cold.points().back().node_voltage("theta");
  require(difference > 0.01, "temperature-to-electrical feedback is not observable");
  std::cout << "feedback_rise_difference_k=" << difference << '\n';
}

void session_replay(Method method) {
  constexpr double dt = 0.05;
  const auto batch = spikes::solve_transient(circuit(), options(dt, method));
  require(batch.converged(), "batch session oracle failed");
  spikes::TransientSession session(circuit(), options(dt, method));
  const auto compare = [&](std::size_t index) {
    require(session.step(dt), "persistent electrothermal step failed: " + session.message());
    const auto &expected = batch.points().at(index);
    near(session.node_voltage("theta"), expected.node_voltage("theta"),
         temperature_tolerance, "persistent/batch thermal state");
    near(session.node_voltage("rail"), expected.node_voltage("rail"),
         power_tolerance, "persistent/batch temperature-dependent electrical state");
    near(session.element_power("R"), element(expected, "R").power_w,
         power_tolerance, "persistent/batch dissipation");
  };
  for (std::size_t index = 0; index < 10; ++index) compare(index);
  const auto checkpoint = session.checkpoint();
  std::vector<double> first;
  for (std::size_t index = 10; index < batch.points().size(); ++index) {
    compare(index);
    first.push_back(session.node_voltage("theta"));
  }
  session.restore(checkpoint);
  near(session.time_s(), 0.5, 2.0e-14, "checkpoint time restore");
  require(session.step_index() == 10, "checkpoint step count restore");
  for (std::size_t index = 10; index < batch.points().size(); ++index) {
    compare(index);
    near(session.node_voltage("theta"), first[index - 10], temperature_tolerance,
         "checkpoint replay thermal history");
  }
  require(session.diagnostics().completed_steps == 40, "replay accepted-step accounting");
  if (method == Method::bdf2) {
    require(session.diagnostics().backward_euler_steps == 1 &&
                session.diagnostics().bdf2_steps == 39,
            "persistent BDF2 checkpoint lost integration history");
  } else {
    // A reviewed current change exercises persistent feedback, not restart.
    double previous = session.node_voltage("theta");
    session.set_source_value("I", 0.5);
    for (int index = 0; index < 10; ++index) {
      const double expected = (previous + 0.25 * dt) / (1.0 + 0.495 * dt);
      require(session.step(dt), "changed-source persistent step failed");
      const double theta = session.node_voltage("theta");
      near(theta, expected, temperature_tolerance, "changed-source feedback oracle");
      near(session.element_current("R"), 0.5, power_tolerance, "changed source current");
      near(capacity * (theta - previous) / dt + theta - session.element_power("R"),
           0.0, power_tolerance, "changed-source thermal ledger");
      previous = theta;
    }
  }
  std::cout << (method == Method::bdf2 ? "BDF2" : "BE")
            << " persistent_batch_and_checkpoint_replay=passed\n";
}

// Averaged buck: ideal duty-controlled source, L/C, explicit series copper
// loss and external load. No PWM edges, transistor/controller device model,
// switching loss or power-stage qualification is implied by this fixture.
using BuckState = std::array<double, 4>; // A, V, temperature rise K, error integral V*s
constexpr double buck_l = 100e-6, buck_c = 100e-6, buck_r = .2;
constexpr double buck_cth = .01, buck_rth = 10, buck_end = .02;

double duty(const BuckState &x) {
  return std::clamp(5.0 / 12.0 + .04 * (5.0 - x[1]) + 10.0 * x[3], 0.0, 1.0);
}

BuckState buck_rhs(const BuckState &x, double coefficient) {
  const double r = buck_r * (1.0 + coefficient * x[2]);
  return {(12.0 * duty(x) - r * x[0] - x[1]) / buck_l,
          (x[0] - x[1] / 5.0) / buck_c,
          (r * x[0] * x[0] - x[2] / buck_rth) / buck_cth, 5.0 - x[1]};
}

BuckState oracle_shift(BuckState x, const BuckState &k, double h) {
  for (std::size_t j = 0; j < x.size(); ++j) x[j] += h * k[j];
  return x;
}

BuckState buck_rk4(double dt, double coefficient) {
  // Independent continuous PI + physical ODE oracle, never a native stamp.
  BuckState x{};
  const auto steps = static_cast<std::size_t>(std::lround(buck_end / dt));
  for (std::size_t n = 0; n < steps; ++n) {
    const auto a = buck_rhs(x, coefficient);
    const auto b = buck_rhs(oracle_shift(x, a, dt / 2), coefficient);
    const auto c = buck_rhs(oracle_shift(x, b, dt / 2), coefficient);
    const auto d = buck_rhs(oracle_shift(x, c, dt), coefficient);
    for (std::size_t j = 0; j < x.size(); ++j)
      x[j] += dt * (a[j] + 2 * b[j] + 2 * c[j] + d[j]) / 6;
  }
  return x;
}

double buck_error(const BuckState &a, const BuckState &b) {
  // Dimensionless norm: scales 1 A, 1 V, 1 K and 0.1 V*s respectively.
  double square = 0.0;
  for (std::size_t j = 0; j < a.size(); ++j) {
    const double difference = (a[j] - b[j]) * (j == 3 ? 10.0 : 1.0);
    square += difference * difference;
  }
  return std::sqrt(square);
}

BuckState buck_native(double dt, double coefficient) {
  spikes::Circuit model;
  model.add_voltage_source("Vavg", "drive", "0", 0.0);
  spikes::ElectrothermalResistorModel copper;
  copper.resistance_ohm = buck_r;
  copper.temperature_coefficient_per_k = coefficient;
  copper.ambient_temperature_k = ambient;
  copper.thermal_resistance_k_per_w = buck_rth;
  copper.thermal_capacitance_j_per_k = buck_cth;
  copper.minimum_temperature_k = ambient;
  copper.maximum_temperature_k = ambient + 100.0;
  model.add_electrothermal_resistor("Rdcr", "drive", "coil", "theta", copper);
  model.add_inductor("L", "coil", "out", buck_l, 0.0);
  model.add_capacitor("C", "out", "0", buck_c, 0.0);
  model.add_resistor("Rload", "out", "0", 5.0);
  spikes::TransientSession session(std::move(model), options(dt, Method::backward_euler));
  BuckState x{};
  double delivered = 0, load = 0, heat = 0, ambient_heat = 0, numerical = 0;
  double max_electrical_step = 0, max_thermal_step = 0, min_duty = 1, max_duty = 0;
  const auto steps = static_cast<std::size_t>(std::lround(buck_end / dt));
  for (std::size_t n = 0; n < steps; ++n) {
    // Sample/hold source and forward-Euler PI integral are intentionally
    // distinct from continuous RK4; their error must decrease with timestep.
    const double command = duty(x);
    min_duty = std::min(min_duty, command); max_duty = std::max(max_duty, command);
    session.set_source_value("Vavg", 12.0 * command);
    require(session.step(dt), "averaged buck step failed: " + session.message());
    BuckState next{session.element_current("L"), session.node_voltage("out"),
                   session.node_voltage("theta"), x[3] + dt * (5.0 - x[1])};
    for (const double value : next) require(std::isfinite(value), "nonfinite buck state");
    require(next[2] >= 0 && next[2] <= 100, "buck temperature law envelope");
    const double psource = -session.element_power("Vavg");
    const double pload = session.element_power("Rload"), pheat = session.element_power("Rdcr");
    near(pheat, buck_r * (1 + coefficient * next[2]) * next[0] * next[0],
         1e-8, "buck temperature-dependent Joule loss");
    near(-psource + pload + pheat + session.element_power("L") + session.element_power("C"),
         0, 1e-8, "buck complete electrical power ledger");
    const double stored_change = .5 * buck_l * (next[0] * next[0] - x[0] * x[0]) +
                                 .5 * buck_c * (next[1] * next[1] - x[1] * x[1]);
    const double be_loss = .5 * buck_l * std::pow(next[0] - x[0], 2) +
                           .5 * buck_c * std::pow(next[1] - x[1], 2);
    const double electric_error = dt * (psource - pload - pheat) - stored_change - be_loss;
    const double thermal_error = dt * (pheat - next[2] / buck_rth) - buck_cth * (next[2] - x[2]);
    near(electric_error, 0, 5e-10, "buck BE electrical energy including numerical dissipation");
    near(thermal_error, 0, 5e-10, "buck physical thermal energy");
    max_electrical_step = std::max(max_electrical_step, std::abs(electric_error));
    max_thermal_step = std::max(max_thermal_step, std::abs(thermal_error));
    delivered += dt * psource; load += dt * pload; heat += dt * pheat;
    ambient_heat += dt * next[2] / buck_rth; numerical += be_loss;
    x = next;
  }
  const double electrical_store = .5 * buck_l * x[0] * x[0] + .5 * buck_c * x[1] * x[1];
  near(delivered - load - heat - electrical_store - numerical, 0, 1e-9, "buck cumulative electrical energy");
  near(heat - ambient_heat - buck_cth * x[2], 0, 1e-9, "buck cumulative thermal energy");
  near(delivered - load - ambient_heat - buck_cth * x[2] - electrical_store - numerical,
       0, 1e-9, "buck combined energy without double-counted copper heat");
  require(min_duty > 0 && max_duty < 1, "benchmark unexpectedly saturates PI duty");
  require(std::abs(x[1] - 5) < .03, "buck 20ms tracking error exceeds declared 30mV gate");
  std::cout << "averaged_buck dt_s=" << dt << " alpha=" << coefficient << " voltage_v=" << x[1]
            << " rise_k=" << x[2] << " source_j=" << delivered << " load_j=" << load
            << " copper_j=" << heat << " ambient_j=" << ambient_heat << " numerical_j=" << numerical
            << " max_electrical_step_error_j=" << max_electrical_step
            << " max_thermal_step_error_j=" << max_thermal_step << '\n';
  return x;
}

void averaged_buck_feedback() {
  const auto reference = buck_rk4(1e-7, alpha);
  require(buck_error(reference, buck_rk4(5e-8, alpha)) < 1e-8, "RK4 oracle not time-resolved");
  std::array<double, 3> errors{};
  const std::array<double, 3> steps{20e-6, 10e-6, 5e-6};
  BuckState fine{};
  for (std::size_t j = 0; j < steps.size(); ++j) {
    fine = buck_native(steps[j], alpha); errors[j] = buck_error(fine, reference);
    std::cout << "averaged_buck continuous_normalized_error=" << errors[j] << '\n';
    // Frozen from an independently evaluated sampled scalar BE recurrence:
    // expected ratios .61633 and .56384, approaching first-order .5.
    if (j > 0) require(errors[j] / errors[j - 1] > .45 && errors[j] / errors[j - 1] < .70,
                       "averaged buck sampled-BE refinement fails first-order trend");
  }
  require(errors.back() < .01, "finest averaged buck trajectory endpoint error");
  const auto cold = buck_native(5e-6, 0.0);
  require(fine[2] > cold[2] + .001 && fine[1] < cold[1] - .0001,
          "averaged buck electrical/thermal feedback not observable");
  std::cout << "averaged_buck closed_loop_tracking_energy_feedback_refinement=passed\n";
}

} // namespace

int main() {
  std::cout << std::setprecision(12);
  try {
    refinement_and_feedback();
    session_replay(Method::backward_euler);
    session_replay(Method::bdf2);
    averaged_buck_feedback();
  } catch (const std::exception &error) {
    std::cerr << "Native electrothermal analytical reference FAILED: " << error.what() << '\n';
    return 1;
  }
  std::cout << "Native electrothermal analytical reference PASSED; synthetic resistor/RC and averaged buck only, "
               "not PWM transistor/SPICE-device, spatial-thermal, or hardware qualification.\n";
  return 0;
}
