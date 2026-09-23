#include "spikes/c_api.h"

#include "spikes/dc_solver.hpp"
#include "spikes/transient_solver.hpp"
#include "spikes/transient_session.hpp"

#include <algorithm>
#include <atomic>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>

struct spikes_circuit {
  spikes::Circuit value;
};

struct spikes_result {
  explicit spikes_result(spikes::OperatingPointResult result)
      : value(std::move(result)) {}
  spikes::OperatingPointResult value;
};

struct spikes_transient_result {
  explicit spikes_transient_result(spikes::TransientResult result)
      : value(std::move(result)) {}
  spikes::TransientResult value;
};

namespace {
std::atomic<std::uint64_t> next_session_token{1};
}

struct spikes_transient_session {
  spikes_transient_session(spikes::Circuit circuit,
                           spikes::TransientOptions options)
      : value(std::move(circuit), options),
        token(next_session_token.fetch_add(1, std::memory_order_relaxed)) {}
  spikes::TransientSession value;
  std::uint64_t token;
};

struct spikes_transient_checkpoint {
  spikes_transient_checkpoint(spikes::TransientSessionCheckpoint checkpoint,
                              std::uint64_t session_token)
      : value(std::move(checkpoint)), owner_token(session_token) {}
  spikes::TransientSessionCheckpoint value;
  std::uint64_t owner_token;
};

namespace {

thread_local std::string last_error;

spikes_error_code invalid(const char *message) {
  last_error = message;
  return SPIKES_INVALID_ARGUMENT;
}

template <typename Function>
spikes_error_code guard(Function &&function) noexcept {
  try {
    function();
    last_error.clear();
    return SPIKES_OK;
  } catch (const std::invalid_argument &error) {
    last_error = error.what();
    return SPIKES_INVALID_ARGUMENT;
  } catch (const std::out_of_range &error) {
    last_error = error.what();
    return SPIKES_NOT_FOUND;
  } catch (const std::bad_alloc &) {
    last_error = "SPIKES allocation failed";
    return SPIKES_ALLOCATION_FAILURE;
  } catch (const std::exception &error) {
    last_error = error.what();
    return SPIKES_INTERNAL_ERROR;
  } catch (...) {
    last_error = "unknown SPIKES internal error";
    return SPIKES_INTERNAL_ERROR;
  }
}

bool valid_text(const char *value) { return value != nullptr && value[0] != '\0'; }

spikes_solve_status translate_status(spikes::SolveStatus status) {
  switch (status) {
  case spikes::SolveStatus::converged:
    return SPIKES_SOLVE_CONVERGED;
  case spikes::SolveStatus::singular:
    return SPIKES_SOLVE_SINGULAR;
  case spikes::SolveStatus::numerical_failure:
  case spikes::SolveStatus::nonconverged:
    // ABI v1 did not distinguish nonlinear nonconvergence. Preserve that
    // mapping; callers can use the result message and diagnostics.
    return SPIKES_SOLVE_NUMERICAL_FAILURE;
  }
  return SPIKES_SOLVE_NUMERICAL_FAILURE;
}

std::vector<spikes::PwlPoint> copy_pwl_points(const spikes_pwl_point *points,
                                              size_t point_count) {
  if (points == nullptr || point_count == 0) {
    throw std::invalid_argument(
        "PWL points and a nonzero point count are required");
  }
  std::vector<spikes::PwlPoint> native;
  native.reserve(point_count);
  for (size_t index = 0; index < point_count; ++index) {
    native.push_back({points[index].time_s, points[index].value});
  }
  return native;
}

} // namespace

extern "C" {

uint32_t spikes_abi_version(void) { return SPIKES_ABI_VERSION; }

const char *spikes_last_error(void) { return last_error.c_str(); }

spikes_error_code spikes_circuit_create(spikes_circuit **out_circuit) {
  if (out_circuit == nullptr) {
    return invalid("out_circuit must not be null");
  }
  *out_circuit = nullptr;
  return guard([&] { *out_circuit = new spikes_circuit{}; });
}

void spikes_circuit_destroy(spikes_circuit *circuit) { delete circuit; }

spikes_error_code spikes_circuit_add_resistor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double resistance_ohm) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] { circuit->value.add_resistor(id, positive_node, negative_node, resistance_ohm); });
}

spikes_error_code spikes_circuit_add_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double current_a) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] { circuit->value.add_current_source(id, positive_node, negative_node, current_a); });
}

spikes_error_code spikes_circuit_add_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double voltage_v) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] { circuit->value.add_voltage_source(id, positive_node, negative_node, voltage_v); });
}

spikes_error_code spikes_circuit_add_pulse_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double initial_value, double pulsed_value,
    double delay_s, double rise_time_s, double fall_time_s,
    double pulse_width_s, double period_s) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] {
    circuit->value.add_pulse_current_source(
        id, positive_node, negative_node,
        {initial_value, pulsed_value, delay_s, rise_time_s, fall_time_s,
         pulse_width_s, period_s});
  });
}

spikes_error_code spikes_circuit_add_pulse_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double initial_value, double pulsed_value,
    double delay_s, double rise_time_s, double fall_time_s,
    double pulse_width_s, double period_s) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] {
    circuit->value.add_pulse_voltage_source(
        id, positive_node, negative_node,
        {initial_value, pulsed_value, delay_s, rise_time_s, fall_time_s,
         pulse_width_s, period_s});
  });
}

spikes_error_code spikes_circuit_add_pwl_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const spikes_pwl_point *points,
    size_t point_count) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] {
    circuit->value.add_pwl_current_source(
        id, positive_node, negative_node, copy_pwl_points(points, point_count));
  });
}

