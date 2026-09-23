#include "spikes/transient_solver.hpp"
#include "spikes/osdi_device.hpp"

#include <Eigen/OrderingMethods>
#include <Eigen/SparseCore>
#include <Eigen/SparseLU>

#include <algorithm>
#include <bit>
#include <cmath>
#include <functional>
#include <limits>
#include <stdexcept>
#include <utility>

namespace spikes {
namespace {

using SparseMatrix = Eigen::SparseMatrix<double, Eigen::ColMajor, int>;
using SparseTriplet = Eigen::Triplet<double, int>;

constexpr double pivot_tolerance =
    64.0 * std::numeric_limits<double>::epsilon();
constexpr double boltzmann_over_charge = 8.617333262145e-5;
constexpr double maximum_exponential_argument = 80.0;

[[nodiscard]] bool ground_name(std::string_view name) {
  return name == "0" || name == "GND" || name == "gnd";
}

[[nodiscard]] std::size_t at(std::size_t row, std::size_t column,
                             std::size_t order) {
  return row * order + column;
}

void stamp(std::vector<double> &matrix, std::size_t order, NodeId row,
           NodeId column, double value) {
  if (row != ground_node && column != ground_node) {
    matrix[at(row - 1, column - 1, order)] += value;
  }
}

void stamp_rhs(std::vector<double> &rhs, NodeId node, double value) {
  if (node != ground_node) {
    rhs[node - 1] += value;
  }
}

void stamp_sparse(std::vector<SparseTriplet> &triplets, NodeId row,
                  NodeId column, double value) {
  if (row != ground_node && column != ground_node) {
    triplets.emplace_back(static_cast<int>(row - 1),
                          static_cast<int>(column - 1), value);
  }
}

void stamp_sparse_index(std::vector<SparseTriplet> &triplets,
                        std::size_t row, std::size_t column, double value) {
  triplets.emplace_back(static_cast<int>(row), static_cast<int>(column), value);
}

[[nodiscard]] double inf_norm(const std::vector<double> &values) {
  double result = 0.0;
  for (const double value : values) {
    result = std::max(result, std::abs(value));
  }
  return result;
}

[[nodiscard]] bool numerically_same_matrix(const std::vector<double> &left,
                                            const std::vector<double> &right) {
  if (left.size() != right.size()) {
    return false;
  }
  for (std::size_t index = 0; index < left.size(); ++index) {
    const double scale =
        std::max({std::abs(left[index]), std::abs(right[index]),
                  std::numeric_limits<double>::min()});
    if (std::abs(left[index] - right[index]) >
        64.0 * std::numeric_limits<double>::epsilon() * scale) {
      return false;
    }
  }
  return true;
}

struct DenseResult {
  SolveStatus status{SolveStatus::numerical_failure};
  std::string message;
  std::vector<double> values;
  std::size_t swaps{0};
};

struct DenseFactorization {
  SolveStatus status{SolveStatus::numerical_failure};
  std::string message;
  std::vector<double> lu;
  std::vector<std::size_t> pivot_rows;
  std::size_t order{0};
  std::size_t swaps{0};
};

struct CachedFactorization {
  std::vector<double> matrix;
  DenseFactorization factorization;
};

struct CachedJacobianFactorization {
  std::vector<double> jacobian;
  DenseFactorization factorization;
};

struct NonlinearEvaluation {
  std::vector<double> residual;
  std::vector<double> dense_jacobian;
  SparseMatrix sparse_jacobian;
};

struct SparseTransientFactorization {
  Eigen::SparseLU<SparseMatrix, Eigen::COLAMDOrdering<int>> solver;
  std::vector<int> outer_indices;
  std::vector<int> inner_indices;
  std::vector<double> values;
  int rows{0};
  int columns{0};
  bool analyzed{false};
  bool factorized{false};
};

[[nodiscard]] bool same_sparse_pattern(const SparseMatrix &matrix,
                                       const SparseTransientFactorization &cache) {
  if (!cache.analyzed || matrix.rows() != cache.rows ||
      matrix.cols() != cache.columns ||
      static_cast<std::size_t>(matrix.outerSize() + 1) !=
          cache.outer_indices.size() ||
      static_cast<std::size_t>(matrix.nonZeros()) != cache.inner_indices.size()) {
    return false;
  }
  return std::equal(matrix.outerIndexPtr(),
                    matrix.outerIndexPtr() + matrix.outerSize() + 1,
                    cache.outer_indices.begin()) &&
         std::equal(matrix.innerIndexPtr(),
                    matrix.innerIndexPtr() + matrix.nonZeros(),
                    cache.inner_indices.begin());
}

[[nodiscard]] bool same_sparse_values(const SparseMatrix &matrix,
                                      const SparseTransientFactorization &cache) {
  if (!cache.factorized ||
      static_cast<std::size_t>(matrix.nonZeros()) != cache.values.size()) {
    return false;
  }
  for (int index = 0; index < matrix.nonZeros(); ++index) {
    const double left = matrix.valuePtr()[index];
    const double right = cache.values[static_cast<std::size_t>(index)];
    const double scale = std::max({std::abs(left), std::abs(right),
                                   std::numeric_limits<double>::min()});
    if (std::abs(left - right) >
        64.0 * std::numeric_limits<double>::epsilon() * scale) {
      return false;
    }
  }
  return true;
}

[[nodiscard]] DenseFactorization factor_dense(std::vector<double> matrix,
                                               std::size_t order) {
  DenseFactorization result;
  result.order = order;
  result.lu = std::move(matrix);
  result.pivot_rows.resize(order);
  if (order == 0) {
    result.status = SolveStatus::converged;
    return result;
  }
  for (std::size_t column = 0; column < order; ++column) {
    std::size_t pivot_row = column;
    double pivot = 0.0;
    double scale = 0.0;
    for (std::size_t row = column; row < order; ++row) {
      const double magnitude = std::abs(result.lu[at(row, column, order)]);
      scale = std::max(scale, magnitude);
      if (magnitude > pivot) {
        pivot = magnitude;
        pivot_row = row;
      }
    }
    if (!std::isfinite(pivot) || scale == 0.0 ||
        pivot <= pivot_tolerance * scale) {
      result.status = SolveStatus::singular;
      result.message = "singular or underconstrained transient MNA system";
      result.lu.clear();
      result.pivot_rows.clear();
      return result;
    }
    result.pivot_rows[column] = pivot_row;
    if (pivot_row != column) {
      for (std::size_t j = 0; j < order; ++j) {
        std::swap(result.lu[at(column, j, order)],
                  result.lu[at(pivot_row, j, order)]);
      }
      ++result.swaps;
    }
    const double diagonal = result.lu[at(column, column, order)];
    for (std::size_t row = column + 1; row < order; ++row) {
      const double multiplier = result.lu[at(row, column, order)] / diagonal;
      result.lu[at(row, column, order)] = multiplier;
      for (std::size_t j = column + 1; j < order; ++j) {
        result.lu[at(row, j, order)] -=
            multiplier * result.lu[at(column, j, order)];
      }
    }
  }
  result.status = SolveStatus::converged;
  return result;
}

[[nodiscard]] DenseResult
solve_factorized(const DenseFactorization &factorization,
                 std::vector<double> rhs) {
  DenseResult result;
  result.status = factorization.status;
  result.message = factorization.message;
  if (factorization.status != SolveStatus::converged) {
    return result;
  }
  const std::size_t order = factorization.order;
  result.values = std::move(rhs);
  for (std::size_t column = 0; column < order; ++column) {
    const std::size_t pivot_row = factorization.pivot_rows[column];
    if (pivot_row != column) {
      std::swap(result.values[column], result.values[pivot_row]);
    }
  }
  for (std::size_t row = 0; row < order; ++row) {
    for (std::size_t column = 0; column < row; ++column) {
      result.values[row] -=
          factorization.lu[at(row, column, order)] * result.values[column];
    }
  }
  for (std::size_t row = order; row-- > 0;) {
    double value = result.values[row];
    for (std::size_t column = row + 1; column < order; ++column) {
      value -= factorization.lu[at(row, column, order)] * result.values[column];
    }
    result.values[row] = value / factorization.lu[at(row, row, order)];
    if (!std::isfinite(result.values[row])) {
      result.status = SolveStatus::numerical_failure;
      result.message = "non-finite value produced by transient linear solve";
      result.values.clear();
      return result;
    }
  }
  result.status = SolveStatus::converged;
  return result;
}

[[nodiscard]] DenseResult solve_dense(std::vector<double> matrix,
                                      std::vector<double> rhs,
                                      std::size_t order) {
  auto factorization = factor_dense(std::move(matrix), order);
  auto result = solve_factorized(factorization, std::move(rhs));
  result.swaps = factorization.swaps;
  return result;
}

struct DiodePoint {
  double current;
  double conductance;
};

struct SwitchPoint {
  double conductance;
  double derivative;
};

[[nodiscard]] SwitchPoint
voltage_controlled_switch(const VoltageControlledSwitchModel &model,
                          double control_voltage) {
  const double on_conductance = 1.0 / model.on_resistance_ohm;
  const double off_conductance = 1.0 / model.off_resistance_ohm;
  const double normalized =
      (control_voltage - model.threshold_voltage_v) /
      model.transition_voltage_v;
  const double tangent = std::tanh(normalized);
  const double blend = 0.5 * (1.0 + tangent);
  const double derivative = 0.5 * (1.0 - tangent * tangent) /
                            model.transition_voltage_v;
  return {off_conductance + blend * (on_conductance - off_conductance),
          derivative * (on_conductance - off_conductance)};
}

[[nodiscard]] DiodePoint diode(double saturation_current,
                               double emission_coefficient,
                               double temperature, double voltage) {
  const double thermal = boltzmann_over_charge * emission_coefficient * temperature;
  const double argument = voltage / thermal;
  if (argument <= maximum_exponential_argument) {
    const double exponential = std::exp(argument);
    return {saturation_current * std::expm1(argument),
            saturation_current * exponential / thermal};
  }
  const double boundary = std::exp(maximum_exponential_argument);
  return {saturation_current *
              (boundary * (1.0 + argument - maximum_exponential_argument) - 1.0),
          saturation_current * boundary / thermal};
}

struct ElectrothermalResistorPoint {
  double current{0.0};
  double conductance{0.0};
  double current_temperature_derivative{0.0};
  double power{0.0};
  double power_voltage_derivative{0.0};
  double power_temperature_derivative{0.0};
};

[[nodiscard]] ElectrothermalResistorPoint electrothermal_resistor(
    const ElectrothermalResistorModel &model, double voltage,
    double temperature_rise) {
  const double temperature = model.ambient_temperature_k + temperature_rise;
  const double scale =
      1.0 + model.temperature_coefficient_per_k * temperature_rise;
  if (!std::isfinite(voltage) || !std::isfinite(temperature_rise) ||
      temperature < model.minimum_temperature_k ||
      temperature > model.maximum_temperature_k || !(scale > 0.0)) {
    throw std::out_of_range(
        "electrothermal resistor is outside its temperature envelope");
  }
  const double resistance = model.resistance_ohm * scale;
  const double conductance = 1.0 / resistance;
  const double dg_dt =
      -model.resistance_ohm * model.temperature_coefficient_per_k /
      (resistance * resistance);
  return {voltage * conductance,
          conductance,
          voltage * dg_dt,
          voltage * voltage * conductance,
          2.0 * voltage * conductance,
          voltage * voltage * dg_dt};
}

[[nodiscard]] double saturating_flux_linkage(
    const SaturatingInductorModel &model, double current) {
  return model.saturated_inductance_h * current +
         (model.unsaturated_inductance_h -
          model.saturated_inductance_h) *
             model.saturation_current_a *
             std::tanh(current / model.saturation_current_a);
}

[[nodiscard]] double saturating_differential_inductance(
    const SaturatingInductorModel &model, double current) {
  const double tangent = std::tanh(current / model.saturation_current_a);
  return model.saturated_inductance_h +
         (model.unsaturated_inductance_h -
          model.saturated_inductance_h) *
             (1.0 - tangent * tangent);
}

[[nodiscard]] double pulse_value(const PulseWaveform &pulse, double time) {
  if (time < pulse.delay_s) {
    return pulse.initial_value;
  }
  double phase = std::fmod(time - pulse.delay_s, pulse.period_s);
  if (phase < 0.0) {
    phase += pulse.period_s;
  }
  if (pulse.rise_time_s > 0.0 && phase < pulse.rise_time_s) {
    const double fraction = phase / pulse.rise_time_s;
    return pulse.initial_value +
           fraction * (pulse.pulsed_value - pulse.initial_value);
  }
  const double high_end = pulse.rise_time_s + pulse.pulse_width_s;
  if (phase < high_end) {
    return pulse.pulsed_value;
  }
  const double fall_end = high_end + pulse.fall_time_s;
  if (pulse.fall_time_s > 0.0 && phase < fall_end) {
    const double fraction = (phase - high_end) / pulse.fall_time_s;
    return pulse.pulsed_value +
           fraction * (pulse.initial_value - pulse.pulsed_value);
  }
  return pulse.initial_value;
}

[[nodiscard]] double pwl_value(const std::vector<PwlPoint> &points,
                               double time) {
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
  const double fraction =
      (time - left.time_s) / (right.time_s - left.time_s);
  return left.value + fraction * (right.value - left.value);
}

} // namespace

struct TransientWorkspace::Impl {
  std::vector<CachedFactorization> factorization_cache;
  std::vector<CachedJacobianFactorization> jacobian_cache;
  std::unique_ptr<SparseTransientFactorization> sparse_factorization{
      std::make_unique<SparseTransientFactorization>()};
  std::unique_ptr<SparseTransientFactorization> sparse_jacobian_factorization{
      std::make_unique<SparseTransientFactorization>()};
  TransientIntegrationHistory integration_history;
};

TransientWorkspace::TransientWorkspace() : impl_(std::make_unique<Impl>()) {}
TransientWorkspace::~TransientWorkspace() = default;
TransientWorkspace::TransientWorkspace(TransientWorkspace &&) noexcept =
    default;
TransientWorkspace &
TransientWorkspace::operator=(TransientWorkspace &&) noexcept = default;

void TransientWorkspace::clear() noexcept {
  impl_->factorization_cache.clear();
  impl_->jacobian_cache.clear();
  impl_->sparse_factorization = std::make_unique<SparseTransientFactorization>();
  impl_->sparse_jacobian_factorization =
      std::make_unique<SparseTransientFactorization>();
  impl_->integration_history = {};
}

TransientIntegrationHistory TransientWorkspace::integration_history() const {
  return impl_->integration_history;
}

void TransientWorkspace::restore_integration_history(
    const TransientIntegrationHistory &history) {
  impl_->integration_history = history;
}

double TransientPoint::node_voltage(std::string_view name) const {
  if (ground_name(name)) {
    return 0.0;
  }
  const auto found = std::find_if(
      node_voltages.begin(), node_voltages.end(),
      [name](const NodeVoltage &entry) { return entry.name == name; });
  if (found == node_voltages.end()) {
    throw std::out_of_range("unknown transient node");
  }
  return found->voltage_v;
}

double TransientPoint::element_current(std::string_view id) const {
  const auto found = std::find_if(
      elements.begin(), elements.end(),
      [id](const ElementOperatingPoint &entry) { return entry.id == id; });
  if (found == elements.end()) {
    throw std::out_of_range("unknown transient element");
  }
  return found->current_a;
}

TransientResult solve_transient(const Circuit &circuit,
                                const TransientOptions &options) {
  TransientWorkspace workspace;
  return solve_transient(circuit, options, workspace);
}

TransientResult solve_transient(const Circuit &circuit,
                                const TransientOptions &options,
                                TransientWorkspace &workspace) {
  TransientResult output;
  const auto &nonlinear = options.nonlinear;
  if (!std::isfinite(options.time_step_s) || options.time_step_s <= 0.0 ||
      !std::isfinite(options.minimum_time_step_s) ||
      options.minimum_time_step_s <= 0.0 ||
      options.minimum_time_step_s > options.time_step_s ||
      !std::isfinite(options.stop_time_s) || options.stop_time_s <= 0.0 ||
      options.max_steps == 0 || nonlinear.max_newton_iterations == 0 ||
      nonlinear.max_backtracks == 0 ||
      !std::isfinite(nonlinear.absolute_tolerance) ||
      nonlinear.absolute_tolerance <= 0.0 ||
      !std::isfinite(nonlinear.relative_tolerance) ||
      nonlinear.relative_tolerance < 0.0 ||
      !std::isfinite(options.lte_absolute_tolerance) ||
      options.lte_absolute_tolerance <= 0.0 ||
      !std::isfinite(options.lte_relative_tolerance) ||
      options.lte_relative_tolerance < 0.0 ||
      options.max_rejected_steps == 0 ||
      (options.integration_method !=
           TransientIntegrationMethod::backward_euler &&
       options.integration_method !=
           TransientIntegrationMethod::hybrid_trapezoidal &&
       options.integration_method != TransientIntegrationMethod::bdf2)) {
    output.message_ = "invalid transient solver options";
    return output;
  }
  if (options.integration_method == TransientIntegrationMethod::hybrid_trapezoidal && std::any_of(circuit.elements_.begin(), circuit.elements_.end(),
                  [](const Circuit::Element &element) {
                     return element.type == Circuit::ElementType::mosfet_level1 ||
                            element.type == Circuit::ElementType::bjt_ebers_moll;
                   })) {
    output.message_ =
        "Compact transistor charge integration requires backward Euler or BDF2";
    return output;
  }
  const bool has_osdi_device = std::any_of(
      circuit.elements_.begin(), circuit.elements_.end(),
      [](const Circuit::Element &element) {
        return element.type == Circuit::ElementType::osdi_device;
      });
  if (has_osdi_device &&
      (options.integration_method !=
           TransientIntegrationMethod::backward_euler ||
       options.adaptive_time_step)) {
    output.message_ =
        "OSDI transient callbacks currently require fixed-step backward Euler";
    return output;
  }
  const bool has_dynamic_diode = std::any_of(
      circuit.elements_.begin(), circuit.elements_.end(),
      [](const Circuit::Element &element) {
        return element.type == Circuit::ElementType::dynamic_diode;
      });
  const bool has_be_bdf2_only_device =
      has_dynamic_diode ||
      std::any_of(circuit.elements_.begin(), circuit.elements_.end(),
                  [](const Circuit::Element &element) {
                    return element.type ==
                               Circuit::ElementType::electrothermal_resistor ||
                            element.type ==
                                Circuit::ElementType::saturating_inductor ||
                            element.type ==
                                Circuit::ElementType::wbg_fet_electrothermal;
                  });
  if (has_be_bdf2_only_device &&
      options.integration_method ==
          TransientIntegrationMethod::hybrid_trapezoidal) {
    output.message_ =
        "dynamic diode reverse recovery and electrothermal/WBG/saturating-magnetic devices "
        "currently require backward Euler or BDF2";
    return output;
  }
  if (options.adaptive_time_step &&
      options.integration_method == TransientIntegrationMethod::backward_euler) {
    output.message_ =
        "adaptive transient requires the embedded BDF2 or trapezoidal/BE pair";
    return output;
  }
  const double requested_steps =
      std::ceil(options.stop_time_s / options.time_step_s);
  if (!std::isfinite(requested_steps) ||
      requested_steps > static_cast<double>(options.max_steps)) {
    output.message_ = "transient step count exceeds the configured bound";
    return output;
  }
  const std::size_t node_unknowns = circuit.node_names_.size() - 1;
  std::size_t branch_count = 0;
  std::size_t dynamic_state_count = 0;
  for (const auto &element : circuit.elements_) {
    if (element.type == Circuit::ElementType::voltage_source ||
        element.type == Circuit::ElementType::inductor ||
        element.type == Circuit::ElementType::saturating_inductor) {
      ++branch_count;
    } else if (element.type == Circuit::ElementType::dynamic_diode) {
      ++dynamic_state_count;
    }
  }
  const std::size_t order =
      node_unknowns + branch_count + dynamic_state_count;
  output.diagnostics_.matrix_order = order;
  const bool has_nonlinear_element = std::any_of(
      circuit.elements_.begin(), circuit.elements_.end(),
      [](const Circuit::Element &element) {
        return element.behavioral || element.type == Circuit::ElementType::diode ||
               element.type == Circuit::ElementType::dynamic_diode ||
               element.type == Circuit::ElementType::electrothermal_resistor ||
               element.type == Circuit::ElementType::saturating_inductor ||
               element.type == Circuit::ElementType::mosfet_level1 ||
               element.type == Circuit::ElementType::bjt_ebers_moll ||
               element.type == Circuit::ElementType::wbg_fet_electrothermal ||
               element.type == Circuit::ElementType::osdi_device ||
               element.type == Circuit::ElementType::voltage_controlled_switch;
      });
  const bool use_sparse_transient = options.sparse_linear_threshold > 0 &&
                                    order >= options.sparse_linear_threshold;
  const bool use_sparse_nonlinear =
      has_nonlinear_element && use_sparse_transient;
  std::vector<std::uint64_t> structural_signature;
  structural_signature.reserve(2 + circuit.elements_.size() * 10);
  structural_signature.push_back(circuit.node_names_.size());
  structural_signature.push_back(circuit.elements_.size());
  const auto append_double = [&](double value) {
    structural_signature.push_back(std::bit_cast<std::uint64_t>(value));
  };
  for (const auto &element : circuit.elements_) {
    structural_signature.push_back(static_cast<std::uint64_t>(element.type));
    structural_signature.push_back(element.positive_node);
    structural_signature.push_back(element.negative_node);
    structural_signature.push_back(element.control_positive_node);
    structural_signature.push_back(element.control_negative_node);
    structural_signature.push_back(element.thermal_node);
    structural_signature.push_back(element.dependent);append_double(element.dependent_gain);
    structural_signature.push_back(element.controlling_source.size());for(unsigned char c:element.controlling_source)structural_signature.push_back(c);
    structural_signature.push_back(element.behavioral?1:0);
    if(element.behavioral) {
      structural_signature.push_back(element.behavioral_controls.size());
      structural_signature.push_back(element.behavioral->serialized.size());for(unsigned char c:element.behavioral->serialized)structural_signature.push_back(c);
      for(const auto& control:element.behavioral_controls) {
        structural_signature.push_back(control.positive);structural_signature.push_back(control.negative);
        structural_signature.push_back(control.branch.size());for(unsigned char c:control.branch)structural_signature.push_back(c);
      }
    }
    for(double charge_parameter:element.compact_charge) append_double(charge_parameter);
    if (element.type == Circuit::ElementType::resistor ||
        element.type == Circuit::ElementType::capacitor ||
        element.type == Circuit::ElementType::inductor) {
      append_double(element.value);
    } else if (element.type == Circuit::ElementType::diode) {
      append_double(element.diode.saturation_current_a);
      append_double(element.diode.emission_coefficient);
      append_double(element.diode.temperature_k);
    } else if (element.type == Circuit::ElementType::dynamic_diode) {
      append_double(element.dynamic_diode.junction.saturation_current_a);
      append_double(element.dynamic_diode.junction.emission_coefficient);
      append_double(element.dynamic_diode.junction.temperature_k);
      append_double(element.dynamic_diode.transit_time_s);
      append_double(element.dynamic_diode.junction_capacitance_f);
      append_double(element.dynamic_diode.initial_stored_charge_c);
    } else if (element.type ==
               Circuit::ElementType::electrothermal_resistor) {
      const auto &model = element.electrothermal_resistor;
      append_double(model.resistance_ohm);
      append_double(model.temperature_coefficient_per_k);
      append_double(model.ambient_temperature_k);
      append_double(model.thermal_resistance_k_per_w);
      append_double(model.thermal_capacitance_j_per_k);
      append_double(model.minimum_temperature_k);
      append_double(model.maximum_temperature_k);
    } else if (element.type ==
               Circuit::ElementType::saturating_inductor) {
      const auto &model = element.saturating_inductor;
      append_double(model.unsaturated_inductance_h);
      append_double(model.saturated_inductance_h);
      append_double(model.saturation_current_a);
      append_double(model.initial_current_a);
    } else if (element.type ==
               Circuit::ElementType::voltage_controlled_switch) {
      append_double(element.switch_model.on_resistance_ohm);
      append_double(element.switch_model.off_resistance_ohm);
      append_double(element.switch_model.threshold_voltage_v);
      append_double(element.switch_model.transition_voltage_v);
    } else if (element.type ==
               Circuit::ElementType::wbg_fet_electrothermal) {
      const auto &model = element.wbg_fet_electrothermal;
      structural_signature.push_back(
          static_cast<std::uint64_t>(model.technology));
      append_double(model.threshold_voltage_v);
      append_double(model.transconductance_a_per_v2);
      append_double(model.channel_length_modulation_per_v);
      append_double(model.mobility_temperature_exponent);
      append_double(model.threshold_temperature_coefficient_v_per_k);
      append_double(model.off_conductance_s);
      append_double(model.reverse_conduction_threshold_v);
      append_double(model.reverse_conductance_s);
      append_double(model.body_diode_saturation_current_a);
      append_double(model.body_diode_emission_coefficient);
      append_double(model.breakdown_voltage_v);
      append_double(model.breakdown_temperature_coefficient_v_per_k);
      append_double(model.avalanche_current_scale_a);
      append_double(model.avalanche_slope_v);
      append_double(model.gate_leakage_conductance_s);
      append_double(model.gate_source_capacitance_f);
      append_double(model.gate_drain_capacitance_f);
      append_double(model.drain_source_capacitance_f);
      append_double(model.ambient_temperature_k);
      append_double(model.thermal_resistance_k_per_w);
      append_double(model.thermal_capacitance_j_per_k);
      append_double(model.minimum_temperature_k);
      append_double(model.maximum_temperature_k);
      append_double(model.maximum_absolute_voltage_v);
      append_double(model.maximum_absolute_current_a);
    } else if (element.type == Circuit::ElementType::mosfet_level1 || element.type == Circuit::ElementType::bjt_ebers_moll) {
      const auto& m=element.mosfet_level1;const auto& b=element.bjt_ebers_moll;
      for(double x:{m.threshold_voltage_v,m.transconductance_a_per_v2,m.channel_length_modulation_per_v,m.body_effect_sqrt_v,m.surface_potential_v,m.width_over_length,m.off_conductance_s,b.saturation_current_a,b.forward_alpha,b.reverse_alpha,b.emission_coefficient,b.temperature_k}) append_double(x);
    } else if (element.type == Circuit::ElementType::osdi_device) {
      structural_signature.push_back(element.osdi_device->abi_minor());
      structural_signature.push_back(element.osdi_device->node_count());
      structural_signature.push_back(
          static_cast<std::uint64_t>(
              std::hash<std::string_view>{}(element.osdi_device->module_name())));
      for (const auto node : element.osdi_nodes) {
        structural_signature.push_back(node);
      }
    }
  }
  const auto &saved_history = workspace.impl_->integration_history;
  const bool has_persistent_history =
      !options.initialize_from_operating_point && saved_history.valid &&
      saved_history.structural_signature == structural_signature &&
      saved_history.capacitor_currents.size() == circuit.elements_.size() &&
      saved_history.inductor_voltages.size() == circuit.elements_.size() &&
      saved_history.capacitor_previous_voltages.size() ==
          circuit.elements_.size() &&
      saved_history.inductor_previous_currents.size() ==
          circuit.elements_.size() &&
      saved_history.dynamic_diode_stored_currents.size() ==
          circuit.elements_.size() &&
      saved_history.dynamic_diode_previous_stored_currents.size() ==
          circuit.elements_.size() &&
      saved_history.dynamic_diode_voltages.size() ==
          circuit.elements_.size() &&
      saved_history.dynamic_diode_previous_voltages.size() ==
          circuit.elements_.size() &&
      saved_history.osdi_device_states.size() == circuit.elements_.size() &&
      saved_history.osdi_reactive_residuals.size() ==
          circuit.elements_.size() &&
      saved_history.last_solution.size() == order &&
      saved_history.previous_solution.size() == order;
  std::vector<std::size_t> branch_index(circuit.elements_.size(), order);
  std::vector<std::size_t> dynamic_state_index(circuit.elements_.size(), order);
  std::vector<double> base_matrix(use_sparse_transient ? 0 : order * order,
                                  0.0);
  std::vector<SparseTriplet> base_sparse_triplets;
  if (use_sparse_transient) {
    base_sparse_triplets.reserve(circuit.elements_.size() * 12 +
                                 branch_count * 4 + dynamic_state_count * 4);
  }
  std::vector<double> base_rhs(order, 0.0);
  std::size_t branch_number = 0;
  std::size_t dynamic_state_number = 0;
  const auto stamp_base = [&](NodeId row, NodeId column, double value) {
    if (use_sparse_transient) {
      stamp_sparse(base_sparse_triplets, row, column, value);
    } else {
      stamp(base_matrix, order, row, column, value);
    }
  };
  const auto stamp_base_index = [&](std::size_t row, std::size_t column,
                                    double value) {
    if (use_sparse_transient) {
      stamp_sparse_index(base_sparse_triplets, row, column, value);
    } else {
      base_matrix[at(row, column, order)] += value;
    }
  };
  for (std::size_t element_index = 0;
       element_index < circuit.elements_.size(); ++element_index) {
    const auto &element = circuit.elements_[element_index];
    if (element.type == Circuit::ElementType::resistor) {
      const double conductance = 1.0 / element.value;
      stamp_base(element.positive_node, element.positive_node, conductance);
      stamp_base(element.negative_node, element.negative_node, conductance);
      stamp_base(element.positive_node, element.negative_node, -conductance);
      stamp_base(element.negative_node, element.positive_node, -conductance);
    } else if (element.type == Circuit::ElementType::current_source) {
      // Time-dependent sources are stamped into the RHS at each accepted step.
    } else if (element.type == Circuit::ElementType::voltage_source ||
               element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor) {
      const std::size_t branch = node_unknowns + branch_number++;
      branch_index[element_index] = branch;
      if (element.positive_node != ground_node) {
        stamp_base_index(element.positive_node - 1, branch, 1.0);
        stamp_base_index(branch, element.positive_node - 1, 1.0);
      }
      if (element.negative_node != ground_node) {
        stamp_base_index(element.negative_node - 1, branch, -1.0);
        stamp_base_index(branch, element.negative_node - 1, -1.0);
      }
      // Voltage-source values are stamped into the RHS at each accepted step.
    } else if (element.type == Circuit::ElementType::dynamic_diode) {
      dynamic_state_index[element_index] =
          node_unknowns + branch_count + dynamic_state_number++;
    } else if (element.type == Circuit::ElementType::mosfet_level1 || element.type == Circuit::ElementType::bjt_ebers_moll) {
      const NodeId terminals[]{element.positive_node,element.control_positive_node,element.negative_node,element.control_negative_node};
      for(auto row:terminals) for(auto column:terminals) stamp_base(row,column,0.0);
    } else if (element.type == Circuit::ElementType::osdi_device) {
      for (const auto &[local_row, local_column] :
           element.osdi_device->jacobian_pattern()) {
        stamp_base(element.osdi_nodes[local_row],
                   element.osdi_nodes[local_column], 0.0);
      }
    }
  }

  for (std::size_t i=0; i<circuit.elements_.size(); ++i) {
    const auto& e = circuit.elements_[i];
    if(e.behavioral)for(const auto& signal:circuit.behavioral_columns(e))for(const auto& [column,gain]:signal) {
      if(e.type==Circuit::ElementType::voltage_source)stamp_base_index(branch_index[i],column,0.);
      else {
        if(e.positive_node!=ground_node)stamp_base_index(e.positive_node-1,column,0.);
        if(e.negative_node!=ground_node)stamp_base_index(e.negative_node-1,column,0.);
      }
    }
    if (!e.dependent) continue;
    for (const auto& [column,gain] : circuit.control_columns(e)) {
      if (e.type == Circuit::ElementType::voltage_source) stamp_base_index(branch_index[i],column,-gain);
      else {
        if (e.positive_node != ground_node) stamp_base_index(e.positive_node-1,column,gain);
        if (e.negative_node != ground_node) stamp_base_index(e.negative_node-1,column,-gain);
      }
    }
  }
  std::vector<double> state(order, 0.0);
  std::vector<double> capacitor_voltage(circuit.elements_.size(), 0.0);
  std::vector<double> capacitor_current(circuit.elements_.size(), 0.0);
  std::vector<double> capacitor_previous_voltage(circuit.elements_.size(), 0.0);
  std::vector<double> inductor_current(circuit.elements_.size(), 0.0);
  std::vector<double> inductor_previous_current(circuit.elements_.size(), 0.0);
  std::vector<double> inductor_voltage(circuit.elements_.size(), 0.0);
  std::vector<double> dynamic_diode_stored_current(circuit.elements_.size(),
                                                   0.0);
  std::vector<double> dynamic_diode_previous_stored_current(
      circuit.elements_.size(), 0.0);
  std::vector<double> dynamic_diode_voltage(circuit.elements_.size(), 0.0);
  std::vector<double> dynamic_diode_previous_voltage(circuit.elements_.size(),
                                                      0.0);
  std::vector<std::vector<double>> osdi_device_states(circuit.elements_.size());
  std::vector<std::vector<double>> osdi_reactive_residuals(
      circuit.elements_.size());
  double previous_step_s = 0.0;
  std::size_t history_depth = 1;
  std::vector<double> previous_solution(order, 0.0);
  std::size_t solution_history_depth = 1;
  if (has_persistent_history) {
    capacitor_current = saved_history.capacitor_currents;
    inductor_voltage = saved_history.inductor_voltages;
    capacitor_previous_voltage = saved_history.capacitor_previous_voltages;
    inductor_previous_current = saved_history.inductor_previous_currents;
    dynamic_diode_stored_current =
        saved_history.dynamic_diode_stored_currents;
    dynamic_diode_previous_stored_current =
        saved_history.dynamic_diode_previous_stored_currents;
    dynamic_diode_voltage = saved_history.dynamic_diode_voltages;
    dynamic_diode_previous_voltage =
        saved_history.dynamic_diode_previous_voltages;
    osdi_device_states = saved_history.osdi_device_states;
    osdi_reactive_residuals = saved_history.osdi_reactive_residuals;
    previous_step_s = saved_history.previous_step_s;
    history_depth = saved_history.history_depth;
    previous_solution = saved_history.previous_solution;
    solution_history_depth = saved_history.solution_history_depth;
  }
  for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
    const auto &element = circuit.elements_[index];
    if (element.type == Circuit::ElementType::capacitor) {
      capacitor_voltage[index] = element.initial_condition;
    } else if (element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor) {
      inductor_current[index] = element.initial_condition;
      state[branch_index[index]] = element.initial_condition;
    } else if (element.type == Circuit::ElementType::dynamic_diode) {
      const double stored_current =
          element.dynamic_diode.initial_stored_charge_c /
          element.dynamic_diode.transit_time_s;
      dynamic_diode_stored_current[index] = stored_current;
      dynamic_diode_previous_stored_current[index] = stored_current;
      state[dynamic_state_index[index]] = stored_current;
    }
  }
  if (has_persistent_history) {
    state = saved_history.last_solution;
  }

