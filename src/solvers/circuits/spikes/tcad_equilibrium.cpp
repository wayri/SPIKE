// SPDX-License-Identifier: Apache-2.0
// Clean-room finite-volume derivation; no external implementation was used.
#include "tcad_equilibrium.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace spikes::tcad {
namespace {
constexpr double q = 1.602176634e-19; // C, exact SI elementary charge
constexpr double kb = 1.380649e-23; // J/K, exact SI Boltzmann constant
constexpr double eps0 = 8.8541878128e-12; // F/m, CODATA 2018
constexpr double minimum_coefficient = 1e-14;
constexpr double maximum_coefficient = 1e12;

bool positive(double v) { return std::isfinite(v) && v > 0.; }
void admit(bool yes, const char* text) {
    if (!yes) throw std::invalid_argument(text);
}
double neutral_u(double doping, double ni) {
    // Admission rejects unrepresentable ratios, without modifying the input.
    const double ratio = (doping / ni) * .5;
    admit(std::isfinite(ratio), "TCAD doping/intrinsic-density ratio is not representable");
    return std::asinh(ratio);
}
bool carriers(double u, double log_ni, double& n, double& p) {
    // Keep every returned carrier normal, finite and strictly positive. This is
    // a representability guard, not a nondegenerate-statistics validity test.
    const double a = log_ni + u, b = log_ni - u;
    if (!std::isfinite(a) || !std::isfinite(b) ||
        a < -700. || a > 700. || b < -700. || b > 700.) return false;
    n = std::exp(a); p = std::exp(b);
    return positive(n) && positive(p);
}
struct Scales {
    double vt, h, density, charge, a, log_ni;
};
Scales scales(const Config& c) {
    Scales s{};
    s.vt = (kb / q) * c.temperature_k;
    s.h = c.length_m / (c.grid_points - 1);
    s.density = c.intrinsic_density_m3;
    for (double d : c.net_doping_m3) s.density = std::max(s.density, std::abs(d));
    s.charge = q * s.density;
    s.a = (eps0 * c.relative_permittivity / s.charge) * (s.vt / s.h) / s.h;
    s.log_ni = std::log(c.intrinsic_density_m3);
    return s;
}
bool evaluate(const Config& c, const Scales& s, const std::vector<double>& u,
              std::vector<double>& residual, std::vector<double>& derivative,
              double& norm) {
    norm = 0.;
    for (int i = 0; i < c.grid_points; ++i) {
        double n = 0., p = 0.;
        if (!carriers(u[i], s.log_ni, n, p)) return false;
        if (i == 0 || i == c.grid_points - 1) continue;
        // -div(epsilon grad(phi)) - rho = 0, divided by q*density.
        // u=phi/Vt gives a strictly positive tridiagonal Newton Jacobian.
        residual[i-1] = s.a * ((u[i] - u[i-1]) + (u[i] - u[i+1]))
            + (n / s.density - p / s.density) - c.net_doping_m3[i] / s.density;
        derivative[i-1] = 2. * s.a + n / s.density + p / s.density;
        if (!std::isfinite(residual[i-1]) || !positive(derivative[i-1])) return false;
        norm = std::max(norm, std::abs(residual[i-1]));
    }
    return true;
}
bool newton_step(double a, const std::vector<double>& r,
                 const std::vector<double>& diagonal, std::vector<double>& step) {
    // Thomas elimination for the positive-definite Dirichlet Jacobian. Positive
    // pivots and finite intermediates are checked; no pivot repair is allowed.
    std::vector<double> upper(r.size(), 0.);
    double pivot = diagonal[0];
    if (!positive(pivot)) return false;
    upper[0] = -a / pivot;
    step[0] = -r[0] / pivot;
    for (std::size_t i = 1; i < r.size(); ++i) {
        pivot = diagonal[i] + a * upper[i-1];
        if (!positive(pivot)) return false;
        upper[i] = -a / pivot;
        step[i] = (-r[i] + a * step[i-1]) / pivot;
        if (!std::isfinite(step[i]) || !std::isfinite(upper[i])) return false;
    }
    for (std::size_t i = r.size() - 1; i > 0; --i) step[i-1] -= upper[i-1] * step[i];
    return std::all_of(step.begin(), step.end(), [](double v) { return std::isfinite(v); });
}
} // namespace

void validate(const Config& c) {
    admit(c.grid_points >= 3 && c.grid_points <= 100001, "TCAD requires 3..100001 grid points");
    admit(c.net_doping_m3.size() == static_cast<std::size_t>(c.grid_points),
          "TCAD doping count must equal grid_points");
    admit(positive(c.length_m) && positive(c.relative_permittivity) &&
          positive(c.temperature_k) && positive(c.intrinsic_density_m3),
          "TCAD length, relative permittivity, temperature and intrinsic density must be finite and positive");
    admit(c.max_iterations >= 1 && c.max_iterations <= 1000, "TCAD requires 1..1000 Newton iterations");
    admit(std::isfinite(c.residual_tolerance) && c.residual_tolerance >= 1e-13 &&
          c.residual_tolerance <= 1e-3, "TCAD normalized residual tolerance must lie in [1e-13,1e-3]");
    for (double d : c.net_doping_m3) admit(std::isfinite(d), "TCAD doping must be finite");
    const auto s = scales(c);
    admit(positive(s.vt) && positive(s.h) && positive(s.charge) && positive(s.a) &&
          s.a >= minimum_coefficient && s.a <= maximum_coefficient,
          "TCAD scaled spatial coefficient outside supported [1e-14,1e12] conditioning range");
    double n = 0., p = 0.;
    for (double d : c.net_doping_m3)
        admit(carriers(neutral_u(d, c.intrinsic_density_m3), s.log_ni, n, p),
              "TCAD inferred neutral carrier density outside supported exponent range [-700,700]");
    for (const auto contact : {c.left_potential_v, c.right_potential_v}) {
        if (contact) admit(std::isfinite(*contact) && carriers(*contact / s.vt, s.log_ni, n, p),
                           "TCAD contact potential/carrier density not representable");
    }
}

