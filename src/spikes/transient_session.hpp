/**
 * @file transient_session.hpp
 * @brief Persistent stateful stepping foundation for interactive SPIKES use.
 */

#pragma once

#include "spikes/transient_solver.hpp"

#include <cstddef>
#include <string>
#include <string_view>

namespace spikes {

struct TransientSessionCheckpoint;

class TransientSession {
public:
  /**
   * Create a persistent session from an immutable circuit snapshot.
   *
   * Version 1 accepts constant/PULSE/PWL independent sources and backward
   * Euler, hybrid trapezoidal, or BDF2 integration. Waveform event times are
   * interpreted on the persistent global clock and exact internal source
   * breakpoints remain bounded by max_steps.
   */
  explicit TransientSession(Circuit circuit,
                            TransientOptions options = TransientOptions{});

  /** Update one constant independent voltage/current source by element id. */
  void set_source_value(std::string_view element_id, double value);

  /** Advance exactly one step. Failure leaves the last accepted state intact. */
  [[nodiscard]] bool step(double step_s);

  [[nodiscard]] SolveStatus status() const noexcept { return status_; }
  [[nodiscard]] const std::string &message() const noexcept { return message_; }
  [[nodiscard]] double time_s() const noexcept { return time_s_; }
  [[nodiscard]] std::size_t step_index() const noexcept { return step_index_; }
  [[nodiscard]] bool has_point() const noexcept { return has_point_; }
  [[nodiscard]] double node_voltage(std::string_view name) const;
  [[nodiscard]] double element_voltage(std::string_view id) const;
  [[nodiscard]] double element_current(std::string_view id) const;
  [[nodiscard]] double element_power(std::string_view id) const;
  [[nodiscard]] const TransientDiagnostics &diagnostics() const noexcept {
    return diagnostics_;
  }

  [[nodiscard]] TransientSessionCheckpoint checkpoint() const;
  void restore(const TransientSessionCheckpoint &checkpoint);

private:
  Circuit circuit_;
  TransientOptions options_;
  TransientWorkspace workspace_;
  TransientPoint point_;
  TransientDiagnostics diagnostics_;
  SolveStatus status_{SolveStatus::converged};
  std::string message_{"persistent transient session ready"};
  double time_s_{0.0};
  std::size_t step_index_{0};
  bool first_step_{true};
  bool has_point_{false};
};

struct TransientSessionCheckpoint {
private:
  friend class TransientSession;
  Circuit circuit;
  TransientPoint point;
  TransientDiagnostics diagnostics;
  SolveStatus status{SolveStatus::converged};
  std::string message;
  double time_s{0.0};
  std::size_t step_index{0};
  bool first_step{true};
  bool has_point{false};
  TransientIntegrationHistory integration_history;
};

} // namespace spikes
