/**
 * @file dc_solver.hpp
 * @brief Phase-1 SPIKES linear DC operating-point solver API.
 *
 * The API deliberately exposes no linear-algebra implementation types.  That
 * keeps callers independent of the dense reference backend used in Phase 1
 * and lets later sparse backends preserve source compatibility.
 */

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace spikes {

class TransientResult;
class TransientSession;
class TransientWorkspace;
class OsdiDeviceInstance;
struct TransientOptions;

using NodeId = std::uint32_t;
inline constexpr NodeId ground_node = 0;

enum class SolveStatus {
  converged,
  singular,
  numerical_failure,
  nonconverged,
};

enum class LinearSolverMethod {
  automatic,
  dense_lu,
  conjugate_gradient,
  gmres,
  sparse_lu,
  ilu_gmres,
  sparse_qr,
};

struct DiodeModel {
  double saturation_current_a{1.0e-14};
  double emission_coefficient{1.0};
  double temperature_k{300.15};
};

/**
 * Charge-control diode used by the native transient kernel.
 *
 * ``transit_time_s`` stores the forward diffusion charge as an internal
 * current-equivalent state.  Its decay after commutation produces a bounded
 * reverse-recovery tail.  ``junction_capacitance_f`` is a linear depletion
 * capacitance in this first native slice; voltage-dependent depletion charge
 * remains a later compact-model extension.
 */
struct DynamicDiodeModel {
  DiodeModel junction{};
  double transit_time_s{50.0e-9};
  double junction_capacitance_f{10.0e-12};
  double initial_stored_charge_c{0.0};
};

/** Coupled electrical/thermal resistor with one thermal-capacitance DAE. */
struct ElectrothermalResistorModel {
  double resistance_ohm{1.0};
  double temperature_coefficient_per_k{3.9e-3};
  double ambient_temperature_k{300.15};
  double thermal_resistance_k_per_w{10.0};
  double thermal_capacitance_j_per_k{1.0e-3};
  double minimum_temperature_k{200.0};
  double maximum_temperature_k{1000.0};
};

/** Smooth, single-valued saturating flux-linkage model. */
struct SaturatingInductorModel {
  double unsaturated_inductance_h{1.0e-3};
  double saturated_inductance_h{1.0e-5};
  double saturation_current_a{1.0};
  double initial_current_a{0.0};
};

/** Bounded four-terminal n-channel Shichman-Hodges Level-1 model. */
struct MosfetLevel1Model {
  double threshold_voltage_v{1.0};
  double transconductance_a_per_v2{1.0e-3};
  double channel_length_modulation_per_v{0.0};
  double body_effect_sqrt_v{0.0};
  double surface_potential_v{0.6};
  double width_over_length{1.0};
  double off_conductance_s{1.0e-12};
};

/** Bounded three-terminal NPN Ebers-Moll DC model. */
struct BjtEbersMollModel {
  double saturation_current_a{1.0e-15};
  double forward_alpha{0.99};
  double reverse_alpha{0.5};
  double emission_coefficient{1.0};
  double temperature_k{300.15};
};

/** Technology branch for the bounded native wide-bandgap power-FET model. */
enum class WbgTechnology {
  gan_hemt,
  sic_mosfet,
};

/**
 * Five-terminal electrothermal WBG power-FET model.
 *
 * D/G/S/B currents, conservative terminal charges, avalanche, reverse
 * conduction and temperature-dependent channel parameters are evaluated by
 * the native kernel.  The fifth terminal is junction-temperature rise in
 * kelvin above ``ambient_temperature_k``.  Its MNA residual is
 * ``T_rise/Rth - Pdevice``.
 *
 * This bounded model is not BSIM, ASM-HEMT, HiSIM-HV, or a vendor-qualified
 * compact model. Its conservative charge and thermal state are integrated by
 * the native backward-Euler/BDF2 transient solver.
 */
struct WbgFetElectrothermalModel {
  WbgTechnology technology{WbgTechnology::gan_hemt};
  double threshold_voltage_v{2.0};
  double transconductance_a_per_v2{2.0};
  double channel_length_modulation_per_v{0.01};
  double mobility_temperature_exponent{1.5};
  double threshold_temperature_coefficient_v_per_k{-2.0e-3};
  double off_conductance_s{1.0e-9};
  double reverse_conduction_threshold_v{1.5};
  double reverse_conductance_s{1.0};
  double body_diode_saturation_current_a{1.0e-12};
  double body_diode_emission_coefficient{1.5};
  double breakdown_voltage_v{650.0};
  double breakdown_temperature_coefficient_v_per_k{0.25};
  double avalanche_current_scale_a{1.0e-9};
  double avalanche_slope_v{5.0};
  double gate_leakage_conductance_s{1.0e-12};
  double gate_source_capacitance_f{1.0e-9};
  double gate_drain_capacitance_f{1.0e-10};
  double drain_source_capacitance_f{1.0e-10};
  double ambient_temperature_k{300.15};
  double thermal_resistance_k_per_w{2.0};
  double thermal_capacitance_j_per_k{1.0e-3};
  double minimum_temperature_k{200.0};
  double maximum_temperature_k{600.0};
  double maximum_absolute_voltage_v{2.0e3};
  double maximum_absolute_current_a{1.0e4};
};

/** Constitutive point used by native stamping and direct model qualification. */
struct WbgFetElectrothermalPoint {
  // D, G, S, B currents, positive into the device.
  std::array<double, 4> terminal_current_a{};
  // Derivatives of D/G/S/B currents versus D/G/S/B/T-rise.
  std::array<std::array<double, 5>, 4> current_jacobian{};
  // Conservative D/G/S/B charges.
  std::array<double, 4> terminal_charge_c{};
  // Charge derivatives versus D/G/S/B voltage.
  std::array<std::array<double, 4>, 4> charge_jacobian{};
  double dissipated_power_w{0.0};
  // Power derivatives versus D/G/S/B/T-rise.
  std::array<double, 5> power_jacobian{};
  double junction_temperature_k{300.15};
};

/** Evaluate the bounded native WBG constitutive equations and Jacobians. */
[[nodiscard]] WbgFetElectrothermalPoint evaluate_wbg_fet_electrothermal(
    const WbgFetElectrothermalModel &model, double drain_voltage_v,
    double gate_voltage_v, double source_voltage_v, double bulk_voltage_v,
    double temperature_rise_k);

struct PulseWaveform {
  double initial_value{0.0};
  double pulsed_value{1.0};
  double delay_s{0.0};
  double rise_time_s{0.0};
  double fall_time_s{0.0};
  double pulse_width_s{0.5};
  double period_s{1.0};
};

struct PwlPoint {
  double time_s{0.0};
  double value{0.0};
};

struct VoltageControlledSwitchModel {
  double on_resistance_ohm{1.0e-3};
  double off_resistance_ohm{1.0e9};
  double threshold_voltage_v{0.5};
  double transition_voltage_v{1.0e-3};
};

struct SolverOptions {
  std::size_t max_newton_iterations{100};
  std::size_t max_backtracks{20};
  double absolute_tolerance{1.0e-12};
  double relative_tolerance{1.0e-9};
  LinearSolverMethod linear_solver{LinearSolverMethod::automatic};
  std::size_t max_linear_iterations{10'000};
  double linear_absolute_tolerance{1.0e-14};
  double linear_relative_tolerance{1.0e-10};
  std::size_t linear_threads{1};
};

struct NodeVoltage {
  NodeId node{ground_node};
  std::string name;
  double voltage_v{0.0};
};

struct ElementOperatingPoint {
  std::string id;
  double voltage_v{0.0};
  double current_a{0.0};
  double power_w{0.0};
};

struct SolveDiagnostics {
  std::size_t matrix_order{0};
  std::size_t matrix_nonzeros{0};
  std::size_t pivot_swaps{0};
  double residual_inf_norm{0.0};
  std::size_t nonlinear_iterations{0};
  std::size_t damping_steps{0};
  std::size_t junction_limit_steps{0};
  LinearSolverMethod linear_solver_used{LinearSolverMethod::dense_lu};
  std::size_t linear_iterations{0};
  std::size_t linear_threads{1};
  std::size_t symbolic_analyses{0};
  std::size_t numeric_factorizations{0};
};

class OperatingPointResult {
public:
  [[nodiscard]] SolveStatus status() const noexcept { return status_; }
  [[nodiscard]] bool converged() const noexcept {
    return status_ == SolveStatus::converged;
  }
  [[nodiscard]] const std::string &message() const noexcept { return message_; }
  [[nodiscard]] const std::vector<NodeVoltage> &node_voltages() const noexcept {
    return node_voltages_;
  }
  [[nodiscard]] const std::vector<ElementOperatingPoint> &elements() const
      noexcept {
    return elements_;
  }
  [[nodiscard]] const SolveDiagnostics &diagnostics() const noexcept {
    return diagnostics_;
  }

  // Named accessors throw std::out_of_range when the requested name is absent.
  [[nodiscard]] double node_voltage(std::string_view name) const;
  [[nodiscard]] double element_current(std::string_view id) const;
  [[nodiscard]] double element_power(std::string_view id) const;

private:
  friend OperatingPointResult solve_operating_point(const class Circuit &);
  friend OperatingPointResult solve_operating_point(const class Circuit &,
                                                     const SolverOptions &);

  SolveStatus status_{SolveStatus::numerical_failure};
  std::string message_;
  std::vector<NodeVoltage> node_voltages_;
  std::vector<ElementOperatingPoint> elements_;
  SolveDiagnostics diagnostics_;
};

class Circuit {
public:
  Circuit();

  /** Return an existing node or create it. "0" and "GND" are ground. */
  NodeId node(std::string_view name);

  /**
   * Add a resistor. Current and power use the passive-sign convention from
   * positive_node to negative_node.
   */
  void add_resistor(std::string id, std::string positive_node,
                    std::string negative_node, double resistance_ohm);

  /** Add a source whose positive current flows positive_node -> negative_node. */
  void add_current_source(std::string id, std::string positive_node,
                          std::string negative_node, double current_a);

  /** Add a source enforcing V(positive_node)-V(negative_node)=voltage_v. */
  void add_voltage_source(std::string id, std::string positive_node,
                          std::string negative_node, double voltage_v);

  /** Add a periodic PULSE current source with exact transient breakpoints. */
  void add_pulse_current_source(std::string id, std::string positive_node,
                                std::string negative_node,
                                PulseWaveform waveform);

  /** Add a periodic PULSE voltage source with exact transient breakpoints. */
  void add_pulse_voltage_source(std::string id, std::string positive_node,
                                std::string negative_node,
                                PulseWaveform waveform);

  /** Add a piecewise-linear current source. Point times must increase. */
  void add_pwl_current_source(std::string id, std::string positive_node,
                              std::string negative_node,
                              std::vector<PwlPoint> points);

  /** Add a piecewise-linear voltage source. Point times must increase. */
  void add_pwl_voltage_source(std::string id, std::string positive_node,
                              std::string negative_node,
                              std::vector<PwlPoint> points);

  /**
   * Add a smooth, bidirectional voltage-controlled switch. The finite Ron/Roff
   * and analytic transition Jacobian avoid topology singularities at edges.
   */
  void add_voltage_controlled_switch(
      std::string id, std::string positive_node, std::string negative_node,
      std::string control_positive_node, std::string control_negative_node,
      VoltageControlledSwitchModel model = {});

  /** Add a Shockley diode whose positive terminal is the anode. */
  void add_diode(std::string id, std::string anode_node,
                 std::string cathode_node, DiodeModel model = {});

  /** Add a charge-control diode with reverse recovery and depletion charge. */
  void add_dynamic_diode(std::string id, std::string anode_node,
                         std::string cathode_node,
                         DynamicDiodeModel model = {});

  /** Add a resistor coupled to a thermal-rise node with Rth/Cth dynamics. */
  void add_electrothermal_resistor(
      std::string id, std::string positive_node, std::string negative_node,
      std::string thermal_node, ElectrothermalResistorModel model = {});

  /** Add a bidirectional four-terminal nMOS Level-1 DC compact model. */
  void add_mosfet_level1(std::string id, std::string drain_node,
                         std::string gate_node, std::string source_node,
                         std::string bulk_node,
                         MosfetLevel1Model model = {});

  /** Add a three-terminal NPN Ebers-Moll DC compact model. */
  void add_bjt_ebers_moll(std::string id, std::string collector_node,
                          std::string base_node, std::string emitter_node,
                          BjtEbersMollModel model = {});

  /** Add the native five-terminal electrothermal GaN/SiC DC element. */
  void add_wbg_fet_electrothermal(
      std::string id, std::string drain_node, std::string gate_node,
      std::string source_node, std::string bulk_node,
      std::string thermal_node, WbgFetElectrothermalModel model = {});

  /** Register one initialized trusted OSDI device, including internal nodes. */
  void add_osdi_device(std::string id, std::vector<std::string> terminal_nodes,
                       std::shared_ptr<OsdiDeviceInstance> device);

  /** Add an ideal capacitor, optionally with a transient initial voltage. */
  void add_capacitor(std::string id, std::string positive_node,
                     std::string negative_node, double capacitance_f,
                     double initial_voltage_v = 0.0);

  /** Add an ideal inductor, optionally with a transient initial current. */
  void add_inductor(std::string id, std::string positive_node,
                    std::string negative_node, double inductance_h,
                    double initial_current_a = 0.0);

  /** Add an energy-consistent smooth saturating inductor. */
  void add_saturating_inductor(std::string id, std::string positive_node,
                               std::string negative_node,
                               SaturatingInductorModel model = {});

  [[nodiscard]] std::size_t node_count() const noexcept;
  [[nodiscard]] std::size_t element_count() const noexcept;

private:
  enum class ElementType {
    resistor,
    current_source,
    voltage_source,
    diode,
    dynamic_diode,
    electrothermal_resistor,
    mosfet_level1,
    bjt_ebers_moll,
    wbg_fet_electrothermal,
    osdi_device,
    capacitor,
    inductor,
    saturating_inductor,
    voltage_controlled_switch
  };
  enum class WaveformType { constant, pulse, pwl };
  struct Element {
    ElementType type;
    std::string id;
    NodeId positive_node;
    NodeId negative_node;
    double value;
    double initial_condition;
    DiodeModel diode;
    DynamicDiodeModel dynamic_diode{};
    ElectrothermalResistorModel electrothermal_resistor{};
    SaturatingInductorModel saturating_inductor{};
    MosfetLevel1Model mosfet_level1{};
    BjtEbersMollModel bjt_ebers_moll{};
    WbgFetElectrothermalModel wbg_fet_electrothermal{};
    std::shared_ptr<OsdiDeviceInstance> osdi_device{};
    std::vector<NodeId> osdi_nodes;
    WaveformType waveform_type{WaveformType::constant};
    PulseWaveform pulse{};
    std::vector<PwlPoint> pwl;
    NodeId control_positive_node{ground_node};
    NodeId control_negative_node{ground_node};
    NodeId thermal_node{ground_node};
    VoltageControlledSwitchModel switch_model{};
  };

  void add_element(ElementType type, std::string id,
                   std::string positive_node, std::string negative_node,
                   double value);

  std::vector<std::string> node_names_;
  std::vector<Element> elements_;

  friend OperatingPointResult solve_operating_point(const Circuit &);
  friend OperatingPointResult solve_operating_point(const Circuit &,
                                                     const SolverOptions &);
  friend TransientResult solve_transient(const Circuit &,
                                          const TransientOptions &);
  friend TransientResult solve_transient(const Circuit &,
                                          const TransientOptions &,
                                          TransientWorkspace &);
  friend class TransientSession;
};

/** Solve the linear DC operating point using modified nodal analysis. */
[[nodiscard]] OperatingPointResult solve_operating_point(const Circuit &circuit);

/** Solve with explicit nonlinear iteration and tolerance controls. */
[[nodiscard]] OperatingPointResult
solve_operating_point(const Circuit &circuit, const SolverOptions &options);

} // namespace spikes
