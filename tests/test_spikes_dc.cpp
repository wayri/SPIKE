#include "spikes/dc_solver.hpp"
#include "spikes/osdi_device.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
#include <filesystem>
#include <stdexcept>

namespace {

bool near(double actual, double expected, double tolerance = 1e-12) {
  return std::abs(actual - expected) <= tolerance;
}

void voltage_divider_reports_operating_point_and_power() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "vin", "0", 10.0);
  circuit.add_resistor("R1", "vin", "vout", 1000.0);
  circuit.add_resistor("R2", "vout", "0", 1000.0);

  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.node_voltage("vin"), 10.0));
  assert(near(result.node_voltage("vout"), 5.0));
  assert(near(result.element_current("R1"), 0.005));
  assert(near(result.element_power("R1"), 0.025));
  assert(near(result.element_current("V1"), -0.005));
  assert(near(result.element_power("V1"), -0.05));
  assert(result.diagnostics().matrix_order == 3);
  assert(result.diagnostics().residual_inf_norm < 1e-14);
}

void current_source_sign_follows_declared_terminals() {
  spikes::Circuit circuit;
  circuit.add_current_source("I1", "0", "out", 0.001);
  circuit.add_resistor("R1", "out", "0", 1000.0);

  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.node_voltage("out"), 1.0));
  assert(near(result.element_current("I1"), 0.001));
  assert(near(result.element_power("I1"), -0.001));
}

void floating_network_fails_closed() {
  spikes::Circuit circuit;
  circuit.add_resistor("R1", "a", "b", 1000.0);

  const auto result = spikes::solve_operating_point(circuit);
  assert(!result.converged());
  assert(result.status() == spikes::SolveStatus::singular);
  assert(result.node_voltages().empty());
}

void invalid_model_is_rejected_before_assembly() {
  spikes::Circuit circuit;
  bool rejected = false;
  try {
    circuit.add_resistor("R1", "a", "0", 0.0);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);

  circuit.add_resistor("R1", "a", "0", 10.0);
  rejected = false;
  try {
    circuit.add_current_source("R1", "0", "a", 1.0);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

void ground_aliases_resolve_to_the_reference_node() {
  spikes::Circuit circuit;
  assert(circuit.node("GND") == spikes::ground_node);
  circuit.add_voltage_source("V1", "out", "gnd", 2.5);
  circuit.add_resistor("R1", "out", "0", 1000.0);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.node_voltage("GND"), 0.0));
  assert(near(result.node_voltage("out"), 2.5));
}

void current_driven_diode_matches_the_shockley_solution() {
  constexpr double saturation_current = 1.0e-12;
  constexpr double forced_current = 1.0e-3;
  constexpr double temperature = 300.15;
  constexpr double boltzmann_over_charge = 8.617333262145e-5;

  spikes::Circuit circuit;
  circuit.add_current_source("I1", "0", "junction", forced_current);
  circuit.add_diode("D1", "junction", "0",
                    spikes::DiodeModel{saturation_current, 1.0, temperature});

  const auto result = spikes::solve_operating_point(circuit);
  const double expected = boltzmann_over_charge * temperature *
                          std::log1p(forced_current / saturation_current);
  assert(result.converged());
  assert(near(result.node_voltage("junction"), expected, 5.0e-8));
  assert(near(result.element_current("D1"), forced_current, 2.0e-9));
  assert(result.diagnostics().nonlinear_iterations > 0);
  assert(result.diagnostics().junction_limit_steps > 0);
  assert(result.diagnostics().residual_inf_norm < 2.0e-9);
}

void reverse_biased_diode_remains_finite() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "junction", "0", -5.0);
  circuit.add_diode("D1", "junction", "0",
                    spikes::DiodeModel{1.0e-12, 1.0, 300.15});

  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.node_voltage("junction"), -5.0));
  assert(near(result.element_current("D1"), -1.0e-12, 1.0e-18));
  assert(std::isfinite(result.element_power("D1")));
}

