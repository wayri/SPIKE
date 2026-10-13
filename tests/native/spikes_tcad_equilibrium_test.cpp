// SPDX-License-Identifier: Apache-2.0
// Original analytical/manufactured oracles. No external solver/source fixtures.
#include "spikes/tcad_equilibrium.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace {
using spikes::tcad::Config;
using spikes::tcad::Result;
using spikes::tcad::solve;
constexpr double q = 1.602176634e-19, kb = 1.380649e-23, eps0 = 8.8541878128e-12;
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
void near(double actual, double expected, double absolute, const char* message) {
    require(std::isfinite(actual) && std::abs(actual - expected) <= absolute, message);
}
Config base(int count = 201) {
    Config c;
    c.grid_points = count; c.length_m = 1e-6;
    c.relative_permittivity = 11.7; c.temperature_k = 300.;
    c.intrinsic_density_m3 = 1e16; c.net_doping_m3.assign(count, 0.);
    c.residual_tolerance = 1e-11;
    return c;
}
void admitted(const Result& r) {
    if (!r.converged) std::cerr << "Nonconvergence: " << r.status << " residual=" << r.residual_norm
                              << " iterations=" << r.accepted_iterations << '\n';
    require(r.converged && r.status == "converged", "Expected converged state");
    require(r.residual_norm <= r.config.residual_tolerance, "Residual admission");
    require(r.residual_history.size() == static_cast<std::size_t>(r.accepted_iterations+1), "Accepted history count");
    for (std::size_t i = 1; i < r.residual_history.size(); ++i)
        require(r.residual_history[i] < r.residual_history[i-1], "Residual must decrease");
    require(r.config.net_doping_m3.size() == r.potential_v.size(), "Full provenance");
}
void rejected(const Config& c) {
    try { solve(c); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Invalid input was not rejected");
}
void homogeneous() {
    for (double doping : {0., -1e21, 1e21}) {
        auto c = base();
        std::fill(c.net_doping_m3.begin(), c.net_doping_m3.end(), doping);
        const auto r = solve(c); admitted(r);
        const double phi = kb*c.temperature_k/q*std::asinh(doping/(2.*c.intrinsic_density_m3));
        for (int i = 0; i < c.grid_points; ++i) {
            near(r.potential_v[i], phi, 2e-14, "Homogeneous exact potential");
            near(r.electric_field_v_per_m[i], 0., 1e-6, "Homogeneous zero field");
            near((r.electron_density_m3[i] - r.hole_density_m3[i]) / std::max(c.intrinsic_density_m3,std::abs(doping)),
                 doping/std::max(c.intrinsic_density_m3,std::abs(doping)), 1e-13, "Homogeneous neutrality");
            near((r.electron_density_m3[i]/c.intrinsic_density_m3)*(r.hole_density_m3[i]/c.intrinsic_density_m3),
                 1., 3e-14, "Equilibrium mass action");
        }
    }
}
void gauss(const Result& r) {
    const auto& c = r.config;
    const double eps = eps0*c.relative_permittivity, h = r.spacing_m;
    double integrated_charge = 0.;
    for (int i = 1; i < c.grid_points-1; ++i) {
        const double divergence = eps*(r.face_electric_field_v_per_m[i] - r.face_electric_field_v_per_m[i-1])/h;
        near((divergence-r.charge_density_c_per_m3[i])/r.residual_scale_c_per_m3,
             0., c.residual_tolerance*1.2+1e-12, "Local discrete Gauss law");
        integrated_charge += r.charge_density_c_per_m3[i]*h;
    }
    // Interior control volumes extend from the first face to the last face;
    // contacts are Dirichlet reservoirs, not solved charge-volume equations.
    const double flux = eps*(r.face_electric_field_v_per_m.back()-r.face_electric_field_v_per_m.front());
    near((flux-integrated_charge)/(r.residual_scale_c_per_m3*c.length_m),
         0., c.residual_tolerance*1.2+1e-12, "Integrated discrete Gauss law");
}
Config pn() {
    auto c = base(401);
    c.length_m = 2e-6;
    for (int i = 0; i < c.grid_points; ++i)
        c.net_doping_m3[i] = i < 200 ? -1e21 : i == 200 ? 0. : 1e21;
    return c;
}
void junction() {
    auto c = pn();
    const auto r = solve(c); admitted(r); gauss(r);
    const double vt = kb*c.temperature_k/q;
    const double built_in = 2.*vt*std::asinh(1e21/(2.*c.intrinsic_density_m3));
    near(r.potential_v.back()-r.potential_v.front(), built_in, 2e-14, "PN built-in contact difference");
    for (int i = 0; i < c.grid_points; ++i) {
        near(r.potential_v[i], -r.potential_v[c.grid_points-1-i], 2e-11, "PN antisymmetric potential");
        if (i > 0) require(r.potential_v[i] >= r.potential_v[i-1]-1e-12, "PN monotone potential");
    }
    c.max_iterations = 1;
    const auto partial = solve(c);
    require(!partial.converged && partial.status == "iteration_limit", "Iteration limit is not success");
    require(partial.accepted_iterations == 1 && partial.residual_norm > c.residual_tolerance, "Retain last accepted iteration");
    std::cout << "PN: iterations=" << r.accepted_iterations << " normalized_residual=" << r.residual_norm << '\n';
}
void explicit_contacts_and_small_grid() {
    // Independent single-unknown oracle: with zero doping and opposite
    // boundaries, the center is exactly neutral by odd symmetry.
    auto c = base(3);
    c.relative_permittivity = 4.2; c.temperature_k = 420.;
    c.intrinsic_density_m3 = 3e18;
    c.left_potential_v = -.08; c.right_potential_v = .08;
    auto r = solve(c); admitted(r); gauss(r);
    near(r.potential_v[1], 0., 1e-15, "Three-node exact center");
    near(r.potential_v.front(), -.08, 1e-15, "Explicit left contact");
    near(r.potential_v.back(), .08, 1e-15, "Explicit right contact");
    near(r.electric_field_v_per_m[1], -.16/c.length_m, 1e-8, "Three-node exact field");
    // Asymmetric contact charge checks that global Gauss is not merely passing
    // by cancellation in the antisymmetric PN fixture.
    c = base(65); c.left_potential_v = .03; c.right_potential_v = .08;
    c.intrinsic_density_m3 = 1e20;
    r = solve(c); admitted(r); gauss(r);
    require(r.charge_density_c_per_m3[32] < 0., "Electron accumulation charge sign");
}
double manufactured(int count, double& field_error) {
    auto c = base(count);
    c.length_m = 1e-6; c.intrinsic_density_m3 = 1e20;
    c.left_potential_v = 0.; c.right_potential_v = 0.;
    const double vt = kb*c.temperature_k/q, eps = eps0*c.relative_permittivity;
    const double amplitude = .04, wave = std::numbers::pi/c.length_m;
    // phi=A sin(pi*x/L); doping=(n-p)-eps*phi''/q gives an exact
    // CONTINUOUS Poisson-Boltzmann solution, independent of the discretization.
    for (int i = 0; i < count; ++i) {
        const double phi = amplitude*std::sin(std::numbers::pi*i/(count-1));
        c.net_doping_m3[i] = 2.*c.intrinsic_density_m3*std::sinh(phi/vt) + eps*wave*wave*phi/q;
    }
    const auto r = solve(c); admitted(r); gauss(r);
    double error = 0.; field_error = 0.;
    for (int i = 0; i < count; ++i) {
        const double phi = amplitude*std::sin(std::numbers::pi*i/(count-1));
        error = std::max(error,std::abs(r.potential_v[i]-phi));
        if (i > 0) {
            const double exact_field = -amplitude*wave*std::cos(std::numbers::pi*(i-.5)/(count-1));
            field_error = std::max(field_error,std::abs(r.face_electric_field_v_per_m[i-1]-exact_field));
        }
    }
    return error;
}
void refinement() {
    double efield1 = 0., efield2 = 0., efield3 = 0.;
    const double e1 = manufactured(33,efield1), e2 = manufactured(65,efield2), e3 = manufactured(129,efield3);
    require(e1/e2 > 3.8 && e1/e2 < 4.2 && e2/e3 > 3.8 && e2/e3 < 4.2, "Second-order potential refinement");
    require(efield1/efield2 > 3.8 && efield1/efield2 < 4.2 && efield2/efield3 > 3.8 && efield2/efield3 < 4.2,
            "Second-order face-field refinement");
    require(e3 < 1e-6 && efield3 < 10., "Fine-grid independent solution accuracy");
    std::cout << "Manufactured potential errors (V): " << e1 << ", " << e2 << ", " << e3
              << "; field errors (V/m): " << efield1 << ", " << efield2 << ", " << efield3 << '\n';
}
void invalid_inputs() {
    auto c = base(); c.net_doping_m3.pop_back(); rejected(c);
    c = base(); c.grid_points = 2; rejected(c);
    c = base(); c.grid_points = 100002; rejected(c);
    c = base(); c.length_m = 0.; rejected(c);
    c = base(); c.relative_permittivity = -1.; rejected(c);
    c = base(); c.temperature_k = 0.; rejected(c);
    c = base(); c.intrinsic_density_m3 = -1.; rejected(c);
    c = base(); c.net_doping_m3[6] = std::numeric_limits<double>::quiet_NaN(); rejected(c);
    c = base(); c.left_potential_v = std::numeric_limits<double>::infinity(); rejected(c);
    c = base(); c.right_potential_v = 1e6; rejected(c);
    c = base(); c.max_iterations = 0; rejected(c);
    c = base(); c.max_iterations = 1001; rejected(c);
    c = base(); c.residual_tolerance = 1e-16; rejected(c);
    c = base(); c.length_m = 1e-100; rejected(c);
    c = base(); c.length_m = 1e100; rejected(c);
}
} // namespace

int main() {
    try {
        homogeneous(); junction(); explicit_contacts_and_small_grid(); refinement(); invalid_inputs();
        std::cout << "TCAD equilibrium native tests passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
