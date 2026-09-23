#include "spikes/transient_solver.hpp"
#include "spikes/osdi_device.hpp"

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

} // namespace

int main() {
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
