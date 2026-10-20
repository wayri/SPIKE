// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "kinetic_reference.hpp"

#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace spike::particles {
namespace {
void bounded(double value, double lower, double upper, const char* name) {
    if (!std::isfinite(value) || value < lower || value > upper)
        throw std::invalid_argument(name);
}
void positive(double value, const char* name) {
    if (!std::isfinite(value) || value <= 0)
        throw std::runtime_error(name);
}
// Error-free residual for subtraction of finite bounded binary inputs.
double subtraction_error(double a, double b, double difference) {
    const double neg_b = -b;
    const double recovered_b = difference - a;
    return (a - (difference - recovered_b)) + (neg_b - recovered_b);
}
} // namespace

Kinematics relativistic_kinematics(double mass_kg, double kinetic_j) {
    bounded(mass_kg, 1e-32, 1e-20, "mass outside admitted range");
    bounded(kinetic_j, 0, 1e-6, "kinetic energy outside admitted range");
    const double rest_j = mass_kg * speed_of_light_mps * speed_of_light_mps;
    Kinematics r;
    r.kinetic_to_rest_ratio = kinetic_j / rest_j;
    bounded(r.kinetic_to_rest_ratio, 0, 1e6, "kinetic/rest ratio exceeds admitted range");
    if (kinetic_j == 0) return r;
    positive(r.kinetic_to_rest_ratio, "unrepresentable positive kinetic/rest ratio");
    const double u = r.kinetic_to_rest_ratio;
    const double momentum_factor = std::sqrt(u * (u + 2));
    r.gamma = 1 + u;
    r.momentum_kg_mps = mass_kg * speed_of_light_mps * momentum_factor;
    r.speed_mps = speed_of_light_mps * (momentum_factor / r.gamma);
    r.de_broglie_m = planck_js / r.momentum_kg_mps;
    positive(r.momentum_kg_mps, "unrepresentable positive momentum");
    positive(r.speed_mps, "unrepresentable positive speed");
    positive(*r.de_broglie_m, "unrepresentable positive wavelength");
    if (!(r.speed_mps < speed_of_light_mps))
        throw std::runtime_error("speed must remain below light speed");
    return r;
}

ElectrostaticEnergy electrostatic_energy(double initial_kinetic_j, double charge_c,
                                        double start_v, double end_v) {
    bounded(initial_kinetic_j, 0, 1e-6, "initial kinetic energy outside admitted range");
    bounded(charge_c, -1e-15, 1e-15, "charge outside admitted range");
    if (charge_c == 0) throw std::invalid_argument("charge must be nonzero");
    bounded(start_v, -1e9, 1e9, "start potential outside admitted range");
    bounded(end_v, -1e9, 1e9, "end potential outside admitted range");
    ElectrostaticEnergy r;
    r.initial_kinetic_j = initial_kinetic_j;
    r.potential_difference_v = start_v - end_v;
    const double difference_error = subtraction_error(start_v, end_v, r.potential_difference_v);
    r.work_j = charge_c * r.potential_difference_v;
    if (start_v != end_v && std::abs(r.work_j) < std::numeric_limits<double>::min())
        throw std::runtime_error("nonzero electrostatic work underflows normal precision");
    const double product_error = std::fma(charge_c, r.potential_difference_v, -r.work_j);
    r.final_kinetic_j = std::fma(charge_c, r.potential_difference_v, initial_kinetic_j);
    r.final_kinetic_j = std::fma(charge_c, difference_error, r.final_kinetic_j);
    r.work_j = std::fma(charge_c, difference_error, r.work_j);
    r.cancellation_scale_j = initial_kinetic_j + std::abs(r.work_j);
    // An FMA residual below the subnormal floor cannot prove exactness. The
    // conservative floor below keeps all product residual bits representable.
    const bool exactness_resolved = start_v == end_v || std::abs(r.work_j) >= 0x1p-968;
    // Accept a zero only when both represented work operations are exact.
    r.exact_zero_balance = r.final_kinetic_j == 0 && difference_error == 0 &&
        product_error == 0 && initial_kinetic_j == -r.work_j && exactness_resolved;
    if (!std::isfinite(r.final_kinetic_j) || r.final_kinetic_j < 0 || r.final_kinetic_j > 1e-6)
        throw std::runtime_error("final energy out of bounds; turning trajectories unsupported");
    if (r.cancellation_scale_j > 0) {
        r.resolution_fraction = r.final_kinetic_j / r.cancellation_scale_j;
        if (!r.exact_zero_balance &&
            r.resolution_fraction <= 64 * std::numeric_limits<double>::epsilon())
            throw std::runtime_error("electrostatic energy cancellation unresolved");
    }
    return r;
}

