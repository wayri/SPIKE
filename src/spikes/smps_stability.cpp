// SPDX-License-Identifier: Apache-2.0
// Original SPIKE ideal switch-state derivation: docs/SPIKES_SMPS_STABILITY.md.
// Port of the SPIKE-owned analytical reference, not external implementation code.
#include "smps_stability.hpp"

#include <unsupported/Eigen/Polynomials>
#include <algorithm>
#include <cmath>
#include <numbers>
#include <stdexcept>

namespace spikes::smps {
namespace {
using Complex = std::complex<double>;
using Polynomial = std::vector<double>;
constexpr double tau = 2. * std::numbers::pi;
constexpr double degrees = 180. / std::numbers::pi;

double finite(double value) {
    if (!std::isfinite(value))
        throw std::invalid_argument("Derived values exceed the finite numerical envelope");
    return value;
}
void finite(Complex value) { finite(value.real()); finite(value.imag()); }
template <typename T> void finite_values(const T& values) {
    for (const auto& value : values) finite(value);
}
void trim(Polynomial& p) { while (p.size() > 1 && p.back() == 0.) p.pop_back(); }
Polynomial multiply(const Polynomial& a, const Polynomial& b) {
    Polynomial result(a.size() + b.size() - 1, 0.);
    for (std::size_t i = 0; i < a.size(); ++i)
        for (std::size_t j = 0; j < b.size(); ++j) result[i + j] += a[i] * b[j];
    trim(result);
    finite_values(result);
    return result;
}
Polynomial add(const Polynomial& a, const Polynomial& b) {
    Polynomial result(std::max(a.size(), b.size()), 0.);
    for (std::size_t i = 0; i < a.size(); ++i) result[i] += a[i];
    for (std::size_t i = 0; i < b.size(); ++i) result[i] += b[i];
    trim(result);
    finite_values(result);
    return result;
}
template <typename T> T evaluate(const Polynomial& p, T x) {
    T result{};
    for (auto i = p.rbegin(); i != p.rend(); ++i) result = result * x + static_cast<T>(*i);
    return result;
}
double max_abs(const Polynomial& p) {
    double result = 0.;
    for (double v : p) result = std::max(result, std::abs(v));
    return result;
}
std::vector<Complex> roots(Polynomial coefficients) {
    trim(coefficients);
    finite_values(coefficients);
    const double scale = max_abs(coefficients);
    if (scale == 0.) throw std::invalid_argument("Nonfinite or degenerate polynomial");
    for (double& v : coefficients) v /= scale;
    if (coefficients.size() == 1) return {};
    std::vector<Complex> result;
    if (coefficients.size() == 2) {
        result.emplace_back(-coefficients[0] / coefficients[1], 0.);
    } else {
        Eigen::VectorXd values(static_cast<Eigen::Index>(coefficients.size()));
        for (std::size_t i = 0; i < coefficients.size(); ++i)
            values[static_cast<Eigen::Index>(i)] = coefficients[i];
        Eigen::PolynomialSolver<double, Eigen::Dynamic> solver;
        solver.compute(values);
        for (const auto& root : solver.roots()) result.push_back(root);
    }
    Polynomial absolute = coefficients;
    for (double& v : absolute) v = std::abs(v);
    for (Complex root : result) {
        finite(root);
        const auto residual = evaluate(coefficients, std::complex<long double>(root));
        const auto bound = evaluate(absolute, static_cast<long double>(std::abs(root)));
        if (!std::isfinite(bound) || !std::isfinite(std::abs(residual)) ||
            std::abs(residual) > 1e-7L * bound)
            throw std::invalid_argument("Polynomial roots failed backward-error check");
    }
    std::sort(result.begin(), result.end(), [](Complex a, Complex b) {
        return a.real() == b.real() ? a.imag() < b.imag() : a.real() < b.real();
    });
    return result;
}
std::vector<double> positive_roots(const Polynomial& coefficients) {
    std::vector<double> result;
    for (Complex r : roots(coefficients)) {
        if (r.real() > 0. && std::abs(r.imag()) <= 1e-7 * r.real() &&
            (result.empty() || std::abs(r.real() / result.back() - 1.) > 1e-6))
            result.push_back(r.real());
    }
    return result;
}

// Coefficients of N(jx)conj(D(jx)), independently expanded in ascending order.
std::vector<Complex> conjugate_product(const Polynomial& n, const Polynomial& d) {
    static constexpr std::array<Complex, 4> powers{{{1., 0.}, {0., 1.}, {-1., 0.}, {0., -1.}}};
    std::vector<Complex> result(n.size() + d.size() - 1);
    for (std::size_t i = 0; i < n.size(); ++i)
        for (std::size_t j = 0; j < d.size(); ++j)
            result[i + j] += n[i] * d[j] * powers[i % 4] * std::conj(powers[j % 4]);
    finite_values(result);
    return result;
}
struct Phase {
    double n0, b_voltage, a, b;
    std::vector<double> zeros_hz, poles_hz;
    double plant(double omega) const {
        return degrees * (std::atan2(b_voltage * omega, n0) - std::atan2(a * omega, b - omega * omega));
    }
    double loop(double omega) const {
        double angle = plant(omega) - 90.;
        for (double f : zeros_hz) angle += degrees * std::atan(omega / (tau * f));
        for (double f : poles_hz) angle -= degrees * std::atan(omega / (tau * f));
        return angle;
    }
};
void crossings(Result& r, const Config& c, const Phase& phase) {
    const auto nn = conjugate_product(r.loop_numerator, r.loop_numerator);
    const auto dd = conjugate_product(r.loop_denominator, r.loop_denominator);
    const auto nd = conjugate_product(r.loop_numerator, r.loop_denominator);
    Polynomial magnitude, imaginary;
    for (std::size_t i = 0; i < std::max(nn.size(), dd.size()); i += 2)
        magnitude.push_back((i < nn.size() ? nn[i].real() : 0.) - (i < dd.size() ? dd[i].real() : 0.));
    for (std::size_t i = 1; i < nd.size(); i += 2) imaginary.push_back(nd[i].imag());
    for (int kind = 0; kind < 2; ++kind) {
        const auto& coefficients = kind == 0 ? magnitude : imaginary;
        if (max_abs(coefficients) == 0.)
            throw std::invalid_argument("Degenerate continuum of loop crossings");
        for (double squared : positive_roots(coefficients)) {
            const double x = std::sqrt(squared);
            const double omega = finite(x * r.omega_scale_rad_s);
            const Complex response = evaluate(r.loop_numerator, Complex(0., x)) /
                evaluate(r.loop_denominator, Complex(0., x));
            finite(response);
            Crossing item;
            item.frequency_hz = finite(omega / tau);
            item.in_sweep = item.frequency_hz >= c.start_hz && item.frequency_hz <= c.stop_hz;
            item.below_averaging_limit = item.frequency_hz <= c.switching_frequency_hz / 10.;
            if (kind == 0) {
                if (std::abs(std::abs(response) - 1.) > 1e-5)
                    throw std::invalid_argument("Gain crossing failed response residual check");
                item.phase_deg = finite(phase.loop(omega));
                item.phase_margin_deg = finite(180. + item.phase_deg);
                r.gain_crossings.push_back(item);
            } else {
                if (std::abs(response.imag()) > 1e-5 * std::abs(response))
                    throw std::invalid_argument("Phase crossing failed response residual check");
                if (response.real() >= 0.) continue;
                item.gain_db = finite(20. * std::log10(std::abs(response)));
                item.gain_margin_db = -item.gain_db;
                r.phase_crossings.push_back(item);
            }
        }
    }
}
} // namespace

void validate(const Config& c) {
    if (c.topology < 0 || c.topology > 3 || c.controller_type < 0 || c.controller_type > 2)
        throw std::invalid_argument("Unsupported topology or controller type");
    if (c.points < 3 || c.points > 10000)
        throw std::invalid_argument("points must be an integer in 3..10000");
    for (double value : {c.input_voltage_v, c.duty_cycle, c.inductance_h, c.capacitance_f,
            c.load_resistance_ohm, c.switching_frequency_hz, c.turns_ratio, c.start_hz,
            c.stop_hz, c.controller_gain, c.zero1_hz, c.zero2_hz, c.pole1_hz, c.pole2_hz,
            c.feedback_gain, c.pwm_gain}) {
        if (!std::isfinite(value) || value < 1e-12 || value > 1e12)
            throw std::invalid_argument("Configuration numbers must be finite and in [1e-12, 1e12]");
    }
    if (c.duty_cycle < 1e-6 || c.duty_cycle > 1. - 1e-6)
        throw std::invalid_argument("duty_cycle must be in [1e-6, 1-1e-6]");
    if (c.start_hz >= c.stop_hz) throw std::invalid_argument("start_hz must be less than stop_hz");
    if (c.topology != 3 && c.turns_ratio != 1.)
        throw std::invalid_argument("turns_ratio is Ns/Np and applies only to flyback");
}

Result analyze(const Config& c) {
    validate(c);
    Result r;
    const double vin = c.input_voltage_v, d = c.duty_cycle, l = c.inductance_h;
    const double cap = c.capacitance_f, resistance = c.load_resistance_ohm;
    const double coupling = c.topology == 0 ? 1. : (1. - d) / c.turns_ratio;
    r.output_voltage_v = finite((c.topology == 1 ? vin : vin * d) / coupling);
    const double v = r.output_voltage_v;
    r.inductor_current_a = finite(v / (resistance * coupling));
    const double current = r.inductor_current_a;
    const double slope = (c.topology == 0 ? vin - v : vin) / l;
    r.inductor_ripple_pp_a = finite(slope * d / c.switching_frequency_hz);
    const double ripple = r.inductor_ripple_pp_a;
    r.valley_current_a = finite(current - ripple / 2.);
    if (r.valley_current_a <= 1e-9 * std::max(current, ripple))
        throw std::invalid_argument("CCM not admissible: estimated inductor/magnetizing valley current is nonpositive or at the boundary");
    r.peak_current_a = finite(current + ripple / 2.);
    const double b_current = finite((c.topology == 0 ? vin : c.topology == 1 ? v : vin + v / c.turns_ratio) / l);
    const double b_voltage = c.topology == 0 ? 0. : finite(-current / (c.turns_ratio * cap));
    const double a = finite(1. / (resistance * cap));
    r.omega_scale_rad_s = finite(coupling / std::sqrt(l * cap));
    const double omega_scale = r.omega_scale_rad_s, b = finite(omega_scale * omega_scale);
    const double n0 = finite(coupling * b_current / cap);
    r.plant_numerator = {finite(n0 / b), finite(b_voltage / omega_scale)};
    r.plant_denominator = {1., finite(a / omega_scale), 1.};
    Phase phase{n0, b_voltage, a, b, {c.zero1_hz}, {}};
    if (c.controller_type != 0) phase.poles_hz.push_back(c.pole1_hz);
    if (c.controller_type == 2) { phase.zeros_hz.push_back(c.zero2_hz); phase.poles_hz.push_back(c.pole2_hz); }
    Polynomial breakpoints{a, omega_scale};
    for (double f : phase.zeros_hz) breakpoints.push_back(tau * f);
    for (double f : phase.poles_hz) breakpoints.push_back(tau * f);
    const auto [lo, hi] = std::minmax_element(breakpoints.begin(), breakpoints.end());
    if (*hi / *lo > 1e10)
        throw std::invalid_argument("Model time scales exceed the 1e10 numerical conditioning envelope");
    Polynomial controller_num{c.controller_gain / omega_scale}, controller_den{0., 1.};
    for (double f : phase.zeros_hz) controller_num = multiply(controller_num, {1., omega_scale / (tau * f)});
    for (double f : phase.poles_hz) controller_den = multiply(controller_den, {1., omega_scale / (tau * f)});
    r.loop_numerator = multiply(r.plant_numerator, controller_num);
    for (double& value : r.loop_numerator) value = finite(value * c.feedback_gain * c.pwm_gain);
    r.loop_denominator = multiply(r.plant_denominator, controller_den);
    const double scale = std::max(max_abs(r.loop_numerator), max_abs(r.loop_denominator));
    for (double& value : r.loop_numerator) value /= scale;
    for (double& value : r.loop_denominator) value /= scale;
    r.closed_loop_denominator = add(r.loop_denominator, r.loop_numerator);
    r.closed_loop_poles_rad_s = roots(r.closed_loop_denominator);
    r.stability = "stable";
    for (Complex& pole : r.closed_loop_poles_rad_s) {
        pole *= omega_scale;
        finite(pole);
        const double tolerance = 1e-8 * std::max(omega_scale, std::abs(pole));
        if (pole.real() > tolerance) r.stability = "unstable";
        else if (pole.real() >= -tolerance && r.stability != "unstable") r.stability = "marginal_or_unresolved";
    }
    r.plant_poles_rad_s = roots(r.plant_denominator);
    r.plant_zeros_rad_s = roots(r.plant_numerator);
    for (auto* poles : {&r.plant_poles_rad_s, &r.plant_zeros_rad_s})
        for (Complex& pole : *poles) { pole *= omega_scale; finite(pole); }
    for (auto* curve : {&r.frequency_hz, &r.plant_gain_db, &r.plant_phase_deg, &r.loop_gain_db, &r.loop_phase_deg}) curve->reserve(c.points);
    r.plant.reserve(c.points); r.loop.reserve(c.points);
    const double log_start = std::log(c.start_hz), log_span = std::log(c.stop_hz) - log_start;
    for (int i = 0; i < c.points; ++i) {
        const double f = i == 0 ? c.start_hz : i == c.points - 1 ? c.stop_hz : std::exp(log_start + log_span * i / (c.points - 1));
        const double omega = tau * f;
        const Complex x(0., omega / omega_scale);
        const Complex plant = evaluate(r.plant_numerator, x) / evaluate(r.plant_denominator, x);
        const Complex loop = evaluate(r.loop_numerator, x) / evaluate(r.loop_denominator, x);
        finite(plant); finite(loop);
        r.frequency_hz.push_back(f);
        r.plant.push_back(plant); r.loop.push_back(loop);
        r.plant_gain_db.push_back(finite(20. * std::log10(std::abs(plant))));
        r.loop_gain_db.push_back(finite(20. * std::log10(std::abs(loop))));
        r.plant_phase_deg.push_back(finite(phase.plant(omega)));
        r.loop_phase_deg.push_back(finite(phase.loop(omega)));
    }
    crossings(r, c, phase);
    if (c.stop_hz > c.switching_frequency_hz / 10.)
        r.warnings.emplace_back("Sweep exceeds fs/10: high-frequency averaged response is illustrative, not switching-loop evidence.");
    if (std::any_of(r.gain_crossings.begin(), r.gain_crossings.end(), [](const Crossing& x) { return !x.below_averaging_limit; }))
        r.warnings.emplace_back("A unity crossing exceeds fs/10; model stability cannot establish switching-loop stability.");
    if (ripple / current > .5)
        r.warnings.emplace_back("Inductor ripple exceeds 50% of its average; small-ripple averaging accuracy is unverified.");
    r.output_ripple_pp_v_estimate = finite(c.topology == 0 ? ripple / (8. * c.switching_frequency_hz * cap) : v * d / (resistance * c.switching_frequency_hz * cap));
    if (r.output_ripple_pp_v_estimate > .05 * v)
        r.warnings.emplace_back("Estimated capacitor ripple exceeds 5% of output; constant-voltage ripple/CCM estimates need switched verification.");
    r.output_polarity = c.topology == 2 ? -1 : 1;
    r.output_current_a = finite(v / resistance); r.output_power_w = finite(v * v / resistance);
    r.reference_voltage_v = finite(c.feedback_gain * v);
    r.a_per_s = {{{0., finite(-coupling / l)}, {finite(coupling / cap), -a}}};
    r.b_duty_per_s = {b_current, b_voltage};
    r.plant_dc_gain_v_per_duty = r.plant_numerator[0];
    return r;
}
} // namespace spikes::smps