void resistor_fed_diode_satisfies_kcl_after_damped_newton() {
  constexpr double supply_v = 5.0;
  constexpr double resistance_ohm = 1000.0;
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "supply", "0", supply_v);
  circuit.add_resistor("R1", "supply", "junction", resistance_ohm);
  circuit.add_diode("D1", "junction", "0");

  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  const double voltage = result.node_voltage("junction");
  const double resistor_current = (supply_v - voltage) / resistance_ohm;
  assert(voltage > 0.6 && voltage < 0.8);
  assert(near(result.element_current("D1"), resistor_current, 2.0e-9));
  assert(result.diagnostics().nonlinear_iterations > 1);
}

void nonlinear_iteration_limit_fails_closed() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "supply", "0", 5.0);
  circuit.add_resistor("R1", "supply", "junction", 1000.0);
  circuit.add_diode("D1", "junction", "0");
  spikes::SolverOptions options;
  options.max_newton_iterations = 1;

  const auto result = spikes::solve_operating_point(circuit, options);
  assert(!result.converged());
  assert(result.status() == spikes::SolveStatus::nonconverged);
  assert(result.node_voltages().empty());
  assert(result.elements().empty());
  assert(result.diagnostics().nonlinear_iterations == 1);
}

void invalid_diode_model_is_rejected() {
  spikes::Circuit circuit;
  bool rejected = false;
  try {
    circuit.add_diode("D1", "a", "0",
                      spikes::DiodeModel{-1.0, 1.0, 300.15});
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

void voltage_controlled_switch_is_bidirectional_and_bounded() {
  spikes::VoltageControlledSwitchModel model;
  model.on_resistance_ohm = 1.0;
  model.off_resistance_ohm = 1.0e6;
  model.threshold_voltage_v = 2.5;
  model.transition_voltage_v = 0.1;

  for (double supply : {10.0, -10.0}) {
    spikes::Circuit circuit;
    circuit.add_voltage_source("Vs", "in", "0", supply);
    circuit.add_voltage_source("Vg", "gate", "0", 5.0);
    circuit.add_voltage_controlled_switch("S1", "in", "out", "gate", "0",
                                          model);
    circuit.add_resistor("Rload", "out", "0", 10.0);
    const auto result = spikes::solve_operating_point(circuit);
    assert(result.converged());
    assert(near(result.node_voltage("out"), supply * 10.0 / 11.0, 1.0e-8));
    assert((result.element_current("S1") > 0.0) == (supply > 0.0));
  }

  spikes::Circuit off;
  off.add_voltage_source("Vs", "in", "0", 10.0);
  off.add_voltage_source("Vg", "gate", "0", 0.0);
  off.add_voltage_controlled_switch("S1", "in", "out", "gate", "0", model);
  off.add_resistor("Rload", "out", "0", 10.0);
  const auto off_result = spikes::solve_operating_point(off);
  assert(off_result.converged());
  assert(std::abs(off_result.node_voltage("out")) < 2.0e-4);

  bool rejected = false;
  model.off_resistance_ohm = model.on_resistance_ohm;
  try {
    off.add_voltage_controlled_switch("Sbad", "x", "0", "gate", "0", model);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

void preconditioned_cg_solves_spd_network_and_threads_matvec() {
  spikes::Circuit circuit;
  circuit.add_resistor("R0", "n0", "0", 1.0);
  for (int index = 1; index < 200; ++index) {
    circuit.add_resistor("R" + std::to_string(index),
                         "n" + std::to_string(index - 1),
                         "n" + std::to_string(index), 1.0);
  }
  circuit.add_current_source("I1", "0", "n199", 1.0);
  spikes::SolverOptions options;
  options.linear_solver = spikes::LinearSolverMethod::conjugate_gradient;
  options.linear_threads = 2;
  options.max_linear_iterations = 1000;

  const auto result = spikes::solve_operating_point(circuit, options);
  assert(result.converged());
  assert(near(result.node_voltage("n199"), 200.0, 2.0e-8));
  assert(result.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::conjugate_gradient);
  assert(result.diagnostics().linear_iterations > 0);
  assert(result.diagnostics().linear_threads == 2);
}

void conjugate_gradient_rejects_indefinite_mna() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "out", "0", 1.0);
  circuit.add_resistor("R1", "out", "0", 1.0);
  spikes::SolverOptions options;
  options.linear_solver = spikes::LinearSolverMethod::conjugate_gradient;
  const auto result = spikes::solve_operating_point(circuit, options);
  assert(!result.converged());
  assert(result.status() == spikes::SolveStatus::numerical_failure);
  assert(result.message().find("positive-definite") != std::string::npos);
}

void restarted_gmres_solves_indefinite_and_nonsymmetric_mna() {
  spikes::Circuit divider;
  divider.add_voltage_source("V1", "in", "0", 10.0);
  divider.add_resistor("R1", "in", "out", 1000.0);
  divider.add_resistor("R2", "out", "0", 1000.0);
  spikes::SolverOptions options;
  options.linear_solver = spikes::LinearSolverMethod::gmres;
  options.linear_threads = 2;
  const auto linear = spikes::solve_operating_point(divider, options);
  assert(linear.converged());
  assert(near(linear.node_voltage("out"), 5.0, 2.0e-9));
  assert(linear.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::gmres);
  assert(linear.diagnostics().linear_iterations > 0);

  spikes::Circuit controlled;
  controlled.add_voltage_source("Vs", "in", "0", 10.0);
  controlled.add_voltage_source("Vg", "gate", "0", 2.5);
  controlled.add_voltage_controlled_switch(
      "S1", "in", "out", "gate", "0");
  controlled.add_resistor("Rload", "out", "0", 10.0);
  const auto nonlinear = spikes::solve_operating_point(controlled, options);
  assert(nonlinear.converged());
  assert(nonlinear.node_voltage("out") > 9.99);
  assert(nonlinear.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::gmres);
  assert(nonlinear.diagnostics().linear_iterations > 0);
}

void sparse_lu_uses_linear_storage_and_reuses_newton_symbolics() {
  spikes::Circuit ladder;
  ladder.add_resistor("R0", "n0", "0", 1.0);
  for (int index = 1; index < 1000; ++index) {
    ladder.add_resistor("R" + std::to_string(index),
                        "n" + std::to_string(index - 1),
                        "n" + std::to_string(index), 1.0);
  }
  ladder.add_current_source("I1", "0", "n999", 1.0);
  spikes::SolverOptions sparse_options;
  sparse_options.linear_solver = spikes::LinearSolverMethod::sparse_lu;
  const auto sparse = spikes::solve_operating_point(ladder, sparse_options);
  assert(sparse.converged());
  assert(near(sparse.node_voltage("n999"), 1000.0, 2.0e-7));
  assert(sparse.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::sparse_lu);
  assert(sparse.diagnostics().matrix_nonzeros <
         4 * sparse.diagnostics().matrix_order);
  assert(sparse.diagnostics().symbolic_analyses == 1);
  assert(sparse.diagnostics().numeric_factorizations == 1);

  spikes::SolverOptions qr_options;
  qr_options.linear_solver = spikes::LinearSolverMethod::sparse_qr;
  const auto qr = spikes::solve_operating_point(ladder, qr_options);
  assert(qr.converged());
  assert(near(qr.node_voltage("n999"), 1000.0, 2.0e-7));
  assert(qr.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::sparse_qr);
  assert(qr.diagnostics().symbolic_analyses == 1);
  assert(qr.diagnostics().numeric_factorizations == 1);

  spikes::Circuit nonlinear;
  nonlinear.add_voltage_source("Vs", "in", "0", 10.0);
  nonlinear.add_voltage_source("Vg", "gate", "0", 2.5);
  nonlinear.add_voltage_controlled_switch(
      "S1", "in", "out", "gate", "0");
  nonlinear.add_resistor("Rload", "out", "0", 10.0);
  const auto switched =
      spikes::solve_operating_point(nonlinear, sparse_options);
  assert(switched.converged());
  assert(switched.diagnostics().symbolic_analyses == 1);
  assert(switched.diagnostics().numeric_factorizations > 1);
}

void ilu_gmres_solves_large_indefinite_sparse_mna() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "n0", "0", 10.0);
  for (int index = 1; index <= 400; ++index) {
    circuit.add_resistor("R" + std::to_string(index),
                         "n" + std::to_string(index - 1),
                         "n" + std::to_string(index), 1.0);
  }
  circuit.add_resistor("Rload", "n400", "0", 400.0);
  spikes::SolverOptions options;
  options.linear_solver = spikes::LinearSolverMethod::ilu_gmres;
  options.max_linear_iterations = 2000;
  const auto result = spikes::solve_operating_point(circuit, options);
  assert(result.converged());
  assert(near(result.node_voltage("n400"), 5.0, 2.0e-8));
  assert(result.diagnostics().linear_solver_used ==
         spikes::LinearSolverMethod::ilu_gmres);
  assert(result.diagnostics().linear_iterations > 0);
  assert(result.diagnostics().matrix_nonzeros <
         4 * result.diagnostics().matrix_order);
}

