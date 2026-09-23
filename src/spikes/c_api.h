/**
 * @file c_api.h
 * @brief Stable C ownership boundary for the SPIKES Phase-1 kernel.
 */

#ifndef SPIKES_C_API_H
#define SPIKES_C_API_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(SPIKES_SHARED)
#if defined(SPIKES_BUILDING_LIBRARY)
#define SPIKES_API __declspec(dllexport)
#else
#define SPIKES_API __declspec(dllimport)
#endif
#else
#define SPIKES_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

/*
 * ABI version 1 is retained for additive symbol growth. Existing layouts and
 * function signatures have not changed. The independent transient contract
 * version guards the new options structure.
 */
#define SPIKES_ABI_VERSION 1u
#define SPIKES_TRANSIENT_API_VERSION 1u
#define SPIKES_LINEAR_SOLVER_API_VERSION 1u
#define SPIKES_LINEAR_SOLVER_AUTOMATIC 0u
#define SPIKES_LINEAR_SOLVER_DENSE_LU 1u
#define SPIKES_LINEAR_SOLVER_CONJUGATE_GRADIENT 2u
#define SPIKES_LINEAR_SOLVER_GMRES 3u
#define SPIKES_LINEAR_SOLVER_SPARSE_LU 4u
#define SPIKES_LINEAR_SOLVER_ILU_GMRES 5u
#define SPIKES_LINEAR_SOLVER_SPARSE_QR 6u
#define SPIKES_WBG_TECHNOLOGY_GAN_HEMT 0u
#define SPIKES_WBG_TECHNOLOGY_SIC_MOSFET 1u
#define SPIKES_WBG_FET_MODEL_API_VERSION 1u
/** Legacy/damping-oriented first-order integration. */
#define SPIKES_INTEGRATION_BACKWARD_EULER 0u
/** BE at startup/source breakpoints, trapezoidal between events. */
#define SPIKES_INTEGRATION_HYBRID_TRAPEZOIDAL 1u
/** Variable-step second-order backward differentiation with BE restarts. */
#define SPIKES_INTEGRATION_BDF2 2u

typedef struct spikes_circuit spikes_circuit;
typedef struct spikes_result spikes_result;
typedef struct spikes_transient_result spikes_transient_result;
typedef struct spikes_transient_session spikes_transient_session;
typedef struct spikes_transient_checkpoint spikes_transient_checkpoint;

typedef struct spikes_transient_options {
  uint32_t struct_version;
  size_t struct_size;
  double time_step_s;
  double stop_time_s;
  size_t max_steps;
  uint8_t initialize_from_operating_point;
  uint8_t reserved[7];
  size_t max_newton_iterations;
  size_t max_backtracks;
  double absolute_tolerance;
  double relative_tolerance;
} spikes_transient_options;

typedef struct spikes_linear_solver_options {
  uint32_t struct_version;
  size_t struct_size;
  uint32_t method;
  uint32_t reserved;
  size_t max_iterations;
  double absolute_tolerance;
  double relative_tolerance;
  size_t threads;
} spikes_linear_solver_options;

typedef struct spikes_pwl_point {
  double time_s;
  double value;
} spikes_pwl_point;

/** Additive ABI-v1 parameter block for the bounded native WBG DC model. */
typedef struct spikes_wbg_fet_electrothermal_model {
  uint32_t struct_version;
  uint32_t technology;
  size_t struct_size;
  uint32_t reserved;
  double threshold_voltage_v;
  double transconductance_a_per_v2;
  double channel_length_modulation_per_v;
  double mobility_temperature_exponent;
  double threshold_temperature_coefficient_v_per_k;
  double off_conductance_s;
  double reverse_conduction_threshold_v;
  double reverse_conductance_s;
  double body_diode_saturation_current_a;
  double body_diode_emission_coefficient;
  double breakdown_voltage_v;
  double breakdown_temperature_coefficient_v_per_k;
  double avalanche_current_scale_a;
  double avalanche_slope_v;
  double gate_leakage_conductance_s;
  double gate_source_capacitance_f;
  double gate_drain_capacitance_f;
  double drain_source_capacitance_f;
  double ambient_temperature_k;
  double thermal_resistance_k_per_w;
  double minimum_temperature_k;
  double maximum_temperature_k;
  double maximum_absolute_voltage_v;
  double maximum_absolute_current_a;
  /** Additive size-negotiated field; old ABI-v1 callers receive the default. */
  double thermal_capacitance_j_per_k;
} spikes_wbg_fet_electrothermal_model;

typedef enum spikes_error_code {
  SPIKES_OK = 0,
  SPIKES_INVALID_ARGUMENT = 1,
  SPIKES_NOT_FOUND = 2,
  SPIKES_ALLOCATION_FAILURE = 3,
  SPIKES_INTERNAL_ERROR = 4
} spikes_error_code;

