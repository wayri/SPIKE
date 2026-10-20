// SPDX-License-Identifier: Apache-2.0

#include "spikes/io_pad.hpp"

#include "spikes/transient_session.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace spikes {
namespace {

constexpr double minimum_mutable_resistance_ohm = 1.0e-6;
constexpr double maximum_mutable_resistance_ohm = 1.0e15;

bool is_ground_name(std::string_view name) {
  return name == "0" || name == "GND" || name == "gnd";
}

void validate_name(std::string_view value, const char *description) {
  if (value.empty() || value.find('\0') != std::string_view::npos ||
      value.find('\r') != std::string_view::npos ||
      value.find('\n') != std::string_view::npos) {
    throw std::invalid_argument(std::string(description) +
                                " must be a nonempty single-line name");
  }
}

void validate_resistance(double value, const char *description) {
  if (!std::isfinite(value) || value < minimum_mutable_resistance_ohm ||
      value > maximum_mutable_resistance_ohm) {
    throw std::invalid_argument(std::string(description) +
                                " must be within [1e-6, 1e15] ohm");
  }
}

void validate_nonnegative(double value, const char *description) {
  if (!std::isfinite(value) || value < 0.0) {
    throw std::invalid_argument(std::string(description) +
                                " must be finite and nonnegative");
  }
}

void validate_state(const IoPadState &state) {
  switch (state.drive_level) {
  case IoPadDriveLevel::strong:
  case IoPadDriveLevel::weak:
    break;
  default:
    throw std::invalid_argument("unknown I/O-pad drive level");
  }
  switch (state.pull) {
  case IoPadPull::none:
  case IoPadPull::up:
  case IoPadPull::down:
    break;
  default:
    throw std::invalid_argument("unknown I/O-pad pull state");
  }
  switch (state.mode) {
  case IoPadDriveMode::input:
    if (state.output != IoPadOutputState::released) {
      throw std::invalid_argument("input mode requires a released output");
    }
    return;
  case IoPadDriveMode::push_pull:
    if (state.output != IoPadOutputState::low &&
        state.output != IoPadOutputState::high) {
      throw std::invalid_argument("push-pull mode requires low or high output");
    }
    return;
  case IoPadDriveMode::open_drain:
    if (state.output != IoPadOutputState::low &&
        state.output != IoPadOutputState::released) {
      throw std::invalid_argument("open-drain mode requires low or released output");
    }
    return;
  case IoPadDriveMode::open_source:
    if (state.output != IoPadOutputState::high &&
        state.output != IoPadOutputState::released) {
      throw std::invalid_argument("open-source mode requires high or released output");
    }
    return;
  default:
    throw std::invalid_argument("unknown I/O-pad drive mode");
  }
}

void validate_config(const IoPadConfig &config) {
  validate_resistance(config.high_strong_resistance_ohm,
                      "strong high-drive resistance");
  validate_resistance(config.high_weak_resistance_ohm,
                      "weak high-drive resistance");
  validate_resistance(config.low_strong_resistance_ohm,
                      "strong low-drive resistance");
  validate_resistance(config.low_weak_resistance_ohm,
                      "weak low-drive resistance");
  validate_resistance(config.pull_up_resistance_ohm, "pull-up resistance");
  validate_resistance(config.pull_down_resistance_ohm, "pull-down resistance");
  validate_resistance(config.off_resistance_ohm, "off resistance");
  if (config.high_weak_resistance_ohm < config.high_strong_resistance_ohm ||
      config.low_weak_resistance_ohm < config.low_strong_resistance_ohm) {
    throw std::invalid_argument(
        "weak drive resistance must not be below strong drive resistance");
  }
  const std::array active_resistances{
      config.high_strong_resistance_ohm, config.high_weak_resistance_ohm,
      config.low_strong_resistance_ohm, config.low_weak_resistance_ohm,
      config.pull_up_resistance_ohm, config.pull_down_resistance_ohm};
  if (config.off_resistance_ohm <
      *std::max_element(active_resistances.begin(), active_resistances.end())) {
    throw std::invalid_argument(
        "off resistance must not be below any drive or pull resistance");
  }

  validate_nonnegative(config.package_resistance_ohm,
                       "package resistance");
  if (config.package_resistance_ohm > 0.0) {
    validate_resistance(config.package_resistance_ohm, "package resistance");
  }
  validate_nonnegative(config.package_inductance_h, "package inductance");
  validate_nonnegative(config.capacitance_to_vss_f, "VSS pad capacitance");
  validate_nonnegative(config.capacitance_to_vdd_f, "VDD pad capacitance");

  const auto &diode = config.clamp_diode;
  if (!std::isfinite(diode.saturation_current_a) ||
      diode.saturation_current_a <= 0.0 ||
      !std::isfinite(diode.emission_coefficient) ||
      diode.emission_coefficient <= 0.0 ||
      !std::isfinite(diode.temperature_k) || diode.temperature_k <= 0.0) {
    throw std::invalid_argument(
        "clamp diode parameters must be finite and positive");
  }
}

std::array<double, 4> state_resistances(const IoPadConfig &config,
                                        const IoPadState &state) {
  validate_state(state);
  bool high_active = false;
  bool low_active = false;
  if (state.mode == IoPadDriveMode::push_pull) {
    high_active = state.output == IoPadOutputState::high;
    low_active = state.output == IoPadOutputState::low;
  } else if (state.mode == IoPadDriveMode::open_drain) {
    low_active = state.output == IoPadOutputState::low;
  } else if (state.mode == IoPadDriveMode::open_source) {
    high_active = state.output == IoPadOutputState::high;
  }
  const bool strong = state.drive_level == IoPadDriveLevel::strong;
  const double high_on = strong ? config.high_strong_resistance_ohm
                                : config.high_weak_resistance_ohm;
  const double low_on = strong ? config.low_strong_resistance_ohm
                               : config.low_weak_resistance_ohm;
  return {
      high_active ? high_on : config.off_resistance_ohm,
      low_active ? low_on : config.off_resistance_ohm,
      state.pull == IoPadPull::up ? config.pull_up_resistance_ohm
                                  : config.off_resistance_ohm,
      state.pull == IoPadPull::down ? config.pull_down_resistance_ohm
                                    : config.off_resistance_ohm,
  };
}

std::string id(const std::string &prefix, std::string_view suffix) {
  return prefix + ".io_pad." + std::string(suffix);
}

std::string internal_node(const std::string &prefix, std::string_view suffix) {
  return "@io_pad:" + prefix + ":" + std::string(suffix);
}

void reserve_internal_node(Circuit &circuit, const std::string &name) {
  const auto before = circuit.node_count();
  const auto node = circuit.node(name);
  if (node == ground_node || circuit.node_count() != before + 1u) {
    throw std::invalid_argument("generated I/O-pad internal node collides");
  }
}

} // namespace