void level1_mosfet_is_native_four_terminal_and_bidirectional() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vs", "rail", "0", 10.0);
  circuit.add_voltage_source("Vg", "gate", "0", 5.0);
  circuit.add_resistor("Rload", "rail", "drain", 1000.0);
  spikes::MosfetLevel1Model model;
  model.threshold_voltage_v = 1.0;
  model.transconductance_a_per_v2 = 1.0e-2;
  model.channel_length_modulation_per_v = 0.02;
  model.body_effect_sqrt_v = 0.4;
  circuit.add_mosfet_level1("M1", "drain", "gate", "0", "0", model);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(result.node_voltage("drain") > 0.0);
  assert(result.node_voltage("drain") < 0.5);
  assert(near(result.element_current("M1"),
              result.element_current("Rload"), 2.0e-9));
  assert(result.diagnostics().matrix_nonzeros > 0);

  spikes::Circuit reverse;
  reverse.add_voltage_source("Vd", "drain", "0", -1.0);
  reverse.add_voltage_source("Vg", "gate", "0", 5.0);
  reverse.add_mosfet_level1("M1", "drain", "gate", "0", "0", model);
  const auto reversed = spikes::solve_operating_point(reverse);
  assert(reversed.converged());
  assert(reversed.element_current("M1") < 0.0);

  bool rejected = false;
  try {
    model.transconductance_a_per_v2 = 0.0;
    reverse.add_mosfet_level1("Mbad", "x", "g", "0", "0", model);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

void ebers_moll_bjt_is_native_three_terminal_and_conserves_kcl() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vcc", "rail", "0", 5.0);
  circuit.add_voltage_source("Vb", "base", "0", 0.70);
  circuit.add_resistor("Rc", "rail", "collector", 1000.0);
  spikes::BjtEbersMollModel model;
  model.saturation_current_a = 1.0e-15;
  model.forward_alpha = 0.99;
  model.reverse_alpha = 0.5;
  circuit.add_bjt_ebers_moll("Q1", "collector", "base", "0", model);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(result.node_voltage("collector") > 3.0);
  assert(result.node_voltage("collector") < 5.0);
  assert(near(result.element_current("Q1"),
              result.element_current("Rc"), 2.0e-9));

  spikes::Circuit reverse;
  reverse.add_voltage_source("Vc", "collector", "0", 0.0);
  reverse.add_voltage_source("Vb", "base", "0", 0.70);
  reverse.add_voltage_source("Ve", "emitter", "0", 5.0);
  reverse.add_bjt_ebers_moll("Q1", "collector", "base", "emitter", model);
  const auto reversed = spikes::solve_operating_point(reverse);
  assert(reversed.converged());
  assert(std::isfinite(reversed.element_current("Q1")));
}

