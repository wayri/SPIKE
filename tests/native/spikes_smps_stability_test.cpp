// SPDX-License-Identifier: Apache-2.0
// Original analytical oracles; no switched or hardware qualification implied.
#include "spikes/smps_stability.hpp"
#include <algorithm>
#include <cmath>
#include <complex>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace {
using spikes::smps::Config;
using spikes::smps::analyze;
using Complex = std::complex<double>;
constexpr double tau = 2. * std::numbers::pi;
void require(bool ok, const char* reason) { if (!ok) throw std::runtime_error(reason); }
template <typename T> void near(T actual, T expected, double tolerance, const char* reason) {
    require(std::abs(actual - expected) <= tolerance * std::max(1., std::abs(expected)), reason);
}
void rejected(const Config& c) {
    try { analyze(c); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Invalid model admitted");
}
Complex value(const std::vector<double>& p, Complex x) {
    Complex answer{};
    for (auto i = p.rbegin(); i != p.rend(); ++i) answer = answer * x + *i;
    return answer;
}
void topology_and_controller_oracles() {
    for (int topology = 0; topology < 4; ++topology) {
        for (int controller = 0; controller < 3; ++controller) {
            Config c;
            c.topology = topology; c.controller_type = controller;
            c.turns_ratio = topology == 3 ? 1.5 : 1.; c.duty_cycle = .4;
            c.feedback_gain = .2; c.pwm_gain = .4;
            const auto r = analyze(c);
            const double n = c.turns_ratio, q = 1. - c.duty_cycle;
            const double voltage = topology == 0 ? 9.6 : topology == 1 ? 40. : n * 16.;
            near(r.output_voltage_v, voltage, 1e-13, "DC conversion ratio");
            near(r.plant_dc_gain_v_per_duty, topology == 0 ? 24. : n * 24. / (q*q), 1e-13, "DC duty derivative");
            near(r.inductor_current_a * 24. * (topology == 1 ? 1. : .4), r.output_power_w, 1e-13, "Ideal power balance");
            near((r.plant_poles_rad_s[0] + r.plant_poles_rad_s[1]).real(), -1. / (6. * 470e-6), 1e-12, "Pole sum");
            const double k = topology == 0 ? 1. : q/n;
            near((r.plant_poles_rad_s[0] * r.plant_poles_rad_s[1]).real(), k*k / (100e-6*470e-6), 1e-12, "Pole product");
            if (topology == 0) require(r.plant_zeros_rad_s.empty(), "Buck has no finite zero");
            else near(r.plant_zeros_rad_s[0].real(), 6.*q*q/(100e-6*n*n*(topology == 1 ? 1. : .4)), 1e-12, "RHP zero sign and frequency");
            for (std::size_t i : {0u, 170u, 400u}) {
                const Complex s(0., tau * r.frequency_hz[i]);
                // Cramer's rule solves the retained two-state equations directly.
                const Complex determinant = (s-r.a_per_s[0][0]) * (s-r.a_per_s[1][1]) - r.a_per_s[0][1]*r.a_per_s[1][0];
                const Complex plant = (r.a_per_s[1][0]*r.b_duty_per_s[0] + (s-r.a_per_s[0][0])*r.b_duty_per_s[1]) / determinant;
                Complex comp = c.controller_gain/s*(1.+s/(tau*c.zero1_hz));
                if (controller != 0) comp /= 1.+s/(tau*c.pole1_hz);
                if (controller == 2) comp *= (1.+s/(tau*c.zero2_hz))/(1.+s/(tau*c.pole2_hz));
                near(r.plant[i], plant, 2e-12, "State-space response");
                near(r.loop[i], plant*comp*.08, 2e-12, "Controller factor response");
            }
        }
    }
}
void pole_classification_and_crossings() {
    for (double gain : {.1, 1., 100.}) {
        Config c; c.controller_type = 0; c.controller_gain = gain;
        const auto r = analyze(c);
        const double a = 1./(6.*470e-6), b = 1./(100e-6*470e-6);
        const double constant = 24.*b*gain, linear = b+24.*b*gain/(tau*100.);
        require(r.stability == (a*linear > constant ? "stable" : "unstable"), "Independent cubic Routh criterion");
        for (Complex p : r.closed_loop_poles_rad_s) {
            const auto residual = ((p+a)*p+linear)*p+constant;
            const double bound = ((std::abs(p)+a)*std::abs(p)+linear)*std::abs(p)+constant;
            require(std::abs(residual)/bound < 1e-12, "Dimensional pole polynomial residual");
        }
    }
    Config c; c.controller_gain = 5.; c.points = 10000;
    const auto fine = analyze(c);
    c.points = 3; c.start_hz = 10000.; c.stop_hz = 100000.;
    const auto coarse = analyze(c);
    require(fine.stability == "stable" && fine.gain_crossings.size() == 3, "Three unity crossings retained");
    require(coarse.gain_crossings.size() == fine.gain_crossings.size(), "Grid-independent crossings");
    require(coarse.phase_crossings.size() == fine.phase_crossings.size(), "Grid-independent phase crossings");
    for (std::size_t i = 0; i < fine.gain_crossings.size(); ++i) {
        const auto& g = fine.gain_crossings[i];
        require(g.frequency_hz == coarse.gain_crossings[i].frequency_hz, "Exact display-grid independence");
        const Complex x(0., tau*g.frequency_hz/fine.omega_scale_rad_s);
        near(std::abs(value(fine.loop_numerator,x)/value(fine.loop_denominator,x)), 1., 1e-10, "Unity crossing response residual");
        require(!coarse.gain_crossings[i].in_sweep, "Out-of-sweep crossings still reported");
    }
    for (const auto& g : fine.phase_crossings) {
        const Complex x(0.,tau*g.frequency_hz/fine.omega_scale_rad_s);
        const auto response = value(fine.loop_numerator,x)/value(fine.loop_denominator,x);
        require(response.real() < 0. && std::abs(response.imag()) < 1e-10, "Negative-real crossing residual");
    }
    // At the cubic Routh equality, the conjugate pair lies on the imaginary axis.
    c = {}; c.controller_type = 0;
    const double a = 1./(6.*470e-6);
    c.controller_gain = a/(24.*(1.-a/(tau*100.)));
    require(analyze(c).stability == "marginal_or_unresolved", "Marginal pole tolerance preserved");
}
void admission_and_scaling() {
    Config c;
    c.points = 2; rejected(c);
    c = {}; c.topology = 4; rejected(c);
    c = {}; c.controller_type = -1; rejected(c);
    c = {}; c.duty_cycle = 1.; rejected(c);
    c = {}; c.turns_ratio = 2.; rejected(c);
    c = {}; c.input_voltage_v = std::numeric_limits<double>::infinity(); rejected(c);
    c = {}; c.controller_gain = std::numeric_limits<double>::quiet_NaN(); rejected(c);
    c = {}; c.inductance_h = 15e-6; rejected(c);
    c = {}; c.load_resistance_ohm = 1e9; rejected(c);
    c = {}; c.zero1_hz = 1e-12; rejected(c);
    for (double power : {5., 1000., 1e6}) {
        c = {}; c.load_resistance_ohm = 144./power;
        c.inductance_h *= c.load_resistance_ohm/6.;
        c.capacitance_f *= 6./c.load_resistance_ohm;
        const auto r = analyze(c);
        near(r.output_power_w, power, 1e-13, "Mathematical power scaling");
    }
}
} // namespace
int main() {
    try {
        topology_and_controller_oracles(); pole_classification_and_crossings(); admission_and_scaling();
        std::cout << "Native ideal CCM SMPS analytical checks passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
