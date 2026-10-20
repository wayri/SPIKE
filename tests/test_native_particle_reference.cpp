// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "kinetic_reference.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <string>

namespace {
using namespace spike::particles;
int checks = 0;
void require(bool ok, const char* message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
void relative(double actual, long double expected, long double tolerance, const char* message) {
    require(std::abs(static_cast<long double>(actual)-expected) <=
            tolerance * std::abs(expected), message);
}
template<class Operation> void rejected(Operation operation, const char* message) {
    bool failed = false;
    try { operation(); } catch (const std::exception&) { failed = true; }
    require(failed, message);
}
void kinematic_oracle(double mass, double energy) {
    const auto r = relativistic_kinematics(mass, energy);
    const long double c = 299792458.0L, m = mass, k = energy;
    // Independent energy-momentum identity, not the dimensionless-u kernel.
    const long double momentum = std::sqrt(k * (k + 2*m*c*c)) / c;
    const long double speed = momentum*c*c / (k + m*c*c);
    relative(r.momentum_kg_mps, momentum, 1e-14L, "independent momentum oracle");
    relative(r.speed_mps, speed, 1e-14L, "independent speed oracle");
    require(r.speed_mps > 0 && r.speed_mps < speed_of_light_mps, "subluminal kinematics");
    relative(*r.de_broglie_m, 6.62607015e-34L/momentum, 1e-14L, "de Broglie oracle");
    const long double p = r.momentum_kg_mps;
    const long double reconstructed = p*p*c*c / (std::hypot(p*c, m*c*c) + m*c*c);
    relative(static_cast<double>(reconstructed), k, 1e-14L, "kinetic energy reconstruction");
}
void kinematics() {
    const auto rest = relativistic_kinematics(electron_mass_kg, 0);
    require(rest.gamma == 1 && rest.momentum_kg_mps == 0 && rest.speed_mps == 0 &&
            !rest.de_broglie_m.has_value(), "rest wavelength undefined");
    kinematic_oracle(electron_mass_kg, 200000 * elementary_charge_c);
    kinematic_oracle(electron_mass_kg, elementary_charge_c);
    kinematic_oracle(1e-26, 1e-16); // Synthetic supplied ion mass, not atomic data.
    kinematic_oracle(1e-32, 1e-12);
    kinematic_oracle(1e-20, 1e-6);
    kinematic_oracle(electron_mass_kg, 1e-32);
    for (double mass : {1e-32, electron_mass_kg, 1e-26, 1e-20})
        for (double energy : {1e-200, 1e-100, 1e-20, 1e-14})
            kinematic_oracle(mass, energy);
    const auto low = relativistic_kinematics(electron_mass_kg, 1e-32);
    relative(low.speed_mps, std::sqrt(2e-32L / electron_mass_kg), 1e-14L,
             "nonrelativistic low-energy limit");
    const auto tem = relativistic_kinematics(electron_mass_kg, 200000*elementary_charge_c);
    require(tem.speed_mps > 2e8 && tem.speed_mps < 2.1e8 &&
            *tem.de_broglie_m > 2.5e-12 && *tem.de_broglie_m < 2.6e-12,
            "200 keV scale sanity, not microscope validation");
}
void electrostatic() {
    const auto electron = electrostatic_energy(0, -elementary_charge_c, 0, 200000);
    relative(electron.final_kinetic_j, 200000.0L*elementary_charge_c, 1e-15L, "electron potential sign");
    const auto ion = electrostatic_energy(0, elementary_charge_c, 200000, 0);
    relative(ion.final_kinetic_j, electron.final_kinetic_j, 1e-15L, "positive charge sign");
    const auto unchanged = electrostatic_energy(1e-14, elementary_charge_c, 12, 12);
    require(unchanged.work_j == 0 && unchanged.final_kinetic_j == 1e-14, "equal potentials");
    const double charge = std::ldexp(1.0, -50), work = std::ldexp(1.0, -40);
    const auto balance = electrostatic_energy(work, charge, 0, 1024);
    require(balance.exact_zero_balance && balance.final_kinetic_j == 0, "exact represented balance");
    rejected([=]{electrostatic_energy(work/2,charge,0,1024);}, "turning point rejected");
    rejected([=]{electrostatic_energy(std::nextafter(work, INFINITY),charge,0,1024);},
             "positive unresolved cancellation rejected");
    const auto resolved = electrostatic_energy(work*(1+1e-10),charge,0,1024);
    require(resolved.final_kinetic_j > 0 && !resolved.exact_zero_balance, "resolved cancellation accepted");
    const double sub = std::numeric_limits<double>::denorm_min();
    rejected([=]{electrostatic_energy(0,sub,0.25,0);}, "positive work underflow rejected");
    rejected([=]{electrostatic_energy(0,sub,1.5,0);}, "rounded subnormal work rejected");
    rejected([=]{electrostatic_energy(2*sub,sub,0,1.5);}, "unresolved subnormal cancellation rejected");
}
void gas_and_beam() {
    const double p = 1, t = 300, m = 1e-26, d = 3e-10, length = 0.01;
    const auto g = dilute_hard_sphere_gas(p,t,m,d,length);
    const long double density = 1.0L/(1.380649e-23L*300);
    const long double mean_speed = std::sqrt(8*1.380649e-23L*300/(std::numbers::pi_v<long double>*m));
    const long double free_path = 1/(std::sqrt(2.0L)*density*std::numbers::pi_v<long double>*d*d);
    relative(g.number_density_m3,density,1e-14L,"ideal gas density oracle");
    relative(g.mean_speed_mps,mean_speed,1e-14L,"classical mean-speed oracle");
    relative(g.mean_free_path_m,free_path,1e-14L,"gas path oracle");
    relative(g.mean_collision_time_s,free_path/mean_speed,1e-14L,"gas collision-time oracle");
    relative(g.knudsen_number,free_path/length,1e-14L,"Knudsen oracle");
    require(g.thermal_to_rest_ratio <= classical_temperature_ratio_cap,
            "declared classical applicability cap");
    rejected([]{dilute_hard_sphere_gas(1,1e6,1e-32,1e-12,1);},
             "nonclassical thermal ratio rejected despite dilute packing");
    const auto doubled = dilute_hard_sphere_gas(2*p,t,m,d,length);
    relative(doubled.mean_free_path_m,g.mean_free_path_m/2,1e-14L,"pressure reciprocal path");
    relative(doubled.mean_collision_time_s,g.mean_collision_time_s/2,1e-14L,"pressure reciprocal time");
    relative(doubled.knudsen_number,g.knudsen_number/2,1e-14L,"pressure reciprocal Kn");
    const auto beam = stationary_target_beam(g.number_density_m3,std::numbers::pi*d*d,g.mean_speed_mps,length);
    relative(beam.mean_free_path_m/g.mean_free_path_m,std::sqrt(2.0L),1e-14L,"stationary vs thermal sqrt2");
    relative(beam.mean_collision_time_s/g.mean_collision_time_s,std::sqrt(2.0L),1e-14L,"stationary vs thermal time");
    const auto tiny = stationary_target_beam(1,1e-30,1,1);
    require(tiny.collision_probability > 0 && tiny.uncollided_probability == 1,
            "tiny collision probability retained");
    relative(tiny.collision_probability,1e-30L,1e-14L,"tiny probability oracle");
    const auto ordinary = stationary_target_beam(1e20,1e-20,2e5,0.25);
    relative(ordinary.collision_probability,-std::expm1(-0.25L),1e-14L,"finite collision oracle");
    relative(ordinary.uncollided_probability,std::exp(-0.25L),1e-14L,"uncollided oracle");
    const auto zero = stationary_target_beam(1,1e-30,1,0);
    require(zero.collision_probability == 0 && zero.uncollided_probability == 1 && !zero.saturated,
            "zero path");
    const auto opaque = stationary_target_beam(1e32,1e-10,1,1e6);
    require(opaque.saturated && opaque.collision_probability == 1 && opaque.uncollided_probability == 0 &&
            opaque.saturation_probability_error_bound == 1e-300,"explicit opacity bound");
    const auto below_opaque = stationary_target_beam(1e20,1e-20,1,699);
    require(!below_opaque.saturated && below_opaque.uncollided_probability > 0,
            "survival remains resolved below opacity cutoff");
    relative(below_opaque.uncollided_probability,std::exp(-699.0L),1e-12L,
             "near-opaque independent survival");
    const auto cutoff = stationary_target_beam(1e20,1e-20,1,700);
    require(cutoff.saturated && cutoff.uncollided_probability == 0 &&
            std::exp(-700.0L) < cutoff.saturation_probability_error_bound,
            "opaque boundary approximation is bounded");
    rejected([]{dilute_hard_sphere_gas(1e9,1,1e-26,1e-7,1);},"dense gas excluded");
    const double sub = std::numeric_limits<double>::denorm_min();
    rejected([=]{stationary_target_beam(1e-30,1e-40,sub,1);},"unrepresentable collision time");
    rejected([=]{stationary_target_beam(1e-30,1e-40,1,sub);},"unrepresentable optical depth");
}
void invalid() {
    const double nan = std::numeric_limits<double>::quiet_NaN(), inf = std::numeric_limits<double>::infinity();
    for (double value : {nan, inf, -1.0, 0.0, 1e-33, 1e-19})
        rejected([=]{relativistic_kinematics(value,1e-20);},"mass admission");
    for (double value : {nan, inf, -1.0, 1e-5})
        rejected([=]{relativistic_kinematics(electron_mass_kg,value);},"energy admission");
    rejected([]{relativistic_kinematics(1e-32,1e-6);},"ratio cap");
    for (double value : {nan, inf, 0.0, 1e-14})
        rejected([=]{electrostatic_energy(0,value,0,1);},"charge admission");
    for (double value : {nan, inf, -1e10, 1e10}) {
        rejected([=]{electrostatic_energy(0,elementary_charge_c,value,0);},"start voltage admission");
        rejected([=]{electrostatic_energy(0,elementary_charge_c,0,value);},"end voltage admission");
    }
    rejected([]{electrostatic_energy(1e-6,1e-15,1e9,0);},"final energy cap");
    for (double value : {nan, inf, -1.0, 0.0}) {
        rejected([=]{dilute_hard_sphere_gas(value,300,1e-26,1e-10,1);},"pressure admission");
        rejected([=]{dilute_hard_sphere_gas(1,value,1e-26,1e-10,1);},"temperature admission");
        rejected([=]{dilute_hard_sphere_gas(1,300,value,1e-10,1);},"gas mass admission");
        rejected([=]{dilute_hard_sphere_gas(1,300,1e-26,value,1);},"diameter admission");
        rejected([=]{dilute_hard_sphere_gas(1,300,1e-26,1e-10,value);},"gas length admission");
        rejected([=]{stationary_target_beam(value,1e-20,1,1);},"scatterer density admission");
        rejected([=]{stationary_target_beam(1,value,1,1);},"cross-section admission");
        rejected([=]{stationary_target_beam(1,1e-20,value,1);},"beam velocity admission");
    }
    for (double value : {nan, inf, -1.0, 1e7})
        rejected([=]{stationary_target_beam(1,1e-20,1,value);},"beam path admission");
    rejected([]{stationary_target_beam(1,1e-20,speed_of_light_mps,1);},"luminal beam excluded");
}
} // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2,"optional argument is a JSON summary path");
        kinematics(); electrostatic(); gas_and_beam(); invalid();
        const std::string summary = "{\"contract\":\"spike/native-particle-reference-test/v1\","
            "\"status\":\"passed\",\"checks\":" + std::to_string(checks) +
            ",\"production_qualified\":false,\"gas_cross_sections\":\"synthetic_supplied\","
            "\"electron_mass_source\":\"CODATA2022\",\"opaque_optical_depth\":700,"
            "\"classical_temperature_ratio_cap\":1e-4}\n";
        if (argc == 2) {
            const std::filesystem::path path(argv[1]);
            const auto parent = path.has_parent_path() ? path.parent_path() : std::filesystem::current_path();
            if (!std::filesystem::is_directory(parent)) throw std::runtime_error("summary parent must exist");
            std::ofstream output(path,std::ios::out|std::ios::trunc);
            if (!output) throw std::runtime_error("cannot open summary output");
            output << summary;
            output.close();
            if (!output) throw std::runtime_error("cannot complete summary output");
        }
        std::cout << summary;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native particle reference failed: " << error.what() << '\n';
        return 1;
    }
}
