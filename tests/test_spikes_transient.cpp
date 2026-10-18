#include "spikes/transient_solver.hpp"
#include "spikes/osdi_device.hpp"
#include "spikes/transient_session.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

bool near(double actual, double expected, double tolerance) {
  return std::abs(actual - expected) <= tolerance;
}

void radau_ramp_all_time_oracles_cover_signed_scales_and_dense_sparse() {
  constexpr double rise = 1e-5;
  constexpr double tau = 1e-3;
  for (const bool inductive : {false, true}) {
    for (const double amplitude : {1.0, -1.0, 1e-3, -1e-3, 1e-6, -1e-6, 0.0}) {
      for (const std::size_t sparse_threshold : {0u, 1u}) {
        spikes::Circuit circuit;
        spikes::PulseWaveform pulse;
        pulse.pulsed_value = amplitude;
        pulse.rise_time_s = rise;
        pulse.fall_time_s = rise;
        pulse.pulse_width_s = 0.01;
        pulse.period_s = 0.02;
        circuit.add_pulse_voltage_source("V1", "in", "0", pulse);
        circuit.add_resistor("R1", "in", "out", 1000.0);
        if (inductive) circuit.add_inductor("X1", "out", "0", 1.0);
        else circuit.add_capacitor("X1", "out", "0", 1e-6);
        spikes::TransientOptions options;
        options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
        options.sparse_linear_threshold = sparse_threshold;
        options.time_step_s = 2.5e-7;
        options.stop_time_s = 1.01e-3;
        const auto result = spikes::solve_transient(circuit, options);
        assert(result.converged());
        for (const auto &point : result.points()) {
          const long double t = point.time_s;
          const long double response = t <= rise
              ? (t + tau * std::expm1(-t / tau)) / rise
              : 1.0L + tau / rise * std::expm1(-rise / tau) * std::exp(-(t - rise) / tau);
          const double source = amplitude * std::min(point.time_s / rise, 1.0);
          const double voltage = inductive ? source - amplitude * static_cast<double>(response)
                                           : amplitude * static_cast<double>(response);
          const double current = inductive ? amplitude * static_cast<double>(response) / 1000.0
                                           : (source - voltage) / 1000.0;
          assert(near(point.node_voltage("out"), voltage, 1e-12 + 5e-6 * std::abs(voltage)));
          assert(near(point.element_current("X1"), current, 1e-15 + 5e-6 * std::abs(current)));
        }
        assert(result.diagnostics().radau_iia3_steps == result.diagnostics().completed_steps);
        assert(result.diagnostics().backward_euler_steps == 0);
        assert(result.diagnostics().source_breakpoint_steps == 1);
        assert(result.diagnostics().factorization_reuses > 1000);
      }
    }
  }
}

void radau_jump_limits_preserve_storage_and_persistent_edge_identity() {
  spikes::Circuit circuit;
  spikes::PulseWaveform pulse;
  pulse.pulsed_value = 1.0;
  pulse.delay_s = 0.25;
  pulse.rise_time_s = 0.0;
  pulse.fall_time_s = 0.0;
  pulse.pulse_width_s = 0.01;
  pulse.period_s = 1.0;
  circuit.add_pulse_voltage_source("V1", "in", "0", pulse);
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1.0);
  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
  options.time_step_s = 0.25;
  options.stop_time_s = 0.5;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(near(result.points()[1].time_s, 0.25, 1e-15));
  assert(result.points()[1].node_voltage("out") == 0.0);
  assert(result.points()[1].node_voltage("in") == 0.0); // Left limit at actual jump.
  assert(near(result.points()[2].node_voltage("out"), -std::expm1(-0.01), 2e-10));
  assert(near(result.points().back().node_voltage("out"),
              -std::expm1(-0.01) * std::exp(-0.24), 5e-7));
  spikes::TransientSession session(circuit, options);
  assert(session.step(0.25));
  assert(session.node_voltage("out") == 0.0);
  assert(session.step(0.25));
  assert(near(session.node_voltage("out"), result.points().back().node_voltage("out"), 2e-14));
  assert(session.diagnostics().radau_iia3_steps == 3);
}

void radau_is_stiffly_damped_and_rejects_unsupported_history_contracts() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1e-6);
  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1e-3;
  options.stop_time_s = 1e-3;
  const auto stiff = spikes::solve_transient(circuit, options);
  assert(stiff.converged());
  assert(std::abs(stiff.points().back().node_voltage("out") - 1.0) < 0.003);
  options.adaptive_time_step = true;
  assert(!spikes::solve_transient(circuit, options).converged());
  options.adaptive_time_step = false;
  circuit.add_diode("D1", "out", "0");
  assert(!spikes::solve_transient(circuit, options).converged());
  spikes::Circuit constrained;
  constrained.add_voltage_source("V1", "out", "0", 1.0);
  constrained.add_capacitor("C1", "out", "0", 1.0);
  const auto rejected = spikes::solve_transient(constrained, options);
  assert(!rejected.converged());
  assert(rejected.message().find("loops") != std::string::npos);
  spikes::Circuit cutset;
  cutset.add_current_source("I1", "0", "out", 1.0);
  cutset.add_inductor("L1", "out", "0", 1.0);
  assert(!spikes::solve_transient(cutset, options).converged());
}

void radau_third_order_refinement_and_nonzero_uic_are_independent_of_history() {
  for (const bool inductive : {false, true}) {
    double previous_error = 0.0;
    for (const double h : {0.25, 0.125, 0.0625}) {
      spikes::Circuit circuit;
      circuit.add_voltage_source("V1", "in", "0", 1.0);
      circuit.add_resistor("R1", "in", "out", 1.0);
      if (inductive) circuit.add_inductor("X1", "out", "0", 1.0, 0.3);
      else circuit.add_capacitor("X1", "out", "0", 1.0, 0.3);
      spikes::TransientOptions options;
      options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
      options.initialize_from_operating_point = false;
      options.time_step_s = h;
      options.stop_time_s = 1.0;
      const auto result = spikes::solve_transient(circuit, options);
      assert(result.converged());
      const double final = inductive ? result.points().back().element_current("X1")
                                    : result.points().back().node_voltage("out");
      const double error = std::abs(final - (1.0 - 0.7 * std::exp(-1.0)));
      if (previous_error > 0.0) assert(previous_error / error > 7.0 && previous_error / error < 9.0);
      previous_error = error;
    }
  }
  spikes::Circuit loop;
  loop.add_resistor("R1", "out", "0", 1.0);
  loop.add_capacitor("C1", "out", "0", 1.0, 0.3);
  loop.add_capacitor("C2", "out", "0", 1.0, 0.4);
  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
  options.initialize_from_operating_point = false;
  assert(!spikes::solve_transient(loop, options).converged());
  spikes::Circuit driven;
  driven.add_current_source("I1", "0", "out", 1.0);
  driven.add_resistor("R1", "out", "0", 1.0);
  driven.add_capacitor("C1", "out", "0", 0.5, 0.3);
  driven.add_capacitor("C2", "out", "0", 0.5, 0.3);
  options.time_step_s = 0.01;
  options.stop_time_s = 1.0;
  const auto consistent = spikes::solve_transient(driven, options);
  assert(consistent.converged());
  assert(near(consistent.points().back().node_voltage("out"), 1.0 - 0.7 * std::exp(-1.0), 1e-8));
}

