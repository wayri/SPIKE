// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <optional>

namespace spike::particles {
inline constexpr double speed_of_light_mps = 299792458.0;
inline constexpr double planck_js = 6.62607015e-34;
inline constexpr double boltzmann_jpk = 1.380649e-23;
inline constexpr double elementary_charge_c = 1.602176634e-19;
inline constexpr double electron_mass_kg = 9.1093837139e-31; // CODATA 2022.
inline constexpr double dilute_packing_cap = 1e-4;
inline constexpr double classical_temperature_ratio_cap = 1e-4;
inline constexpr double opaque_optical_depth = 700;

struct Kinematics {
    double kinetic_to_rest_ratio = 0;
    double gamma = 1; // May round to one for extremely small positive energy.
    double momentum_kg_mps = 0;
    double speed_mps = 0;
    std::optional<double> de_broglie_m; // Undefined at exactly zero momentum.
};
// Free-particle kinematics, not charged trajectories or electron imaging.
Kinematics relativistic_kinematics(double mass_kg, double kinetic_j);

struct ElectrostaticEnergy {
    double initial_kinetic_j = 0;
    double potential_difference_v = 0;
    double work_j = 0;
    double final_kinetic_j = 0;
    double cancellation_scale_j = 0;
    double resolution_fraction = 1;
    bool exact_zero_balance = false;
};
// Signed work only; a negative final energy requires a turning trajectory,
// which is not implemented. Unresolved cancellation is rejected, not clamped.
ElectrostaticEnergy electrostatic_energy(double initial_kinetic_j, double charge_c,
                                        double start_v, double end_v);

struct HardSphereGas {
    double number_density_m3 = 0;
    double mean_speed_mps = 0;
    double mean_free_path_m = 0;
    double mean_collision_time_s = 0;
    double knudsen_number = 0;
    double packing_fraction = 0;
    double thermal_to_rest_ratio = 0;
};
// Classical equilibrium identical hard spheres, ideal EOS and dilute cap.
// Also requires k_B*T/(m*c*c)<=1e-4, a declared conservative applicability
// cutoff, not a physical error guarantee or validation of chemical species.
// Not a pressure-only continuum classifier or a relativistic/real-gas EOS.
HardSphereGas dilute_hard_sphere_gas(double pressure_pa, double temperature_k,
    double mass_kg, double diameter_m, double length_m);

struct StationaryBeam {
    double mean_free_path_m = 0;
    double mean_collision_time_s = 0;
    double optical_depth = 0;
    double collision_probability = 0;
    double uncollided_probability = 1;
    bool saturated = false;
    double saturation_probability_error_bound = 0;
};
// Supplied cross section, independent homogeneous stationary scatterers.
// No thermal sqrt(2), collision directions, chemistry or secondary particles.
StationaryBeam stationary_target_beam(double number_density_m3, double cross_section_m2,
    double speed_mps, double path_m);
} // namespace spike::particles