void wbg_fet_constitutive_point_conserves_current_charge_and_has_physics() {
  spikes::WbgFetElectrothermalModel gan;
  gan.transconductance_a_per_v2 = 0.2;
  gan.threshold_temperature_coefficient_v_per_k = 0.0;
  const auto cold = spikes::evaluate_wbg_fet_electrothermal(
      gan, 10.0, 5.0, 0.0, 0.0, 0.0);
  const auto hot = spikes::evaluate_wbg_fet_electrothermal(
      gan, 10.0, 5.0, 0.0, 0.0, 100.0);
  double current_sum = 0.0;
  double charge_sum = 0.0;
  for (std::size_t row = 0; row < 4; ++row) {
    current_sum += cold.terminal_current_a[row];
    charge_sum += cold.terminal_charge_c[row];
    for (std::size_t column = 0; column < 5; ++column) {
      double jacobian_column_sum = 0.0;
      for (std::size_t terminal = 0; terminal < 4; ++terminal) {
        jacobian_column_sum += cold.current_jacobian[terminal][column];
      }
      assert(std::abs(jacobian_column_sum) < 1.0e-8);
    }
  }
  assert(std::abs(current_sum) < 1.0e-12);
  assert(std::abs(charge_sum) < 1.0e-24);
  assert(cold.dissipated_power_w > 0.0);
  assert(hot.terminal_current_a[0] < cold.terminal_current_a[0]);

  spikes::WbgFetElectrothermalModel sic = gan;
  sic.technology = spikes::WbgTechnology::sic_mosfet;
  const auto gan_reverse = spikes::evaluate_wbg_fet_electrothermal(
      gan, -1.0, 0.0, 0.0, 0.0, 0.0);
  const auto sic_reverse = spikes::evaluate_wbg_fet_electrothermal(
      sic, -1.0, 0.0, 0.0, 0.0, 0.0);
  assert(sic_reverse.terminal_current_a[0] <
         gan_reverse.terminal_current_a[0] - 1.0e-6);

  const auto avalanche = spikes::evaluate_wbg_fet_electrothermal(
      gan, 700.0, 0.0, 0.0, 0.0, 0.0);
  assert(avalanche.terminal_current_a[0] > 1.0e-6);
}