std::vector<std::string> IoPadBinding::element_ids() const {
  std::vector<std::string> ids;
  ids.reserve(10);
  const std::array<const std::string *, 10> ordered{
      &package_inductor_id, &package_resistor_id, &drive_high_id,
      &drive_low_id, &pull_up_id, &pull_down_id, &capacitance_to_vss_id,
      &capacitance_to_vdd_id, &clamp_to_vdd_id, &clamp_to_vss_id};
  for (const auto *value : ordered) {
    if (!value->empty()) {
      ids.push_back(*value);
    }
  }
  return ids;
}

IoPadBinding add_io_pad(Circuit &circuit, std::string prefix, std::string pad,
                        std::string vdd, std::string vss,
                        const IoPadConfig &config,
                        const IoPadState &initial_state) {
  validate_name(prefix, "I/O-pad prefix");
  validate_name(pad, "I/O-pad terminal");
  validate_name(vdd, "I/O-pad VDD rail");
  validate_name(vss, "I/O-pad VSS rail");
  if (is_ground_name(pad) || is_ground_name(vdd)) {
    throw std::invalid_argument("I/O-pad terminal and VDD must not be ground");
  }
  validate_config(config);
  const auto initial_resistances = state_resistances(config, initial_state);

  Circuit staged = circuit;
  const NodeId pad_node = staged.node(pad);
  const NodeId vdd_node = staged.node(vdd);
  const NodeId vss_node = staged.node(vss);
  if (pad_node == vdd_node || pad_node == vss_node || vdd_node == vss_node) {
    throw std::invalid_argument("I/O-pad terminal, VDD, and VSS must be distinct");
  }

  IoPadBinding binding;
  binding.prefix = std::move(prefix);
  binding.pad = std::move(pad);
  binding.vdd = std::move(vdd);
  binding.vss = std::move(vss);
  binding.config = config;
  binding.state = initial_state;
  binding.applied_resistances_ohm = initial_resistances;

  const bool has_package_resistance = config.package_resistance_ohm > 0.0;
  const bool has_package_inductance = config.package_inductance_h > 0.0;
  const bool has_package = has_package_resistance || has_package_inductance;
  binding.die_pad = has_package ? internal_node(binding.prefix, "die")
                                : binding.pad;
  if (has_package) {
    reserve_internal_node(staged, binding.die_pad);
  }

  if (has_package_resistance && has_package_inductance) {
    const std::string junction = internal_node(binding.prefix, "package");
    reserve_internal_node(staged, junction);
    binding.package_inductor_id = id(binding.prefix, "package_l");
    staged.add_inductor(binding.package_inductor_id, binding.pad, junction,
                        config.package_inductance_h);
    binding.package_resistor_id = id(binding.prefix, "package_r");
    staged.add_resistor(binding.package_resistor_id, junction, binding.die_pad,
                        config.package_resistance_ohm);
  } else if (has_package_inductance) {
    binding.package_inductor_id = id(binding.prefix, "package_l");
    staged.add_inductor(binding.package_inductor_id, binding.pad,
                        binding.die_pad, config.package_inductance_h);
  } else if (has_package_resistance) {
    binding.package_resistor_id = id(binding.prefix, "package_r");
    staged.add_resistor(binding.package_resistor_id, binding.pad,
                        binding.die_pad, config.package_resistance_ohm);
  }

  binding.drive_high_id = id(binding.prefix, "drive_high");
  binding.drive_low_id = id(binding.prefix, "drive_low");
  binding.pull_up_id = id(binding.prefix, "pull_up");
  binding.pull_down_id = id(binding.prefix, "pull_down");
  staged.add_resistor(binding.drive_high_id, binding.die_pad, binding.vdd,
                      initial_resistances[0]);
  staged.add_resistor(binding.drive_low_id, binding.die_pad, binding.vss,
                      initial_resistances[1]);
  staged.add_resistor(binding.pull_up_id, binding.die_pad, binding.vdd,
                      initial_resistances[2]);
  staged.add_resistor(binding.pull_down_id, binding.die_pad, binding.vss,
                      initial_resistances[3]);

  if (config.capacitance_to_vss_f > 0.0) {
    binding.capacitance_to_vss_id = id(binding.prefix, "cap_vss");
    staged.add_capacitor(binding.capacitance_to_vss_id, binding.die_pad,
                         binding.vss, config.capacitance_to_vss_f);
  }
  if (config.capacitance_to_vdd_f > 0.0) {
    binding.capacitance_to_vdd_id = id(binding.prefix, "cap_vdd");
    staged.add_capacitor(binding.capacitance_to_vdd_id, binding.die_pad,
                         binding.vdd, config.capacitance_to_vdd_f);
  }
  if (config.enable_clamp_to_vdd) {
    binding.clamp_to_vdd_id = id(binding.prefix, "clamp_vdd");
    staged.add_diode(binding.clamp_to_vdd_id, binding.die_pad, binding.vdd,
                     config.clamp_diode);
  }
  if (config.enable_clamp_to_vss) {
    binding.clamp_to_vss_id = id(binding.prefix, "clamp_vss");
    staged.add_diode(binding.clamp_to_vss_id, binding.vss, binding.die_pad,
                     config.clamp_diode);
  }

  circuit = std::move(staged);
  return binding;
}