void radau_full_duty_pulse_has_no_spurious_period_jump() {
  spikes::Circuit circuit;
  spikes::PulseWaveform pulse;
  pulse.pulsed_value = 1.0;
  pulse.delay_s = 0.25;
  pulse.rise_time_s = pulse.fall_time_s = 0.0;
  pulse.pulse_width_s = pulse.period_s = 1.0;
  circuit.add_pulse_voltage_source("V1", "in", "0", pulse);
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1.0);
  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
  options.time_step_s = 0.05;
  options.stop_time_s = 1.25;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(near(result.points().back().node_voltage("in"), 1.0, 1e-14));
  assert(near(result.points().back().node_voltage("out"), -std::expm1(-1.0), 1e-6));
  // All coincident edge shapes retain their actual left limits: zero-width
  // empty pulse, immediate rise with sloped fall, and sloped rise followed by
  // an immediate fall exactly at the period boundary.
  for (const int shape : {0, 1, 2}) {
    spikes::Circuit edge_circuit;
    pulse.rise_time_s = shape == 2 ? 1.0 : 0.0;
    pulse.fall_time_s = shape == 1 ? 1.0 : 0.0;
    pulse.pulse_width_s = 0.0;
    edge_circuit.add_pulse_voltage_source("V1", "in", "0", pulse);
    edge_circuit.add_resistor("R1", "in", "0", 1.0);
    const auto edge_result = spikes::solve_transient(edge_circuit, options);
    assert(edge_result.converged());
    const double expected = shape == 2 ? 1.0 : 0.0;
    assert(near(edge_result.points().back().node_voltage("in"), expected, 2e-14));
  }
}

void radau_sinusoidal_forcing_has_third_order_endpoint_convergence() {
  spikes::Circuit circuit;
  spikes::SineWaveform sine;
  sine.frequency_hz = 1.0 / (2.0 * std::acos(-1.0));
  circuit.add_sine_voltage_source("V1", "in", "0", sine);
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1.0);
  const double expected = (std::sin(1.0) - std::cos(1.0) + std::exp(-1.0)) / 2.0;
  double previous_error = 0.0;
  for (const double h : {0.1, 0.05, 0.025}) {
    spikes::TransientOptions options;
    options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
    options.time_step_s = h;
    options.stop_time_s = 1.0;
    const auto result = spikes::solve_transient(circuit, options);
    assert(result.converged());
    const double error = std::abs(result.points().back().node_voltage("out") - expected);
    if (previous_error > 0.0) assert(previous_error / error >= 7.0);
    previous_error = error;
    spikes::TransientSession session(circuit, options);
    for (int i = 0; i < static_cast<int>(std::round(1.0 / h)); ++i) assert(session.step(h));
    assert(near(session.node_voltage("out"), result.points().back().node_voltage("out"), 2e-13));
  }
}

void radau_pwl_checkpoint_and_failed_window_preserve_storage() {
  spikes::Circuit circuit;
  circuit.add_pwl_voltage_source("V1", "in", "0", {{0.0, 0.0}, {0.2, 1.0}, {0.4, 0.0}, {1.0, 0.0}});
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1.0);
  spikes::TransientOptions options;
  options.integration_method = spikes::TransientIntegrationMethod::radau_iia3;
  options.time_step_s = 0.1;
  options.stop_time_s = 0.5;
  const auto batch = spikes::solve_transient(circuit, options);
  assert(batch.converged());
  spikes::TransientSession session(circuit, options);
  for (int i = 0; i < 2; ++i) assert(session.step(0.1));
  const auto checkpoint = session.checkpoint();
  for (int i = 0; i < 3; ++i) assert(session.step(0.1));
  assert(near(session.node_voltage("out"), batch.points().back().node_voltage("out"), 2e-14));
  session.restore(checkpoint);
  for (int i = 0; i < 3; ++i) assert(session.step(0.1));
  assert(near(session.node_voltage("out"), batch.points().back().node_voltage("out"), 2e-14));
  options.max_steps = 1;
  spikes::TransientSession bounded(circuit, options);
  assert(bounded.step(0.1));
  const double accepted = bounded.node_voltage("out");
  assert(!bounded.step(0.4)); // Multiple corner-aligned stages exceed the bound.
  assert(bounded.time_s() == 0.1);
  assert(bounded.node_voltage("out") == accepted);
  assert(bounded.step(0.1));
  assert(near(bounded.node_voltage("out"), batch.points()[2].node_voltage("out"), 2e-14));
}

void source_breakpoint_diagnostics_include_on_grid_accepted_corners() {
  spikes::Circuit circuit;
  circuit.add_pwl_voltage_source("V1", "in", "0",
      {{0.0, 0.0}, {0.25, 1.0}, {0.5, 1.0}, {0.75, 0.0}});
  circuit.add_resistor("R1", "in", "out", 1.0);
  circuit.add_capacitor("C1", "out", "0", 1.0);
  spikes::TransientOptions options;
  options.time_step_s = 0.25;
  options.stop_time_s = 1.0;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().source_breakpoint_steps == 3);

  // Failure before acceptance must not fabricate a completed corner landing.
  spikes::Circuit singular;
  singular.add_pwl_voltage_source("V1", "in", "0",
      {{0.0, 0.0}, {0.25, 1.0}});
  singular.add_resistor("Rfloat", "a", "b", 1.0);
  options.initialize_from_operating_point = false;
  const auto failed = spikes::solve_transient(singular, options);
  assert(!failed.converged());
  assert(failed.diagnostics().source_breakpoint_steps == 0);
}

void rc_step_matches_backward_euler_recurrence() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "vin", "0", 1.0);
  circuit.add_resistor("R1", "vin", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6, 0.0);

  spikes::TransientOptions options;
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 1.0e-3;
  options.initialize_from_operating_point = false;
  const auto result = spikes::solve_transient(circuit, options);

  assert(result.converged());
  assert(result.points().size() == 10);
  const double alpha = 1.0 / 1.1;
  const double expected = 1.0 - std::pow(alpha, 10.0);
  assert(near(result.points().back().node_voltage("out"), expected, 2.0e-12));
  assert(result.diagnostics().completed_steps == 10);
  assert(result.diagnostics().matrix_order == 3);
  assert(result.diagnostics().residual_inf_norm < 1.0e-12);
  assert(result.diagnostics().matrix_factorizations == 1);
  assert(result.diagnostics().factorization_reuses == 9);
  assert(result.diagnostics().factorization_cache_entries == 1);
}

