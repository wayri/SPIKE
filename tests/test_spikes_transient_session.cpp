#include "spikes/transient_session.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

bool near(double actual, double expected, double tolerance = 2.0e-12) {
  return std::abs(actual - expected) <= tolerance;
}

void require(bool condition, const char *message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void persistent_rc_control_and_checkpoint_replay() {
  spikes::Circuit circuit;
  circuit.add_voltage_source("Vdrive", "in", "0", 0.0);
  circuit.add_resistor("R1", "in", "out", 1000.0);
  circuit.add_capacitor("C1", "out", "0", 1.0e-6);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  spikes::TransientSession session(std::move(circuit), options);

  session.set_source_value("Vdrive", 1.0);
  double expected = 0.0;
  for (int index = 0; index < 10; ++index) {
    if (!session.step(1.0e-4)) {
      throw std::runtime_error(session.message());
    }
    expected = (expected + 0.1) / 1.1;
  }
  require(near(session.node_voltage("out"), expected), "persistent RC value");
  require(near(session.time_s(), 1.0e-3), "persistent RC time");
  require(session.step_index() == 10u, "persistent RC step index");

  const auto checkpoint = session.checkpoint();
  session.set_source_value("Vdrive", -0.5);
  for (int index = 0; index < 5; ++index) {
    if (!session.step(1.0e-4)) {
      throw std::runtime_error(session.message());
    }
  }
  const double first = session.node_voltage("out");
  session.restore(checkpoint);
  session.set_source_value("Vdrive", -0.5);
  for (int index = 0; index < 5; ++index) {
    if (!session.step(1.0e-4)) {
      throw std::runtime_error(session.message());
    }
  }
  require(session.node_voltage("out") == first, "bit-exact checkpoint replay");
  require(session.diagnostics().completed_steps == 15u,
          "checkpoint-restored diagnostic count");
  require(session.diagnostics().matrix_factorizations == 1u,
          "persistent RC factors its invariant matrix once");
  require(session.diagnostics().factorization_reuses == 14u,
          "persistent RC reuses its factorization across calls");
}

void persistent_waveforms_and_checkpointed_hybrid_history() {
  spikes::Circuit waveform;
  spikes::PulseWaveform pulse;
  pulse.initial_value = 0.0;
  pulse.pulsed_value = 5.0;
  pulse.delay_s = 0.1;
  pulse.rise_time_s = 0.1;
  pulse.pulse_width_s = 0.2;
  pulse.fall_time_s = 0.1;
  pulse.period_s = 0.5;
  waveform.add_pulse_voltage_source("V1", "out", "0", pulse);
  waveform.add_resistor("R1", "out", "0", 1.0);
  spikes::TransientOptions waveform_options;
  waveform_options.initialize_from_operating_point = false;
  waveform_options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  spikes::TransientSession waveform_session(std::move(waveform),
                                             waveform_options);
  require(waveform_session.step(0.35), "first global PULSE interval");
  require(near(waveform_session.node_voltage("out"), 5.0),
          "PULSE high value at global 0.35 s");
  require(waveform_session.step(0.20), "second global PULSE interval");
  require(near(waveform_session.node_voltage("out"), 0.0),
          "PULSE low value at global 0.55 s");
  require(waveform_session.step(0.10), "third global PULSE interval");
  require(near(waveform_session.node_voltage("out"), 2.5),
          "PULSE next-cycle rising value at global 0.65 s");
  require(waveform_session.diagnostics().source_breakpoint_steps >= 4u,
          "persistent PULSE internal breakpoint count");
  require(waveform_session.diagnostics().backward_euler_steps >= 5u &&
              waveform_session.diagnostics().trapezoidal_steps >= 3u,
          "persistent hybrid restarts at real PULSE events");

  spikes::Circuit hybrid;
  hybrid.add_voltage_source("V1", "in", "0", 1.0);
  hybrid.add_resistor("R1", "in", "out", 1000.0);
  hybrid.add_capacitor("C1", "out", "0", 1.0e-6);
  spikes::TransientOptions options;
  options.initialize_from_operating_point = false;
  options.integration_method =
      spikes::TransientIntegrationMethod::hybrid_trapezoidal;
  spikes::TransientSession hybrid_session(std::move(hybrid), options);
  double expected = 0.0;
  double capacitor_current = 0.0;
  for (int index = 0; index < 5; ++index) {
    require(hybrid_session.step(1.0e-4), "persistent hybrid first segment");
    if (index == 0) {
      expected = 1.0 / 11.0;
      capacitor_current = 1.0e-6 * expected / 1.0e-4;
    } else {
      const double previous = expected;
      expected = (0.001 + 0.02 * previous + capacitor_current) / 0.021;
      capacitor_current = 0.02 * (expected - previous) - capacitor_current;
    }
  }
  require(near(hybrid_session.node_voltage("out"), expected, 2.0e-11),
          "persistent hybrid RC value");
  const auto checkpoint = hybrid_session.checkpoint();
  for (int index = 0; index < 5; ++index) {
    require(hybrid_session.step(1.0e-4), "persistent hybrid replay first");
  }
  const double replay = hybrid_session.node_voltage("out");
  hybrid_session.restore(checkpoint);
  for (int index = 0; index < 5; ++index) {
    require(hybrid_session.step(1.0e-4), "persistent hybrid replay restored");
  }
  require(hybrid_session.node_voltage("out") == replay,
          "persistent hybrid checkpoint replay");
  require(hybrid_session.diagnostics().backward_euler_steps == 1u &&
              hybrid_session.diagnostics().trapezoidal_steps == 9u,
          "persistent hybrid method history");
  require(hybrid_session.diagnostics().matrix_factorizations == 2u &&
              hybrid_session.diagnostics().factorization_reuses == 8u,
          "persistent hybrid factorization history");
}

} // namespace

int main() {
  try {
    persistent_rc_control_and_checkpoint_replay();
    persistent_waveforms_and_checkpointed_hybrid_history();
  } catch (const std::exception &error) {
    std::cerr << "SPIKES persistent session test exception: " << error.what()
              << '\n';
    return 1;
  }
  std::cout << "SPIKES persistent transient session tests passed\n";
  return 0;
}