spikes_error_code spikes_circuit_add_pwl_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const spikes_pwl_point *points,
    size_t point_count) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and node names are required");
  }
  return guard([&] {
    circuit->value.add_pwl_voltage_source(
        id, positive_node, negative_node, copy_pwl_points(points, point_count));
  });
}

spikes_error_code spikes_circuit_add_voltage_controlled_switch(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const char *control_positive_node,
    const char *control_negative_node, double on_resistance_ohm,
    double off_resistance_ohm, double threshold_voltage_v,
    double transition_voltage_v) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node) || !valid_text(control_positive_node) ||
      !valid_text(control_negative_node)) {
    return invalid("circuit, id, output nodes, and control nodes are required");
  }
  return guard([&] {
    circuit->value.add_voltage_controlled_switch(
        id, positive_node, negative_node, control_positive_node,
        control_negative_node,
        {on_resistance_ohm, off_resistance_ohm, threshold_voltage_v,
         transition_voltage_v});
  });
}

spikes_error_code spikes_circuit_add_diode(
    spikes_circuit *circuit, const char *id, const char *anode_node,
    const char *cathode_node, double saturation_current_a,
    double emission_coefficient, double temperature_k) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(anode_node) ||
      !valid_text(cathode_node)) {
    return invalid("circuit, id, and diode node names are required");
  }
  return guard([&] {
    circuit->value.add_diode(
        id, anode_node, cathode_node,
        spikes::DiodeModel{saturation_current_a, emission_coefficient,
                           temperature_k});
  });
}

spikes_error_code spikes_circuit_add_dynamic_diode(
    spikes_circuit *circuit, const char *id, const char *anode_node,
    const char *cathode_node, double saturation_current_a,
    double emission_coefficient, double temperature_k,
    double transit_time_s, double junction_capacitance_f,
    double initial_stored_charge_c) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(anode_node) ||
      !valid_text(cathode_node)) {
    return invalid("circuit, id, and dynamic diode node names are required");
  }
  return guard([&] {
    circuit->value.add_dynamic_diode(
        id, anode_node, cathode_node,
        spikes::DynamicDiodeModel{
            spikes::DiodeModel{saturation_current_a, emission_coefficient,
                               temperature_k},
            transit_time_s, junction_capacitance_f,
            initial_stored_charge_c});
  });
}

spikes_error_code spikes_circuit_add_electrothermal_resistor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const char *thermal_node,
    double resistance_ohm, double temperature_coefficient_per_k,
    double ambient_temperature_k, double thermal_resistance_k_per_w,
    double thermal_capacitance_j_per_k, double minimum_temperature_k,
    double maximum_temperature_k) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node) || !valid_text(thermal_node)) {
    return invalid(
        "circuit, id, electrical nodes, and thermal node are required");
  }
  return guard([&] {
    circuit->value.add_electrothermal_resistor(
        id, positive_node, negative_node, thermal_node,
        spikes::ElectrothermalResistorModel{
            resistance_ohm, temperature_coefficient_per_k,
            ambient_temperature_k, thermal_resistance_k_per_w,
            thermal_capacitance_j_per_k, minimum_temperature_k,
            maximum_temperature_k});
  });
}

spikes_error_code spikes_circuit_add_mosfet_level1(
    spikes_circuit *circuit, const char *id, const char *drain_node,
    const char *gate_node, const char *source_node, const char *bulk_node,
    double threshold_voltage_v, double transconductance_a_per_v2,
    double channel_length_modulation_per_v, double body_effect_sqrt_v,
    double surface_potential_v, double width_over_length,
    double off_conductance_s) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(drain_node) ||
      !valid_text(gate_node) || !valid_text(source_node) ||
      !valid_text(bulk_node)) {
    return invalid("circuit, id, and all four MOSFET node names are required");
  }
  return guard([&] {
    circuit->value.add_mosfet_level1(
        id, drain_node, gate_node, source_node, bulk_node,
        spikes::MosfetLevel1Model{
            threshold_voltage_v, transconductance_a_per_v2,
            channel_length_modulation_per_v, body_effect_sqrt_v,
            surface_potential_v, width_over_length, off_conductance_s});
  });
}

spikes_error_code spikes_circuit_add_bjt_ebers_moll(
    spikes_circuit *circuit, const char *id, const char *collector_node,
    const char *base_node, const char *emitter_node,
    double saturation_current_a, double forward_alpha, double reverse_alpha,
    double emission_coefficient, double temperature_k) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(collector_node) ||
      !valid_text(base_node) || !valid_text(emitter_node)) {
    return invalid("circuit, id, and all three BJT node names are required");
  }
  return guard([&] {
    circuit->value.add_bjt_ebers_moll(
        id, collector_node, base_node, emitter_node,
        spikes::BjtEbersMollModel{saturation_current_a, forward_alpha,
                                  reverse_alpha, emission_coefficient,
                                  temperature_k});
  });
}