void rl_step_matches_backward_euler_recurrence() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "vin", "0", 1.0);
  circuit.add_resistor("R1", "vin", "out", 10.0);
  circuit.add_inductor("L1", "out", "0", 1.0e-3, 0.0);

  spikes::TransientOptions options;
  options.time_step_s = 1.0e-5;
  options.stop_time_s = 1.0e-4;
  options.initialize_from_operating_point = false;
  const auto result = spikes::solve_transient(circuit, options);

  assert(result.converged());
  const double alpha = 1.0 / 1.1;
  const double expected = 0.1 * (1.0 - std::pow(alpha, 10.0));
  assert(near(result.points().back().element_current("L1"), expected,
              2.0e-13));
  assert(near(result.points().back().element_current("R1"), expected,
              2.0e-13));
}

void dc_initialization_produces_a_time_zero_sample() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 2.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);

  spikes::TransientOptions options;
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 2.0e-4;
  const auto result = spikes::solve_transient(circuit, options);

  assert(result.converged());
  assert(result.points().size() == 3);
  assert(result.points().front().time_s == 0.0);
  assert(near(result.points().front().node_voltage("out"), 2.0, 1.0e-14));
  assert(near(result.points().back().node_voltage("out"), 2.0, 1.0e-14));
}

void dc_treats_capacitors_as_open_and_inductors_as_shorts() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 3.0);
  circuit.add_resistor("R1", "in", "out", 30.0);
  circuit.add_inductor("L1", "out", "0", 1.0e-3);
  circuit.add_capacitor("C1", "in", "out", 1.0e-6);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.node_voltage("out"), 0.0, 1.0e-14));
  assert(near(result.element_current("L1"), 0.1, 1.0e-14));
  assert(near(result.element_current("C1"), 0.0, 1.0e-14));
}

void invalid_inputs_and_work_bounds_fail_closed() {
  spikes::Circuit circuit;
  bool threw = false;
  try {
    circuit.add_capacitor("Cbad", "x", "0", 0.0);
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  assert(threw);
  threw = false;
  try {
    circuit.add_inductor("Lbad", "x", "0", 1.0,
                         std::numeric_limits<double>::infinity());
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  assert(threw);

  circuit.add_resistor("R1", "x", "0", 1.0);
  spikes::TransientOptions invalid;
  invalid.time_step_s = 0.0;
  assert(!spikes::solve_transient(circuit, invalid).converged());
  invalid.time_step_s = 1.0e-6;
  invalid.stop_time_s = 1.0;
  invalid.max_steps = 10;
  const auto bounded = spikes::solve_transient(circuit, invalid);
  assert(!bounded.converged());
  assert(bounded.message().find("bound") != std::string::npos);

  spikes::TransientOptions partial_final_step;
  partial_final_step.initialize_from_operating_point = false;
  partial_final_step.time_step_s = 1.0e-6;
  partial_final_step.stop_time_s = 2.5e-6;
  partial_final_step.max_steps = 3;
  const auto partial = spikes::solve_transient(circuit, partial_final_step);
  assert(partial.converged());
  assert(partial.points().size() == 3);
  assert(partial.points().back().time_s == 2.5e-6);
}

void singular_and_nonlinear_nonconvergence_are_diagnostic() {
  spikes::Circuit floating;
  floating.add_capacitor("C1", "a", "b", 1.0e-6);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1.0e-6;
  options.stop_time_s = 1.0e-6;
  const auto singular = spikes::solve_transient(floating, options);
  assert(singular.status() == spikes::SolveStatus::singular);
  assert(singular.diagnostics().failed_time_s == 1.0e-6);

  spikes::Circuit nonlinear;
  nonlinear.add_voltage_source("V1", "in", "0", 5.0);
  nonlinear.add_resistor("R1", "in", "out", 1000.0);
  nonlinear.add_diode("D1", "out", "0");
  options.nonlinear.max_newton_iterations = 1;
  options.initialize_from_operating_point = false;
  const auto failed = spikes::solve_transient(nonlinear, options);
  assert(failed.status() == spikes::SolveStatus::nonconverged);
  assert(failed.diagnostics().failed_time_s == 1.0e-6);
  assert(failed.message().find("Newton") != std::string::npos);
}

void pulse_sources_force_exact_switching_breakpoints() {
  spikes::Circuit circuit;
  spikes::PulseWaveform pulse;
  pulse.initial_value = 0.0;
  pulse.pulsed_value = 5.0;
  pulse.delay_s = 0.25;
  pulse.rise_time_s = 0.10;
  pulse.pulse_width_s = 0.40;
  pulse.fall_time_s = 0.10;
  pulse.period_s = 1.0;
  circuit.add_pulse_voltage_source("Vgate", "gate", "0", pulse);
  circuit.add_resistor("Rgate", "gate", "0", 10.0);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 0.70;
  options.stop_time_s = 1.90;
  const auto result = spikes::solve_transient(circuit, options);

  assert(result.converged());
  const double expected_breakpoints[] = {0.25, 0.35, 0.75, 0.85,
                                         1.25, 1.35, 1.75, 1.85};
  for (double expected : expected_breakpoints) {
    const auto found = std::find_if(
        result.points().begin(), result.points().end(),
        [expected](const spikes::TransientPoint &point) {
          return near(point.time_s, expected, 2.0e-15);
        });
    assert(found != result.points().end());
  }
  assert(result.diagnostics().source_breakpoint_steps >= 7);
  const auto at_high = std::find_if(
      result.points().begin(), result.points().end(),
      [](const spikes::TransientPoint &point) {
        return near(point.time_s, 0.35, 2.0e-15);
      });
  const auto at_low = std::find_if(
      result.points().begin(), result.points().end(),
      [](const spikes::TransientPoint &point) {
        return near(point.time_s, 0.85, 2.0e-15);
      });
  assert(near(at_high->node_voltage("gate"), 5.0, 1.0e-12));
  assert(near(at_low->node_voltage("gate"), 0.0, 1.0e-12));
}

void pwl_sources_interpolate_and_force_knot_steps() {
  spikes::Circuit circuit;
  circuit.add_pwl_current_source(
      "Ishape", "0", "out",
      {{0.20, 0.0}, {0.50, 3.0}, {0.90, 1.0}});
  circuit.add_resistor("Rload", "out", "0", 2.0);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1.0;
  options.stop_time_s = 1.0;
  const auto result = spikes::solve_transient(circuit, options);

  assert(result.converged());
  assert(result.points().size() == 4);
  assert(near(result.points()[0].time_s, 0.20, 1.0e-15));
  assert(near(result.points()[1].time_s, 0.50, 1.0e-15));
  assert(near(result.points()[1].node_voltage("out"), 6.0, 1.0e-12));
  assert(near(result.points()[2].time_s, 0.90, 1.0e-15));
  assert(near(result.points()[2].node_voltage("out"), 2.0, 1.0e-12));
  assert(near(result.points()[3].time_s, 1.0, 1.0e-15));
}

void waveform_validation_and_breakpoint_work_bounds_fail_closed() {
  spikes::Circuit circuit;
  bool threw = false;
  try {
    circuit.add_pwl_voltage_source("Vbad", "x", "0",
                                   {{0.1, 1.0}, {0.1, 2.0}});
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  assert(threw);

  spikes::PulseWaveform invalid;
  invalid.rise_time_s = 0.6;
  invalid.pulse_width_s = 0.6;
  invalid.period_s = 1.0;
  threw = false;
  try {
    circuit.add_pulse_voltage_source("Vbad2", "x", "0", invalid);
  } catch (const std::invalid_argument &) {
    threw = true;
  }
  assert(threw);

  spikes::PulseWaveform pulse;
  pulse.delay_s = 0.1;
  pulse.rise_time_s = 0.1;
  pulse.pulse_width_s = 0.2;
  pulse.fall_time_s = 0.1;
  pulse.period_s = 0.5;
  circuit.add_pulse_voltage_source("V1", "x", "0", pulse);
  circuit.add_resistor("R1", "x", "0", 1.0);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1.0;
  options.stop_time_s = 1.0;
  options.max_steps = 1;
  const auto bounded = spikes::solve_transient(circuit, options);
  assert(!bounded.converged());
  assert(bounded.message().find("breakpoint") != std::string::npos);
}

void pulse_driven_switch_resolves_on_and_off_states_at_edges() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vs", "in", "0", 10.0);
  spikes::PulseWaveform gate;
  gate.initial_value = 0.0;
  gate.pulsed_value = 5.0;
  gate.delay_s = 0.1;
  gate.rise_time_s = 0.1;
  gate.pulse_width_s = 0.2;
  gate.fall_time_s = 0.1;
  gate.period_s = 0.5;
  circuit.add_pulse_voltage_source("Vg", "gate", "0", gate);
  spikes::VoltageControlledSwitchModel model;
  model.on_resistance_ohm = 1.0;
  model.off_resistance_ohm = 1.0e6;
  model.threshold_voltage_v = 2.5;
  model.transition_voltage_v = 0.1;
  circuit.add_voltage_controlled_switch("S1", "in", "out", "gate", "0",
                                        model);
  circuit.add_resistor("Rload", "out", "0", 10.0);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 0.3;
  options.stop_time_s = 0.5;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  const auto at = [&](double time) -> const spikes::TransientPoint & {
    const auto found = std::find_if(
        result.points().begin(), result.points().end(),
        [time](const spikes::TransientPoint &point) {
          return near(point.time_s, time, 2.0e-15);
        });
    assert(found != result.points().end());
    return *found;
  };
  assert(std::abs(at(0.1).node_voltage("out")) < 2.0e-4);
  assert(near(at(0.2).node_voltage("out"), 10.0 * 10.0 / 11.0, 1.0e-8));
  assert(std::abs(at(0.5).node_voltage("out")) < 2.0e-4);
}

void hybrid_trapezoidal_improves_smooth_rc_accuracy_and_reuses_lu() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);

  spikes::TransientOptions backward_euler;
  backward_euler.initialize_from_operating_point = false;
  backward_euler.time_step_s = 1.0e-4;
  backward_euler.stop_time_s = 1.0e-3;
  const auto be = spikes::solve_transient(circuit, backward_euler);
  assert(be.converged());

  auto hybrid_options = backward_euler;
  hybrid_options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  const auto hybrid = spikes::solve_transient(circuit, hybrid_options);
  assert(hybrid.converged());
  const double exact = 1.0 - std::exp(-1.0);
  const double be_error =
      std::abs(be.points().back().node_voltage("out") - exact);
  const double hybrid_error =
      std::abs(hybrid.points().back().node_voltage("out") - exact);
  assert(hybrid_error < be_error * 0.15);
  assert(hybrid.diagnostics().backward_euler_steps == 1);
  assert(hybrid.diagnostics().trapezoidal_steps == 9);
  assert(hybrid.diagnostics().matrix_factorizations == 2);
  assert(hybrid.diagnostics().factorization_reuses == 8);
  assert(hybrid.diagnostics().factorization_cache_entries == 2);
}