/** Linear E/G/F/H source. Empty control_source selects voltage control. */
SPIKES_API spikes_error_code spikes_circuit_add_dependent_source(
    spikes_circuit*, const char*, const char*, const char*, int,
    const char*, const char*, const char*, double);
SPIKES_API spikes_error_code spikes_circuit_set_compact_charge(spikes_circuit*,const char*,double,double,double,double,double);
SPIKES_API spikes_error_code spikes_circuit_add_behavioral_source(spikes_circuit*,const char*,const char*,const char*,int,const char*,const char*);

typedef enum spikes_solve_status {
  SPIKES_SOLVE_CONVERGED = 0,
  SPIKES_SOLVE_SINGULAR = 1,
  SPIKES_SOLVE_NUMERICAL_FAILURE = 2
} spikes_solve_status;

/** Return the ABI version compiled into the library. */
SPIKES_API uint32_t spikes_abi_version(void);

/** The returned pointer remains valid until the next C-API call on this thread. */
SPIKES_API const char *spikes_last_error(void);

SPIKES_API spikes_error_code spikes_circuit_create(spikes_circuit **out_circuit);
SPIKES_API void spikes_circuit_destroy(spikes_circuit *circuit);

SPIKES_API spikes_error_code spikes_circuit_add_resistor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double resistance_ohm);
SPIKES_API spikes_error_code spikes_circuit_add_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double current_a);
SPIKES_API spikes_error_code spikes_circuit_add_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double voltage_v);
SPIKES_API spikes_error_code spikes_circuit_add_pulse_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double initial_value, double pulsed_value,
    double delay_s, double rise_time_s, double fall_time_s,
    double pulse_width_s, double period_s);
SPIKES_API spikes_error_code spikes_circuit_add_pulse_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double initial_value, double pulsed_value,
    double delay_s, double rise_time_s, double fall_time_s,
    double pulse_width_s, double period_s);
SPIKES_API spikes_error_code spikes_circuit_add_pwl_current_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const spikes_pwl_point *points,
    size_t point_count);
SPIKES_API spikes_error_code spikes_circuit_add_pwl_voltage_source(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const spikes_pwl_point *points,
    size_t point_count);
SPIKES_API spikes_error_code spikes_circuit_add_voltage_controlled_switch(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const char *control_positive_node,
    const char *control_negative_node, double on_resistance_ohm,
    double off_resistance_ohm, double threshold_voltage_v,
    double transition_voltage_v);
SPIKES_API spikes_error_code spikes_circuit_add_diode(
    spikes_circuit *circuit, const char *id, const char *anode_node,
    const char *cathode_node, double saturation_current_a,
    double emission_coefficient, double temperature_k);
/* Loads native code in-process. Caller must authenticate the artifact before use. */
SPIKES_API spikes_error_code spikes_circuit_add_trusted_osdi(
    spikes_circuit *circuit, const char *id, const char *artifact,
    const char *module, const char *terminals, const char *assignments);
SPIKES_API spikes_error_code spikes_circuit_add_dynamic_diode(
    spikes_circuit *circuit, const char *id, const char *anode_node,
    const char *cathode_node, double saturation_current_a,
    double emission_coefficient, double temperature_k,
    double transit_time_s, double junction_capacitance_f,
    double initial_stored_charge_c);
SPIKES_API spikes_error_code spikes_circuit_add_electrothermal_resistor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, const char *thermal_node,
    double resistance_ohm, double temperature_coefficient_per_k,
    double ambient_temperature_k, double thermal_resistance_k_per_w,
    double thermal_capacitance_j_per_k, double minimum_temperature_k,
    double maximum_temperature_k);
SPIKES_API spikes_error_code spikes_circuit_add_mosfet_level1(
    spikes_circuit *circuit, const char *id, const char *drain_node,
    const char *gate_node, const char *source_node, const char *bulk_node,
    double threshold_voltage_v, double transconductance_a_per_v2,
    double channel_length_modulation_per_v, double body_effect_sqrt_v,
    double surface_potential_v, double width_over_length,
    double off_conductance_s);
SPIKES_API spikes_error_code spikes_circuit_add_bjt_ebers_moll(
    spikes_circuit *circuit, const char *id, const char *collector_node,
    const char *base_node, const char *emitter_node,
    double saturation_current_a, double forward_alpha, double reverse_alpha,
    double emission_coefficient, double temperature_k);
SPIKES_API spikes_error_code spikes_wbg_fet_electrothermal_model_init(
    spikes_wbg_fet_electrothermal_model *out_model, uint32_t technology);
