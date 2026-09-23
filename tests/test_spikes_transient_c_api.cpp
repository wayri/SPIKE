#include "spikes/c_api.h"

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>

namespace {

bool near(double actual, double expected, double tolerance = 2.0e-12) {
  return std::abs(actual - expected) <= tolerance;
}

void c_abi_exposes_rc_transient_samples_and_diagnostics() {
  assert(spikes_abi_version() == 1u);
  assert(SPIKES_TRANSIENT_API_VERSION == 1u);
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "V1", "vin", "0", 1.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "vin", "out", 1000.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_capacitor(circuit, "C1", "out", "0", 1.0e-6,
                                      0.0) == SPIKES_OK);

  spikes_transient_options options{};
  assert(spikes_transient_options_init(&options) == SPIKES_OK);
  assert(options.struct_version == SPIKES_TRANSIENT_API_VERSION);
  assert(options.struct_size == sizeof(options));
  options.time_step_s = 1.0e-4;
  options.stop_time_s = 1.0e-3;
  options.initialize_from_operating_point = 0u;

  spikes_transient_result *result = nullptr;
  assert(spikes_solve_transient(circuit, &options, &result) == SPIKES_OK);
  assert(result != nullptr);
  assert(spikes_transient_result_status(result) == SPIKES_SOLVE_CONVERGED);
  assert(std::strstr(spikes_transient_result_message(result),
                     "backward-Euler") != nullptr);
  assert(spikes_transient_result_point_count(result) == 10u);

  double value = 0.0;
  assert(spikes_transient_result_point_time(result, 9, &value) == SPIKES_OK);
  assert(near(value, 1.0e-3));
  assert(spikes_transient_result_node_voltage(result, 9, "out", &value) ==
         SPIKES_OK);
  const double expected = 1.0 - std::pow(1.0 / 1.1, 10.0);
  assert(near(value, expected));
  assert(spikes_transient_result_element_current(result, 9, "R1", &value) ==
         SPIKES_OK);
  assert(value > 0.0);
  assert(spikes_transient_result_element_power(result, 9, "R1", &value) ==
         SPIKES_OK);
  assert(value > 0.0);

  size_t matrix_order = 0;
  size_t completed_steps = 0;
  size_t newton_iterations = 0;
  size_t damping_steps = 0;
  size_t swaps = 0;
  double failed_time = -1.0;
  double residual = -1.0;
  assert(spikes_transient_result_diagnostics(
             result, &matrix_order, &completed_steps, &newton_iterations,
             &damping_steps, &swaps, &failed_time, &residual) == SPIKES_OK);
  assert(matrix_order == 3u);
  assert(completed_steps == 10u);
  assert(newton_iterations == 0u);
  assert(failed_time == 0.0);
  assert(residual < 1.0e-12);
  size_t factorizations = 0;
  size_t reuses = 0;
  size_t cache_entries = 0;
  assert(spikes_transient_result_factorization_diagnostics(
             result, &factorizations, &reuses, &cache_entries) == SPIKES_OK);
  assert(factorizations == 1u);
  assert(reuses == 9u);
  assert(cache_entries == 1u);
  size_t backward_euler_steps = 0;
  size_t trapezoidal_steps = 0;
  assert(spikes_transient_result_integration_diagnostics(
             result, &backward_euler_steps, &trapezoidal_steps) == SPIKES_OK);
  assert(backward_euler_steps == 10u);
  assert(trapezoidal_steps == 0u);

  assert(spikes_transient_result_point_time(result, 10, &value) ==
         SPIKES_NOT_FOUND);
  assert(std::strlen(spikes_last_error()) > 0u);
  spikes_transient_result_destroy(result);

  result = nullptr;
  assert(spikes_solve_transient_with_method(
             circuit, &options, SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL,
             &result) == SPIKES_OK);
  assert(spikes_transient_result_status(result) == SPIKES_SOLVE_CONVERGED);
  assert(spikes_transient_result_node_voltage(result, 9, "out", &value) ==
         SPIKES_OK);
  const double exact = 1.0 - std::exp(-1.0);
  assert(std::abs(value - exact) < 0.15 * std::abs(expected - exact));
  assert(spikes_transient_result_integration_diagnostics(
             result, &backward_euler_steps, &trapezoidal_steps) == SPIKES_OK);
  assert(backward_euler_steps == 1u);
  assert(trapezoidal_steps == 9u);
  assert(spikes_transient_result_factorization_diagnostics(
             result, &factorizations, &reuses, &cache_entries) == SPIKES_OK);
  assert(factorizations == 2u);
  assert(reuses == 8u);
  assert(cache_entries == 2u);
  spikes_transient_result_destroy(result);