  if (options.initialize_from_operating_point) {
    const auto initial = solve_operating_point(circuit, nonlinear);
    if (!initial.converged()) {
      output.status_ = initial.status();
      output.message_ = "DC initialization failed: " + initial.message();
      return output;
    }
    for (std::size_t node = 1; node < circuit.node_names_.size(); ++node) {
      state[node - 1] = initial.node_voltage(circuit.node_names_[node]);
    }
    for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
      const auto &element = circuit.elements_[index];
      const double positive = element.positive_node == ground_node
                                  ? 0.0
                                  : state[element.positive_node - 1];
      const double negative = element.negative_node == ground_node
                                  ? 0.0
                                  : state[element.negative_node - 1];
      if (element.type == Circuit::ElementType::capacitor) {
        capacitor_voltage[index] = positive - negative;
      } else if (element.type == Circuit::ElementType::inductor ||
                 element.type == Circuit::ElementType::saturating_inductor) {
        inductor_current[index] = initial.element_current(element.id);
        state[branch_index[index]] = inductor_current[index];
      } else if (element.type == Circuit::ElementType::voltage_source) {
        state[branch_index[index]] = initial.element_current(element.id);
      } else if (element.type == Circuit::ElementType::dynamic_diode) {
        const double current = initial.element_current(element.id);
        dynamic_diode_stored_current[index] = current;
        dynamic_diode_previous_stored_current[index] = current;
        dynamic_diode_voltage[index] = positive - negative;
        dynamic_diode_previous_voltage[index] = positive - negative;
        state[dynamic_state_index[index]] = current;
      }
    }
    output.points_.push_back(
        TransientPoint{0.0, initial.node_voltages(), initial.elements()});
  }
  if (!has_persistent_history) {
    for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
      const auto &element = circuit.elements_[index];
      if (element.type != Circuit::ElementType::osdi_device) {
        continue;
      }
      std::vector<double> local_voltages(element.osdi_nodes.size(), 0.0);
      for (std::size_t local = 0; local < element.osdi_nodes.size(); ++local) {
        const NodeId node = element.osdi_nodes[local];
        local_voltages[local] =
            node == ground_node ? 0.0 : state[node - 1];
      }
      auto osdi_state =
          element.osdi_device->initial_transient_state(local_voltages, 0.0);
      osdi_device_states[index] = std::move(osdi_state.device_state);
      osdi_reactive_residuals[index] =
          std::move(osdi_state.reactive_residual);
    }
  }

  double time = 0.0;
  double proposed_step_s = options.time_step_s;
  auto source_value = [](const Circuit::Element &element, double at_time) {
    if (element.waveform_type == Circuit::WaveformType::pulse) {
      return pulse_value(element.pulse, at_time);
    }
    if (element.waveform_type == Circuit::WaveformType::pwl) {
      return pwl_value(element.pwl, at_time);
    }
    return element.value;
  };
  auto next_source_breakpoint = [&](double after) {
    double next = std::numeric_limits<double>::infinity();
    const double strictly_after = std::nextafter(after +
        64.0 * std::numeric_limits<double>::epsilon() * std::abs(after),
        std::numeric_limits<double>::infinity());
    for (const auto &element : circuit.elements_) {
      if (element.waveform_type == Circuit::WaveformType::pwl) {
        const auto found = std::lower_bound(
            element.pwl.begin(), element.pwl.end(), strictly_after,
            [](const PwlPoint &point, double value) {
              return point.time_s < value;
            });
        if (found != element.pwl.end()) {
          next = std::min(next, found->time_s);
        }
      } else if (element.waveform_type == Circuit::WaveformType::pulse) {
        const auto &pulse = element.pulse;
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
          if (std::isfinite(candidate)) {
            next = std::min(next, candidate);
          }
        }
      }
    }
    return next;
  };
  constexpr std::size_t maximum_factorization_cache_bytes =
      64u * 1024u * 1024u;
  const std::size_t factorization_entry_bytes =
      std::max<std::size_t>(1, 2 * order * order * sizeof(double) +
                                  order * sizeof(std::size_t));
  const std::size_t maximum_factorization_cache_entries =
      std::min<std::size_t>(16, maximum_factorization_cache_bytes /
                                    factorization_entry_bytes);
  constexpr std::size_t maximum_jacobian_cache_bytes = 64u * 1024u * 1024u;
  const std::size_t jacobian_entry_bytes =
      std::max<std::size_t>(1, 2 * order * order * sizeof(double) +
                                  order * sizeof(std::size_t));
  const std::size_t maximum_jacobian_cache_entries =
      std::min<std::size_t>(16, maximum_jacobian_cache_bytes /
                                    jacobian_entry_bytes);
  auto &factorization_cache = workspace.impl_->factorization_cache;
  auto &jacobian_cache = workspace.impl_->jacobian_cache;
  auto update_cache_diagnostic = [&] {
    output.diagnostics_.factorization_cache_entries =
        factorization_cache.size() + jacobian_cache.size();
  };
  update_cache_diagnostic();
  while (time < options.stop_time_s) {
    if (output.diagnostics_.completed_steps >= options.max_steps) {
      output.status_ = SolveStatus::numerical_failure;
      output.message_ =
          "transient step count exceeds the configured bound after source "
          "breakpoint alignment";
      output.diagnostics_.failed_time_s = time;
      return output;
    }
    double regular_target =
        std::min(options.stop_time_s, time + proposed_step_s);
    if (options.stop_time_s-regular_target <= 64.0*std::numeric_limits<double>::epsilon()*options.stop_time_s)
      regular_target=options.stop_time_s;
    const double breakpoint = next_source_breakpoint(time);
    const bool use_breakpoint = breakpoint < regular_target;
    const double target_time = use_breakpoint ? breakpoint : regular_target;
    const double breakpoint_scale =
        std::max({std::abs(breakpoint), std::abs(target_time),
                  std::numeric_limits<double>::min()});
    const bool lands_on_breakpoint =
        std::isfinite(breakpoint) &&
        std::abs(breakpoint - target_time) <=
            32.0 * std::numeric_limits<double>::epsilon() * breakpoint_scale;
    const bool trapezoidal_step =
        options.integration_method ==
            TransientIntegrationMethod::hybrid_trapezoidal &&
        (output.diagnostics_.completed_steps > 0 || has_persistent_history) &&
        !lands_on_breakpoint;
    const bool bdf2_step =
        options.integration_method == TransientIntegrationMethod::bdf2 &&
        history_depth >= 2 && previous_step_s > 0.0 &&
        std::isfinite(previous_step_s) && !lands_on_breakpoint;
    if (use_breakpoint) {
      ++output.diagnostics_.source_breakpoint_steps;
    }
    const double h = target_time - time;
    if (!(h > 0.0) || !std::isfinite(h)) {
      output.status_ = SolveStatus::numerical_failure;
      output.message_ = "transient time failed to advance";
      output.diagnostics_.failed_time_s = time;
      return output;
    }
    std::vector<double> matrix = base_matrix;
    std::vector<SparseTriplet> sparse_triplets;
    if (use_sparse_transient) {
      sparse_triplets = base_sparse_triplets;
      sparse_triplets.reserve(base_sparse_triplets.size() +
                              circuit.elements_.size() * 4);
    }
    std::vector<double> rhs = base_rhs;
    const std::vector<double> state_before = state;
    const double step_ratio = bdf2_step ? h / previous_step_s : 0.0;
    const double bdf_a0 =
        bdf2_step ? (1.0 + 2.0 * step_ratio) / (1.0 + step_ratio) : 1.0;
    const double bdf_a1 = bdf2_step ? -(1.0 + step_ratio) : -1.0;
    const double bdf_a2 = bdf2_step
                              ? step_ratio * step_ratio / (1.0 + step_ratio)
                              : 0.0;
    const auto stamp_step = [&](NodeId row, NodeId column, double value) {
      if (use_sparse_transient) {
        stamp_sparse(sparse_triplets, row, column, value);
      } else {
        stamp(matrix, order, row, column, value);
      }
    };
    const auto stamp_step_index = [&](std::size_t row, std::size_t column,
                                      double value) {
      if (use_sparse_transient) {
        stamp_sparse_index(sparse_triplets, row, column, value);
      } else {
        matrix[at(row, column, order)] += value;
      }
    };
    for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
      const auto &element = circuit.elements_[index];
      if (element.type == Circuit::ElementType::current_source) {
        const double value = source_value(element, target_time);
        stamp_rhs(rhs, element.positive_node, -value);
        stamp_rhs(rhs, element.negative_node, value);
      } else if (element.type == Circuit::ElementType::voltage_source) {
        rhs[branch_index[index]] += source_value(element, target_time);
      } else if (element.type == Circuit::ElementType::capacitor) {
        const double conductance = (trapezoidal_step ? 2.0 : bdf_a0) *
                                   element.value / h;
        stamp_step(element.positive_node, element.positive_node, conductance);
        stamp_step(element.negative_node, element.negative_node, conductance);
        stamp_step(element.positive_node, element.negative_node, -conductance);
        stamp_step(element.negative_node, element.positive_node, -conductance);
        const double history_current =
            bdf2_step
                ? -element.value / h *
                      (bdf_a1 * capacitor_voltage[index] +
                       bdf_a2 * capacitor_previous_voltage[index])
                : conductance * capacitor_voltage[index] +
                      (trapezoidal_step ? capacitor_current[index] : 0.0);
        stamp_rhs(rhs, element.positive_node, history_current);
        stamp_rhs(rhs, element.negative_node, -history_current);
      } else if (element.type == Circuit::ElementType::inductor) {
        const double coefficient = (trapezoidal_step ? 2.0 : bdf_a0) *
                                   element.value / h;
        stamp_step_index(branch_index[index], branch_index[index],
                         -coefficient);
        rhs[branch_index[index]] +=
            bdf2_step
                ? element.value / h *
                      (bdf_a1 * inductor_current[index] +
                       bdf_a2 * inductor_previous_current[index])
                : -coefficient * inductor_current[index] -
                      (trapezoidal_step ? inductor_voltage[index] : 0.0);
      }
    }

    SparseMatrix sparse_matrix;
    if (use_sparse_transient) {
      sparse_matrix.resize(static_cast<int>(order), static_cast<int>(order));
      sparse_matrix.setFromTriplets(sparse_triplets.begin(), sparse_triplets.end());
      sparse_matrix.makeCompressed();
      ++output.diagnostics_.sparse_assemblies;
    }

    auto evaluate = [&](const std::vector<double> &system_matrix,
                        const std::vector<SparseTriplet> *system_triplets,
                        const std::vector<double> &system_rhs,
                        const std::vector<double> &candidate,
                        double integration_a0, double integration_a1,
                        double integration_a2) {
      NonlinearEvaluation evaluation;
      evaluation.residual.assign(order, 0.0);
      std::vector<SparseTriplet> jacobian_triplets;
      if (system_triplets != nullptr) {
        jacobian_triplets = *system_triplets;
        jacobian_triplets.reserve(system_triplets->size() +
                                  circuit.elements_.size() * 16);
        for (std::size_t row = 0; row < order; ++row) {
          evaluation.residual[row] = -system_rhs[row];
        }
        for (const auto &entry : *system_triplets) {
          evaluation.residual[static_cast<std::size_t>(entry.row())] +=
              entry.value() *
              candidate[static_cast<std::size_t>(entry.col())];
        }
      } else {
        evaluation.dense_jacobian = system_matrix;
        for (std::size_t row = 0; row < order; ++row) {
          evaluation.residual[row] = -system_rhs[row];
          for (std::size_t column = 0; column < order; ++column) {
            evaluation.residual[row] +=
                system_matrix[at(row, column, order)] * candidate[column];
          }
        }
      }
      auto &residual = evaluation.residual;
      const auto stamp_jacobian = [&](NodeId row, NodeId column,
                                      double value) {
        if (system_triplets != nullptr) {
          stamp_sparse(jacobian_triplets, row, column, value);
        } else {
          stamp(evaluation.dense_jacobian, order, row, column, value);
        }
      };
      const auto stamp_jacobian_index = [&](std::size_t row,
                                            std::size_t column,
                                            double value) {
        if (system_triplets != nullptr) {
          stamp_sparse_index(jacobian_triplets, row, column, value);
        } else {
          evaluation.dense_jacobian[at(row, column, order)] += value;
        }
      };
      auto voltage = [&](NodeId node) {
        return node == ground_node ? 0.0 : candidate[node - 1];
      };
      for (std::size_t element_index = 0;
           element_index < circuit.elements_.size(); ++element_index) {
        const auto &element = circuit.elements_[element_index];
        if(element.behavioral) {
          const auto [value,jacobian]=circuit.behavioral_point(element,candidate,target_time);
          if(element.type==Circuit::ElementType::voltage_source) {
            residual[branch_index[element_index]]-=value;
            for(const auto& [column,derivative]:jacobian)stamp_jacobian_index(branch_index[element_index],column,-derivative);
          } else {
            stamp_rhs(residual,element.positive_node,value);stamp_rhs(residual,element.negative_node,-value);
            for(const auto& [column,derivative]:jacobian) {
              if(element.positive_node!=ground_node)stamp_jacobian_index(element.positive_node-1,column,derivative);
              if(element.negative_node!=ground_node)stamp_jacobian_index(element.negative_node-1,column,-derivative);
            }
          }
        } else if (element.type == Circuit::ElementType::diode) {
          const auto point =
              diode(element.diode.saturation_current_a,
                    element.diode.emission_coefficient,
                    element.diode.temperature_k,
                    voltage(element.positive_node) - voltage(element.negative_node));
          stamp_rhs(residual, element.positive_node, point.current);
          stamp_rhs(residual, element.negative_node, -point.current);
          stamp_jacobian(element.positive_node, element.positive_node,
                point.conductance);
          stamp_jacobian(element.negative_node, element.negative_node,
                point.conductance);
          stamp_jacobian(element.positive_node, element.negative_node,
                -point.conductance);
          stamp_jacobian(element.negative_node, element.positive_node,
                -point.conductance);
        } else if (element.type ==
                   Circuit::ElementType::voltage_controlled_switch) {
          const double across = voltage(element.positive_node) -
                                voltage(element.negative_node);
          const double control = voltage(element.control_positive_node) -
                                 voltage(element.control_negative_node);
          const auto point =
              voltage_controlled_switch(element.switch_model, control);
          const double current = point.conductance * across;
          const double transconductance = point.derivative * across;
          stamp_rhs(residual, element.positive_node, current);
          stamp_rhs(residual, element.negative_node, -current);
          stamp_jacobian(element.positive_node, element.positive_node,
                point.conductance);
          stamp_jacobian(element.negative_node, element.negative_node,
                point.conductance);
          stamp_jacobian(element.positive_node, element.negative_node,
                -point.conductance);
          stamp_jacobian(element.negative_node, element.positive_node,
                -point.conductance);
          stamp_jacobian(element.positive_node,
                element.control_positive_node, transconductance);
          stamp_jacobian(element.positive_node,
                element.control_negative_node, -transconductance);
          stamp_jacobian(element.negative_node,
                element.control_positive_node, -transconductance);
          stamp_jacobian(element.negative_node,
                element.control_negative_node, transconductance);
        } else if (element.type == Circuit::ElementType::dynamic_diode) {
          const auto &model = element.dynamic_diode;
          const double across = voltage(element.positive_node) -
                                voltage(element.negative_node);
          const auto point = diode(
              model.junction.saturation_current_a,
              model.junction.emission_coefficient,
              model.junction.temperature_k, across);
          const std::size_t state_index =
              dynamic_state_index[element_index];
          const double stored_current = candidate[state_index];
          const double capacitance_conductance =
              model.junction_capacitance_f * integration_a0 / h;
          const double capacitance_current =
              model.junction_capacitance_f / h *
              (integration_a0 * across +
               integration_a1 * dynamic_diode_voltage[element_index] +
               integration_a2 *
                   dynamic_diode_previous_voltage[element_index]);
          const double terminal_current =
              2.0 * point.current - stored_current + capacitance_current;
          stamp_rhs(residual, element.positive_node, terminal_current);
          stamp_rhs(residual, element.negative_node, -terminal_current);
          const double terminal_conductance =
              2.0 * point.conductance + capacitance_conductance;
          stamp_jacobian(element.positive_node,
                element.positive_node, terminal_conductance);
          stamp_jacobian(element.negative_node,
                element.negative_node, terminal_conductance);
          stamp_jacobian(element.positive_node,
                element.negative_node, -terminal_conductance);
          stamp_jacobian(element.negative_node,
                element.positive_node, -terminal_conductance);
          if (element.positive_node != ground_node) {
            stamp_jacobian_index(element.positive_node - 1, state_index, -1.0);
          }
          if (element.negative_node != ground_node) {
            stamp_jacobian_index(element.negative_node - 1, state_index, 1.0);
          }

          residual[state_index] +=
              model.transit_time_s / h *
                  (integration_a0 * stored_current +
                   integration_a1 *
                       dynamic_diode_stored_current[element_index] +
                   integration_a2 *
                       dynamic_diode_previous_stored_current[element_index]) +
              stored_current - point.current;
          if (element.positive_node != ground_node) {
            stamp_jacobian_index(state_index, element.positive_node - 1,
                                 -point.conductance);
          }
          if (element.negative_node != ground_node) {
            stamp_jacobian_index(state_index, element.negative_node - 1,
                                 point.conductance);
          }
          stamp_jacobian_index(
              state_index, state_index,
              model.transit_time_s * integration_a0 / h + 1.0);
        } else if (element.type ==
                   Circuit::ElementType::electrothermal_resistor) {
          const auto &model = element.electrothermal_resistor;
          const double across = voltage(element.positive_node) -
                                voltage(element.negative_node);
          const double temperature_rise = voltage(element.thermal_node);
          const auto point =
              electrothermal_resistor(model, across, temperature_rise);
          stamp_rhs(residual, element.positive_node, point.current);
          stamp_rhs(residual, element.negative_node, -point.current);
          stamp_jacobian(element.positive_node,
                element.positive_node, point.conductance);
          stamp_jacobian(element.positive_node,
                element.negative_node, -point.conductance);
          stamp_jacobian(element.negative_node,
                element.positive_node, -point.conductance);
          stamp_jacobian(element.negative_node,
                element.negative_node, point.conductance);
          stamp_jacobian(element.positive_node,
                element.thermal_node,
                point.current_temperature_derivative);
          stamp_jacobian(element.negative_node,
                element.thermal_node,
                -point.current_temperature_derivative);

          const std::size_t thermal_index = element.thermal_node - 1;
          const double thermal_storage =
              model.thermal_capacitance_j_per_k / h *
              (integration_a0 * temperature_rise +
               integration_a1 * state_before[thermal_index] +
               integration_a2 * previous_solution[thermal_index]);
          residual[thermal_index] +=
              thermal_storage +
              temperature_rise / model.thermal_resistance_k_per_w -
              point.power;
          stamp_jacobian(element.thermal_node,
                element.positive_node, -point.power_voltage_derivative);
          stamp_jacobian(element.thermal_node,
                element.negative_node, point.power_voltage_derivative);
          stamp_jacobian(element.thermal_node,
                element.thermal_node,
                model.thermal_capacitance_j_per_k * integration_a0 / h +
                    1.0 / model.thermal_resistance_k_per_w -
                    point.power_temperature_derivative);
        } else if (element.type == Circuit::ElementType::mosfet_level1 || element.type == Circuit::ElementType::bjt_ebers_moll) {
          const NodeId nodes[]{element.positive_node,element.control_positive_node,element.negative_node,element.control_negative_node};
          const auto now=circuit.compact_point(element,candidate),prior=circuit.compact_point(element,state_before),older=circuit.compact_point(element,previous_solution);
          for(std::size_t row=0;row<4;++row) {
            stamp_rhs(residual,nodes[row],now.current[row]+(integration_a0*now.charge[row]+integration_a1*prior.charge[row]+integration_a2*older.charge[row])/h);
            for(std::size_t col=0;col<4;++col) stamp_jacobian(nodes[row],nodes[col],now.conductance[row][col]+integration_a0/h*now.capacitance[row][col]);
          }
        } else if (element.type ==
                   Circuit::ElementType::wbg_fet_electrothermal) {
          const auto &model = element.wbg_fet_electrothermal;
          const std::array<NodeId, 5> terminals{
              element.positive_node, element.control_positive_node,
              element.negative_node, element.control_negative_node,
              element.thermal_node};
          const auto state_voltage = [](const std::vector<double> &values,
                                        NodeId node) {
            return node == ground_node ? 0.0 : values[node - 1];
          };
          const auto constitutive_point =
              [&](const std::vector<double> &values) {
                return evaluate_wbg_fet_electrothermal(
                    model, state_voltage(values, terminals[0]),
                    state_voltage(values, terminals[1]),
                    state_voltage(values, terminals[2]),
                    state_voltage(values, terminals[3]),
                    state_voltage(values, terminals[4]));
              };
          const auto device_point = constitutive_point(candidate);
          const auto previous_point = constitutive_point(state_before);
          const auto older_point = constitutive_point(previous_solution);

          for (std::size_t row = 0; row < 4; ++row) {
            const double charge_current =
                (integration_a0 * device_point.terminal_charge_c[row] +
                 integration_a1 * previous_point.terminal_charge_c[row] +
                 integration_a2 * older_point.terminal_charge_c[row]) /
                h;
            stamp_rhs(residual, terminals[row],
                      device_point.terminal_current_a[row] + charge_current);
            for (std::size_t column = 0; column < 4; ++column) {
              stamp_jacobian(
                  terminals[row], terminals[column],
                  device_point.current_jacobian[row][column] +
                      integration_a0 / h *
                          device_point.charge_jacobian[row][column]);
            }
            stamp_jacobian(terminals[row], terminals[4],
                           device_point.current_jacobian[row][4]);
          }

          const std::size_t thermal_index = element.thermal_node - 1;
          residual[thermal_index] +=
              model.thermal_capacitance_j_per_k / h *
                  (integration_a0 * candidate[thermal_index] +
                   integration_a1 * state_before[thermal_index] +
                   integration_a2 * previous_solution[thermal_index]) +
              candidate[thermal_index] / model.thermal_resistance_k_per_w -
              device_point.dissipated_power_w;
          for (std::size_t column = 0; column < terminals.size(); ++column) {
            double derivative = -device_point.power_jacobian[column];
            if (column == 4) {
              derivative +=
                  model.thermal_capacitance_j_per_k * integration_a0 / h +
                  1.0 / model.thermal_resistance_k_per_w;
            }
            stamp_jacobian(element.thermal_node, terminals[column], derivative);
          }
        } else if (element.type ==
                   Circuit::ElementType::saturating_inductor) {
          const auto &model = element.saturating_inductor;
          const std::size_t current_index = branch_index[element_index];
          const double current = candidate[current_index];
          residual[current_index] -=
              (integration_a0 * saturating_flux_linkage(model, current) +
               integration_a1 * saturating_flux_linkage(
                                    model, inductor_current[element_index]) +
               integration_a2 * saturating_flux_linkage(
                                    model,
                                    inductor_previous_current[element_index])) /
              h;
          stamp_jacobian_index(
              current_index, current_index,
              -integration_a0 *
                  saturating_differential_inductance(model, current) / h);
        } else if (element.type == Circuit::ElementType::osdi_device) {
          std::vector<double> local_candidate(element.osdi_nodes.size(), 0.0);
          std::vector<double> local_previous(element.osdi_nodes.size(), 0.0);
          for (std::size_t local = 0; local < element.osdi_nodes.size(); ++local) {
            const NodeId node = element.osdi_nodes[local];
            if (node != ground_node) {
              local_candidate[local] = candidate[node - 1];
              local_previous[local] = state_before[node - 1];
            }
          }
          const OsdiTransientState prior{osdi_device_states[element_index],
                                         osdi_reactive_residuals[element_index]};
          const auto osdi =
              element.osdi_device->evaluate_transient_backward_euler(
                  local_candidate, local_previous, target_time, h, prior);
          for (std::size_t local = 0; local < element.osdi_nodes.size(); ++local) {
            stamp_rhs(residual, element.osdi_nodes[local], osdi.residual[local]);
          }
          for (const auto &entry : osdi.jacobian) {
            stamp_jacobian(element.osdi_nodes[entry.row],
                           element.osdi_nodes[entry.column], entry.value);
          }
        }
      }
      if (system_triplets != nullptr) {
        evaluation.sparse_jacobian.resize(static_cast<int>(order),
                                          static_cast<int>(order));
        evaluation.sparse_jacobian.setFromTriplets(jacobian_triplets.begin(),
                                                   jacobian_triplets.end());
        evaluation.sparse_jacobian.makeCompressed();
        ++output.diagnostics_.sparse_assemblies;
      }
      return evaluation;
    };

    double final_residual = 0.0;
    if (!has_nonlinear_element) {
      DenseResult solved;
      if (use_sparse_transient) {
        auto &cache = *workspace.impl_->sparse_factorization;
        const bool pattern_reused = same_sparse_pattern(sparse_matrix, cache);
        if (!pattern_reused) {
          cache.solver.analyzePattern(sparse_matrix);
          cache.rows = sparse_matrix.rows();
          cache.columns = sparse_matrix.cols();
          cache.outer_indices.assign(
              sparse_matrix.outerIndexPtr(),
              sparse_matrix.outerIndexPtr() + sparse_matrix.outerSize() + 1);
          cache.inner_indices.assign(
              sparse_matrix.innerIndexPtr(),
              sparse_matrix.innerIndexPtr() + sparse_matrix.nonZeros());
          cache.values.clear();
          cache.analyzed = true;
          cache.factorized = false;
          ++output.diagnostics_.sparse_symbolic_analyses;
        }
        if (!same_sparse_values(sparse_matrix, cache)) {
          cache.solver.factorize(sparse_matrix);
          ++output.diagnostics_.sparse_numeric_factorizations;
          ++output.diagnostics_.matrix_factorizations;
          if (pattern_reused && cache.factorized) {
            ++output.diagnostics_.partial_numeric_refactorizations;
          }
          if (cache.solver.info() != Eigen::Success) {
            output.status_ = SolveStatus::singular;
            output.message_ = "sparse transient numeric factorization failed";
            output.diagnostics_.failed_time_s = time + h;
            return output;
          }
          cache.values.assign(sparse_matrix.valuePtr(),
                              sparse_matrix.valuePtr() + sparse_matrix.nonZeros());
          cache.factorized = true;
        } else {
          ++output.diagnostics_.factorization_reuses;
        }
        const Eigen::Map<const Eigen::VectorXd> sparse_rhs(
            rhs.data(), static_cast<Eigen::Index>(rhs.size()));
        const Eigen::VectorXd sparse_solution = cache.solver.solve(sparse_rhs);
        if (cache.solver.info() != Eigen::Success ||
            !sparse_solution.allFinite()) {
          output.status_ = SolveStatus::numerical_failure;
          output.message_ = "sparse transient solve failed";
          output.diagnostics_.failed_time_s = time + h;
          return output;
        }
        state.assign(sparse_solution.data(),
                     sparse_solution.data() + sparse_solution.size());
        final_residual =
            (sparse_matrix * sparse_solution - sparse_rhs).lpNorm<Eigen::Infinity>();
      } else {
        const auto cached = std::find_if(
            factorization_cache.begin(), factorization_cache.end(),
            [&](const CachedFactorization &entry) {
              return numerically_same_matrix(entry.matrix, matrix);
            });
        if (cached != factorization_cache.end()) {
          solved = solve_factorized(cached->factorization, rhs);
          ++output.diagnostics_.factorization_reuses;
        } else {
          auto factorization = factor_dense(matrix, order);
          output.diagnostics_.pivot_swaps += factorization.swaps;
          ++output.diagnostics_.matrix_factorizations;
          solved = solve_factorized(factorization, rhs);
          if (factorization.status == SolveStatus::converged &&
              factorization_cache.size() <
                maximum_factorization_cache_entries) {
            factorization_cache.push_back(CachedFactorization{
                matrix, std::move(factorization)});
            update_cache_diagnostic();
          }
        }
        if (solved.status != SolveStatus::converged) {
          output.status_ = solved.status;
          output.message_ = solved.message;
          output.diagnostics_.failed_time_s = time + h;
          return output;
        }
        state = std::move(solved.values);
        final_residual =
            inf_norm(evaluate(matrix, nullptr, rhs, state, bdf_a0, bdf_a1,
                              bdf_a2).residual);
      }
    } else {
      auto current = evaluate(
          matrix, use_sparse_nonlinear ? &sparse_triplets : nullptr, rhs,
          state, bdf_a0, bdf_a1, bdf_a2);
      double current_norm = inf_norm(current.residual);
      const double threshold = nonlinear.absolute_tolerance +
          nonlinear.relative_tolerance * std::max(1.0, inf_norm(rhs));
      bool converged = current_norm <= threshold;
      for (std::size_t iteration = 0;
           !converged && iteration < nonlinear.max_newton_iterations;
           ++iteration) {
        for (double &value : current.residual) {
          value = -value;
        }
        DenseResult direction;
        if (use_sparse_nonlinear) {
          auto &cache = *workspace.impl_->sparse_jacobian_factorization;
          auto &sparse_jacobian = current.sparse_jacobian;
          const bool pattern_reused =
              same_sparse_pattern(sparse_jacobian, cache);
          if (!pattern_reused) {
            cache.solver.analyzePattern(sparse_jacobian);
            cache.rows = sparse_jacobian.rows();
            cache.columns = sparse_jacobian.cols();
            cache.outer_indices.assign(
                sparse_jacobian.outerIndexPtr(),
                sparse_jacobian.outerIndexPtr() +
                    sparse_jacobian.outerSize() + 1);
            cache.inner_indices.assign(
                sparse_jacobian.innerIndexPtr(),
                sparse_jacobian.innerIndexPtr() +
                    sparse_jacobian.nonZeros());
            cache.values.clear();
            cache.analyzed = true;
            cache.factorized = false;
            ++output.diagnostics_.sparse_symbolic_analyses;
          }
          if (!same_sparse_values(sparse_jacobian, cache)) {
            const bool had_factorization = cache.factorized;
            cache.solver.factorize(sparse_jacobian);
            ++output.diagnostics_.sparse_numeric_factorizations;
            ++output.diagnostics_.matrix_factorizations;
            if (pattern_reused && had_factorization) {
              ++output.diagnostics_.partial_numeric_refactorizations;
            }
            if (cache.solver.info() != Eigen::Success) {
              direction.status = SolveStatus::singular;
              direction.message =
                  "sparse nonlinear transient Jacobian factorization failed";
            } else {
              cache.values.assign(
                  sparse_jacobian.valuePtr(),
                  sparse_jacobian.valuePtr() + sparse_jacobian.nonZeros());
              cache.factorized = true;
            }
          } else {
            ++output.diagnostics_.factorization_reuses;
          }
          if (cache.factorized && direction.status != SolveStatus::singular) {
            const Eigen::Map<const Eigen::VectorXd> sparse_rhs(
                current.residual.data(),
                static_cast<Eigen::Index>(current.residual.size()));
            const Eigen::VectorXd sparse_direction =
                cache.solver.solve(sparse_rhs);
            if (cache.solver.info() != Eigen::Success ||
                !sparse_direction.allFinite()) {
              direction.status = SolveStatus::numerical_failure;
              direction.message =
                  "sparse nonlinear transient Jacobian solve failed";
            } else {
              direction.status = SolveStatus::converged;
              direction.values.assign(
                  sparse_direction.data(),
                  sparse_direction.data() + sparse_direction.size());
            }
          }
        } else {
          std::vector<double> jacobian = std::move(current.dense_jacobian);
          const auto cached = std::find_if(
              jacobian_cache.begin(), jacobian_cache.end(),
              [&](const CachedJacobianFactorization &entry) {
                return numerically_same_matrix(entry.jacobian, jacobian);
              });
          if (cached != jacobian_cache.end()) {
            direction = solve_factorized(cached->factorization,
                                         std::move(current.residual));
            ++output.diagnostics_.factorization_reuses;
          } else {
            auto factorization = factor_dense(jacobian, order);
            output.diagnostics_.pivot_swaps += factorization.swaps;
            ++output.diagnostics_.matrix_factorizations;
            direction = solve_factorized(factorization,
                                         std::move(current.residual));
            if (factorization.status == SolveStatus::converged &&
                jacobian_cache.size() < maximum_jacobian_cache_entries) {
              jacobian_cache.push_back(CachedJacobianFactorization{
                  std::move(jacobian), std::move(factorization)});
              update_cache_diagnostic();
            }
          }
        }
        ++output.diagnostics_.total_newton_iterations;
        if (direction.status != SolveStatus::converged) {
          output.status_ = direction.status;
          output.message_ = direction.message;
          output.diagnostics_.failed_time_s = time + h;
          return output;
        }
        double damping = 1.0;
        bool accepted = false;
        std::vector<double> candidate(order, 0.0);
        for (std::size_t backtrack = 0;
             backtrack < nonlinear.max_backtracks; ++backtrack) {
          for (std::size_t index = 0; index < order; ++index) {
            candidate[index] = state[index] + damping * direction.values[index];
          }
          NonlinearEvaluation trial;
          try {
            trial = evaluate(
                matrix, use_sparse_nonlinear ? &sparse_triplets : nullptr,
                rhs, candidate, bdf_a0, bdf_a1, bdf_a2);
          } catch (const std::out_of_range &) {
            damping *= 0.5;
            ++output.diagnostics_.total_damping_steps;
            continue;
          }
          const double trial_norm = inf_norm(trial.residual);
          if (std::isfinite(trial_norm) && trial_norm < current_norm) {
            state = std::move(candidate);
            current = std::move(trial);
            current_norm = trial_norm;
            accepted = true;
            break;
          }
          damping *= 0.5;
          ++output.diagnostics_.total_damping_steps;
        }
        if (!accepted) {
          output.status_ = SolveStatus::nonconverged;
          output.message_ =
              "transient Newton damping failed to reduce the residual";
          output.diagnostics_.failed_time_s = time + h;
          output.diagnostics_.residual_inf_norm = current_norm;
          return output;
        }
        converged = current_norm <= threshold;
      }
      final_residual = current_norm;
      if (!converged) {
        output.status_ = SolveStatus::nonconverged;
        output.message_ = "maximum transient Newton iterations reached";
        output.diagnostics_.failed_time_s = time + h;
        output.diagnostics_.residual_inf_norm = current_norm;
        return output;
      }
    }

    double lte_ratio = 0.0;
    const bool estimate_lte =
        options.adaptive_time_step && (bdf2_step || trapezoidal_step) &&
        !lands_on_breakpoint;
    if (estimate_lte) {
      // Embedded BE companion solve at the same endpoint.  BDF2/trapezoidal
      // and BE share the accepted history and source evaluation, so their
      // scaled difference is a genuine order-2/order-1 local defect rather
      // than a state extrapolation heuristic.
      std::vector<double> embedded_rhs = base_rhs;
      std::vector<double> embedded_matrix = base_matrix;
      std::vector<SparseTriplet> embedded_triplets;
      if (use_sparse_transient) {
        embedded_triplets = base_sparse_triplets;
        embedded_triplets.reserve(base_sparse_triplets.size() +
                                  circuit.elements_.size() * 4);
      }
      const auto embedded_stamp = [&](NodeId row, NodeId column, double value) {
        if (use_sparse_transient) {
          stamp_sparse(embedded_triplets, row, column, value);
        } else {
          stamp(embedded_matrix, order, row, column, value);
        }
      };
      for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
        const auto &element = circuit.elements_[index];
        if (element.type == Circuit::ElementType::current_source) {
          const double value = source_value(element, target_time);
          stamp_rhs(embedded_rhs, element.positive_node, -value);
          stamp_rhs(embedded_rhs, element.negative_node, value);
        } else if (element.type == Circuit::ElementType::voltage_source) {
          embedded_rhs[branch_index[index]] += source_value(element, target_time);
        } else if (element.type == Circuit::ElementType::capacitor) {
          const double conductance = element.value / h;
          embedded_stamp(element.positive_node, element.positive_node, conductance);
          embedded_stamp(element.negative_node, element.negative_node, conductance);
          embedded_stamp(element.positive_node, element.negative_node, -conductance);
          embedded_stamp(element.negative_node, element.positive_node, -conductance);
          const double history_current = conductance * capacitor_voltage[index];
          stamp_rhs(embedded_rhs, element.positive_node, history_current);
          stamp_rhs(embedded_rhs, element.negative_node, -history_current);
        } else if (element.type == Circuit::ElementType::inductor) {
          const double coefficient = element.value / h;
          if (use_sparse_transient) {
            stamp_sparse_index(embedded_triplets, branch_index[index],
                               branch_index[index], -coefficient);
          } else {
            embedded_matrix[at(branch_index[index], branch_index[index], order)] -=
                coefficient;
          }
          embedded_rhs[branch_index[index]] -=
              coefficient * inductor_current[index];
        }
      }
      std::vector<double> embedded_state;
      bool embedded_converged = true;
      if (has_nonlinear_element) {
        // Solve the order-one BE companion with the converged order-two state
        // as its initial guess.  This is a true nonlinear embedded solve: both
        // states satisfy their respective discrete DAEs at the same endpoint.
        embedded_state = state;
        auto current = evaluate(
            embedded_matrix,
            use_sparse_nonlinear ? &embedded_triplets : nullptr,
            embedded_rhs, embedded_state, 1.0, -1.0, 0.0);
        double current_norm = inf_norm(current.residual);
        const double threshold = nonlinear.absolute_tolerance +
            nonlinear.relative_tolerance *
                std::max(1.0, inf_norm(embedded_rhs));
        embedded_converged = current_norm <= threshold;
        for (std::size_t iteration = 0;
             !embedded_converged &&
             iteration < nonlinear.max_newton_iterations;
             ++iteration) {
          for (double &value : current.residual) {
            value = -value;
          }
          DenseResult direction;
          if (use_sparse_nonlinear) {
            Eigen::SparseLU<SparseMatrix, Eigen::COLAMDOrdering<int>>
                embedded_solver;
            embedded_solver.analyzePattern(current.sparse_jacobian);
            embedded_solver.factorize(current.sparse_jacobian);
            ++output.diagnostics_.sparse_symbolic_analyses;
            ++output.diagnostics_.sparse_numeric_factorizations;
            ++output.diagnostics_.matrix_factorizations;
            if (embedded_solver.info() != Eigen::Success) {
              direction.status = SolveStatus::singular;
              direction.message =
                  "embedded sparse nonlinear Jacobian factorization failed";
            } else {
              const Eigen::Map<const Eigen::VectorXd> embedded_rhs_map(
                  current.residual.data(),
                  static_cast<Eigen::Index>(current.residual.size()));
              const Eigen::VectorXd embedded_direction =
                  embedded_solver.solve(embedded_rhs_map);
              if (embedded_solver.info() != Eigen::Success ||
                  !embedded_direction.allFinite()) {
                direction.status = SolveStatus::numerical_failure;
                direction.message =
                    "embedded sparse nonlinear Jacobian solve failed";
              } else {
                direction.status = SolveStatus::converged;
                direction.values.assign(
                    embedded_direction.data(),
                    embedded_direction.data() + embedded_direction.size());
              }
            }
          } else {
            auto factorization =
                factor_dense(std::move(current.dense_jacobian), order);
            output.diagnostics_.pivot_swaps += factorization.swaps;
            ++output.diagnostics_.matrix_factorizations;
            direction =
                solve_factorized(factorization, std::move(current.residual));
          }
          ++output.diagnostics_.total_newton_iterations;
          if (direction.status != SolveStatus::converged) {
            embedded_converged = false;
            break;
          }
          double damping = 1.0;
          bool accepted = false;
          std::vector<double> candidate(order, 0.0);
          for (std::size_t backtrack = 0;
               backtrack < nonlinear.max_backtracks; ++backtrack) {
            for (std::size_t index = 0; index < order; ++index) {
              candidate[index] =
                  embedded_state[index] + damping * direction.values[index];
            }
            NonlinearEvaluation trial;
            try {
              trial = evaluate(
                  embedded_matrix,
                  use_sparse_nonlinear ? &embedded_triplets : nullptr,
                  embedded_rhs, candidate, 1.0, -1.0, 0.0);
            } catch (const std::out_of_range &) {
              damping *= 0.5;
              ++output.diagnostics_.total_damping_steps;
              continue;
            }
            const double trial_norm = inf_norm(trial.residual);
            if (std::isfinite(trial_norm) && trial_norm < current_norm) {
              embedded_state = std::move(candidate);
              current = std::move(trial);
              current_norm = trial_norm;
              accepted = true;
              break;
            }
            damping *= 0.5;
            ++output.diagnostics_.total_damping_steps;
          }
          if (!accepted) {
            embedded_converged = false;
            break;
          }
          embedded_converged = current_norm <= threshold;
        }
      } else if (use_sparse_transient) {
        SparseMatrix embedded_sparse(static_cast<int>(order),
                                     static_cast<int>(order));
        embedded_sparse.setFromTriplets(embedded_triplets.begin(),
                                        embedded_triplets.end());
        embedded_sparse.makeCompressed();
        Eigen::SparseLU<SparseMatrix, Eigen::COLAMDOrdering<int>> embedded_solver;
        embedded_solver.analyzePattern(embedded_sparse);
        embedded_solver.factorize(embedded_sparse);
        if (embedded_solver.info() != Eigen::Success) {
          output.status_ = SolveStatus::singular;
          output.message_ = "embedded LTE factorization failed";
          output.diagnostics_.failed_time_s = time;
          return output;
        }
        const Eigen::Map<const Eigen::VectorXd> embedded_b(
            embedded_rhs.data(), static_cast<Eigen::Index>(embedded_rhs.size()));
        const Eigen::VectorXd embedded_x = embedded_solver.solve(embedded_b);
        if (embedded_solver.info() != Eigen::Success || !embedded_x.allFinite()) {
          output.status_ = SolveStatus::numerical_failure;
          output.message_ = "embedded LTE solve failed";
          output.diagnostics_.failed_time_s = time;
          return output;
        }
        embedded_state.assign(embedded_x.data(),
                              embedded_x.data() + embedded_x.size());
      } else {
        const auto embedded = solve_dense(std::move(embedded_matrix),
                                          std::move(embedded_rhs), order);
        if (embedded.status != SolveStatus::converged) {
          output.status_ = embedded.status;
          output.message_ = "embedded LTE solve failed: " + embedded.message;
          output.diagnostics_.failed_time_s = time;
          return output;
        }
        embedded_state = embedded.values;
      }
      ++output.diagnostics_.embedded_lte_solves;
      if (!embedded_converged) {
        lte_ratio = std::numeric_limits<double>::infinity();
      } else {
        for (std::size_t index = 0; index < order; ++index) {
          const double scale =
              options.lte_absolute_tolerance +
              options.lte_relative_tolerance *
                  std::max(std::abs(state[index]),
                           std::abs(state_before[index]));
          lte_ratio = std::max(
              lte_ratio,
              std::abs(state[index] - embedded_state[index]) / scale);
        }
      }
      output.diagnostics_.last_lte_ratio = lte_ratio;
      if (!std::isfinite(lte_ratio) || lte_ratio > 1.0) {
        state = state_before;
        ++output.diagnostics_.rejected_lte_steps;
        if (output.diagnostics_.rejected_lte_steps >
            options.max_rejected_steps) {
          output.status_ = SolveStatus::nonconverged;
          output.message_ = "adaptive transient LTE rejection limit reached";
          output.diagnostics_.failed_time_s = time;
          return output;
        }
        const double factor = std::isfinite(lte_ratio)
                                  ? std::clamp(0.8 / std::sqrt(lte_ratio),
                                               0.1, 0.5)
                                  : 0.1;
        proposed_step_s = h * factor;
        if (proposed_step_s < options.minimum_time_step_s) {
          output.status_ = SolveStatus::nonconverged;
          output.message_ = "adaptive transient reached minimum timestep";
          output.diagnostics_.failed_time_s = time;
          return output;
        }
        continue;
      }
    }

    auto node_voltage = [&](NodeId node) {
      return node == ground_node ? 0.0 : state[node - 1];
    };
    TransientPoint point;
    point.time_s = target_time;
    point.node_voltages.reserve(circuit.node_names_.size());
    point.node_voltages.push_back({ground_node, "0", 0.0});
    for (std::size_t node = 1; node < circuit.node_names_.size(); ++node) {
      point.node_voltages.push_back(
          {static_cast<NodeId>(node), circuit.node_names_[node], state[node - 1]});
    }
    point.elements.reserve(circuit.elements_.size());
    for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
      const auto &element = circuit.elements_[index];
      const double across = node_voltage(element.positive_node) -
                            node_voltage(element.negative_node);
      double current = 0.0;
      double reported_power = 0.0;
      bool has_explicit_power = false;
      if (element.type == Circuit::ElementType::resistor) {
        current = across / element.value;
      } else if (element.type == Circuit::ElementType::current_source) {
        current = element.behavioral ? circuit.behavioral_point(element,state,target_time).first : element.dependent ? circuit.control_value(element,state) : source_value(element, target_time);
      } else if (element.type == Circuit::ElementType::voltage_source ||
                 element.type == Circuit::ElementType::inductor ||
                 element.type == Circuit::ElementType::saturating_inductor) {
        current = state[branch_index[index]];
      } else if (element.type == Circuit::ElementType::capacitor) {
        current = bdf2_step
                      ? element.value / h *
                            (bdf_a0 * across +
                             bdf_a1 * capacitor_voltage[index] +
                             bdf_a2 * capacitor_previous_voltage[index])
                      : (trapezoidal_step ? 2.0 : 1.0) * element.value *
                                (across - capacitor_voltage[index]) / h -
                            (trapezoidal_step ? capacitor_current[index] : 0.0);
      } else if (element.type == Circuit::ElementType::diode) {
        current = diode(element.diode.saturation_current_a,
                        element.diode.emission_coefficient,
                        element.diode.temperature_k, across).current;
      } else if (element.type == Circuit::ElementType::dynamic_diode) {
        const auto &model = element.dynamic_diode;
        const auto point = diode(
            model.junction.saturation_current_a,
            model.junction.emission_coefficient,
            model.junction.temperature_k, across);
        const double capacitance_current =
            model.junction_capacitance_f / h *
            (bdf_a0 * across +
             bdf_a1 * dynamic_diode_voltage[index] +
             bdf_a2 * dynamic_diode_previous_voltage[index]);
        current = 2.0 * point.current -
                  state[dynamic_state_index[index]] + capacitance_current;
      } else if (element.type ==
                 Circuit::ElementType::electrothermal_resistor) {
        current = electrothermal_resistor(
                      element.electrothermal_resistor, across,
                      node_voltage(element.thermal_node))
                      .current;
      } else if (element.type == Circuit::ElementType::mosfet_level1 || element.type == Circuit::ElementType::bjt_ebers_moll) {
        const auto now=circuit.compact_point(element,state),prior=circuit.compact_point(element,state_before),older=circuit.compact_point(element,previous_solution);
        current=now.current[0]+(bdf_a0*now.charge[0]+bdf_a1*prior.charge[0]+bdf_a2*older.charge[0])/h;
      } else if (element.type ==
                 Circuit::ElementType::wbg_fet_electrothermal) {
        const auto &model = element.wbg_fet_electrothermal;
        const std::array<NodeId, 5> terminals{
            element.positive_node, element.control_positive_node,
            element.negative_node, element.control_negative_node,
            element.thermal_node};
        const auto state_voltage = [](const std::vector<double> &values,
                                      NodeId node) {
          return node == ground_node ? 0.0 : values[node - 1];
        };
        const auto device_point = evaluate_wbg_fet_electrothermal(
            model, node_voltage(terminals[0]), node_voltage(terminals[1]),
            node_voltage(terminals[2]), node_voltage(terminals[3]),
            node_voltage(terminals[4]));
        const auto previous_point = evaluate_wbg_fet_electrothermal(
            model, state_voltage(state_before, terminals[0]),
            state_voltage(state_before, terminals[1]),
            state_voltage(state_before, terminals[2]),
            state_voltage(state_before, terminals[3]),
            state_voltage(state_before, terminals[4]));
        const auto older_point = evaluate_wbg_fet_electrothermal(
            model, state_voltage(previous_solution, terminals[0]),
            state_voltage(previous_solution, terminals[1]),
            state_voltage(previous_solution, terminals[2]),
            state_voltage(previous_solution, terminals[3]),
            state_voltage(previous_solution, terminals[4]));
        current = device_point.terminal_current_a[0] +
                  (bdf_a0 * device_point.terminal_charge_c[0] +
                   bdf_a1 * previous_point.terminal_charge_c[0] +
                   bdf_a2 * older_point.terminal_charge_c[0]) /
                      h;
        reported_power = device_point.dissipated_power_w;
        has_explicit_power = true;
      } else if (element.type == Circuit::ElementType::osdi_device) {
        std::vector<double> local_candidate(element.osdi_nodes.size(), 0.0);
        std::vector<double> local_previous(element.osdi_nodes.size(), 0.0);
        for (std::size_t local = 0; local < element.osdi_nodes.size(); ++local) {
          const NodeId node = element.osdi_nodes[local];
          if (node != ground_node) {
            local_candidate[local] = state[node - 1];
            local_previous[local] = state_before[node - 1];
          }
        }
        const OsdiTransientState prior{osdi_device_states[index],
                                       osdi_reactive_residuals[index]};
        const auto osdi =
            element.osdi_device->evaluate_transient_backward_euler(
                local_candidate, local_previous, target_time, h, prior);
        current=0.;reported_power=0.;has_explicit_power=true;
        const auto aliases=element.osdi_device->node_aliases();
        for(std::size_t i=0;i<osdi.residual.size();++i){
          if(aliases[i]==aliases[0])current+=osdi.residual[i];
          reported_power+=local_candidate[i]*osdi.residual[i];
        }
      } else {
        const double control = node_voltage(element.control_positive_node) -
                               node_voltage(element.control_negative_node);
        current = voltage_controlled_switch(element.switch_model, control)
                      .conductance *
                  across;
      }
      if (!has_explicit_power) {
        reported_power = across * current;
      }
      point.elements.push_back(
          {element.id, across, current, reported_power});
    }
    output.points_.push_back(std::move(point));
    for (std::size_t index = 0; index < circuit.elements_.size(); ++index) {
      const auto &element = circuit.elements_[index];
      if (element.type == Circuit::ElementType::capacitor) {
        const double across = node_voltage(element.positive_node) -
                              node_voltage(element.negative_node);
        const double previous_voltage = capacitor_voltage[index];
        capacitor_current[index] =
            bdf2_step
                ? element.value / h *
                      (bdf_a0 * across + bdf_a1 * previous_voltage +
                       bdf_a2 * capacitor_previous_voltage[index])
                : (trapezoidal_step ? 2.0 : 1.0) * element.value *
                          (across - previous_voltage) / h -
                      (trapezoidal_step ? capacitor_current[index] : 0.0);
        capacitor_previous_voltage[index] = previous_voltage;
        capacitor_voltage[index] = across;
      } else if (element.type == Circuit::ElementType::inductor ||
                 element.type == Circuit::ElementType::saturating_inductor) {
        inductor_previous_current[index] = inductor_current[index];
        inductor_current[index] = state[branch_index[index]];
        inductor_voltage[index] = node_voltage(element.positive_node) -
                                  node_voltage(element.negative_node);
      } else if (element.type == Circuit::ElementType::dynamic_diode) {
        dynamic_diode_previous_stored_current[index] =
            dynamic_diode_stored_current[index];
        dynamic_diode_stored_current[index] =
            state[dynamic_state_index[index]];
        dynamic_diode_previous_voltage[index] = dynamic_diode_voltage[index];
        dynamic_diode_voltage[index] =
            node_voltage(element.positive_node) -
            node_voltage(element.negative_node);
      } else if (element.type == Circuit::ElementType::osdi_device) {
        std::vector<double> local_candidate(element.osdi_nodes.size(), 0.0);
        std::vector<double> local_previous(element.osdi_nodes.size(), 0.0);
        for (std::size_t local = 0; local < element.osdi_nodes.size(); ++local) {
          const NodeId node = element.osdi_nodes[local];
          if (node != ground_node) {
            local_candidate[local] = state[node - 1];
            local_previous[local] = state_before[node - 1];
          }
        }
        const OsdiTransientState prior{osdi_device_states[index],
                                       osdi_reactive_residuals[index]};
        auto accepted = element.osdi_device->evaluate_transient_backward_euler(
            local_candidate, local_previous, target_time, h, prior);
        osdi_device_states[index] = std::move(accepted.next.device_state);
        osdi_reactive_residuals[index] =
            std::move(accepted.next.reactive_residual);
      }
    }
    time = target_time;
    previous_solution = state_before;
    solution_history_depth =
        std::min<std::size_t>(2, solution_history_depth + 1);
    previous_step_s = h;
    history_depth = std::min<std::size_t>(2, history_depth + 1);
    ++output.diagnostics_.completed_steps;
    if (bdf2_step) {
      ++output.diagnostics_.bdf2_steps;
    } else if (trapezoidal_step) {
      ++output.diagnostics_.trapezoidal_steps;
    } else {
      ++output.diagnostics_.backward_euler_steps;
    }
    output.diagnostics_.residual_inf_norm = final_residual;
    if (output.diagnostics_.completed_steps == 1) {
      output.diagnostics_.minimum_accepted_step_s = h;
      output.diagnostics_.maximum_accepted_step_s = h;
    } else {
      output.diagnostics_.minimum_accepted_step_s =
          std::min(output.diagnostics_.minimum_accepted_step_s, h);
      output.diagnostics_.maximum_accepted_step_s =
          std::max(output.diagnostics_.maximum_accepted_step_s, h);
    }
    if (options.adaptive_time_step && estimate_lte) {
      const double factor = std::clamp(
          0.9 / std::sqrt(std::max(lte_ratio, 1.0e-12)), 0.5, 2.0);
      proposed_step_s = std::clamp(h * factor, options.minimum_time_step_s,
                                   options.time_step_s);
    } else {
      proposed_step_s = options.time_step_s;
    }
  }
  output.status_ = SolveStatus::converged;
  workspace.impl_->integration_history = {
      capacitor_current,
      inductor_voltage,
      capacitor_previous_voltage,
      inductor_previous_current,
      dynamic_diode_stored_current,
      dynamic_diode_previous_stored_current,
      dynamic_diode_voltage,
      dynamic_diode_previous_voltage,
      osdi_device_states,
      osdi_reactive_residuals,
      state,
      previous_solution,
      structural_signature,
      previous_step_s,
      history_depth,
      solution_history_depth,
      true};
  output.message_ =
      options.integration_method == TransientIntegrationMethod::bdf2
          ? "breakpoint-aware variable-step BDF2 transient completed"
          : options.integration_method ==
              TransientIntegrationMethod::hybrid_trapezoidal
          ? "breakpoint-aware hybrid trapezoidal transient completed"
          : "breakpoint-aware backward-Euler transient completed";
  return output;
}

} // namespace spikes
