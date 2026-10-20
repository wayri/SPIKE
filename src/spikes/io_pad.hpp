// SPDX-License-Identifier: Apache-2.0
/**
 * @file io_pad.hpp
 * @brief Generic, user-parameterized electrical GPIO-pad composition.
 *
 * This model is an experimental composition of ordinary native MNA elements.
 * It does not contain vendor-calibrated STM, Nordic, or other device constants.
 */

#pragma once

#include "spikes/dc_solver.hpp"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace spikes {

class TransientSession;

enum class IoPadDriveMode : std::uint32_t {
  input,
  push_pull,
  open_drain,
  open_source,
};

enum class IoPadOutputState : std::uint32_t {
  low,
  high,
  released,
};

/** Selects the user profile's active output resistance, not a pull strength. */
enum class IoPadDriveLevel : std::uint32_t {
  strong,
  weak,
};

enum class IoPadPull : std::uint32_t {
  none,
  up,
  down,
};

enum class IoPadReceiverState : std::uint32_t {
  unknown,
  low,
  high,
};

struct IoPadState {
  IoPadDriveMode mode{IoPadDriveMode::input};
  IoPadOutputState output{IoPadOutputState::released};
  IoPadDriveLevel drive_level{IoPadDriveLevel::strong};
  IoPadPull pull{IoPadPull::none};

  bool operator==(const IoPadState &) const = default;
};

/**
 * Explicit generic values in SI units. The defaults are stable numerical
 * examples only; callers must supply a characterized profile for hardware use.
 */
struct IoPadConfig {
  double high_strong_resistance_ohm{50.0};
  double high_weak_resistance_ohm{500.0};
  double low_strong_resistance_ohm{50.0};
  double low_weak_resistance_ohm{500.0};
  double pull_up_resistance_ohm{50'000.0};
  double pull_down_resistance_ohm{50'000.0};
  double off_resistance_ohm{1.0e12};

  /** Zero omits the corresponding package or pad-storage element. */
  double package_resistance_ohm{0.0};
  double package_inductance_h{0.0};
  double capacitance_to_vss_f{0.0};
  double capacitance_to_vdd_f{0.0};

  bool enable_clamp_to_vdd{false};
  bool enable_clamp_to_vss{false};
  DiodeModel clamp_diode{};
};

/**
 * Stable names for every composed branch. Empty optional IDs mean that the
 * corresponding element was not configured. Currents use each native
 * element's stated positive-to-negative convention.
 */
struct IoPadBinding {
  std::string prefix;
  std::string pad;
  std::string die_pad;
  std::string vdd;
  std::string vss;

  std::string package_resistor_id;
  std::string package_inductor_id;
  std::string drive_high_id;
  std::string drive_low_id;
  std::string pull_up_id;
  std::string pull_down_id;
  std::string capacitance_to_vss_id;
  std::string capacitance_to_vdd_id;
  std::string clamp_to_vdd_id;
  std::string clamp_to_vss_id;

  IoPadConfig config{};
  IoPadState state{};
  /** Last values applied to high, low, pull-up, and pull-down branches. */
  std::array<double, 4> applied_resistances_ohm{};

  /** IDs in deterministic circuit insertion order, with omitted branches absent. */
  [[nodiscard]] std::vector<std::string> element_ids() const;
};

/** Instantaneous terminal voltages and currents; positive current enters the pad network. */
struct IoPadObservation {
  double pad_voltage_v{0.0};
  double die_voltage_v{0.0};
  double vdd_voltage_v{0.0};
  double vss_voltage_v{0.0};
  double pad_current_a{0.0};
  double vdd_current_a{0.0};
  double vss_current_a{0.0};
};

/**
 * Atomically compose one finite passive pad network on a staged Circuit copy.
 * The external pad and actual VDD/VSS rails must be distinct; only VSS may be
 * a ground alias. Generated internal-node and element-ID collisions fail.
 */
[[nodiscard]] IoPadBinding add_io_pad(
    Circuit &circuit, std::string prefix, std::string pad, std::string vdd,
    std::string vss, const IoPadConfig &config,
    const IoPadState &initial_state = IoPadState{});

/**
 * Apply a validated state using the session's topology-preserving resistor
 * setter. Returns false and performs no setter calls when the state is equal
 * to the binding's last applied state.
 *
 * A binding returned by add_io_pad is required. Because the current session
 * API updates one resistor at a time, caller mutation of public branch IDs can
 * make an exceptional update partially applied; ordinary validated bindings
 * contain four known resistor IDs and do not have that failure mode.
 */
bool update_io_pad(TransientSession &session, IoPadBinding &binding,
                   const IoPadState &state);

/** Read one accepted session point without reconstructing package current from KCL. */
[[nodiscard]] IoPadObservation observe_io_pad(
    const TransientSession &session, const IoPadBinding &binding);

/**
 * Classify a finite pad voltage against explicit rail-relative thresholds.
 * Inside the threshold band a prior known state supplies generic hysteresis;
 * otherwise the result remains unknown. This helper contains no vendor levels.
 */
[[nodiscard]] IoPadReceiverState receiver_voltage_state(
    double pad_voltage_v, double vdd_voltage_v, double vss_voltage_v,
    double low_threshold_ratio, double high_threshold_ratio,
    IoPadReceiverState previous = IoPadReceiverState::unknown);

} // namespace spikes
