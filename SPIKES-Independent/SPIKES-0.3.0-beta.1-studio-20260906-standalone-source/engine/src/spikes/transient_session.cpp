#include "spikes/transient_session.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace spikes {
namespace {

double pulse_value_at(const PulseWaveform &pulse, double time) {
  if (time < pulse.delay_s) {
    return pulse.initial_value;
  }
  double phase = std::fmod(time - pulse.delay_s, pulse.period_s);
  if (phase < 0.0) {
    phase += pulse.period_s;
  }
  if (pulse.rise_time_s > 0.0 && phase < pulse.rise_time_s) {
    return pulse.initial_value + phase / pulse.rise_time_s *
                                     (pulse.pulsed_value - pulse.initial_value);
  }
  const double high_end = pulse.rise_time_s + pulse.pulse_width_s;
  if (phase < high_end) {
    return pulse.pulsed_value;
  }
  const double fall_end = high_end + pulse.fall_time_s;
  if (pulse.fall_time_s > 0.0 && phase < fall_end) {
    return pulse.pulsed_value + (phase - high_end) / pulse.fall_time_s *
                                    (pulse.initial_value - pulse.pulsed_value);
  }
  return pulse.initial_value;
}

double pwl_value_at(const std::vector<PwlPoint> &points, double time) {
  if (time <= points.front().time_s) {
    return points.front().value;
  }
  const auto upper = std::upper_bound(
      points.begin(), points.end(), time,
      [](double value, const PwlPoint &point) { return value < point.time_s; });
  if (upper == points.end()) {
    return points.back().value;
  }
  const auto &right = *upper;
  const auto &left = *(upper - 1);
  return left.value + (time - left.time_s) /
                          (right.time_s - left.time_s) *
                          (right.value - left.value);
}

double next_pulse_breakpoint(const PulseWaveform &pulse, double after) {
  const double strictly_after =
      std::nextafter(after, std::numeric_limits<double>::infinity());
  double next = std::numeric_limits<double>::infinity();
  const double offsets[] = {0.0, pulse.rise_time_s,
                            pulse.rise_time_s + pulse.pulse_width_s,
                            pulse.rise_time_s + pulse.pulse_width_s +
                                pulse.fall_time_s};
  for (const double offset : offsets) {
    const double first = pulse.delay_s + offset;
    double candidate = first;
    if (candidate < strictly_after) {
      const double cycles =
          std::ceil((strictly_after - first) / pulse.period_s);
      candidate = first + std::max(0.0, cycles) * pulse.period_s;
      if (candidate < strictly_after) {
        candidate += pulse.period_s;
      }
    }
    next = std::min(next, candidate);
  }
  return next;
}

} // namespace

TransientSession::TransientSession(Circuit circuit, TransientOptions options)
    : circuit_(std::move(circuit)), options_(options) {}

void TransientSession::set_source_value(std::string_view element_id,
                                        double value) {
  if (!std::isfinite(value)) {
    throw std::invalid_argument("persistent source value must be finite");
  }
  const auto found = std::find_if(
      circuit_.elements_.begin(), circuit_.elements_.end(),
      [element_id](const Circuit::Element &element) {
        return element.id == element_id;
      });
  if (found == circuit_.elements_.end()) {
    throw std::out_of_range("unknown persistent-session element");
  }
  if ((found->type != Circuit::ElementType::current_source &&
       found->type != Circuit::ElementType::voltage_source) ||
      found->waveform_type != Circuit::WaveformType::constant) {
    throw std::invalid_argument(
        "only constant independent sources are interactive in session v1");
  }
  found->value = value;
}

