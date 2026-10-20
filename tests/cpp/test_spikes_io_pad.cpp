// SPDX-License-Identifier: Apache-2.0

#include "spikes/io_pad.hpp"
#include "spikes/transient_session.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const char *message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

bool near(double actual, double expected, double tolerance) {
  return std::abs(actual - expected) <= tolerance;
}

spikes::IoPadConfig base_config() {
  spikes::IoPadConfig config;
  config.high_strong_resistance_ohm = 50.0;
  config.high_weak_resistance_ohm = 500.0;
  config.low_strong_resistance_ohm = 50.0;
  config.low_weak_resistance_ohm = 500.0;
  config.pull_up_resistance_ohm = 10'000.0;
  config.pull_down_resistance_ohm = 20'000.0;
  config.off_resistance_ohm = 1.0e15;
  return config;
}

spikes::IoPadState input(spikes::IoPadPull pull = spikes::IoPadPull::none) {
  return {spikes::IoPadDriveMode::input,
          spikes::IoPadOutputState::released,
          spikes::IoPadDriveLevel::strong, pull};
}

spikes::IoPadState push_pull(spikes::IoPadOutputState output,
                             spikes::IoPadDriveLevel level =
                                 spikes::IoPadDriveLevel::strong) {
  return {spikes::IoPadDriveMode::push_pull, output, level,
          spikes::IoPadPull::none};
}

void dc_pull_divider_matches_conductance_oracle() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vrail", "vdd", "0", 3.3);
  circuit.add_resistor("Rload", "pad", "0", 10'000.0);
  const auto config = base_config();
  const auto binding = spikes::add_io_pad(circuit, "gpio0", "pad", "vdd",
                                          "0", config,
                                          input(spikes::IoPadPull::up));
  const auto result = spikes::solve_operating_point(circuit);
  require(result.converged(), "pull-divider operating point");

  const double g_up = 1.0 / config.pull_up_resistance_ohm +
                      1.0 / config.off_resistance_ohm;
  const double g_down = 1.0 / 10'000.0 +
                        2.0 / config.off_resistance_ohm;
  const double expected = 3.3 * g_up / (g_up + g_down);
  require(near(result.node_voltage(binding.pad), expected, 2.0e-11),
          "pull-divider voltage oracle");
  require(near(result.element_current(binding.pull_up_id),
               (expected - 3.3) / config.pull_up_resistance_ohm, 2.0e-14),
          "pull-up branch current observable");
}

void open_drain_release_and_noop_update_are_stateful() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vrail", "vdd", "0", 3.3);
  circuit.add_resistor("Rexternal_pull", "vdd", "pad", 1'000.0);
  auto config = base_config();
  const spikes::IoPadState low{spikes::IoPadDriveMode::open_drain,
                               spikes::IoPadOutputState::low,
                               spikes::IoPadDriveLevel::strong,
                               spikes::IoPadPull::none};
  auto binding = spikes::add_io_pad(circuit, "od", "pad", "vdd", "0",
                                    config, low);
  spikes::TransientSession session(circuit);
  require(session.step(1.0e-9), "open-drain low step");
  require(session.node_voltage("pad") < 0.16,
          "open-drain low sinks the external pull-up");

  const spikes::IoPadState released{spikes::IoPadDriveMode::open_drain,
                                    spikes::IoPadOutputState::released,
                                    spikes::IoPadDriveLevel::strong,
                                    spikes::IoPadPull::none};
  require(spikes::update_io_pad(session, binding, released),
          "open-drain release changes resistance state");
  require(session.step(1.0e-9), "open-drain released step");
  require(session.node_voltage("pad") > 3.299999,
          "external pull-up raises released open drain");
  const auto factorizations = session.diagnostics().matrix_factorizations;
  const auto reuses = session.diagnostics().factorization_reuses;
  require(!spikes::update_io_pad(session, binding, released),
          "unchanged state is a no-op");
  require(session.step(1.0e-9), "unchanged-state follow-up step");
  require(session.diagnostics().matrix_factorizations == factorizations,
          "unchanged state does not invalidate factorization");
  require(session.diagnostics().factorization_reuses > reuses,
          "unchanged state reuses the existing factorization");
  binding.config.off_resistance_ohm = 1.0e14;
  require(spikes::update_io_pad(session, binding, released),
          "changed valid profile is applied even when logical state is unchanged");
}