void bdf2_improves_smooth_rc_accuracy_and_reports_order_restarts() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);

  spikes::TransientOptions backward_euler;
  backward_euler.initialize_from_operating_point = false;
  backward_euler.time_step_s = 1.0e-4;
  backward_euler.stop_time_s = 1.0e-3;
  const auto be = spikes::solve_transient(circuit, backward_euler);
  assert(be.converged());

  auto bdf2_options = backward_euler;
  bdf2_options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  const auto bdf2 = spikes::solve_transient(circuit, bdf2_options);
  assert(bdf2.converged());
  const double exact = 1.0 - std::exp(-1.0);
  const double be_error =
      std::abs(be.points().back().node_voltage("out") - exact);
  const double bdf2_error =
      std::abs(bdf2.points().back().node_voltage("out") - exact);
  assert(bdf2_error < be_error * 0.25);
  assert(bdf2.diagnostics().backward_euler_steps == 1);
  assert(bdf2.diagnostics().bdf2_steps == 9);
  assert(bdf2.diagnostics().trapezoidal_steps == 0);
  assert(bdf2.message().find("BDF2") != std::string::npos);
}

void adaptive_embedded_lte_rejects_and_refines_rc_steps() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.time_step_s = 1.0e-4;
  options.minimum_time_step_s = 1.0e-8;
  options.stop_time_s = 1.0e-3;
  options.adaptive_time_step = true;
  options.lte_absolute_tolerance = 1.0e-5;
  options.lte_relative_tolerance = 1.0e-3;
  options.max_steps = 10'000;
  const auto adaptive = spikes::solve_transient(circuit, options);
  assert(adaptive.converged());
  assert(adaptive.diagnostics().rejected_lte_steps > 0);
  assert(adaptive.diagnostics().embedded_lte_solves > 0);
  assert(adaptive.diagnostics().completed_steps > 2);
  assert(adaptive.diagnostics().minimum_accepted_step_s < options.time_step_s);
  assert(adaptive.diagnostics().maximum_accepted_step_s <= options.time_step_s);
  const double exact = 1.0 - std::exp(-1.0);
  assert(std::abs(adaptive.points().back().node_voltage("out") - exact) < 0.01);
}