bool TransientSession::step(double step_s) {
  if (!std::isfinite(step_s) || step_s <= 0.0) {
    throw std::invalid_argument("persistent transient step must be positive");
  }
  auto step_options = options_;
  step_options.time_step_s = step_s;
  step_options.stop_time_s = step_s;
  step_options.max_steps = options_.max_steps;
  step_options.initialize_from_operating_point =
      first_step_ && options_.initialize_from_operating_point;
  Circuit local_circuit;
  const Circuit *solve_circuit = &circuit_;
  const bool has_waveform = std::any_of(
      circuit_.elements_.begin(), circuit_.elements_.end(),
      [](const Circuit::Element &element) {
        return element.waveform_type != Circuit::WaveformType::constant;
      });
  if (has_waveform) {
    local_circuit = circuit_;
    const double interval_end = time_s_ + step_s;
    for (auto &element : local_circuit.elements_) {
      if (element.waveform_type == Circuit::WaveformType::constant) {
        continue;
      }
      std::vector<PwlPoint> local_points;
      const auto append = [&](double global_time, double value) {
        const double local_time = global_time - time_s_;
        if (!local_points.empty() &&
            local_time <= local_points.back().time_s) {
          return;
        }
        local_points.push_back({local_time, value});
      };
      const auto append_synthetic_endpoint = [&](double value) {
        const double guard =
            256.0 * std::numeric_limits<double>::epsilon() *
            std::max(step_s, std::numeric_limits<double>::min());
        local_points.push_back({step_s + guard, value});
      };
      if (element.waveform_type == Circuit::WaveformType::pulse) {
        append(time_s_, pulse_value_at(element.pulse, time_s_));
        double cursor = time_s_;
        bool endpoint_is_breakpoint = false;
        while (true) {
          const double breakpoint = next_pulse_breakpoint(element.pulse, cursor);
          if (!std::isfinite(breakpoint) || breakpoint > interval_end) {
            break;
          }
          append(breakpoint, pulse_value_at(element.pulse, breakpoint));
          if (breakpoint == interval_end) {
            endpoint_is_breakpoint = true;
            break;
          }
          cursor = breakpoint;
          if (local_points.size() > options_.max_steps + 1u) {
            throw std::invalid_argument(
                "persistent PULSE breakpoint count exceeds max_steps");
          }
        }
        if (!endpoint_is_breakpoint) {
          append_synthetic_endpoint(
              pulse_value_at(element.pulse, interval_end));
        }
      } else {
        append(time_s_, pwl_value_at(element.pwl, time_s_));
        const auto first = std::upper_bound(
            element.pwl.begin(), element.pwl.end(), time_s_,
            [](double value, const PwlPoint &point) {
              return value < point.time_s;
            });
        bool endpoint_is_breakpoint = false;
        for (auto point = first;
             point != element.pwl.end() && point->time_s <= interval_end;
             ++point) {
          append(point->time_s, point->value);
          endpoint_is_breakpoint = point->time_s == interval_end;
          if (local_points.size() > options_.max_steps + 1u) {
            throw std::invalid_argument(
                "persistent PWL breakpoint count exceeds max_steps");
          }
        }
        if (!endpoint_is_breakpoint) {
          append_synthetic_endpoint(
              pwl_value_at(element.pwl, interval_end));
        }
      }
      element.waveform_type = Circuit::WaveformType::pwl;
      element.pwl = std::move(local_points);
    }
    solve_circuit = &local_circuit;
  }
  const auto solved = solve_transient(*solve_circuit, step_options, workspace_);
  const auto &step_diagnostics = solved.diagnostics();
  diagnostics_.matrix_order = step_diagnostics.matrix_order;
  diagnostics_.total_newton_iterations +=
      step_diagnostics.total_newton_iterations;
  diagnostics_.total_damping_steps += step_diagnostics.total_damping_steps;
  diagnostics_.pivot_swaps += step_diagnostics.pivot_swaps;
  diagnostics_.source_breakpoint_steps +=
      step_diagnostics.source_breakpoint_steps;
  diagnostics_.matrix_factorizations += step_diagnostics.matrix_factorizations;
  diagnostics_.factorization_reuses += step_diagnostics.factorization_reuses;
  diagnostics_.factorization_cache_entries =
      std::max(diagnostics_.factorization_cache_entries,
               step_diagnostics.factorization_cache_entries);
  diagnostics_.backward_euler_steps += step_diagnostics.backward_euler_steps;
  diagnostics_.trapezoidal_steps += step_diagnostics.trapezoidal_steps;
  diagnostics_.bdf2_steps += step_diagnostics.bdf2_steps;
  diagnostics_.residual_inf_norm = step_diagnostics.residual_inf_norm;
  if (!solved.converged() || solved.points().empty()) {
    status_ = solved.status();
    message_ = solved.message();
    diagnostics_.failed_time_s = time_s_;
    return false;
  }

  auto accepted = solved.points().back();
  if (accepted.elements.size() != circuit_.elements_.size()) {
    throw std::runtime_error(
        "persistent transient result element count does not match circuit");
  }
  for (std::size_t index = 0; index < circuit_.elements_.size(); ++index) {
    auto &element = circuit_.elements_[index];
    const auto &operating = accepted.elements[index];
    if (element.type == Circuit::ElementType::capacitor) {
      element.initial_condition = operating.voltage_v;
    } else if (element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor) {
      element.initial_condition = operating.current_a;
    }
  }
  time_s_ += step_s;
  ++step_index_;
  diagnostics_.completed_steps += step_diagnostics.completed_steps;
  accepted.time_s = time_s_;
  point_ = std::move(accepted);
  has_point_ = true;
  first_step_ = false;
  status_ = SolveStatus::converged;
  message_ = options_.integration_method == TransientIntegrationMethod::bdf2
                 ? "persistent BDF2 step completed"
                 : options_.integration_method ==
                     TransientIntegrationMethod::hybrid_trapezoidal
                 ? "persistent hybrid-trapezoidal step completed"
                 : "persistent backward-Euler step completed";
  diagnostics_.failed_time_s = 0.0;
  return true;
}