void finite_output_contention_has_bounded_current() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vrail", "vdd", "0", 3.3);
  const auto config = base_config();
  const auto high = spikes::add_io_pad(
      circuit, "high_driver", "bus", "vdd", "0", config,
      push_pull(spikes::IoPadOutputState::high));
  const auto low = spikes::add_io_pad(
      circuit, "low_driver", "bus", "vdd", "0", config,
      push_pull(spikes::IoPadOutputState::low));
  const auto result = spikes::solve_operating_point(circuit);
  require(result.converged(), "contending pads operating point");
  require(near(result.node_voltage("bus"), 1.65, 2.0e-11),
          "equal finite drivers divide the rail");
  const double expected = 1.65 / config.high_strong_resistance_ohm;
  require(near(-result.element_current(high.drive_high_id), expected, 2.0e-12),
          "high-side contention current");
  require(near(result.element_current(low.drive_low_id), expected, 2.0e-12),
          "low-side contention current");
}

void actual_rail_droop_is_not_hidden_by_an_ideal_pad_source() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vsupply", "supply", "0", 3.3);
  circuit.add_resistor("Rrail", "supply", "vdd", 10.0);
  circuit.add_resistor("Rload", "pad", "0", 100.0);
  auto config = base_config();
  config.high_strong_resistance_ohm = 50.0;
  const auto binding = spikes::add_io_pad(
      circuit, "droop", "pad", "vdd", "0", config,
      push_pull(spikes::IoPadOutputState::high));
  const auto result = spikes::solve_operating_point(circuit);
  require(result.converged(), "rail-droop operating point");
  require(near(result.node_voltage(binding.pad), 2.0625, 2.0e-10),
          "loaded pad voltage includes output and supply resistance");
  require(near(result.node_voltage(binding.vdd), 3.09375, 2.0e-10),
          "pad current produces actual VDD rail droop");
}

struct RcObservation {
  double error_v;
  double charge_residual_c;
  double kcl_residual_a;
};

RcObservation rc_observation(double step_s) {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vrail", "vdd", "0", 1.0);
  auto config = base_config();
  config.high_strong_resistance_ohm = 1'000.0;
  config.high_weak_resistance_ohm = 2'000.0;
  config.low_strong_resistance_ohm = 1'000.0;
  config.low_weak_resistance_ohm = 2'000.0;
  config.pull_up_resistance_ohm = 10'000.0;
  config.pull_down_resistance_ohm = 1.0;
  config.capacitance_to_vss_f = 1.0e-6;
  config.capacitance_to_vdd_f = 2.0e-6;
  auto binding = spikes::add_io_pad(circuit, "rc", "pad", "vdd", "0",
                                    config,
                                    input(spikes::IoPadPull::down));

  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::backward_euler;
  options.initialize_from_operating_point = true;
  spikes::TransientSession session(circuit, options);
  require(session.step(step_s), "RC initial operating-point step");
  const double initial_v = session.node_voltage("pad");
  require(spikes::update_io_pad(
              session, binding, push_pull(spikes::IoPadOutputState::high)),
          "RC rising output transition");

  constexpr double duration_s = 1.0e-3;
  const int count = static_cast<int>(std::llround(duration_s / step_s));
  double previous_v = initial_v;
  for (int index = 0; index < count; ++index) {
    previous_v = session.node_voltage("pad");
    require(session.step(step_s), "RC response step");
  }
  const double final_v = session.node_voltage("pad");

  const double off_g = 1.0 / config.off_resistance_ohm;
  const double up_g = 1.0 / config.high_strong_resistance_ohm + off_g;
  const double down_g = 2.0 * off_g;
  const double steady_v = up_g / (up_g + down_g);
  const double r_thevenin = 1.0 / (up_g + down_g);
  const double capacitance = config.capacitance_to_vss_f +
                             config.capacitance_to_vdd_f;
  const double exact_v = steady_v + (initial_v - steady_v) *
                                        std::exp(-duration_s /
                                                 (r_thevenin * capacitance));
  const double capacitor_current =
      session.element_current(binding.capacitance_to_vss_id) +
      session.element_current(binding.capacitance_to_vdd_id);
  const double resistor_current =
      session.element_current(binding.drive_high_id) +
      session.element_current(binding.drive_low_id) +
      session.element_current(binding.pull_up_id) +
      session.element_current(binding.pull_down_id);
  return {std::abs(final_v - exact_v),
          capacitor_current * step_s - capacitance * (final_v - previous_v),
          capacitor_current + resistor_current};
}

void rc_step_refines_toward_analytic_response_and_conserves_charge() {
  const auto coarse = rc_observation(1.0e-4);
  const auto fine = rc_observation(5.0e-5);
  require(fine.error_v < 0.56 * coarse.error_v,
          "backward-Euler RC error decreases at first order");
  require(fine.error_v < 2.0e-3, "refined RC analytic error bound");
  require(std::abs(coarse.charge_residual_c) < 2.0e-15,
          "split pad capacitance conserves backward-Euler charge");
  require(std::abs(fine.kcl_residual_a) < 2.0e-12,
          "pad branch currents satisfy KCL");
}