void adaptive_embedded_lte_solves_nonlinear_diode_dae() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 0.8);
  circuit.add_resistor("R1", "in", "out", 100.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);
  circuit.add_diode("D1", "out", "0");

  spikes::TransientOptions reference_options;
  reference_options.initialize_from_operating_point = false;
  reference_options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  reference_options.time_step_s = 1.0e-7;
  reference_options.stop_time_s = 1.0e-4;
  reference_options.max_steps = 10'000;
  const auto reference = spikes::solve_transient(circuit, reference_options);
  assert(reference.converged());

  auto adaptive_options = reference_options;
  adaptive_options.time_step_s = 2.0e-5;
  adaptive_options.minimum_time_step_s = 1.0e-9;
  adaptive_options.adaptive_time_step = true;
  adaptive_options.lte_absolute_tolerance = 1.0e-6;
  adaptive_options.lte_relative_tolerance = 1.0e-4;
  adaptive_options.max_steps = 100'000;
  adaptive_options.max_rejected_steps = 1'000;
  const auto adaptive = spikes::solve_transient(circuit, adaptive_options);
  assert(adaptive.converged());
  assert(adaptive.diagnostics().embedded_lte_solves > 0);
  assert(adaptive.diagnostics().rejected_lte_steps > 0);
  assert(adaptive.diagnostics().total_newton_iterations > 0);
  assert(adaptive.diagnostics().minimum_accepted_step_s <
         adaptive_options.time_step_s);
  assert(std::abs(adaptive.points().back().node_voltage("out") -
                  reference.points().back().node_voltage("out")) < 6.0e-3);
}

void adaptive_newton_failure_retries_without_committing_charge_history() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 5.0);
  circuit.add_resistor("R1", "in", "out", 100.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);
  circuit.add_diode("D1", "out", "0");
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.time_step_s = 2.0e-5;
  options.stop_time_s = 1.0e-4;
  options.nonlinear.max_newton_iterations = 3;
  options.nonlinear.absolute_tolerance = 1.0e-12;
  options.nonlinear.relative_tolerance = 1.0e-10;
  const auto fixed = spikes::solve_transient(circuit, options);
  assert(!fixed.converged());
  assert(fixed.diagnostics().rejected_newton_steps == 0);

  auto reference_options = options;
  reference_options.time_step_s = 1.0e-7;
  reference_options.nonlinear.max_newton_iterations = 100;
  const auto reference = spikes::solve_transient(circuit, reference_options);
  assert(reference.converged());

  options.adaptive_time_step = true;
  options.minimum_time_step_s = 1.0e-9;
  options.lte_absolute_tolerance = 1.0e-6;
  options.lte_relative_tolerance = 1.0e-4;
  for (const std::size_t sparse_threshold : {std::size_t{1}, std::size_t{128}}) {
    options.sparse_linear_threshold = sparse_threshold;
    const auto recovered = spikes::solve_transient(circuit, options);
    assert(recovered.converged());
    assert(recovered.diagnostics().rejected_newton_steps > 0);
    assert(recovered.diagnostics().failed_time_s == 0.0);
    assert(recovered.diagnostics().minimum_accepted_step_s < options.time_step_s);
    assert(near(recovered.points().back().node_voltage("out"),
                reference.points().back().node_voltage("out"), 6.0e-3));
    assert(recovered.points().back().time_s == options.stop_time_s);
    for (std::size_t index = 1; index < recovered.points().size(); ++index) {
      assert(recovered.points()[index].time_s > recovered.points()[index - 1].time_s);
    }
    if (sparse_threshold == 1) {
      // One primary and one BE companion pattern, not one ordering per Newton solve.
      assert(recovered.diagnostics().sparse_symbolic_analyses == 2);
      assert(recovered.diagnostics().embedded_lte_solves > 2);
    }
  }
  options.nonlinear.max_newton_iterations = 1;
  options.minimum_time_step_s = 1.0e-5;
  const auto bounded = spikes::solve_transient(circuit, options);
  assert(!bounded.converged());
  assert(bounded.diagnostics().rejected_newton_steps > 0);
  assert(bounded.message().find("minimum timestep") != std::string::npos);
  assert(bounded.points().empty());
  options.minimum_time_step_s = 1.0e-9;
  options.max_rejected_steps = 1;
  const auto limited = spikes::solve_transient(circuit, options);
  assert(!limited.converged());
  assert(limited.diagnostics().rejected_newton_steps == 2);
  assert(limited.message().find("rejection limit") != std::string::npos);
  assert(limited.points().empty());
}

void adaptive_sparse_linear_companion_reuses_symbolic_ordering() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.adaptive_time_step = true;
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 1.0e-3;
  options.sparse_linear_threshold = 1;
  const auto sparse = spikes::solve_transient(circuit, options);
  assert(sparse.converged());
  assert(sparse.diagnostics().embedded_lte_solves > 2);
  assert(sparse.diagnostics().sparse_symbolic_analyses == 2);
  assert(sparse.diagnostics().sparse_numeric_factorizations > 2);
  options.sparse_linear_threshold = 128;
  const auto dense = spikes::solve_transient(circuit, options);
  assert(dense.converged());
  assert(sparse.points().size() == dense.points().size());
  for (std::size_t index = 0; index < sparse.points().size(); ++index) {
    assert(near(sparse.points()[index].time_s, dense.points()[index].time_s, 1.0e-14));
    assert(near(sparse.points()[index].node_voltage("out"),
                dense.points()[index].node_voltage("out"), 1.0e-10));
  }
}

void adaptive_bdf2_restarts_order_and_bounds_growth_after_short_source_edges() {
  spikes::Circuit circuit;
  spikes::PulseWaveform pulse;
  pulse.initial_value = 0.0;
  pulse.pulsed_value = 1.0;
  pulse.delay_s = 99e-9;
  pulse.rise_time_s = 1e-9;
  pulse.fall_time_s = 1e-9;
  pulse.pulse_width_s = 100e-9;
  pulse.period_s = 1e-6;
  circuit.add_pulse_voltage_source("V1", "in", "0", pulse);
  circuit.add_resistor("R1", "in", "out", 100.0);
  circuit.add_capacitor("C1", "out", "0", 1e-9);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.adaptive_time_step = true;
  options.time_step_s = 100e-9;
  options.stop_time_s = 500e-9;
  options.minimum_time_step_s = 1e-12;
  const auto adaptive = spikes::solve_transient(circuit, options);
  assert(adaptive.converged());
  double previous_step = 0.0;
  double previous_time = 0.0;
  for (const auto &point : adaptive.points()) {
    const double step = point.time_s - previous_time;
    if (previous_step > 0.0) {
      assert(step <= 2.0 * previous_step * (1.0 + 1e-8));
    }
    previous_step = step;
    previous_time = point.time_s;
  }
  // Startup, four pulse corners and two post-corner restarts. Adjacent
  // 1-ns corners share their restart; they are not eight independent steps.
  assert(adaptive.diagnostics().backward_euler_steps == 7);
  for (const double corner : {99e-9, 100e-9, 200e-9, 201e-9}) {
    assert(std::any_of(adaptive.points().begin(), adaptive.points().end(),
                       [corner](const auto &point) {
                         return near(point.time_s, corner, 1e-18);
                       }));
  }
  auto reference_options = options;
  reference_options.adaptive_time_step = false;
  reference_options.time_step_s = 0.1e-9;
  reference_options.minimum_time_step_s = 1e-12;
  const auto reference = spikes::solve_transient(circuit, reference_options);
  assert(reference.converged());
  assert(near(adaptive.points().back().node_voltage("out"),
              reference.points().back().node_voltage("out"), 3e-3));
}

