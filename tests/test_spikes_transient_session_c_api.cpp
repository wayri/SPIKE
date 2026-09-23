#include "spikes/c_api.h"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const char *message) {
  if (!condition) {
    throw std::runtime_error(std::string(message) + ": " + spikes_last_error());
  }
}

spikes_circuit *make_rc() {
  spikes_circuit *circuit = nullptr;
  require(spikes_circuit_create(&circuit) == SPIKES_OK, "create RC circuit");
  require(spikes_circuit_add_voltage_source(circuit, "Vdrive", "in", "0", 0.0) ==
              SPIKES_OK,
          "add drive source");
  require(spikes_circuit_add_resistor(circuit, "R1", "in", "out", 1000.0) ==
              SPIKES_OK,
          "add resistor");
  require(spikes_circuit_add_capacitor(circuit, "C1", "out", "0", 1.0e-6,
                                       0.0) == SPIKES_OK,
          "add capacitor");
  return circuit;
}

void persistent_c_api_control_checkpoint_and_ownership() {
  spikes_transient_options options{};
  require(spikes_transient_options_init(&options) == SPIKES_OK, "init options");
  options.initialize_from_operating_point = 0u;
  auto *circuit = make_rc();
  spikes_transient_session *session = nullptr;
  require(spikes_transient_session_create(circuit, &options, &session) == SPIKES_OK,
          "create persistent session");
  double value = 0.0;
  require(spikes_transient_session_node_voltage(session, "out", &value) ==
              SPIKES_NOT_FOUND,
          "read before first accepted point");
  require(spikes_transient_session_set_source_value(session, "Vdrive", 1.0) ==
              SPIKES_OK,
          "set source");
  uint8_t accepted = 0u;
  double expected = 0.0;
  for (int index = 0; index < 10; ++index) {
    require(spikes_transient_session_step(session, 1.0e-4, &accepted) == SPIKES_OK &&
                accepted == 1u,
            "step persistent session");
    expected = (expected + 0.1) / 1.1;
  }
  require(spikes_transient_session_node_voltage(session, "out", &value) == SPIKES_OK,
          "read persistent output");
  require(std::abs(value - expected) <= 2.0e-12, "persistent RC value");
  require(spikes_transient_session_element_voltage(session, "R1", &value) ==
              SPIKES_OK,
          "read persistent element voltage");
  require(std::abs(value - (1.0 - expected)) <= 2.0e-12,
          "persistent resistor voltage");
  double time_s = 0.0;
  size_t step_index = 0;
  require(spikes_transient_session_position(session, &time_s, &step_index) == SPIKES_OK,
          "query persistent position");
  require(std::abs(time_s - 1.0e-3) <= 2.0e-15 && step_index == 10u,
          "persistent position value");

  spikes_transient_checkpoint *checkpoint = nullptr;
  require(spikes_transient_session_checkpoint_create(session, &checkpoint) == SPIKES_OK,
          "create checkpoint");
  require(spikes_transient_session_set_source_value(session, "Vdrive", -0.5) ==
              SPIKES_OK,
          "set replay source");
  for (int index = 0; index < 5; ++index) {
    require(spikes_transient_session_step(session, 1.0e-4, &accepted) == SPIKES_OK &&
                accepted == 1u,
            "advance replay");
  }
  require(spikes_transient_session_node_voltage(session, "out", &value) == SPIKES_OK,
          "read first replay");
  const double first_replay = value;
  require(spikes_transient_session_restore(session, checkpoint) == SPIKES_OK,
          "restore checkpoint");
  require(spikes_transient_session_set_source_value(session, "Vdrive", -0.5) ==
              SPIKES_OK,
          "set restored replay source");
  for (int index = 0; index < 5; ++index) {
    require(spikes_transient_session_step(session, 1.0e-4, &accepted) == SPIKES_OK &&
                accepted == 1u,
            "advance restored replay");
  }
  require(spikes_transient_session_node_voltage(session, "out", &value) == SPIKES_OK &&
              value == first_replay,
          "bit-exact native replay");

  auto *other_circuit = make_rc();
  spikes_transient_session *other = nullptr;
  require(spikes_transient_session_create(other_circuit, &options, &other) == SPIKES_OK,
          "create second session");
  require(spikes_transient_session_restore(other, checkpoint) ==
              SPIKES_INVALID_ARGUMENT,
          "reject foreign checkpoint");

  size_t completed = 0;
  size_t factorizations = 0;
  size_t newton = 0;
  double residual = 0.0;
  require(spikes_transient_session_diagnostics(
              session, &completed, &factorizations, &newton, &residual) == SPIKES_OK,
          "query persistent diagnostics");
  require(completed == 15u && factorizations == 1u && newton == 0u,
          "persistent diagnostic totals");
  size_t reuses = 0;
  size_t cache_entries = 0;
  require(spikes_transient_session_factorization_diagnostics(
              session, &reuses, &cache_entries) == SPIKES_OK,
          "query persistent factorization diagnostics");
  require(reuses == 14u && cache_entries == 1u,
          "persistent factorization reuse totals");

  auto *hybrid_circuit = make_rc();
  spikes_transient_session *hybrid = nullptr;
  require(spikes_transient_session_create_with_method(
              hybrid_circuit, &options,
              SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL, &hybrid) == SPIKES_OK,
          "create persistent hybrid session");
  require(spikes_transient_session_set_source_value(hybrid, "Vdrive", 1.0) ==
              SPIKES_OK,
          "set hybrid source");
  require(spikes_transient_session_step(hybrid, 1.0e-4, &accepted) == SPIKES_OK &&
              accepted == 1u,
          "persistent hybrid startup step");
  require(spikes_transient_session_step(hybrid, 1.0e-4, &accepted) == SPIKES_OK &&
              accepted == 1u,
          "persistent hybrid trapezoidal step");
  size_t backward_euler = 0;
  size_t trapezoidal = 0;
  require(spikes_transient_session_integration_diagnostics(
              hybrid, &backward_euler, &trapezoidal) == SPIKES_OK,
          "query persistent integration diagnostics");
  require(backward_euler == 1u && trapezoidal == 1u,
          "persistent hybrid integration totals");
  spikes_transient_session_destroy(hybrid);
  spikes_circuit_destroy(hybrid_circuit);

  spikes_transient_session_destroy(other);
  spikes_circuit_destroy(other_circuit);
  spikes_transient_checkpoint_destroy(checkpoint);
  spikes_transient_session_destroy(session);
  spikes_circuit_destroy(circuit);
}

} // namespace

int main() {
  try {
    persistent_c_api_control_checkpoint_and_ownership();
    std::cout << "SPIKES persistent transient C ABI tests passed\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