spikes_error_code spikes_wbg_fet_electrothermal_model_init(
    spikes_wbg_fet_electrothermal_model *out_model, uint32_t technology) {
  if (out_model == nullptr ||
      (technology != SPIKES_WBG_TECHNOLOGY_GAN_HEMT &&
       technology != SPIKES_WBG_TECHNOLOGY_SIC_MOSFET)) {
    return invalid("output model and a known WBG technology are required");
  }
  const spikes::WbgFetElectrothermalModel defaults{
      technology == SPIKES_WBG_TECHNOLOGY_GAN_HEMT
          ? spikes::WbgTechnology::gan_hemt
          : spikes::WbgTechnology::sic_mosfet};
  *out_model = {
      SPIKES_WBG_FET_MODEL_API_VERSION,
      technology,
      sizeof(spikes_wbg_fet_electrothermal_model),
      0u,
      defaults.threshold_voltage_v,
      defaults.transconductance_a_per_v2,
      defaults.channel_length_modulation_per_v,
      defaults.mobility_temperature_exponent,
      defaults.threshold_temperature_coefficient_v_per_k,
      defaults.off_conductance_s,
      defaults.reverse_conduction_threshold_v,
      defaults.reverse_conductance_s,
      defaults.body_diode_saturation_current_a,
      defaults.body_diode_emission_coefficient,
      defaults.breakdown_voltage_v,
      defaults.breakdown_temperature_coefficient_v_per_k,
      defaults.avalanche_current_scale_a,
      defaults.avalanche_slope_v,
      defaults.gate_leakage_conductance_s,
      defaults.gate_source_capacitance_f,
      defaults.gate_drain_capacitance_f,
      defaults.drain_source_capacitance_f,
      defaults.ambient_temperature_k,
      defaults.thermal_resistance_k_per_w,
      defaults.minimum_temperature_k,
      defaults.maximum_temperature_k,
      defaults.maximum_absolute_voltage_v,
      defaults.maximum_absolute_current_a,
      defaults.thermal_capacitance_j_per_k,
  };
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_circuit_add_wbg_fet_electrothermal(
    spikes_circuit *circuit, const char *id, const char *drain_node,
    const char *gate_node, const char *source_node, const char *bulk_node,
    const char *thermal_node,
    const spikes_wbg_fet_electrothermal_model *model) {
  if (circuit == nullptr || model == nullptr || !valid_text(id) ||
      !valid_text(drain_node) || !valid_text(gate_node) ||
      !valid_text(source_node) || !valid_text(bulk_node) ||
      !valid_text(thermal_node) ||
      model->struct_version != SPIKES_WBG_FET_MODEL_API_VERSION ||
      model->struct_size <
          offsetof(spikes_wbg_fet_electrothermal_model,
                   thermal_capacitance_j_per_k) ||
      (model->technology != SPIKES_WBG_TECHNOLOGY_GAN_HEMT &&
       model->technology != SPIKES_WBG_TECHNOLOGY_SIC_MOSFET)) {
    return invalid("circuit, WBG model, id, technology, and five nodes are required");
  }
  return guard([&] {
    spikes::WbgFetElectrothermalModel native;
    native.technology = model->technology == SPIKES_WBG_TECHNOLOGY_GAN_HEMT
                            ? spikes::WbgTechnology::gan_hemt
                            : spikes::WbgTechnology::sic_mosfet;
    native.threshold_voltage_v = model->threshold_voltage_v;
    native.transconductance_a_per_v2 = model->transconductance_a_per_v2;
    native.channel_length_modulation_per_v =
        model->channel_length_modulation_per_v;
    native.mobility_temperature_exponent =
        model->mobility_temperature_exponent;
    native.threshold_temperature_coefficient_v_per_k =
        model->threshold_temperature_coefficient_v_per_k;
    native.off_conductance_s = model->off_conductance_s;
    native.reverse_conduction_threshold_v =
        model->reverse_conduction_threshold_v;
    native.reverse_conductance_s = model->reverse_conductance_s;
    native.body_diode_saturation_current_a =
        model->body_diode_saturation_current_a;
    native.body_diode_emission_coefficient =
        model->body_diode_emission_coefficient;
    native.breakdown_voltage_v = model->breakdown_voltage_v;
    native.breakdown_temperature_coefficient_v_per_k =
        model->breakdown_temperature_coefficient_v_per_k;
    native.avalanche_current_scale_a = model->avalanche_current_scale_a;
    native.avalanche_slope_v = model->avalanche_slope_v;
    native.gate_leakage_conductance_s = model->gate_leakage_conductance_s;
    native.gate_source_capacitance_f = model->gate_source_capacitance_f;
    native.gate_drain_capacitance_f = model->gate_drain_capacitance_f;
    native.drain_source_capacitance_f = model->drain_source_capacitance_f;
    native.ambient_temperature_k = model->ambient_temperature_k;
    native.thermal_resistance_k_per_w = model->thermal_resistance_k_per_w;
    if (model->struct_size >=
        offsetof(spikes_wbg_fet_electrothermal_model,
                 thermal_capacitance_j_per_k) + sizeof(double)) {
      native.thermal_capacitance_j_per_k =
          model->thermal_capacitance_j_per_k;
    }
    native.minimum_temperature_k = model->minimum_temperature_k;
    native.maximum_temperature_k = model->maximum_temperature_k;
    native.maximum_absolute_voltage_v = model->maximum_absolute_voltage_v;
    native.maximum_absolute_current_a = model->maximum_absolute_current_a;
    circuit->value.add_wbg_fet_electrothermal(
        id, drain_node, gate_node, source_node, bulk_node, thermal_node,
        native);
  });
}

spikes_error_code spikes_circuit_add_capacitor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double capacitance_f,
    double initial_voltage_v) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and capacitor node names are required");
  }
  return guard([&] {
    circuit->value.add_capacitor(id, positive_node, negative_node,
                                 capacitance_f, initial_voltage_v);
  });
}

spikes_error_code spikes_circuit_add_inductor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double inductance_h,
    double initial_current_a) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and inductor node names are required");
  }
  return guard([&] {
    circuit->value.add_inductor(id, positive_node, negative_node, inductance_h,
                                initial_current_a);
  });
}