double TransientSession::node_voltage(std::string_view name) const {
  if (!has_point_) {
    throw std::out_of_range("persistent session has no accepted point");
  }
  return point_.node_voltage(name);
}

double TransientSession::element_current(std::string_view id) const {
  if (!has_point_) {
    throw std::out_of_range("persistent session has no accepted point");
  }
  return point_.element_current(id);
}

double TransientSession::element_voltage(std::string_view id) const {
  if (!has_point_) {
    throw std::out_of_range("persistent session has no accepted point");
  }
  const auto found = std::find_if(
      point_.elements.begin(), point_.elements.end(),
      [id](const ElementOperatingPoint &element) { return element.id == id; });
  if (found == point_.elements.end()) {
    throw std::out_of_range("unknown persistent-session element");
  }
  return found->voltage_v;
}

double TransientSession::element_power(std::string_view id) const {
  if (!has_point_) {
    throw std::out_of_range("persistent session has no accepted point");
  }
  const auto found = std::find_if(
      point_.elements.begin(), point_.elements.end(),
      [id](const ElementOperatingPoint &element) { return element.id == id; });
  if (found == point_.elements.end()) {
    throw std::out_of_range("unknown persistent-session element");
  }
  return found->power_w;
}

TransientSessionCheckpoint TransientSession::checkpoint() const {
  TransientSessionCheckpoint value;
  value.circuit = circuit_;
  value.point = point_;
  value.diagnostics = diagnostics_;
  value.status = status_;
  value.message = message_;
  value.time_s = time_s_;
  value.step_index = step_index_;
  value.first_step = first_step_;
  value.has_point = has_point_;
  value.integration_history = workspace_.integration_history();
  return value;
}

void TransientSession::restore(const TransientSessionCheckpoint &checkpoint) {
  circuit_ = checkpoint.circuit;
  point_ = checkpoint.point;
  diagnostics_ = checkpoint.diagnostics;
  status_ = checkpoint.status;
  message_ = checkpoint.message;
  time_s_ = checkpoint.time_s;
  step_index_ = checkpoint.step_index;
  first_step_ = checkpoint.first_step;
  has_point_ = checkpoint.has_point;
  workspace_.restore_integration_history(checkpoint.integration_history);
}

} // namespace spikes
