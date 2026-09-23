#include "spikes/c_api.h"

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>

namespace {

bool near(double actual, double expected) {
  return std::abs(actual - expected) <= 1e-12;
}

void c_abi_solves_and_owns_results() {
  assert(spikes_abi_version() == 1u);
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(circuit != nullptr);
  assert(spikes_circuit_add_voltage_source(circuit, "V1", "vin", "0", 10.0) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "vin", "out", 1000.0) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R2", "out", "0", 1000.0) == SPIKES_OK);

  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point(circuit, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_CONVERGED);
  double value = 0.0;
  assert(spikes_result_node_voltage(result, "out", &value) == SPIKES_OK);
  assert(near(value, 5.0));
  assert(spikes_result_element_power(result, "R1", &value) == SPIKES_OK);
  assert(near(value, 0.025));
  size_t order = 0;
  size_t swaps = 0;
  double residual = 0.0;
  assert(spikes_result_diagnostics(result, &order, &swaps, &residual) == SPIKES_OK);
  assert(order == 3);
  assert(residual < 1e-14);

  spikes_linear_solver_options iterative_options{};
  assert(spikes_linear_solver_options_init(&iterative_options) == SPIKES_OK);
  iterative_options.method = SPIKES_LINEAR_SOLVER_GMRES;
  iterative_options.threads = 2;
  spikes_result *iterative = nullptr;
  assert(spikes_solve_operating_point_with_linear_solver(
             circuit, &iterative_options, &iterative) == SPIKES_OK);
  assert(spikes_result_status(iterative) == SPIKES_SOLVE_CONVERGED);
  assert(spikes_result_node_voltage(iterative, "out", &value) == SPIKES_OK);
  assert(near(value, 5.0));
  uint32_t iterative_method = 0;
  size_t iterative_iterations = 0;
  size_t iterative_threads = 0;
  assert(spikes_result_linear_solver_diagnostics(
             iterative, &iterative_method, &iterative_iterations,
             &iterative_threads) == SPIKES_OK);
  assert(iterative_method == SPIKES_LINEAR_SOLVER_GMRES);
  assert(iterative_iterations > 0u && iterative_threads == 2u);
  spikes_result_destroy(iterative);

  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

void c_abi_contains_errors_and_reports_singular_models() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "a", "b", 1000.0) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R2", "a", "0", 0.0) == SPIKES_INVALID_ARGUMENT);
  assert(std::strlen(spikes_last_error()) > 0);

  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point(circuit, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_SINGULAR);
  double value = 0.0;
  assert(spikes_result_node_voltage(result, "missing", &value) == SPIKES_NOT_FOUND);
  assert(std::strlen(spikes_last_error()) > 0);

  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

void c_abi_exposes_nonlinear_diode_operating_points() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_current_source(circuit, "I1", "0", "junction", 1e-3) == SPIKES_OK);
  assert(spikes_circuit_add_diode(circuit, "D1", "junction", "0", 1e-12, 1.0, 300.15) == SPIKES_OK);
  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point(circuit, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_CONVERGED);
  double voltage = 0.0;
  assert(spikes_result_node_voltage(result, "junction", &voltage) == SPIKES_OK);
  assert(voltage > 0.5 && voltage < 0.6);
  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

void c_abi_selects_and_reports_conjugate_gradient() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_current_source(circuit, "I1", "0", "out", 1e-3) ==
         SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "out", "0", 1000.0) ==
         SPIKES_OK);
  spikes_linear_solver_options options{};
  assert(spikes_linear_solver_options_init(&options) == SPIKES_OK);
  options.method = SPIKES_LINEAR_SOLVER_CONJUGATE_GRADIENT;
  options.threads = 2;
  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point_with_linear_solver(
             circuit, &options, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_CONVERGED);
  double voltage = 0.0;
  assert(spikes_result_node_voltage(result, "out", &voltage) == SPIKES_OK);
  assert(near(voltage, 1.0));
  uint32_t method = 0;
  size_t iterations = 0;
  size_t threads = 0;
  assert(spikes_result_linear_solver_diagnostics(
             result, &method, &iterations, &threads) == SPIKES_OK);
  assert(method == SPIKES_LINEAR_SOLVER_CONJUGATE_GRADIENT);
  assert(iterations == 1u && threads == 2u);
  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

void c_abi_exposes_sparse_solver_and_structure_diagnostics() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "V1", "in", "0", 10.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "in", "out", 1000.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R2", "out", "0", 1000.0) ==
         SPIKES_OK);
  spikes_linear_solver_options options{};
  assert(spikes_linear_solver_options_init(&options) == SPIKES_OK);
  options.method = SPIKES_LINEAR_SOLVER_SPARSE_LU;
  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point_with_linear_solver(
             circuit, &options, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_CONVERGED);
  uint32_t method = 0;
  size_t iterations = 0;
  size_t threads = 0;
  assert(spikes_result_linear_solver_diagnostics(
             result, &method, &iterations, &threads) == SPIKES_OK);
  assert(method == SPIKES_LINEAR_SOLVER_SPARSE_LU);
  size_t nonzeros = 0;
  size_t symbolic = 0;
  size_t numeric = 0;
  assert(spikes_result_sparse_solver_diagnostics(
             result, &nonzeros, &symbolic, &numeric) == SPIKES_OK);
  assert(nonzeros > 0 && nonzeros < 9);
  assert(symbolic == 1 && numeric == 1);
  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

void c_abi_exposes_native_electrothermal_wbg_fet() {
  spikes_wbg_fet_electrothermal_model model{};
  assert(spikes_wbg_fet_electrothermal_model_init(
             &model, SPIKES_WBG_TECHNOLOGY_SIC_MOSFET) == SPIKES_OK);
  model.transconductance_a_per_v2 = 0.1;
  model.thermal_resistance_k_per_w = 2.0;
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "Vd", "drain", "0",
                                           10.0) == SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "Vg", "gate", "0",
                                           5.0) == SPIKES_OK);
  assert(spikes_circuit_add_wbg_fet_electrothermal(
             circuit, "QW1", "drain", "gate", "0", "0", "tj_rise",
             &model) == SPIKES_OK);
  spikes_result *result = nullptr;
  assert(spikes_solve_operating_point(circuit, &result) == SPIKES_OK);
  assert(spikes_result_status(result) == SPIKES_SOLVE_CONVERGED);
  double rise = 0.0;
  double power = 0.0;
  assert(spikes_result_node_voltage(result, "tj_rise", &rise) == SPIKES_OK);
  assert(spikes_result_element_power(result, "QW1", &power) == SPIKES_OK);
  assert(rise > 0.0);
  assert(std::abs(rise - power * model.thermal_resistance_k_per_w) < 2.0e-7);
  spikes_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

} // namespace

int main() {
  c_abi_solves_and_owns_results();
  c_abi_contains_errors_and_reports_singular_models();
  c_abi_exposes_nonlinear_diode_operating_points();
  c_abi_selects_and_reports_conjugate_gradient();
  c_abi_exposes_sparse_solver_and_structure_diagnostics();
  c_abi_exposes_native_electrothermal_wbg_fet();
  std::cout << "SPIKES Phase-1 C ABI tests passed\n";
  return 0;
}