spikes_error_code spikes_circuit_add_saturating_inductor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double unsaturated_inductance_h,
    double saturated_inductance_h, double saturation_current_a,
    double initial_current_a) {
  if (circuit == nullptr || !valid_text(id) || !valid_text(positive_node) ||
      !valid_text(negative_node)) {
    return invalid("circuit, id, and saturating inductor nodes are required");
  }
  return guard([&] {
    circuit->value.add_saturating_inductor(
        id, positive_node, negative_node,
        spikes::SaturatingInductorModel{
            unsaturated_inductance_h, saturated_inductance_h,
            saturation_current_a, initial_current_a});
  });
}

spikes_error_code spikes_solve_operating_point(
    const spikes_circuit *circuit, spikes_result **out_result) {
  if (circuit == nullptr || out_result == nullptr) {
    return invalid("circuit and out_result are required");
  }
  *out_result = nullptr;
  return guard([&] {
    *out_result = new spikes_result(spikes::solve_operating_point(circuit->value));
  });
}

spikes_error_code spikes_linear_solver_options_init(
    spikes_linear_solver_options *out_options) {
  if (out_options == nullptr) {
    return invalid("linear solver out_options must not be null");
  }
  const spikes::SolverOptions defaults;
  *out_options = {};
  out_options->struct_version = SPIKES_LINEAR_SOLVER_API_VERSION;
  out_options->struct_size = sizeof(*out_options);
  out_options->method = SPIKES_LINEAR_SOLVER_AUTOMATIC;
  out_options->max_iterations = defaults.max_linear_iterations;
  out_options->absolute_tolerance = defaults.linear_absolute_tolerance;
  out_options->relative_tolerance = defaults.linear_relative_tolerance;
  out_options->threads = defaults.linear_threads;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_solve_operating_point_with_linear_solver(
    const spikes_circuit *circuit,
    const spikes_linear_solver_options *linear_options,
    spikes_result **out_result) {
  if (circuit == nullptr || linear_options == nullptr || out_result == nullptr) {
    return invalid("circuit, linear options, and out_result are required");
  }
  *out_result = nullptr;
  if (linear_options->struct_version != SPIKES_LINEAR_SOLVER_API_VERSION ||
      linear_options->struct_size < sizeof(spikes_linear_solver_options)) {
    return invalid("unsupported linear solver options structure");
  }
  spikes::SolverOptions options;
  if (linear_options->method == SPIKES_LINEAR_SOLVER_AUTOMATIC) {
    options.linear_solver = spikes::LinearSolverMethod::automatic;
  } else if (linear_options->method == SPIKES_LINEAR_SOLVER_DENSE_LU) {
    options.linear_solver = spikes::LinearSolverMethod::dense_lu;
  } else if (linear_options->method ==
             SPIKES_LINEAR_SOLVER_CONJUGATE_GRADIENT) {
    options.linear_solver = spikes::LinearSolverMethod::conjugate_gradient;
  } else if (linear_options->method == SPIKES_LINEAR_SOLVER_GMRES) {
    options.linear_solver = spikes::LinearSolverMethod::gmres;
  } else if (linear_options->method == SPIKES_LINEAR_SOLVER_SPARSE_LU) {
    options.linear_solver = spikes::LinearSolverMethod::sparse_lu;
  } else if (linear_options->method == SPIKES_LINEAR_SOLVER_ILU_GMRES) {
    options.linear_solver = spikes::LinearSolverMethod::ilu_gmres;
  } else if (linear_options->method == SPIKES_LINEAR_SOLVER_SPARSE_QR) {
    options.linear_solver = spikes::LinearSolverMethod::sparse_qr;
  } else {
    return invalid("unsupported linear solver method");
  }
  options.max_linear_iterations = linear_options->max_iterations;
  options.linear_absolute_tolerance = linear_options->absolute_tolerance;
  options.linear_relative_tolerance = linear_options->relative_tolerance;
  options.linear_threads = linear_options->threads;
  return guard([&] {
    *out_result = new spikes_result(
        spikes::solve_operating_point(circuit->value, options));
  });
}

void spikes_result_destroy(spikes_result *result) { delete result; }

spikes_solve_status spikes_result_status(const spikes_result *result) {
  if (result == nullptr) {
    last_error = "result must not be null";
    return SPIKES_SOLVE_NUMERICAL_FAILURE;
  }
  return translate_status(result->value.status());
}

const char *spikes_result_message(const spikes_result *result) {
  if (result == nullptr) {
    last_error = "result must not be null";
    return "";
  }
  return result->value.message().c_str();
}

spikes_error_code spikes_result_node_voltage(
    const spikes_result *result, const char *node_name, double *out_voltage_v) {
  if (result == nullptr || !valid_text(node_name) || out_voltage_v == nullptr) {
    return invalid("result, node name, and output are required");
  }
  return guard([&] { *out_voltage_v = result->value.node_voltage(node_name); });
}

spikes_error_code spikes_result_element_current(
    const spikes_result *result, const char *element_id, double *out_current_a) {
  if (result == nullptr || !valid_text(element_id) || out_current_a == nullptr) {
    return invalid("result, element id, and output are required");
  }
  return guard([&] { *out_current_a = result->value.element_current(element_id); });
}

spikes_error_code spikes_result_element_power(
    const spikes_result *result, const char *element_id, double *out_power_w) {
  if (result == nullptr || !valid_text(element_id) || out_power_w == nullptr) {
    return invalid("result, element id, and output are required");
  }
  return guard([&] { *out_power_w = result->value.element_power(element_id); });
}

spikes_error_code spikes_result_diagnostics(
    const spikes_result *result, size_t *out_matrix_order,
    size_t *out_pivot_swaps, double *out_residual_inf_norm) {
  if (result == nullptr || out_matrix_order == nullptr ||
      out_pivot_swaps == nullptr || out_residual_inf_norm == nullptr) {
    return invalid("result and all diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_matrix_order = diagnostics.matrix_order;
  *out_pivot_swaps = diagnostics.pivot_swaps;
  *out_residual_inf_norm = diagnostics.residual_inf_norm;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_result_linear_solver_diagnostics(
    const spikes_result *result, uint32_t *out_method,
    size_t *out_iterations, size_t *out_threads) {
  if (result == nullptr || out_method == nullptr || out_iterations == nullptr ||
      out_threads == nullptr) {
    return invalid("result and all linear diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  if (diagnostics.linear_solver_used ==
      spikes::LinearSolverMethod::conjugate_gradient) {
    *out_method = SPIKES_LINEAR_SOLVER_CONJUGATE_GRADIENT;
  } else if (diagnostics.linear_solver_used ==
             spikes::LinearSolverMethod::gmres) {
    *out_method = SPIKES_LINEAR_SOLVER_GMRES;
  } else if (diagnostics.linear_solver_used ==
             spikes::LinearSolverMethod::sparse_lu) {
    *out_method = SPIKES_LINEAR_SOLVER_SPARSE_LU;
  } else if (diagnostics.linear_solver_used ==
             spikes::LinearSolverMethod::ilu_gmres) {
    *out_method = SPIKES_LINEAR_SOLVER_ILU_GMRES;
  } else if (diagnostics.linear_solver_used ==
             spikes::LinearSolverMethod::sparse_qr) {
    *out_method = SPIKES_LINEAR_SOLVER_SPARSE_QR;
  } else {
    *out_method = SPIKES_LINEAR_SOLVER_DENSE_LU;
  }
  *out_iterations = diagnostics.linear_iterations;
  *out_threads = diagnostics.linear_threads;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_result_sparse_solver_diagnostics(
    const spikes_result *result, size_t *out_matrix_nonzeros,
    size_t *out_symbolic_analyses, size_t *out_numeric_factorizations) {
  if (result == nullptr || out_matrix_nonzeros == nullptr ||
      out_symbolic_analyses == nullptr || out_numeric_factorizations == nullptr) {
    return invalid("result and all sparse diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_matrix_nonzeros = diagnostics.matrix_nonzeros;
  *out_symbolic_analyses = diagnostics.symbolic_analyses;
  *out_numeric_factorizations = diagnostics.numeric_factorizations;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code
spikes_transient_options_init(spikes_transient_options *out_options) {
  if (out_options == nullptr) {
    return invalid("out_options must not be null");
  }
  const spikes::TransientOptions defaults;
  *out_options = {};
  out_options->struct_version = SPIKES_TRANSIENT_API_VERSION;
  out_options->struct_size = sizeof(*out_options);
  out_options->time_step_s = defaults.time_step_s;
  out_options->stop_time_s = defaults.stop_time_s;
  out_options->max_steps = defaults.max_steps;
  out_options->initialize_from_operating_point =
      defaults.initialize_from_operating_point ? 1u : 0u;
  out_options->max_newton_iterations =
      defaults.nonlinear.max_newton_iterations;
  out_options->max_backtracks = defaults.nonlinear.max_backtracks;
  out_options->absolute_tolerance = defaults.nonlinear.absolute_tolerance;
  out_options->relative_tolerance = defaults.nonlinear.relative_tolerance;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_solve_transient(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    spikes_transient_result **out_result) {
  return spikes_solve_transient_with_method(
      circuit, options, SPIKES_INTEGRATION_BACKWARD_EULER, out_result);
}

spikes_error_code spikes_solve_transient_with_method(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, spikes_transient_result **out_result) {
  if (options == nullptr) {
    return invalid("transient options are required");
  }
  return spikes_solve_transient_adaptive(
      circuit, options, integration_method, 0u,
      std::min(1.0e-15, options->time_step_s), 1.0e-6, 1.0e-3, 10'000,
      out_result);
}

spikes_error_code spikes_solve_transient_adaptive(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, uint8_t adaptive_time_step,
    double minimum_time_step_s, double lte_absolute_tolerance,
    double lte_relative_tolerance, size_t max_rejected_steps,
    spikes_transient_result **out_result) {
  if (circuit == nullptr || options == nullptr || out_result == nullptr) {
    return invalid("circuit, transient options, and out_result are required");
  }
  *out_result = nullptr;
  if (options->struct_version != SPIKES_TRANSIENT_API_VERSION ||
      options->struct_size < sizeof(spikes_transient_options)) {
    return invalid("unsupported transient options structure version or size");
  }
  if (options->initialize_from_operating_point > 1u) {
    return invalid("initialize_from_operating_point must be zero or one");
  }
  if (adaptive_time_step > 1u) {
    return invalid("adaptive_time_step must be zero or one");
  }
  if (integration_method != SPIKES_INTEGRATION_BACKWARD_EULER &&
      integration_method != SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL &&
      integration_method != SPIKES_INTEGRATION_BDF2) {
    return invalid("unsupported transient integration method");
  }
  spikes::TransientOptions native;
  native.time_step_s = options->time_step_s;
  native.stop_time_s = options->stop_time_s;
  native.max_steps = options->max_steps;
  native.initialize_from_operating_point =
      options->initialize_from_operating_point != 0u;
  native.integration_method =
      integration_method == SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL
          ? spikes::TransientIntegrationMethod::hybrid_trapezoidal
          : integration_method == SPIKES_INTEGRATION_BDF2
                ? spikes::TransientIntegrationMethod::bdf2
                : spikes::TransientIntegrationMethod::backward_euler;
  native.adaptive_time_step = adaptive_time_step != 0u;
  native.minimum_time_step_s = minimum_time_step_s;
  native.lte_absolute_tolerance = lte_absolute_tolerance;
  native.lte_relative_tolerance = lte_relative_tolerance;
  native.max_rejected_steps = max_rejected_steps;
  native.nonlinear.max_newton_iterations = options->max_newton_iterations;
  native.nonlinear.max_backtracks = options->max_backtracks;
  native.nonlinear.absolute_tolerance = options->absolute_tolerance;
  native.nonlinear.relative_tolerance = options->relative_tolerance;
  return guard([&] {
    *out_result = new spikes_transient_result(
        spikes::solve_transient(circuit->value, native));
  });
}

void spikes_transient_result_destroy(spikes_transient_result *result) {
  delete result;
}

spikes_solve_status
spikes_transient_result_status(const spikes_transient_result *result) {
  if (result == nullptr) {
    last_error = "transient result must not be null";
    return SPIKES_SOLVE_NUMERICAL_FAILURE;
  }
  return translate_status(result->value.status());
}

const char *
spikes_transient_result_message(const spikes_transient_result *result) {
  if (result == nullptr) {
    last_error = "transient result must not be null";
    return "";
  }
  return result->value.message().c_str();
}

size_t
spikes_transient_result_point_count(const spikes_transient_result *result) {
  if (result == nullptr) {
    last_error = "transient result must not be null";
    return 0;
  }
  last_error.clear();
  return result->value.points().size();
}

spikes_error_code spikes_transient_result_point_time(
    const spikes_transient_result *result, size_t point_index,
    double *out_time_s) {
  if (result == nullptr || out_time_s == nullptr) {
    return invalid("transient result and time output are required");
  }
  return guard([&] {
    *out_time_s = result->value.points().at(point_index).time_s;
  });
}

spikes_error_code spikes_transient_result_node_voltage(
    const spikes_transient_result *result, size_t point_index,
    const char *node_name, double *out_voltage_v) {
  if (result == nullptr || !valid_text(node_name) || out_voltage_v == nullptr) {
    return invalid("transient result, node name, and voltage output are required");
  }
  return guard([&] {
    *out_voltage_v =
        result->value.points().at(point_index).node_voltage(node_name);
  });
}

spikes_error_code spikes_transient_result_element_current(
    const spikes_transient_result *result, size_t point_index,
    const char *element_id, double *out_current_a) {
  if (result == nullptr || !valid_text(element_id) || out_current_a == nullptr) {
    return invalid(
        "transient result, element id, and current output are required");
  }
  return guard([&] {
    *out_current_a =
        result->value.points().at(point_index).element_current(element_id);
  });
}

spikes_error_code spikes_transient_result_element_power(
    const spikes_transient_result *result, size_t point_index,
    const char *element_id, double *out_power_w) {
  if (result == nullptr || !valid_text(element_id) || out_power_w == nullptr) {
    return invalid(
        "transient result, element id, and power output are required");
  }
  return guard([&] {
    const auto &elements = result->value.points().at(point_index).elements;
    const auto found = std::find_if(
        elements.begin(), elements.end(),
        [element_id](const spikes::ElementOperatingPoint &element) {
          return element.id == element_id;
        });
    if (found == elements.end()) {
      throw std::out_of_range("unknown transient element");
    }
    *out_power_w = found->power_w;
  });
}

spikes_error_code spikes_transient_result_diagnostics(
    const spikes_transient_result *result, size_t *out_matrix_order,
    size_t *out_completed_steps, size_t *out_total_newton_iterations,
    size_t *out_total_damping_steps, size_t *out_pivot_swaps,
    double *out_failed_time_s, double *out_residual_inf_norm) {
  if (result == nullptr || out_matrix_order == nullptr ||
      out_completed_steps == nullptr ||
      out_total_newton_iterations == nullptr ||
      out_total_damping_steps == nullptr || out_pivot_swaps == nullptr ||
      out_failed_time_s == nullptr || out_residual_inf_norm == nullptr) {
    return invalid("transient result and all diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_matrix_order = diagnostics.matrix_order;
  *out_completed_steps = diagnostics.completed_steps;
  *out_total_newton_iterations = diagnostics.total_newton_iterations;
  *out_total_damping_steps = diagnostics.total_damping_steps;
  *out_pivot_swaps = diagnostics.pivot_swaps;
  *out_failed_time_s = diagnostics.failed_time_s;
  *out_residual_inf_norm = diagnostics.residual_inf_norm;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_breakpoint_steps(
    const spikes_transient_result *result,
    size_t *out_source_breakpoint_steps) {
  if (result == nullptr || out_source_breakpoint_steps == nullptr) {
    return invalid("transient result and breakpoint-step output are required");
  }
  *out_source_breakpoint_steps =
      result->value.diagnostics().source_breakpoint_steps;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_factorization_diagnostics(
    const spikes_transient_result *result, size_t *out_matrix_factorizations,
    size_t *out_factorization_reuses, size_t *out_cache_entries) {
  if (result == nullptr || out_matrix_factorizations == nullptr ||
      out_factorization_reuses == nullptr || out_cache_entries == nullptr) {
    return invalid(
        "transient result and all factorization diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_matrix_factorizations = diagnostics.matrix_factorizations;
  *out_factorization_reuses = diagnostics.factorization_reuses;
  *out_cache_entries = diagnostics.factorization_cache_entries;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_integration_diagnostics(
    const spikes_transient_result *result, size_t *out_backward_euler_steps,
    size_t *out_trapezoidal_steps) {
  if (result == nullptr || out_backward_euler_steps == nullptr ||
      out_trapezoidal_steps == nullptr) {
    return invalid(
        "transient result and all integration diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_backward_euler_steps = diagnostics.backward_euler_steps;
  *out_trapezoidal_steps = diagnostics.trapezoidal_steps;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_bdf2_steps(
    const spikes_transient_result *result, size_t *out_bdf2_steps) {
  if (result == nullptr || out_bdf2_steps == nullptr) {
    return invalid("transient result and BDF2-step output are required");
  }
  *out_bdf2_steps = result->value.diagnostics().bdf2_steps;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_lte_diagnostics(
    const spikes_transient_result *result, size_t *out_rejected_steps,
    double *out_last_lte_ratio, double *out_minimum_accepted_step_s,
    double *out_maximum_accepted_step_s) {
  if (result == nullptr || out_rejected_steps == nullptr ||
      out_last_lte_ratio == nullptr || out_minimum_accepted_step_s == nullptr ||
      out_maximum_accepted_step_s == nullptr) {
    return invalid("transient result and all LTE diagnostic outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_rejected_steps = diagnostics.rejected_lte_steps;
  *out_last_lte_ratio = diagnostics.last_lte_ratio;
  *out_minimum_accepted_step_s = diagnostics.minimum_accepted_step_s;
  *out_maximum_accepted_step_s = diagnostics.maximum_accepted_step_s;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_result_sparse_lte_diagnostics(
    const spikes_transient_result *result, size_t *out_embedded_lte_solves,
    size_t *out_sparse_assemblies, size_t *out_sparse_symbolic_analyses,
    size_t *out_sparse_numeric_factorizations,
    size_t *out_partial_numeric_refactorizations) {
  if (result == nullptr || out_embedded_lte_solves == nullptr ||
      out_sparse_assemblies == nullptr ||
      out_sparse_symbolic_analyses == nullptr ||
      out_sparse_numeric_factorizations == nullptr ||
      out_partial_numeric_refactorizations == nullptr) {
    return invalid("transient result and all sparse/LTE outputs are required");
  }
  const auto &diagnostics = result->value.diagnostics();
  *out_embedded_lte_solves = diagnostics.embedded_lte_solves;
  *out_sparse_assemblies = diagnostics.sparse_assemblies;
  *out_sparse_symbolic_analyses = diagnostics.sparse_symbolic_analyses;
  *out_sparse_numeric_factorizations =
      diagnostics.sparse_numeric_factorizations;
  *out_partial_numeric_refactorizations =
      diagnostics.partial_numeric_refactorizations;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_create(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    spikes_transient_session **out_session) {
  return spikes_transient_session_create_with_method(
      circuit, options, SPIKES_INTEGRATION_BACKWARD_EULER, out_session);
}

spikes_error_code spikes_transient_session_create_with_method(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, spikes_transient_session **out_session) {
  if (circuit == nullptr || options == nullptr || out_session == nullptr) {
    return invalid("circuit, transient options, and out_session are required");
  }
  *out_session = nullptr;
  if (options->struct_version != SPIKES_TRANSIENT_API_VERSION ||
      options->struct_size < sizeof(spikes_transient_options)) {
    return invalid("unsupported transient options structure version or size");
  }
  if (options->initialize_from_operating_point > 1u) {
    return invalid("initialize_from_operating_point must be zero or one");
  }
  if (integration_method != SPIKES_INTEGRATION_BACKWARD_EULER &&
      integration_method != SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL &&
      integration_method != SPIKES_INTEGRATION_BDF2) {
    return invalid("unsupported persistent transient integration method");
  }
  spikes::TransientOptions native;
  native.time_step_s = options->time_step_s;
  native.stop_time_s = options->stop_time_s;
  native.max_steps = options->max_steps;
  native.initialize_from_operating_point =
      options->initialize_from_operating_point != 0u;
  native.integration_method =
      integration_method == SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL
          ? spikes::TransientIntegrationMethod::hybrid_trapezoidal
          : integration_method == SPIKES_INTEGRATION_BDF2
                ? spikes::TransientIntegrationMethod::bdf2
                : spikes::TransientIntegrationMethod::backward_euler;
  native.nonlinear.max_newton_iterations = options->max_newton_iterations;
  native.nonlinear.max_backtracks = options->max_backtracks;
  native.nonlinear.absolute_tolerance = options->absolute_tolerance;
  native.nonlinear.relative_tolerance = options->relative_tolerance;
  return guard([&] {
    *out_session = new spikes_transient_session(circuit->value, native);
  });
}

void spikes_transient_session_destroy(spikes_transient_session *session) {
  delete session;
}

spikes_error_code spikes_transient_session_set_source_value(
    spikes_transient_session *session, const char *element_id, double value) {
  if (session == nullptr || !valid_text(element_id)) {
    return invalid("session and source element id are required");
  }
  return guard([&] { session->value.set_source_value(element_id, value); });
}

spikes_error_code spikes_transient_session_step(
    spikes_transient_session *session, double step_s, uint8_t *out_accepted) {
  if (session == nullptr || out_accepted == nullptr) {
    return invalid("session and accepted output are required");
  }
  *out_accepted = 0u;
  return guard([&] {
    *out_accepted = session->value.step(step_s) ? 1u : 0u;
  });
}

spikes_solve_status spikes_transient_session_status(
    const spikes_transient_session *session) {
  if (session == nullptr) {
    last_error = "persistent transient session must not be null";
    return SPIKES_SOLVE_NUMERICAL_FAILURE;
  }
  return translate_status(session->value.status());
}

const char *spikes_transient_session_message(
    const spikes_transient_session *session) {
  if (session == nullptr) {
    last_error = "persistent transient session must not be null";
    return "";
  }
  return session->value.message().c_str();
}

spikes_error_code spikes_transient_session_position(
    const spikes_transient_session *session, double *out_time_s,
    size_t *out_step_index) {
  if (session == nullptr || out_time_s == nullptr || out_step_index == nullptr) {
    return invalid("session and position outputs are required");
  }
  *out_time_s = session->value.time_s();
  *out_step_index = session->value.step_index();
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_node_voltage(
    const spikes_transient_session *session, const char *node_name,
    double *out_voltage_v) {
  if (session == nullptr || !valid_text(node_name) || out_voltage_v == nullptr) {
    return invalid("session, node name, and voltage output are required");
  }
  return guard([&] { *out_voltage_v = session->value.node_voltage(node_name); });
}

spikes_error_code spikes_transient_session_element_voltage(
    const spikes_transient_session *session, const char *element_id,
    double *out_voltage_v) {
  if (session == nullptr || !valid_text(element_id) ||
      out_voltage_v == nullptr) {
    return invalid("session, element id, and out_voltage are required");
  }
  return guard(
      [&] { *out_voltage_v = session->value.element_voltage(element_id); });
}

spikes_error_code spikes_transient_session_element_current(
    const spikes_transient_session *session, const char *element_id,
    double *out_current_a) {
  if (session == nullptr || !valid_text(element_id) || out_current_a == nullptr) {
    return invalid("session, element id, and current output are required");
  }
  return guard([&] {
    *out_current_a = session->value.element_current(element_id);
  });
}

spikes_error_code spikes_transient_session_element_power(
    const spikes_transient_session *session, const char *element_id,
    double *out_power_w) {
  if (session == nullptr || !valid_text(element_id) || out_power_w == nullptr) {
    return invalid("session, element id, and power output are required");
  }
  return guard([&] { *out_power_w = session->value.element_power(element_id); });
}

spikes_error_code spikes_transient_session_diagnostics(
    const spikes_transient_session *session, size_t *out_completed_steps,
    size_t *out_matrix_factorizations, size_t *out_newton_iterations,
    double *out_residual_inf_norm) {
  if (session == nullptr || out_completed_steps == nullptr ||
      out_matrix_factorizations == nullptr || out_newton_iterations == nullptr ||
      out_residual_inf_norm == nullptr) {
    return invalid("session and all diagnostic outputs are required");
  }
  const auto &diagnostics = session->value.diagnostics();
  *out_completed_steps = diagnostics.completed_steps;
  *out_matrix_factorizations = diagnostics.matrix_factorizations;
  *out_newton_iterations = diagnostics.total_newton_iterations;
  *out_residual_inf_norm = diagnostics.residual_inf_norm;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_factorization_diagnostics(
    const spikes_transient_session *session, size_t *out_factorization_reuses,
    size_t *out_cache_entries) {
  if (session == nullptr || out_factorization_reuses == nullptr ||
      out_cache_entries == nullptr) {
    return invalid("session and all factorization outputs are required");
  }
  const auto &diagnostics = session->value.diagnostics();
  *out_factorization_reuses = diagnostics.factorization_reuses;
  *out_cache_entries = diagnostics.factorization_cache_entries;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_integration_diagnostics(
    const spikes_transient_session *session, size_t *out_backward_euler_steps,
    size_t *out_trapezoidal_steps) {
  if (session == nullptr || out_backward_euler_steps == nullptr ||
      out_trapezoidal_steps == nullptr) {
    return invalid("session and all integration outputs are required");
  }
  const auto &diagnostics = session->value.diagnostics();
  *out_backward_euler_steps = diagnostics.backward_euler_steps;
  *out_trapezoidal_steps = diagnostics.trapezoidal_steps;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_bdf2_steps(
    const spikes_transient_session *session, size_t *out_bdf2_steps) {
  if (session == nullptr || out_bdf2_steps == nullptr) {
    return invalid("session and BDF2-step output are required");
  }
  *out_bdf2_steps = session->value.diagnostics().bdf2_steps;
  last_error.clear();
  return SPIKES_OK;
}

spikes_error_code spikes_transient_session_checkpoint_create(
    const spikes_transient_session *session,
    spikes_transient_checkpoint **out_checkpoint) {
  if (session == nullptr || out_checkpoint == nullptr) {
    return invalid("session and checkpoint output are required");
  }
  *out_checkpoint = nullptr;
  return guard([&] {
    *out_checkpoint = new spikes_transient_checkpoint(
        session->value.checkpoint(), session->token);
  });
}

void spikes_transient_checkpoint_destroy(
    spikes_transient_checkpoint *checkpoint) {
  delete checkpoint;
}

spikes_error_code spikes_transient_session_restore(
    spikes_transient_session *session,
    const spikes_transient_checkpoint *checkpoint) {
  if (session == nullptr || checkpoint == nullptr) {
    return invalid("session and checkpoint are required");
  }
  if (session->token != checkpoint->owner_token) {
    return invalid("checkpoint belongs to a different persistent session");
  }
  return guard([&] { session->value.restore(checkpoint->value); });
}

} // extern "C"