void wbg_fet_stamps_coupled_electrothermal_sparse_mna() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vd", "drain", "0", 10.0);
  circuit.add_voltage_source("Vg", "gate", "0", 5.0);
  spikes::WbgFetElectrothermalModel model;
  model.transconductance_a_per_v2 = 0.1;
  model.thermal_resistance_k_per_w = 2.0;
  circuit.add_wbg_fet_electrothermal(
      "QW1", "drain", "gate", "0", "0", "tj_rise", model);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  const double temperature_rise = result.node_voltage("tj_rise");
  const double power = result.element_power("QW1");
  assert(temperature_rise > 0.0 && temperature_rise < 50.0);
  assert(near(temperature_rise, power * model.thermal_resistance_k_per_w,
              2.0e-7));
  assert(result.element_current("QW1") > 0.0);
  assert(result.diagnostics().nonlinear_iterations > 0);
  assert(result.diagnostics().matrix_nonzeros > 0);

  bool rejected = false;
  try {
    model.thermal_resistance_k_per_w = 0.0;
    circuit.add_wbg_fet_electrothermal(
        "Qbad", "x", "g", "0", "0", "thermal_bad", model);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

#ifdef SPIKES_TEST_OSDI_ARTIFACT
void trusted_osdi_device_registers_directly_in_cpp_sparse_mna() {
  const auto device = spikes::load_trusted_osdi_0_3_device(
      std::filesystem::path(SPIKES_TEST_OSDI_ARTIFACT),
      "spikes_linear_resistor");
  assert(device->terminal_count() == 2);
  assert(device->node_count() == 2);

  spikes::Circuit circuit;
  circuit.add_voltage_source("V1", "in", "0", 1.0);
  circuit.add_osdi_device("N1", {"in", "0"}, device);
  const auto result = spikes::solve_operating_point(circuit);
  assert(result.converged());
  assert(near(result.element_current("N1"), 1.0e-3, 1.0e-12));
  assert(near(result.element_current("V1"), -1.0e-3, 1.0e-12));
  assert(result.diagnostics().nonlinear_iterations > 0);
}
#endif

#if defined(SPIKES_TEST_BSIM_BULK_OSDI) && defined(SPIKES_TEST_BSIM_CMG_OSDI)
void official_berkeley_bsim_osdi_models_expose_parameters_dc_charge_and_noise() {
  const auto exercise = [](const std::filesystem::path &artifact,
                           const char *module_name) {
    const std::array<spikes::OsdiParameterAssignment, 3> geometry{
        spikes::OsdiParameterAssignment{"L", 1.0e-6, true},
        spikes::OsdiParameterAssignment{"W", 10.0e-6, true},
        spikes::OsdiParameterAssignment{"TNOIMOD", std::int32_t{1}, false}};
    const std::array<spikes::OsdiParameterAssignment, 3> cmg_geometry{
        spikes::OsdiParameterAssignment{"L", 30.0e-9, true},
        spikes::OsdiParameterAssignment{"NFIN", 2.0, true},
        spikes::OsdiParameterAssignment{"TNOIMOD", std::int32_t{1}, false}};
    const auto device = std::string_view(module_name) == "bsimbulk"
                            ? spikes::load_trusted_osdi_device(
                                  artifact, module_name, 300.15, geometry)
                            : spikes::load_trusted_osdi_device(
                                  artifact, module_name, 300.15, cmg_geometry);
    assert(device->abi_minor() == 4);
    assert(device->terminal_count() == 5);
    const auto metadata = device->parameter_info();
    assert(metadata.size() > 100);
    const auto named = [&metadata](std::string name) {
      std::transform(name.begin(), name.end(), name.begin(),
                     [](unsigned char value) { return static_cast<char>(std::tolower(value)); });
      return std::any_of(metadata.begin(), metadata.end(),
                         [&name](const spikes::OsdiParameterInfo &entry) {
                           return std::any_of(entry.names.begin(), entry.names.end(),
                                              [&name](std::string candidate) {
                                                std::transform(candidate.begin(), candidate.end(),
                                                               candidate.begin(), [](unsigned char value) {
                                                                 return static_cast<char>(std::tolower(value));
                                                               });
                                                return candidate == name;
                                              });
                         });
    };
    assert(named("L"));
    assert(named(std::string_view(module_name) == "bsimbulk" ? "W" : "NFIN"));

    std::vector<double> voltages(device->node_count(), 0.0);
    voltages[0] = 1.0; // drain
    voltages[1] = 1.2; // gate
    const auto dc = device->evaluate_dc(voltages);
    assert(dc.residual.size() == device->node_count());
    assert(!dc.jacobian.empty());
    assert(std::all_of(dc.residual.begin(), dc.residual.end(),
                       [](double value) { return std::isfinite(value); }));

    const auto state = device->initial_transient_state(voltages);
    assert(state.reactive_residual.size() == device->node_count());
    const auto noise = device->evaluate_noise(voltages, 1.0e6);
    assert(!noise.contributions.empty());
    assert(std::any_of(noise.contributions.begin(), noise.contributions.end(),
                       [](const spikes::OsdiNoiseContribution &entry) {
                         return entry.density_a2_per_hz > 0.0 &&
                                std::isfinite(entry.density_a2_per_hz);
                       }));
    const auto correlated_components = std::count_if(
        noise.contributions.begin(), noise.contributions.end(),
        [](const spikes::OsdiNoiseContribution &entry) {
          return entry.name == "corl" && entry.density_a2_per_hz > 0.0;
        });
    assert(correlated_components >= 1);
  };
  exercise(std::filesystem::path(SPIKES_TEST_BSIM_BULK_OSDI), "bsimbulk");
  exercise(std::filesystem::path(SPIKES_TEST_BSIM_CMG_OSDI), "bsimcmg_va");
}
#endif

#if defined(SPIKES_TEST_OSDI04_CAPACITOR) && defined(SPIKES_TEST_OSDI04_NOISE)
void osdi_0_4_traversal_transient_and_noise_callbacks_are_executed() {
  const auto capacitor = spikes::load_trusted_osdi_device(
      std::filesystem::path(SPIKES_TEST_OSDI04_CAPACITOR),
      "spikes_osdi_capacitor");
  assert(capacitor->abi_minor() == 4);
  assert(capacitor->node_count() == 2);
  const std::array<double, 2> zero{0.0, 0.0};
  const std::array<double, 2> charged{1.0, 0.0};
  const auto initial = capacitor->initial_transient_state(zero);
  const auto transient = capacitor->evaluate_transient_backward_euler(
      charged, zero, 1.0e-3, 1.0e-3, initial);
  assert(near(transient.residual[0], 1.0e-3, 1.0e-12));
  assert(near(transient.residual[1], -1.0e-3, 1.0e-12));
  bool found_positive_diagonal = false;
  bool found_negative_transfer = false;
  for (const auto &entry : transient.jacobian) {
    if (entry.row == 0 && entry.column == 0 &&
        near(entry.value, 1.0e-3, 1.0e-12)) {
      found_positive_diagonal = true;
    }
    if (entry.row == 0 && entry.column == 1 &&
        near(entry.value, -1.0e-3, 1.0e-12)) {
      found_negative_transfer = true;
    }
  }
  assert(found_positive_diagonal);
  assert(found_negative_transfer);

  const auto noisy = spikes::load_trusted_osdi_device(
      std::filesystem::path(SPIKES_TEST_OSDI04_NOISE), "spikes_osdi_noise");
  assert(noisy->abi_minor() == 4);
  const auto noise = noisy->evaluate_noise(zero, 1000.0);
  assert(noise.contributions.size() == 2);
  const auto thermal = std::find_if(
      noise.contributions.begin(), noise.contributions.end(),
      [](const spikes::OsdiNoiseContribution &entry) {
        return entry.name == "thermal";
      });
  const auto flicker = std::find_if(
      noise.contributions.begin(), noise.contributions.end(),
      [](const spikes::OsdiNoiseContribution &entry) {
        return entry.name == "flicker";
      });
  assert(thermal != noise.contributions.end());
  assert(flicker != noise.contributions.end());
  assert(thermal->density_a2_per_hz > 1.0e-24);
  assert(thermal->density_a2_per_hz < 1.0e-22);
  assert(thermal->type == spikes::OsdiNoiseType::white);
  assert(near(flicker->density_a2_per_hz, 1.0e-21, 1.0e-27));
  assert(flicker->type == spikes::OsdiNoiseType::flicker);
}
#endif

} // namespace

