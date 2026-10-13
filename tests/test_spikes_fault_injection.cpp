// SPDX-License-Identifier: Apache-2.0
// Standalone ABI regression; link against the rebuilt spikes_c_api library.
#include "spikes/c_api.h"
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
void ok(spikes_error_code code) {
  if (code != SPIKES_OK) throw std::runtime_error(spikes_last_error());
}
void require(bool value) {
  if (!value) throw std::runtime_error("native fault regression failed");
}
}

int main() {
  spikes_circuit *circuit = nullptr;
  spikes_transient_session *session = nullptr;
  spikes_transient_checkpoint *checkpoint = nullptr;
  try {
    ok(spikes_circuit_create(&circuit));
    ok(spikes_circuit_add_voltage_source(circuit, "V1", "in", "0", 1));
    ok(spikes_circuit_add_resistor(circuit, "R1", "in", "out", 1000));
    ok(spikes_circuit_add_capacitor(circuit, "C1", "out", "0", 1e-6, 0));
    spikes_transient_options options{};
    ok(spikes_transient_options_init(&options));
    options.initialize_from_operating_point = 0;
    ok(spikes_transient_session_create(circuit, &options, &session));
    uint8_t accepted = 0;
    ok(spikes_transient_session_step(session, 1e-4, &accepted));
    require(accepted != 0);
    ok(spikes_transient_session_checkpoint_create(session, &checkpoint));
    require(spikes_transient_session_set_resistance(session, "R1", 0) != SPIKES_OK);
    require(spikes_transient_session_set_resistance(session, "C1", 100) != SPIKES_OK);
    ok(spikes_transient_session_set_resistance(session, "R1", 2000));
    ok(spikes_transient_session_step(session, 1e-4, &accepted));
    require(accepted != 0);
    double voltage = 0;
    ok(spikes_transient_session_node_voltage(session, "out", &voltage));
    require(std::abs(voltage - (1.0 / 11 + .05) / 1.05) < 1e-12);
    ok(spikes_transient_session_restore(session, checkpoint));
    ok(spikes_transient_session_step(session, 1e-4, &accepted));
    require(accepted != 0);
    ok(spikes_transient_session_node_voltage(session, "out", &voltage));
    require(std::abs(voltage - (1.0 / 11 + .1) / 1.1) < 1e-12);
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  spikes_transient_checkpoint_destroy(checkpoint);
  spikes_transient_session_destroy(session);
  spikes_circuit_destroy(circuit);
  std::cout << "SPIKES native fault regression passed\n";
}