  result = reinterpret_cast<spikes_transient_result *>(1);
  assert(spikes_solve_transient_with_method(circuit, &options, 99u, &result) ==
         SPIKES_INVALID_ARGUMENT);
  assert(result == nullptr);
  spikes_circuit_destroy(circuit);
}

void c_abi_exposes_inductors_and_rejects_bad_option_contracts() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "V1", "vin", "0", 1.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "vin", "out", 10.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_inductor(circuit, "L1", "out", "0", 1.0e-3,
                                     0.0) == SPIKES_OK);
  assert(spikes_circuit_add_inductor(circuit, "bad", "x", "0", 0.0, 0.0) ==
         SPIKES_INVALID_ARGUMENT);

  spikes_transient_options options{};
  assert(spikes_transient_options_init(&options) == SPIKES_OK);
  options.time_step_s = 1.0e-5;
  options.stop_time_s = 1.0e-4;
  options.initialize_from_operating_point = 0u;
  spikes_transient_result *result = nullptr;
  assert(spikes_solve_transient(circuit, &options, &result) == SPIKES_OK);
  assert(spikes_transient_result_status(result) == SPIKES_SOLVE_CONVERGED);
  double current = 0.0;
  assert(spikes_transient_result_element_current(result, 9, "L1", &current) ==
         SPIKES_OK);
  assert(near(current, 0.1 * (1.0 - std::pow(1.0 / 1.1, 10.0))));
  spikes_transient_result_destroy(result);

  options.struct_version = SPIKES_TRANSIENT_API_VERSION + 1u;
  result = reinterpret_cast<spikes_transient_result *>(1);
  assert(spikes_solve_transient(circuit, &options, &result) ==
         SPIKES_INVALID_ARGUMENT);
  assert(result == nullptr);
  assert(spikes_transient_options_init(nullptr) == SPIKES_INVALID_ARGUMENT);
  spikes_circuit_destroy(circuit);
}

void c_abi_exposes_breakpoint_aware_waveform_sources() {
  spikes_circuit *circuit = nullptr;
  assert(spikes_circuit_create(&circuit) == SPIKES_OK);
  assert(spikes_circuit_add_pulse_voltage_source(
             circuit, "Vpwm", "gate", "0", 0.0, 5.0, 0.25, 0.10, 0.10,
             0.40, 1.0) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "R1", "gate", "0", 10.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_voltage_source(circuit, "Vs", "in", "0", 10.0) ==
         SPIKES_OK);
  assert(spikes_circuit_add_voltage_controlled_switch(
             circuit, "S1", "in", "out", "gate", "0", 1.0, 1.0e6, 2.5,
             0.1) == SPIKES_OK);
  assert(spikes_circuit_add_resistor(circuit, "Rload", "out", "0", 10.0) ==
         SPIKES_OK);
  const spikes_pwl_point invalid[] = {{0.2, 0.0}, {0.1, 1.0}};
  assert(spikes_circuit_add_pwl_current_source(
             circuit, "Ibad", "0", "x", invalid, 2) ==
         SPIKES_INVALID_ARGUMENT);

  spikes_transient_options options{};
  assert(spikes_transient_options_init(&options) == SPIKES_OK);
  options.time_step_s = 0.7;
  options.stop_time_s = 0.9;
  options.initialize_from_operating_point = 0u;
  spikes_transient_result *result = nullptr;
  assert(spikes_solve_transient(circuit, &options, &result) == SPIKES_OK);
  assert(spikes_transient_result_status(result) == SPIKES_SOLVE_CONVERGED);

  const double edges[] = {0.25, 0.35, 0.75, 0.85};
  for (double edge : edges) {
    bool found = false;
    for (size_t index = 0;
         index < spikes_transient_result_point_count(result); ++index) {
      double time = 0.0;
      assert(spikes_transient_result_point_time(result, index, &time) ==
             SPIKES_OK);
      found = found || near(time, edge, 2.0e-15);
    }
    assert(found);
  }
  double output = 0.0;
  assert(spikes_transient_result_node_voltage(result, 1, "out", &output) ==
         SPIKES_OK);
  assert(near(output, 10.0 * 10.0 / 11.0, 1.0e-8));
  size_t breakpoint_steps = 0;
  assert(spikes_transient_result_breakpoint_steps(result, &breakpoint_steps) ==
         SPIKES_OK);
  assert(breakpoint_steps >= 3u);
  spikes_transient_result_destroy(result);
  spikes_circuit_destroy(circuit);
}

} // namespace

int main() {
  c_abi_exposes_rc_transient_samples_and_diagnostics();
  c_abi_exposes_inductors_and_rejects_bad_option_contracts();
  c_abi_exposes_breakpoint_aware_waveform_sources();
  std::cout << "SPIKES transient C ABI tests passed\n";
  return 0;
}