void construction_validation_is_atomic_and_optional_ids_are_complete() {
  spikes::Circuit collision;
  collision.add_resistor("dup.io_pad.drive_high", "a", "0", 1.0);
  const auto old_nodes = collision.node_count();
  const auto old_elements = collision.element_count();
  bool threw = false;
  try {
    static_cast<void>(spikes::add_io_pad(collision, "dup", "pad", "vdd",
                                         "0", base_config(), input()));
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  require(threw, "element-ID collision is rejected");
  require(collision.node_count() == old_nodes &&
              collision.element_count() == old_elements,
          "failed composition leaves circuit unchanged");

  spikes::Circuit node_collision;
  node_collision.node("@io_pad:pkg:die");
  auto packaged = base_config();
  packaged.package_resistance_ohm = 0.25;
  const auto node_count = node_collision.node_count();
  threw = false;
  try {
    static_cast<void>(spikes::add_io_pad(node_collision, "pkg", "pad", "vdd",
                                         "0", packaged, input()));
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  require(threw && node_collision.node_count() == node_count,
          "generated internal-node collision is rejected atomically");

  auto invalid = base_config();
  invalid.off_resistance_ohm = invalid.pull_up_resistance_ohm / 2.0;
  threw = false;
  try {
    spikes::Circuit circuit;
    static_cast<void>(spikes::add_io_pad(circuit, "bad", "pad", "vdd", "0",
                                         invalid, input()));
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  require(threw, "off resistance below pull resistance is rejected");

  spikes::Circuit complete;
  auto all = base_config();
  all.package_resistance_ohm = 0.25;
  all.package_inductance_h = 2.0e-9;
  all.capacitance_to_vss_f = 1.0e-12;
  all.capacitance_to_vdd_f = 2.0e-12;
  all.enable_clamp_to_vdd = true;
  all.enable_clamp_to_vss = true;
  const auto binding = spikes::add_io_pad(complete, "all", "pad", "vdd", "0",
                                          all, input());
  require(binding.pad == "pad" && binding.die_pad == "@io_pad:all:die" &&
              binding.vdd == "vdd" && binding.vss == "0",
          "binding exposes external and die-pad nodes");
  require(binding.element_ids().size() == 10u,
          "binding exposes all configured native branch IDs");
}

void generic_receiver_uses_explicit_thresholds_and_prior_only_in_band() {
  using State = spikes::IoPadReceiverState;
  require(spikes::receiver_voltage_state(0.6, 3.0, 0.0, 0.2, 0.7) ==
              State::low,
          "receiver includes VIL boundary in low state");
  require(spikes::receiver_voltage_state(2.1, 3.0, 0.0, 0.2, 0.7) ==
              State::high,
          "receiver includes VIH boundary in high state");
  require(spikes::receiver_voltage_state(1.5, 3.0, 0.0, 0.2, 0.7,
                                         State::low) == State::low &&
              spikes::receiver_voltage_state(1.5, 3.0, 0.0, 0.2, 0.7,
                                              State::high) == State::high &&
              spikes::receiver_voltage_state(1.5, 3.0, 0.0, 0.2, 0.7) ==
                  State::unknown,
          "receiver band retains only a prior known state");
  require(spikes::receiver_voltage_state(0.0, 0.0, 0.0, 0.2, 0.7,
                                         State::high) == State::unknown,
          "nonpositive rail span is unknown");
  bool threw = false;
  try {
    static_cast<void>(
        spikes::receiver_voltage_state(1.0, 3.0, 0.0, 0.8, 0.7));
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  require(threw, "invalid receiver threshold ordering is rejected");
}

void moving_vdd_capacitance_uses_the_actual_rail() {
  spikes::Circuit circuit;
  spikes::PulseWaveform ramp;
  ramp.initial_value = 0.0;
  ramp.pulsed_value = 1.0;
  ramp.rise_time_s = 1.0e-3;
  ramp.pulse_width_s = 1.0;
  ramp.period_s = 2.0;
  circuit.add_pulse_voltage_source("Vrail", "vdd", "0", ramp);
  circuit.add_voltage_source("Vpad_clamp", "pad", "0", 0.0);
  auto config = base_config();
  config.capacitance_to_vdd_f = 2.0e-6;
  const auto binding = spikes::add_io_pad(circuit, "moving_rail", "pad",
                                          "vdd", "0", config, input());
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  spikes::TransientSession session(circuit, options);
  require(session.step(2.5e-4), "moving-VDD ramp step");
  require(near(session.element_current(binding.capacitance_to_vdd_id),
               -2.0e-3, 2.0e-12),
          "VDD capacitance responds to pad-minus-actual-rail slope");
  const auto observation = spikes::observe_io_pad(session, binding);
  require(near(observation.pad_voltage_v, 0.0, 1.0e-12) &&
              near(observation.vdd_voltage_v, 0.25, 1.0e-10),
          "observation reports actual pad and moving-rail voltages");
  require(std::abs(observation.pad_current_a + observation.vdd_current_a +
                   observation.vss_current_a) < 2.0e-12,
          "unpackaged observation terminal currents conserve charge");
  require(observation.vdd_current_a > 1.9e-3,
          "VDD terminal current includes split-capacitance displacement current");
}

void package_rl_and_clamp_directions_match_independent_oracles() {
  {
    spikes::Circuit circuit;
    circuit.add_voltage_source("Vrail", "vdd", "0", 1.0);
    circuit.add_resistor("Rload", "pad", "0", 10.0);
    auto config = base_config();
    config.high_strong_resistance_ohm = 10.0;
    config.high_weak_resistance_ohm = 100.0;
    config.low_strong_resistance_ohm = 10.0;
    config.low_weak_resistance_ohm = 100.0;
    config.package_resistance_ohm = 5.0;
    config.package_inductance_h = 1.0e-3;
    const auto binding = spikes::add_io_pad(
        circuit, "rl", "pad", "vdd", "0", config,
        push_pull(spikes::IoPadOutputState::high));
    spikes::TransientOptions options;
    options.initialize_from_operating_point = false;
    spikes::TransientSession session(circuit, options);
    constexpr double step_s = 1.0e-6;
    constexpr int count = 100;
    for (int index = 0; index < count; ++index) {
      require(session.step(step_s), "package RL step");
    }
    constexpr double total_resistance = 25.0;
    constexpr double duration_s = step_s * count;
    const double expected =
        (1.0 / total_resistance) *
        (1.0 - std::exp(-total_resistance * duration_s / 1.0e-3));
    require(near(-session.element_current(binding.package_inductor_id),
                 expected, 5.0e-4),
            "package RL current approaches analytic series response");
    const auto observation = spikes::observe_io_pad(session, binding);
    require(observation.pad_current_a ==
                session.element_current(binding.package_inductor_id),
            "packaged observation uses the independently stamped package current");
    require(near(observation.pad_voltage_v, session.node_voltage("pad"), 0.0) &&
                near(observation.die_voltage_v,
                     session.node_voltage(binding.die_pad), 0.0),
            "packaged observation keeps external and die voltages distinct");
  }

  for (const bool upper : {true, false}) {
    spikes::Circuit circuit;
    circuit.add_voltage_source("Vrail", "vdd", "0", 3.3);
    circuit.add_voltage_source("Vstress", "stress", "0", upper ? 5.0 : -1.0);
    circuit.add_resistor("Rstress", "stress", "pad", 1'000.0);
    auto config = base_config();
    config.enable_clamp_to_vdd = upper;
    config.enable_clamp_to_vss = !upper;
    const auto binding = spikes::add_io_pad(circuit, upper ? "upper" : "lower",
                                            "pad", "vdd", "0", config,
                                            input());
    const auto result = spikes::solve_operating_point(circuit);
    require(result.converged(), "diode-clamp operating point");
    const auto &clamp_id = upper ? binding.clamp_to_vdd_id
                                 : binding.clamp_to_vss_id;
    require(result.element_current(clamp_id) > 1.0e-6,
            "upper/lower clamp forward current follows declared orientation");
    require(upper ? result.node_voltage("pad") > 3.3
                  : result.node_voltage("pad") < 0.0,
            "finite source resistance leaves clamp overdrive observable");
  }
}

} // namespace

int main() {
  try {
    dc_pull_divider_matches_conductance_oracle();
    open_drain_release_and_noop_update_are_stateful();
    finite_output_contention_has_bounded_current();
    actual_rail_droop_is_not_hidden_by_an_ideal_pad_source();
    rc_step_refines_toward_analytic_response_and_conserves_charge();
    construction_validation_is_atomic_and_optional_ids_are_complete();
    generic_receiver_uses_explicit_thresholds_and_prior_only_in_band();
    moving_vdd_capacitance_uses_the_actual_rail();
    package_rl_and_clamp_directions_match_independent_oracles();
  } catch (const std::exception &error) {
    std::cerr << "SPIKES I/O-pad test exception: " << error.what() << '\n';
    return 1;
  }
  std::cout << "SPIKES native I/O-pad tests passed\n";
  return 0;
}