SPIKES_API spikes_error_code spikes_circuit_add_wbg_fet_electrothermal(
    spikes_circuit *circuit, const char *id, const char *drain_node,
    const char *gate_node, const char *source_node, const char *bulk_node,
    const char *thermal_node,
    const spikes_wbg_fet_electrothermal_model *model);
SPIKES_API spikes_error_code spikes_circuit_add_capacitor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double capacitance_f,
    double initial_voltage_v);
SPIKES_API spikes_error_code spikes_circuit_add_inductor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double inductance_h,
    double initial_current_a);
SPIKES_API spikes_error_code spikes_circuit_add_saturating_inductor(
    spikes_circuit *circuit, const char *id, const char *positive_node,
    const char *negative_node, double unsaturated_inductance_h,
    double saturated_inductance_h, double saturation_current_a,
    double initial_current_a);

SPIKES_API spikes_error_code spikes_solve_operating_point(
    const spikes_circuit *circuit, spikes_result **out_result);
SPIKES_API spikes_error_code spikes_linear_solver_options_init(
    spikes_linear_solver_options *out_options);
SPIKES_API spikes_error_code spikes_solve_operating_point_with_linear_solver(
    const spikes_circuit *circuit,
    const spikes_linear_solver_options *linear_options,
    spikes_result **out_result);
SPIKES_API void spikes_result_destroy(spikes_result *result);
SPIKES_API spikes_solve_status spikes_result_status(const spikes_result *result);
SPIKES_API const char *spikes_result_message(const spikes_result *result);

SPIKES_API spikes_error_code spikes_result_node_voltage(
    const spikes_result *result, const char *node_name, double *out_voltage_v);
SPIKES_API spikes_error_code spikes_result_element_current(
    const spikes_result *result, const char *element_id, double *out_current_a);
SPIKES_API spikes_error_code spikes_result_element_power(
    const spikes_result *result, const char *element_id, double *out_power_w);
SPIKES_API spikes_error_code spikes_result_diagnostics(
    const spikes_result *result, size_t *out_matrix_order,
    size_t *out_pivot_swaps, double *out_residual_inf_norm);
SPIKES_API spikes_error_code spikes_result_linear_solver_diagnostics(
    const spikes_result *result, uint32_t *out_method,
    size_t *out_iterations, size_t *out_threads);
/** Additive sparse-structure diagnostics; does not change ABI-v1 layouts. */
SPIKES_API spikes_error_code spikes_result_sparse_solver_diagnostics(
    const spikes_result *result, size_t *out_matrix_nonzeros,
    size_t *out_symbolic_analyses, size_t *out_numeric_factorizations);

/** Initialize a versioned transient-options structure with kernel defaults. */
SPIKES_API spikes_error_code
spikes_transient_options_init(spikes_transient_options *out_options);

SPIKES_API spikes_error_code spikes_solve_transient(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    spikes_transient_result **out_result);
/** Additive method-selecting solve; the legacy entry point remains BE. */
SPIKES_API spikes_error_code spikes_solve_transient_with_method(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, spikes_transient_result **out_result);
SPIKES_API spikes_error_code spikes_solve_transient_adaptive(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, uint8_t adaptive_time_step,
    double minimum_time_step_s, double lte_absolute_tolerance,
    double lte_relative_tolerance, size_t max_rejected_steps,
    spikes_transient_result **out_result);
SPIKES_API void
spikes_transient_result_destroy(spikes_transient_result *result);
SPIKES_API spikes_solve_status
spikes_transient_result_status(const spikes_transient_result *result);
SPIKES_API const char *
spikes_transient_result_message(const spikes_transient_result *result);
SPIKES_API size_t
spikes_transient_result_point_count(const spikes_transient_result *result);
SPIKES_API spikes_error_code spikes_transient_result_point_time(
    const spikes_transient_result *result, size_t point_index,
    double *out_time_s);
SPIKES_API spikes_error_code spikes_transient_result_node_voltage(
    const spikes_transient_result *result, size_t point_index,
    const char *node_name, double *out_voltage_v);
SPIKES_API spikes_error_code spikes_transient_result_element_current(
    const spikes_transient_result *result, size_t point_index,
    const char *element_id, double *out_current_a);
SPIKES_API spikes_error_code spikes_transient_result_element_power(
    const spikes_transient_result *result, size_t point_index,
    const char *element_id, double *out_power_w);
SPIKES_API spikes_error_code spikes_transient_result_diagnostics(
    const spikes_transient_result *result, size_t *out_matrix_order,
    size_t *out_completed_steps, size_t *out_total_newton_iterations,
    size_t *out_total_damping_steps, size_t *out_pivot_swaps,
    double *out_failed_time_s, double *out_residual_inf_norm);