void nonlinear_storage_residual_preserves_microamp_kcl_at_picosecond_steps() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "out", "0", 1.0);
  circuit.add_resistor("R1", "out", "0", 1e6);
  circuit.add_capacitor("C1", "out", "0", 100e-6, 1.0);
  circuit.add_diode("D1", "0", "out");
  spikes::TransientOptions options;
  options.time_step_s = 1e-12;
  options.stop_time_s = 3e-12;
  options.nonlinear.absolute_tolerance = 1e-12;
  options.nonlinear.relative_tolerance = 0.0;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  for (const std::size_t threshold : {std::size_t{1}, std::size_t{128}}) {
    options.sparse_linear_threshold = threshold;
    const auto result = spikes::solve_transient(circuit, options);
    assert(result.converged());
    assert(result.diagnostics().residual_inf_norm <= 1e-12);
    for (const auto &point : result.points()) {
      assert(near(point.node_voltage("out"), 1.0, 1e-14));
      assert(near(point.element_current("C1"), 0.0, 1e-12));
      assert(near(point.element_current("V1"), -1e-6, 1e-12));
    }
  }
}

void nonlinear_storage_step_coordinates_preserve_charging_kcl() {
  for (const auto method : {spikes::TransientIntegrationMethod::backward_euler,
                            spikes::TransientIntegrationMethod::hybrid_trapezoidal,
                            spikes::TransientIntegrationMethod::bdf2}) {
    for (const std::size_t threshold : {std::size_t{1}, std::size_t{128}}) {
      spikes::Circuit circuit;
      circuit.add_current_source("I1", "0", "out", 1e-3);
      circuit.add_capacitor("C1", "out", "0", 100e-6, 1.0);
      circuit.add_diode("D1", "0", "out");
      spikes::TransientOptions options;
      options.initialize_from_operating_point = false;
      options.time_step_s = 1e-12;
      options.stop_time_s = 8e-12;
      options.integration_method = method;
      options.sparse_linear_threshold = threshold;
      options.nonlinear.absolute_tolerance = 1e-12;
      options.nonlinear.relative_tolerance = 0.0;
      spikes::TransientWorkspace workspace;
      const auto result = spikes::solve_transient(circuit, options, workspace);
      assert(result.converged());
      for (const auto &point : result.points()) {
        // Reverse diode current is approximately -Is; independent KCL oracle.
        assert(near(point.element_current("C1"),
                    1e-3 + point.element_current("D1"), 1e-12));
        assert(near(point.node_voltage("out"), 1.0 + 10.0 * point.time_s, 2e-14));
      }
      // Session-style continuation preserves the unrounded storage change.
      const auto continued = spikes::solve_transient(circuit, options, workspace);
      assert(continued.converged());
      for (const auto &point : continued.points()) {
        assert(near(point.element_current("C1"),
                    1e-3 + point.element_current("D1"), 1e-12));
        assert(near(point.node_voltage("out"),
                    1.0 + 10.0 * (options.stop_time_s + point.time_s), 4e-14));
      }
    }
  }
}

void stiff_buck_extinction_completes_without_algebraic_error_suppression() {
  const auto make_circuit = [] {
    spikes::Circuit circuit;
    circuit.add_voltage_source("Vs", "in", "0", 12.0);
    spikes::PulseWaveform gate;
    gate.initial_value = 0.0;
    gate.pulsed_value = 5.0;
    gate.delay_s = 1e-6;
    gate.rise_time_s = gate.fall_time_s = 50e-9;
    gate.pulse_width_s = 4e-6;
    gate.period_s = 10e-6;
    circuit.add_pulse_voltage_source("Vgate", "gate", "0", gate);
    spikes::VoltageControlledSwitchModel model;
    model.on_resistance_ohm = .02;
    model.off_resistance_ohm = 1e6;
    model.threshold_voltage_v = 2.5;
    model.transition_voltage_v = .1;
    circuit.add_voltage_controlled_switch("Smain", "in", "sw", "gate", "0", model);
    spikes::DiodeModel diode;
    diode.saturation_current_a = 1e-9;
    circuit.add_diode("Dfree", "0", "sw", diode);
    circuit.add_inductor("L1", "sw", "out", 10e-6);
    circuit.add_resistor("Rload", "out", "0", 10.0);
    circuit.add_resistor("Resr", "out", "cap", .03);
    circuit.add_capacitor("Cout", "cap", "0", 100e-6);
    return circuit;
  };
  const auto circuit = make_circuit();
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 200e-9;
  options.stop_time_s = 200e-6;
  options.minimum_time_step_s = 1e-15;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.adaptive_time_step = true;
  options.lte_absolute_tolerance = 1e-6;
  options.lte_relative_tolerance = 1e-4;
  const auto dense = spikes::solve_transient(circuit, options);
  assert(dense.converged());
  assert(near(dense.points().back().time_s, options.stop_time_s, 1e-18));
  assert(dense.diagnostics().minimum_accepted_step_s < 1e-12);
  assert(dense.diagnostics().last_lte_ratio <= 1.0);
  options.sparse_linear_threshold = 1;
  const auto sparse = spikes::solve_transient(circuit, options);
  assert(sparse.converged());
  options.time_step_s = 20e-9;
  options.minimum_time_step_s = 1e-17;
  const auto accurate = spikes::solve_transient(circuit, options);
  assert(accurate.converged());
  options.time_step_s = 10e-9;
  options.minimum_time_step_s = 1e-17;
  options.lte_relative_tolerance = 2.5e-5;
  options.lte_absolute_tolerance = 2.5e-7;
  const auto refined = spikes::solve_transient(circuit, options);
  assert(refined.converged());
  const auto sample = [](const auto &result, double time, bool current) {
    const auto &points = result.points();
    const auto upper = std::lower_bound(points.begin(), points.end(), time,
        [](const auto &point, double target) { return point.time_s < target; });
    const auto value = [current](const auto &point) {
      return current ? point.element_current("L1") : point.node_voltage("out");
    };
    if (upper == points.begin()) return value(*upper);
    if (upper == points.end()) return value(points.back());
    const auto &lower = *(upper - 1);
    const double fraction = (time - lower.time_s) / (upper->time_s - lower.time_s);
    return value(lower) + fraction * (value(*upper) - value(lower));
  };
  double maximum_voltage_difference = 0.0;
  double maximum_current_difference = 0.0;
  for (const auto *comparison : {&sparse, &refined}) {
    assert(near(dense.points().back().node_voltage("out"),
                comparison->points().back().node_voltage("out"), .02));
    assert(near(dense.points().back().element_current("L1"),
                comparison->points().back().element_current("L1"), .01));
  }
  for (int microsecond = 1; microsecond <= 200; ++microsecond) {
      const double time = microsecond * 1e-6;
      maximum_voltage_difference = std::max(maximum_voltage_difference,
          std::abs(sample(accurate, time, false) - sample(refined, time, false)));
      maximum_current_difference = std::max(maximum_current_difference,
          std::abs(sample(accurate, time, true) - sample(refined, time, true)));
  }
  std::cout << "Buck 20-ns/10-ns refined comparison: max dV="
            << maximum_voltage_difference << " V, max dI="
            << maximum_current_difference << " A, minimum h="
            << dense.diagnostics().minimum_accepted_step_s << " s" << std::endl;
  assert(maximum_voltage_difference < .02);
  assert(maximum_current_difference < .02);
  // Too-large user step floors remain failures, not silently relaxed accuracy.
  options = spikes::TransientOptions{};
  options.initialize_from_operating_point = false;
  options.time_step_s = 200e-9;
  options.stop_time_s = 200e-6;
  options.minimum_time_step_s = 1e-12;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.adaptive_time_step = true;
  options.lte_absolute_tolerance = 1e-6;
  options.lte_relative_tolerance = 1e-4;
  const auto limited = spikes::solve_transient(circuit, options);
  assert(!limited.converged());
  assert(limited.message().find("minimum timestep") != std::string::npos);
}

