// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <optional>
#include <string>
#include <vector>

namespace spikes::tcad {

// Original bounded 1D equilibrium Poisson-Boltzmann model, all inputs SI.
// Uniform material, fully ionized net doping ND-NA, nondegenerate carriers,
// one constant Fermi level. Explicit contact values are electrostatic boundary
// values at that same Fermi level, NOT applied-bias transport conditions.
struct Config {
    double length_m = 0.;
    double relative_permittivity = 0.;
    double temperature_k = 0.;
    double intrinsic_density_m3 = 0.;
    int grid_points = 201;
    std::vector<double> net_doping_m3;
    std::optional<double> left_potential_v, right_potential_v;
    int max_iterations = 100;
    double residual_tolerance = 1e-10;
};

struct Result {
    Config config; // Exact user inputs, including omitted/inferred contacts.
    bool converged = false;
    std::string status, diagnostic;
    int accepted_iterations = 0;
    double thermal_voltage_v = 0., spacing_m = 0.;
    // Residual infinity norm divided by q*max(ni,max(abs(ND-NA))).
    // This is a nonlinear algebraic residual, NOT a mesh-error estimate.
    double residual_scale_c_per_m3 = 0., residual_norm = 0.;
    double residual_charge_c_per_m3 = 0.;
    std::vector<double> x_m, potential_v, electric_field_v_per_m;
    std::vector<double> face_electric_field_v_per_m;
    std::vector<double> electron_density_m3, hole_density_m3;
    std::vector<double> charge_density_c_per_m3, residual_history;
};

// Invalid inputs/unsupported floating-point conditioning throw invalid_argument.
// Newton failure returns the last accepted state with converged=false.
// The current bound is 3..100001 nodes, 1..1000 Newton iterations, and at most
// 40 trial halvings per iteration. No exponent or physical density is clamped.
void validate(const Config& config);
Result solve(const Config& config);

} // namespace spikes::tcad
