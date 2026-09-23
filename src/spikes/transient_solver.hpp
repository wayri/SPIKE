/**
 * @file transient_solver.hpp
 * @brief Experimental breakpoint-aware transient foundation for SPIKES.
 *
 * Version 1 supports backward Euler, event-aware hybrid trapezoidal, and
 * variable-step BDF2 with backward-Euler discontinuity restarts, an embedded
 * BDF2/trapezoidal-versus-BE error controller for linear and diode/switch
 * nonlinear DAEs, and direct sparse assembly for sufficiently large linear
 * systems. Nonlinear Jacobians retain the dense correctness path. This is not
 * a claim of complete SPICE compatibility.
 */

#pragma once

#include "spikes/dc_solver.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace spikes {

inline constexpr std::uint32_t transient_api_version = 1;

enum class TransientIntegrationMethod {
  backward_euler,
  hybrid_trapezoidal,
  bdf2,
};

struct TransientOptions {
  double time_step_s{1.0e-6};
  double minimum_time_step_s{1.0e-15};
  double stop_time_s{1.0e-3};
  std::size_t max_steps{1'000'000};
  bool initialize_from_operating_point{true};
  TransientIntegrationMethod integration_method{
      TransientIntegrationMethod::backward_euler};
  bool adaptive_time_step{false};
  double lte_absolute_tolerance{1.0e-6};
  double lte_relative_tolerance{1.0e-3};
  std::size_t max_rejected_steps{10'000};
  /** Linear systems at or above this order use direct sparse assembly/SparseLU. */
  std::size_t sparse_linear_threshold{128};
  SolverOptions nonlinear{};
};

struct TransientPoint {
  double time_s{0.0};
  std::vector<NodeVoltage> node_voltages;
  std::vector<ElementOperatingPoint> elements;

  [[nodiscard]] double node_voltage(std::string_view name) const;
  [[nodiscard]] double element_current(std::string_view id) const;
};

struct TransientDiagnostics {
  std::size_t matrix_order{0};
  std::size_t completed_steps{0};
  std::size_t total_newton_iterations{0};
  std::size_t total_damping_steps{0};
  std::size_t pivot_swaps{0};
  std::size_t source_breakpoint_steps{0};
  std::size_t matrix_factorizations{0};
  std::size_t factorization_reuses{0};
  std::size_t factorization_cache_entries{0};
  std::size_t backward_euler_steps{0};
  std::size_t trapezoidal_steps{0};
  std::size_t bdf2_steps{0};
  std::size_t rejected_lte_steps{0};
  std::size_t embedded_lte_solves{0};
  std::size_t sparse_assemblies{0};
  std::size_t sparse_symbolic_analyses{0};
  std::size_t sparse_numeric_factorizations{0};
  std::size_t partial_numeric_refactorizations{0};
  double last_lte_ratio{0.0};
  double minimum_accepted_step_s{0.0};
  double maximum_accepted_step_s{0.0};
  double failed_time_s{0.0};
  double residual_inf_norm{0.0};
};

/** Copyable dynamic companion history used by persistent checkpoints. */
struct TransientIntegrationHistory {
  std::vector<double> capacitor_currents;
  std::vector<double> inductor_voltages;
  std::vector<double> capacitor_previous_voltages;
  std::vector<double> inductor_previous_currents;
  std::vector<double> dynamic_diode_stored_currents;
  std::vector<double> dynamic_diode_previous_stored_currents;
  std::vector<double> dynamic_diode_voltages;
  std::vector<double> dynamic_diode_previous_voltages;
  std::vector<std::vector<double>> osdi_device_states;
  std::vector<std::vector<double>> osdi_reactive_residuals;
  std::vector<double> last_solution;
  std::vector<double> previous_solution;
  std::vector<std::uint64_t> structural_signature;
  double previous_step_s{0.0};
  std::size_t history_depth{0};
  std::size_t solution_history_depth{0};
  bool valid{false};
};

/**
 * Bounded reusable numerical state for a sequence of transient solves.
 *
 * Cache keys contain the complete stamped matrix and use a strict
 * machine-epsilon-relative coefficient comparison, so changing independent
 * source values (the right-hand side) cannot produce an unsafe factor reuse.
 */
class TransientWorkspace {
public:
  TransientWorkspace();
  ~TransientWorkspace();
  TransientWorkspace(TransientWorkspace &&) noexcept;
  TransientWorkspace &operator=(TransientWorkspace &&) noexcept;
  TransientWorkspace(const TransientWorkspace &) = delete;
  TransientWorkspace &operator=(const TransientWorkspace &) = delete;

  void clear() noexcept;
  [[nodiscard]] TransientIntegrationHistory integration_history() const;
  void restore_integration_history(const TransientIntegrationHistory &history);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
  friend TransientResult solve_transient(const Circuit &,
                                          const TransientOptions &,
                                          TransientWorkspace &);
};

class TransientResult {
public:
  [[nodiscard]] SolveStatus status() const noexcept { return status_; }
  [[nodiscard]] bool converged() const noexcept {
    return status_ == SolveStatus::converged;
  }
  [[nodiscard]] const std::string &message() const noexcept { return message_; }
  [[nodiscard]] const std::vector<TransientPoint> &points() const noexcept {
    return points_;
  }
  [[nodiscard]] const TransientDiagnostics &diagnostics() const noexcept {
    return diagnostics_;
  }

private:
  friend TransientResult solve_transient(const Circuit &,
                                          const TransientOptions &);
  friend TransientResult solve_transient(const Circuit &,
                                          const TransientOptions &,
                                          TransientWorkspace &);
  SolveStatus status_{SolveStatus::numerical_failure};
  std::string message_;
  std::vector<TransientPoint> points_;
  TransientDiagnostics diagnostics_;
};

/**
 * Solve a bounded backward-Euler transient. time_step_s is the maximum step;
 * PULSE and PWL source breakpoints force smaller steps so source transitions
 * are never crossed without a solve at the edge.
 *
 * With DC initialization enabled, the first sample is the operating point at
 * t=0. With it disabled, capacitor voltages and inductor currents begin at
 * their declared initial conditions and the first returned sample is at dt.
 */
[[nodiscard]] TransientResult
solve_transient(const Circuit &circuit,
                const TransientOptions &options = TransientOptions{});

/** Solve while retaining dense exact-matrix and sparse symbolic/numeric caches. */
[[nodiscard]] TransientResult
solve_transient(const Circuit &circuit, const TransientOptions &options,
                TransientWorkspace &workspace);

} // namespace spikes