void uic_storage_predictor_cannot_hide_a_floating_singular_subsystem() {
  for (const std::size_t threshold : {std::size_t{1}, std::size_t{128}}) {
    spikes::Circuit circuit;
    circuit.add_capacitor("C1", "out", "0", 100e-6, 1.0);
    circuit.add_diode("D1", "0", "out");
    circuit.add_resistor("Rf", "floating1", "floating2", 100.0);
    spikes::TransientOptions options;
    options.initialize_from_operating_point = false;
    options.time_step_s = 1e-12;
    options.stop_time_s = 2e-12;
    options.sparse_linear_threshold = threshold;
    const auto result = spikes::solve_transient(circuit, options);
    assert(result.status() == spikes::SolveStatus::singular);
    assert(result.points().empty());
  }
}

void dynamic_diode_releases_stored_charge_as_reverse_recovery_current() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vreverse", "rail", "0", -5.0);
  circuit.add_resistor("Rlimit", "rail", "anode", 10.0);
  spikes::DynamicDiodeModel model;
  model.transit_time_s = 100.0e-9;
  model.junction_capacitance_f = 0.0;
  model.initial_stored_charge_c = 1.0e-9;
  circuit.add_dynamic_diode("Drr", "anode", "0", model);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1.0e-9;
  options.stop_time_s = 300.0e-9;
  options.max_steps = 1'000;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().matrix_order == 4);
  const double initial_reverse = result.points().front().element_current("Drr");
  const double final_reverse = result.points().back().element_current("Drr");
  assert(initial_reverse < -8.0e-3);
  assert(final_reverse < 0.0);
  assert(std::abs(final_reverse) < 0.08 * std::abs(initial_reverse));
  assert(near(result.points().front().element_current("Rlimit"),
              initial_reverse, 1.0e-10));

  options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  const auto unsupported = spikes::solve_transient(circuit, options);
  assert(!unsupported.converged());
  assert(unsupported.message().find("dynamic diode reverse recovery") !=
         std::string::npos);
}

void electrothermal_resistor_couples_joule_heat_and_resistance() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vheat", "rail", "0", 10.0);
  spikes::ElectrothermalResistorModel model;
  model.resistance_ohm = 10.0;
  model.temperature_coefficient_per_k = 1.0e-2;
  model.thermal_resistance_k_per_w = 1.0;
  model.thermal_capacitance_j_per_k = 1.0e-2;
  model.minimum_temperature_k = 250.0;
  circuit.add_electrothermal_resistor("Rth", "rail", "0", "temp", model);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.time_step_s = 1.0e-3;
  options.stop_time_s = 50.0e-3;
  options.max_steps = 100;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().total_newton_iterations > 0);
  const double initial_temperature = result.points().front().node_voltage("temp");
  const double final_temperature = result.points().back().node_voltage("temp");
  const double initial_current = result.points().front().element_current("Rth");
  const double final_current = result.points().back().element_current("Rth");
  assert(final_temperature > initial_temperature);
  assert(final_temperature > 8.0 && final_temperature < 10.0);
  assert(final_current < initial_current);
  assert(final_current > 0.90 && final_current < 0.93);

  options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  const auto unsupported = spikes::solve_transient(circuit, options);
  assert(!unsupported.converged());
}

void saturating_inductor_uses_flux_linkage_dae() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "drive", "0", 1.0);
  spikes::SaturatingInductorModel model;
  model.unsaturated_inductance_h = 1.0e-3;
  model.saturated_inductance_h = 1.0e-4;
  model.saturation_current_a = 0.1;
  circuit.add_saturating_inductor("Lsat", "drive", "0", model);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.time_step_s = 10.0e-6;
  options.stop_time_s = 1.0e-3;
  options.max_steps = 200;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().matrix_order == 3);
  const double final_current = result.points().back().element_current("Lsat");
  assert(final_current > 8.5 && final_current < 9.5);
  assert(result.diagnostics().total_newton_iterations > 0);
}

void sparse_transient_assembles_directly_and_reuses_symbolic_pattern() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);

  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 2.5e-4;
  options.sparse_linear_threshold = 1;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().completed_steps == 3);
  assert(result.diagnostics().sparse_assemblies == 3);
  assert(result.diagnostics().sparse_symbolic_analyses == 1);
  assert(result.diagnostics().sparse_numeric_factorizations == 2);
  assert(result.diagnostics().partial_numeric_refactorizations == 1);
  assert(result.diagnostics().factorization_reuses == 1);
}

void sparse_nonlinear_transient_matches_dense_and_refactorizes_numeric_values() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-9);
  circuit.add_diode("D1", "out", "0");

  spikes::TransientOptions dense_options;
  dense_options.initialize_from_operating_point = false;
  dense_options.time_step_s = 1.0e-7;
  dense_options.stop_time_s = 2.0e-6;
  dense_options.max_steps = 100;
  dense_options.sparse_linear_threshold = 1'000'000;
  const auto dense = spikes::solve_transient(circuit, dense_options);
  assert(dense.converged());

  auto sparse_options = dense_options;
  sparse_options.sparse_linear_threshold = 1;
  const auto sparse = spikes::solve_transient(circuit, sparse_options);
  assert(sparse.converged());
  assert(near(sparse.points().back().node_voltage("out"),
              dense.points().back().node_voltage("out"), 2.0e-10));
  assert(sparse.diagnostics().sparse_assemblies >
         sparse.diagnostics().completed_steps);
  assert(sparse.diagnostics().sparse_symbolic_analyses == 1);
  assert(sparse.diagnostics().sparse_numeric_factorizations > 0);
  assert(sparse.diagnostics().partial_numeric_refactorizations > 0);
  assert(sparse.diagnostics().total_newton_iterations > 0);
}