SPIKES_API spikes_error_code spikes_transient_result_breakpoint_steps(
    const spikes_transient_result *result,
    size_t *out_source_breakpoint_steps);
SPIKES_API spikes_error_code spikes_transient_result_factorization_diagnostics(
    const spikes_transient_result *result, size_t *out_matrix_factorizations,
    size_t *out_factorization_reuses, size_t *out_cache_entries);
SPIKES_API spikes_error_code spikes_transient_result_integration_diagnostics(
    const spikes_transient_result *result, size_t *out_backward_euler_steps,
    size_t *out_trapezoidal_steps);
/** Additive BDF2 diagnostic; preserves the ABI-v1 integration diagnostic. */
SPIKES_API spikes_error_code spikes_transient_result_bdf2_steps(
    const spikes_transient_result *result, size_t *out_bdf2_steps);
SPIKES_API spikes_error_code spikes_transient_result_lte_diagnostics(
    const spikes_transient_result *result, size_t *out_rejected_steps,
    double *out_last_lte_ratio, double *out_minimum_accepted_step_s,
    double *out_maximum_accepted_step_s);
SPIKES_API spikes_error_code spikes_transient_result_sparse_lte_diagnostics(
    const spikes_transient_result *result, size_t *out_embedded_lte_solves,
    size_t *out_sparse_assemblies, size_t *out_sparse_symbolic_analyses,
    size_t *out_sparse_numeric_factorizations,
    size_t *out_partial_numeric_refactorizations);

/**
 * Create a persistent backward-Euler session from a copied circuit snapshot.
 * Session v1 advances constant/PULSE/PWL independent sources on a persistent
 * global clock. Only constant sources may be changed interactively.
 */
SPIKES_API spikes_error_code spikes_transient_session_create(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    spikes_transient_session **out_session);
/** Additive method-selecting persistent session; the legacy entry point is BE. */
SPIKES_API spikes_error_code spikes_transient_session_create_with_method(
    const spikes_circuit *circuit, const spikes_transient_options *options,
    uint32_t integration_method, spikes_transient_session **out_session);
SPIKES_API void
spikes_transient_session_destroy(spikes_transient_session *session);
SPIKES_API spikes_error_code spikes_transient_session_set_source_value(
    spikes_transient_session *session, const char *element_id, double value);
SPIKES_API spikes_error_code spikes_transient_session_step(
    spikes_transient_session *session, double step_s, uint8_t *out_accepted);
SPIKES_API spikes_solve_status spikes_transient_session_status(
    const spikes_transient_session *session);
SPIKES_API const char *spikes_transient_session_message(
    const spikes_transient_session *session);
SPIKES_API spikes_error_code spikes_transient_session_position(
    const spikes_transient_session *session, double *out_time_s,
    size_t *out_step_index);
SPIKES_API spikes_error_code spikes_transient_session_node_voltage(
    const spikes_transient_session *session, const char *node_name,
    double *out_voltage_v);
SPIKES_API spikes_error_code spikes_transient_session_element_voltage(
    const spikes_transient_session *session, const char *element_id,
    double *out_voltage_v);
SPIKES_API spikes_error_code spikes_transient_session_element_current(
    const spikes_transient_session *session, const char *element_id,
    double *out_current_a);
SPIKES_API spikes_error_code spikes_transient_session_element_power(
    const spikes_transient_session *session, const char *element_id,
    double *out_power_w);
SPIKES_API spikes_error_code spikes_transient_session_diagnostics(
    const spikes_transient_session *session, size_t *out_completed_steps,
    size_t *out_matrix_factorizations, size_t *out_newton_iterations,
    double *out_residual_inf_norm);
SPIKES_API spikes_error_code
spikes_transient_session_factorization_diagnostics(
    const spikes_transient_session *session, size_t *out_factorization_reuses,
    size_t *out_cache_entries);
SPIKES_API spikes_error_code spikes_transient_session_integration_diagnostics(
    const spikes_transient_session *session, size_t *out_backward_euler_steps,
    size_t *out_trapezoidal_steps);
SPIKES_API spikes_error_code spikes_transient_session_bdf2_steps(
    const spikes_transient_session *session, size_t *out_bdf2_steps);
SPIKES_API spikes_error_code spikes_transient_session_checkpoint_create(
    const spikes_transient_session *session,
    spikes_transient_checkpoint **out_checkpoint);
SPIKES_API void spikes_transient_checkpoint_destroy(
    spikes_transient_checkpoint *checkpoint);
SPIKES_API spikes_error_code spikes_transient_session_restore(
    spikes_transient_session *session,
    const spikes_transient_checkpoint *checkpoint);

#ifdef __cplusplus
}
#endif

#endif