bool update_io_pad(TransientSession &session, IoPadBinding &binding,
                   const IoPadState &state) {
  validate_config(binding.config);
  const auto resistances = state_resistances(binding.config, state);
  if (state == binding.state && resistances == binding.applied_resistances_ohm) {
    return false;
  }
  if (binding.drive_high_id.empty() || binding.drive_low_id.empty() ||
      binding.pull_up_id.empty() || binding.pull_down_id.empty()) {
    throw std::invalid_argument("I/O-pad binding is missing resistor branch IDs");
  }

  session.set_resistance(binding.drive_high_id, resistances[0]);
  session.set_resistance(binding.drive_low_id, resistances[1]);
  session.set_resistance(binding.pull_up_id, resistances[2]);
  session.set_resistance(binding.pull_down_id, resistances[3]);
  binding.state = state;
  binding.applied_resistances_ohm = resistances;
  return true;
}

IoPadObservation observe_io_pad(const TransientSession &session,
                                const IoPadBinding &binding) {
  const auto current = [&session](const std::string &element_id) {
    return element_id.empty() ? 0.0 : session.element_current(element_id);
  };
  const double upper_current = current(binding.drive_high_id) +
                               current(binding.pull_up_id) +
                               current(binding.capacitance_to_vdd_id) +
                               current(binding.clamp_to_vdd_id);
  // The lower clamp is oriented VSS -> die; the other lower branches are
  // oriented die -> VSS.
  const double lower_die_to_vss =
      current(binding.drive_low_id) + current(binding.pull_down_id) +
      current(binding.capacitance_to_vss_id) -
      current(binding.clamp_to_vss_id);

  IoPadObservation observation;
  observation.pad_voltage_v = session.node_voltage(binding.pad);
  observation.die_voltage_v = session.node_voltage(binding.die_pad);
  observation.vdd_voltage_v = session.node_voltage(binding.vdd);
  observation.vss_voltage_v = session.node_voltage(binding.vss);
  observation.vdd_current_a = -upper_current;
  observation.vss_current_a = -lower_die_to_vss;
  if (!binding.package_inductor_id.empty()) {
    observation.pad_current_a =
        session.element_current(binding.package_inductor_id);
  } else if (!binding.package_resistor_id.empty()) {
    observation.pad_current_a =
        session.element_current(binding.package_resistor_id);
  } else {
    observation.pad_current_a = upper_current + lower_die_to_vss;
  }
  return observation;
}

