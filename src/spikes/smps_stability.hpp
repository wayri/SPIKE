// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <array>
#include <complex>
#include <string>
#include <vector>

namespace spikes::smps {

// SI inputs. Enum codes form the native transport contract.
struct Config {
    int topology = 0; // buck, boost, buck_boost, flyback
    int controller_type = 1; // pi, type_ii, type_iii
    int points = 401;
    double input_voltage_v = 24., duty_cycle = .5, inductance_h = 100e-6;
    double capacitance_f = 470e-6, load_resistance_ohm = 6.;
    double switching_frequency_hz = 100000., turns_ratio = 1.;
    double start_hz = 1., stop_hz = 10000., controller_gain = 100.;
    double zero1_hz = 100., zero2_hz = 1000.;
    double pole1_hz = 10000., pole2_hz = 20000.;
    double feedback_gain = 1., pwm_gain = 1.;
};

struct Crossing {
    double frequency_hz = 0.;
    bool in_sweep = false, below_averaging_limit = false;
    double phase_deg = 0., phase_margin_deg = 0.; // gain crossing
    double gain_db = 0., gain_margin_db = 0.; // phase crossing
};

struct Result {
    std::vector<double> frequency_hz, plant_gain_db, plant_phase_deg;
    std::vector<double> loop_gain_db, loop_phase_deg;
    std::vector<std::complex<double>> plant, loop;
    double output_voltage_v = 0., output_current_a = 0., output_power_w = 0.;
    int output_polarity = 1;
    double inductor_current_a = 0., reference_voltage_v = 0.;
    double inductor_ripple_pp_a = 0., valley_current_a = 0., peak_current_a = 0.;
    double output_ripple_pp_v_estimate = 0.;
    std::array<std::array<double, 2>, 2> a_per_s{};
    std::array<double, 2> b_duty_per_s{};
    double plant_dc_gain_v_per_duty = 0., omega_scale_rad_s = 0.;
    std::vector<std::complex<double>> plant_poles_rad_s, plant_zeros_rad_s;
    std::vector<std::complex<double>> closed_loop_poles_rad_s;
    std::vector<double> plant_numerator, plant_denominator;
    std::vector<double> loop_numerator, loop_denominator, closed_loop_denominator;
    std::vector<Crossing> gain_crossings, phase_crossings;
    std::string stability;
    std::vector<std::string> warnings;
};

// Invalid, DCM/boundary, ill-conditioned and nonfinite cases throw invalid_argument.
// No switching-loop or hardware validation is implied by successful completion.
void validate(const Config& config);
Result analyze(const Config& config);

} // namespace spikes::smps