void electrothermal_wbg_transient_integrates_charge_and_thermal_state() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vd", "drain", "0", 10.0);
  circuit.add_voltage_source("Vg", "gate", "0", 5.0);
  spikes::WbgFetElectrothermalModel model;
  model.gate_drain_capacitance_f = 1.0e-10;
  model.drain_source_capacitance_f = 1.0e-10;
  model.thermal_capacitance_j_per_k = 1.0e-3;
  circuit.add_wbg_fet_electrothermal("QW1", "drain", "gate", "0", "0",
                                    "tj_rise", model);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.time_step_s = 1.0e-9;
  options.stop_time_s = 10.0e-9;
  options.sparse_linear_threshold = 1;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.points().size() == 10);
  assert(result.points().back().node_voltage("tj_rise") > 0.0);
  assert(std::isfinite(result.points().back().element_current("QW1")));
  assert(std::abs(result.points().front().element_current("QW1") -
                  result.points().back().element_current("QW1")) > 0.5);
  assert(result.diagnostics().sparse_symbolic_analyses == 1);
  assert(result.diagnostics().partial_numeric_refactorizations > 0);

  options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  const auto unsupported = spikes::solve_transient(circuit, options);
  assert(!unsupported.converged());
}

#ifdef SPIKES_TEST_OSDI04_CAPACITOR
void osdi_0_4_reactive_callbacks_stamp_native_transient_mna() {
  const auto capacitor = spikes::load_trusted_osdi_device(
      std::filesystem::path(SPIKES_TEST_OSDI04_CAPACITOR),
      "spikes_osdi_capacitor");
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "vin", "0", 1.0);
  circuit.add_resistor("R1", "vin", "out", 1000.0);
  circuit.add_osdi_device("NC1", {"out", "0"}, capacitor);

  spikes::TransientOptions options;
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 1.0e-3;
  options.initialize_from_operating_point = false;
  options.sparse_linear_threshold = 1;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.points().size() == 10);
  const double expected = 1.0 - std::pow(1.0 / 1.1, 10.0);
  assert(near(result.points().back().node_voltage("out"), expected, 2.0e-11));
  assert(std::isfinite(result.points().back().element_current("NC1")));
  assert(result.diagnostics().total_newton_iterations > 0);
  assert(result.diagnostics().sparse_symbolic_analyses == 1);

  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  const auto unsupported = spikes::solve_transient(circuit, options);
  assert(!unsupported.converged());
}
#endif

void analytic_sine_sources_use_internal_time_and_delay_breakpoints() {
  spikes::Circuit circuit;
  const spikes::SineWaveform wave{0.75, 2.0, 1000.0, 0.00023, 250.0, 30.0};
  circuit.add_sine_voltage_source("V1", "vin", "0", wave);
  circuit.add_sine_current_source("I1", "0", "cur", wave);
  circuit.add_resistor("R1", "vin", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1e-7);
  circuit.add_resistor("R2", "cur", "0", 1.0);
  spikes::TransientOptions options;
  options.time_step_s = 1e-4;
  options.stop_time_s = 1e-3;
  options.integration_method = spikes::TransientIntegrationMethod::bdf2;
  options.adaptive_time_step = true;
  options.lte_absolute_tolerance = 1e-6;
  options.lte_relative_tolerance = 1e-4;
  const auto result = spikes::solve_transient(circuit, options);
  assert(result.converged());
  assert(result.diagnostics().source_breakpoint_steps >= 1);
  assert(result.points().size() > 11);
  bool found_delay = false;
  for (const auto &point : result.points()) {
    const double elapsed = std::max(0.0, point.time_s - 0.00023);
    const double expected = 0.75 + 2.0 * std::exp(-250.0 * elapsed) *
        std::sin(2.0 * 3.14159265358979323846 * 1000.0 * elapsed +
                 3.14159265358979323846 / 6.0);
    assert(near(point.node_voltage("vin"), expected, 2e-11));
    assert(near(point.node_voltage("cur"), expected, 2e-11));
    found_delay = found_delay || near(point.time_s, wave.delay_s, 1e-15);
  }
  assert(found_delay);
  for (const double invalid : {-1.0, 0.0, std::numeric_limits<double>::infinity()}) {
    bool rejected = false;
    try { circuit.add_sine_voltage_source("bad", "x", "0", {0, 1, invalid}); }
    catch (const std::invalid_argument &) { rejected = true; }
    assert(rejected);
  }
}

} // namespace

int main() {
  radau_ramp_all_time_oracles_cover_signed_scales_and_dense_sparse();
  radau_jump_limits_preserve_storage_and_persistent_edge_identity();
  radau_is_stiffly_damped_and_rejects_unsupported_history_contracts();
  radau_third_order_refinement_and_nonzero_uic_are_independent_of_history();
  radau_full_duty_pulse_has_no_spurious_period_jump();
  radau_sinusoidal_forcing_has_third_order_endpoint_convergence();
  radau_pwl_checkpoint_and_failed_window_preserve_storage();
  source_breakpoint_diagnostics_include_on_grid_accepted_corners();
  analytic_sine_sources_use_internal_time_and_delay_breakpoints();
  rc_step_matches_backward_euler_recurrence();
  rl_step_matches_backward_euler_recurrence();
  dc_initialization_produces_a_time_zero_sample();
  dc_treats_capacitors_as_open_and_inductors_as_shorts();
  invalid_inputs_and_work_bounds_fail_closed();
  singular_and_nonlinear_nonconvergence_are_diagnostic();
  pulse_sources_force_exact_switching_breakpoints();
  pwl_sources_interpolate_and_force_knot_steps();
  waveform_validation_and_breakpoint_work_bounds_fail_closed();
  pulse_driven_switch_resolves_on_and_off_states_at_edges();
  hybrid_trapezoidal_improves_smooth_rc_accuracy_and_reuses_lu();
  bdf2_improves_smooth_rc_accuracy_and_reports_order_restarts();
  adaptive_embedded_lte_rejects_and_refines_rc_steps();
  adaptive_embedded_lte_solves_nonlinear_diode_dae();
  adaptive_newton_failure_retries_without_committing_charge_history();
  adaptive_sparse_linear_companion_reuses_symbolic_ordering();
  adaptive_bdf2_restarts_order_and_bounds_growth_after_short_source_edges();
  nonlinear_storage_residual_preserves_microamp_kcl_at_picosecond_steps();
  nonlinear_storage_step_coordinates_preserve_charging_kcl();
  stiff_buck_extinction_completes_without_algebraic_error_suppression();
  uic_storage_predictor_cannot_hide_a_floating_singular_subsystem();
  dynamic_diode_releases_stored_charge_as_reverse_recovery_current();
  electrothermal_resistor_couples_joule_heat_and_resistance();
  saturating_inductor_uses_flux_linkage_dae();
  sparse_transient_assembles_directly_and_reuses_symbolic_pattern();
  sparse_nonlinear_transient_matches_dense_and_refactorizes_numeric_values();
  electrothermal_wbg_transient_integrates_charge_and_thermal_state();
#ifdef SPIKES_TEST_OSDI04_CAPACITOR
  osdi_0_4_reactive_callbacks_stamp_native_transient_mna();
#endif
  std::cout << "SPIKES transient tests passed\n";
  return 0;
}