IoPadReceiverState receiver_voltage_state(
    double pad_voltage_v, double vdd_voltage_v, double vss_voltage_v,
    double low_threshold_ratio, double high_threshold_ratio,
    IoPadReceiverState previous) {
  const std::array values{pad_voltage_v, vdd_voltage_v, vss_voltage_v,
                          low_threshold_ratio, high_threshold_ratio};
  if (!std::all_of(values.begin(), values.end(),
                   [](double value) { return std::isfinite(value); }) ||
      low_threshold_ratio < 0.0 ||
      low_threshold_ratio >= high_threshold_ratio ||
      high_threshold_ratio > 1.0) {
    throw std::invalid_argument(
        "receiver voltages must be finite and thresholds satisfy "
        "0 <= VIL ratio < VIH ratio <= 1");
  }
  switch (previous) {
  case IoPadReceiverState::unknown:
  case IoPadReceiverState::low:
  case IoPadReceiverState::high:
    break;
  default:
    throw std::invalid_argument("unknown prior I/O-pad receiver state");
  }
  const double span = vdd_voltage_v - vss_voltage_v;
  if (!std::isfinite(span) || span <= 0.0) {
    return IoPadReceiverState::unknown;
  }
  const double low_threshold = vss_voltage_v + low_threshold_ratio * span;
  const double high_threshold = vss_voltage_v + high_threshold_ratio * span;
  if (pad_voltage_v <= low_threshold) {
    return IoPadReceiverState::low;
  }
  if (pad_voltage_v >= high_threshold) {
    return IoPadReceiverState::high;
  }
  return previous == IoPadReceiverState::low ||
                 previous == IoPadReceiverState::high
             ? previous
             : IoPadReceiverState::unknown;
}

} // namespace spikes