Result solve(const Config& c) {
    validate(c);
    const auto s = scales(c);
    Result result;
    result.config = c;
    result.thermal_voltage_v = s.vt;
    result.spacing_m = s.h;
    result.residual_scale_c_per_m3 = s.charge;
    const auto count = static_cast<std::size_t>(c.grid_points);
    std::vector<double> u(count), trial(count), r(count-2), d(count-2);
    std::vector<double> trial_r(count-2), trial_d(count-2), step(count-2);
    for (std::size_t i = 0; i < count; ++i) u[i] = neutral_u(c.net_doping_m3[i], c.intrinsic_density_m3);
    if (c.left_potential_v) u.front() = *c.left_potential_v / s.vt;
    if (c.right_potential_v) u.back() = *c.right_potential_v / s.vt;
    double norm = 0.;
    admit(evaluate(c, s, u, r, d, norm), "TCAD initial residual is not representable");
    result.residual_history.push_back(norm);
    result.status = "iteration_limit";
    result.diagnostic = "Newton iteration limit reached; refine inputs or increase the bounded iteration budget";
    while (norm > c.residual_tolerance && result.accepted_iterations < c.max_iterations) {
        if (!newton_step(s.a, r, d, step)) {
            result.status = "numerical_failure";
            result.diagnostic = "Nonfinite or nonpositive Newton elimination pivot; revise conditioning";
            break;
        }
        bool accepted = false;
        double fraction = 1.;
        for (int attempt = 0; attempt < 40; ++attempt, fraction *= .5) {
            trial = u;
            for (std::size_t i = 1; i + 1 < count; ++i) trial[i] += fraction * step[i-1];
            double candidate = 0.;
            if (evaluate(c, s, trial, trial_r, trial_d, candidate) &&
                (candidate <= c.residual_tolerance || candidate <= norm * (1. - 1e-4 * fraction))) {
                u.swap(trial); r.swap(trial_r); d.swap(trial_d);
                norm = candidate;
                accepted = true;
                ++result.accepted_iterations;
                result.residual_history.push_back(norm);
                break;
            }
        }
        if (!accepted) {
            result.status = "line_search_failed";
            result.diagnostic = "No finite residual-decreasing trial in 40 halvings; last accepted state retained";
            break;
        }
    }
    result.converged = norm <= c.residual_tolerance;
    if (result.converged) {
        result.status = "converged";
        result.diagnostic = "Algebraic equilibrium residual met; mesh accuracy and material validity require separate review";
    }
    result.residual_norm = norm;
    result.residual_charge_c_per_m3 = norm * s.charge;
    result.x_m.resize(count); result.potential_v.resize(count);
    result.electron_density_m3.resize(count); result.hole_density_m3.resize(count);
    result.charge_density_c_per_m3.resize(count);
    result.electric_field_v_per_m.resize(count);
    result.face_electric_field_v_per_m.resize(count-1);
    for (std::size_t i = 0; i < count; ++i) {
        result.x_m[i] = i * s.h;
        result.potential_v[i] = u[i] * s.vt;
        carriers(u[i], s.log_ni, result.electron_density_m3[i], result.hole_density_m3[i]);
        result.charge_density_c_per_m3[i] = q * result.hole_density_m3[i]
            - q * result.electron_density_m3[i] + q * c.net_doping_m3[i];
        if (i > 0) result.face_electric_field_v_per_m[i-1] = -(u[i] - u[i-1]) * (s.vt / s.h);
    }
    result.electric_field_v_per_m.front() = result.face_electric_field_v_per_m.front();
    result.electric_field_v_per_m.back() = result.face_electric_field_v_per_m.back();
    for (std::size_t i = 1; i + 1 < count; ++i)
        result.electric_field_v_per_m[i] = .5 * result.face_electric_field_v_per_m[i-1]
            + .5 * result.face_electric_field_v_per_m[i];
    // Inputs can be finite while derived SI output overflows (for example an
    // extreme length/temperature combination). Never emit a successful result
    // containing infinities, even when the dimensionless solve converged.
    admit(std::isfinite(result.residual_charge_c_per_m3), "TCAD SI residual is not representable");
    for (const auto* values : {&result.x_m, &result.potential_v,
                              &result.electric_field_v_per_m, &result.face_electric_field_v_per_m,
                              &result.charge_density_c_per_m3})
        admit(std::all_of(values->begin(), values->end(), [](double v) { return std::isfinite(v); }),
              "TCAD derived SI output is not representable");
    return result;
}
} // namespace spikes::tcad