HardSphereGas dilute_hard_sphere_gas(double pressure_pa, double temperature_k,
    double mass_kg, double diameter_m, double length_m) {
    bounded(pressure_pa, 1e-20, 1e9, "pressure outside admitted range");
    bounded(temperature_k, 1, 1e6, "temperature outside admitted range");
    bounded(mass_kg, 1e-32, 1e-20, "gas mass outside admitted range");
    bounded(diameter_m, 1e-12, 1e-7, "diameter outside admitted range");
    bounded(length_m, 1e-12, 1e6, "length outside admitted range");
    HardSphereGas r;
    r.thermal_to_rest_ratio = boltzmann_jpk * temperature_k /
        (mass_kg * speed_of_light_mps * speed_of_light_mps);
    if (r.thermal_to_rest_ratio > classical_temperature_ratio_cap)
        throw std::invalid_argument("gas exceeds declared classical temperature ratio cap");
    r.number_density_m3 = pressure_pa / (boltzmann_jpk * temperature_k);
    r.mean_speed_mps = std::sqrt(8 * boltzmann_jpk * temperature_k /
        (std::numbers::pi * mass_kg));
    r.mean_free_path_m = 1 / (std::numbers::sqrt2 * r.number_density_m3 *
        std::numbers::pi * diameter_m * diameter_m);
    r.mean_collision_time_s = r.mean_free_path_m / r.mean_speed_mps;
    r.knudsen_number = r.mean_free_path_m / length_m;
    r.packing_fraction = std::numbers::pi * r.number_density_m3 *
        diameter_m * diameter_m * diameter_m / 6;
    for (double value : {r.number_density_m3, r.mean_speed_mps, r.mean_free_path_m,
                        r.mean_collision_time_s, r.knudsen_number, r.packing_fraction,
                        r.thermal_to_rest_ratio})
        positive(value, "unrepresentable positive hard-sphere result");
    if (r.packing_fraction > dilute_packing_cap)
        throw std::invalid_argument("hard-sphere packing exceeds declared dilute cap");
    return r;
}

StationaryBeam stationary_target_beam(double number_density_m3, double cross_section_m2,
    double speed_mps, double path_m) {
    bounded(number_density_m3, 1e-30, 1e32, "scatterer density outside admitted range");
    bounded(cross_section_m2, 1e-40, 1e-10, "cross section outside admitted range");
    bounded(speed_mps, 0, speed_of_light_mps, "beam speed outside admitted range");
    if (!(speed_mps > 0 && speed_mps < speed_of_light_mps))
        throw std::invalid_argument("beam speed must be positive and subluminal");
    bounded(path_m, 0, 1e6, "path outside admitted range");
    StationaryBeam r;
    const double inverse_path = number_density_m3 * cross_section_m2;
    r.mean_free_path_m = 1 / inverse_path;
    r.mean_collision_time_s = r.mean_free_path_m / speed_mps;
    r.optical_depth = inverse_path * path_m;
    positive(r.mean_free_path_m, "unrepresentable positive beam free path");
    positive(r.mean_collision_time_s, "unrepresentable positive beam collision time");
    if (path_m > 0) positive(r.optical_depth, "unrepresentable positive beam optical depth");
    r.saturated = r.optical_depth >= opaque_optical_depth;
    if (r.saturated) {
        r.collision_probability = 1;
        r.uncollided_probability = 0;
        r.saturation_probability_error_bound = 1e-300; // exp(-700) < bound.
    } else {
        r.collision_probability = -std::expm1(-r.optical_depth);
        r.uncollided_probability = std::exp(-r.optical_depth);
        if (path_m > 0) positive(r.collision_probability, "unrepresentable collision probability");
        positive(r.uncollided_probability, "unrepresentable uncollided probability");
    }
    if (std::abs(r.collision_probability + r.uncollided_probability - 1) > 1e-12)
        throw std::runtime_error("beam probability closure failed");
    return r;
}
} // namespace spike::particles