int main() {
  voltage_divider_reports_operating_point_and_power();
  current_source_sign_follows_declared_terminals();
  floating_network_fails_closed();
  invalid_model_is_rejected_before_assembly();
  ground_aliases_resolve_to_the_reference_node();
  current_driven_diode_matches_the_shockley_solution();
  reverse_biased_diode_remains_finite();
  resistor_fed_diode_satisfies_kcl_after_damped_newton();
  nonlinear_iteration_limit_fails_closed();
  invalid_diode_model_is_rejected();
  voltage_controlled_switch_is_bidirectional_and_bounded();
  preconditioned_cg_solves_spd_network_and_threads_matvec();
  conjugate_gradient_rejects_indefinite_mna();
  restarted_gmres_solves_indefinite_and_nonsymmetric_mna();
  sparse_lu_uses_linear_storage_and_reuses_newton_symbolics();
  ilu_gmres_solves_large_indefinite_sparse_mna();
  level1_mosfet_is_native_four_terminal_and_bidirectional();
  ebers_moll_bjt_is_native_three_terminal_and_conserves_kcl();
  wbg_fet_constitutive_point_conserves_current_charge_and_has_physics();
  wbg_fet_stamps_coupled_electrothermal_sparse_mna();
#ifdef SPIKES_TEST_OSDI_ARTIFACT
  trusted_osdi_device_registers_directly_in_cpp_sparse_mna();
#endif
#if defined(SPIKES_TEST_OSDI04_CAPACITOR) && defined(SPIKES_TEST_OSDI04_NOISE)
  osdi_0_4_traversal_transient_and_noise_callbacks_are_executed();
#endif
#if defined(SPIKES_TEST_BSIM_BULK_OSDI) && defined(SPIKES_TEST_BSIM_CMG_OSDI)
  official_berkeley_bsim_osdi_models_expose_parameters_dc_charge_and_noise();
#endif
  std::cout << "SPIKES Phase-1 DC solver tests passed\n";
  return 0;
}
