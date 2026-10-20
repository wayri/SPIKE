// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "planar_reference.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <string>

namespace {
int checks = 0;
void require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
void close(double actual, long double expected, long double tolerance,
           const char* message) {
    require(std::abs(static_cast<long double>(actual) - expected) <= tolerance, message);
}
template<class Operation> void rejected(Operation operation, const char* message) {
    bool failed = false;
    try { operation(); } catch (const std::exception&) { failed = true; }
    require(failed, message);
}
void interface_oracle(double n0, double n, double k, double wavelength, double depth) {
    const auto r = spike::optics::normal_interface(n0, n, k, wavelength, depth);
    // Independent scalar long-double expansion, not complex division or scaling.
    const long double a = n0, b = n, c = k;
    const long double denominator = (a+b)*(a+b) + c*c;
    const long double reflectance = ((a-b)*(a-b) + c*c) / denominator;
    const long double entry = 4*a*b / denominator;
    close(r.reflectance, reflectance, 2e-15L, "scalar reflection oracle");
    close(r.interface_entry_fraction, entry, 2e-15L * entry, "scalar entry oracle");
    const std::complex<double> transmitted(n, k);
    require(std::abs(1.0 + r.r - r.t) <= 1e-14, "tangential E continuity");
    const auto left = n0 * (1.0 - r.r), right = transmitted * r.t;
    const double boundary_scale = std::max({n0, std::abs(left), std::abs(right)});
    require(std::abs(left-right) / boundary_scale <= 1e-14, "tangential H continuity");
    const long double alpha = 4 * std::numbers::pi_v<long double> * c / wavelength;
    const long double optical_depth = alpha * depth;
    const long double forward = entry * std::exp(-optical_depth);
    const long double absorbed = entry * (-std::expm1(-optical_depth));
    close(r.forward_fraction_at_depth, forward,
          2e-15L * entry + r.saturation_fraction_error_bound, "depth flux oracle");
    close(r.absorbed_fraction_to_depth, absorbed,
          2e-15L * entry + r.saturation_fraction_error_bound, "depth absorption oracle");
    require(r.power_defect <= spike::optics::power_tolerance, "fixed power gate");
}
void interfaces() {
    interface_oracle(1, 1, 0, 500e-9, 0);
    interface_oracle(1, 1.5, 0, 500e-9, 10);
    interface_oracle(1, 0.999, 0.001, 1e-9, 1e-8);
    interface_oracle(1.2, 0.3, 4.5, 500e-9, 2e-8);
    interface_oracle(1e-12, 1e12, 1e12, 1e-15, 1e6);
    interface_oracle(1e12, 1e-12, 0, 1e3, 0);
    interface_oracle(1e-12, 1e-12, 1e12, 1e-15, 1e6);
    // Synthetic wavelength sweeps: no metal or spectral-band qualification.
    for (double wavelength : {1e-10, 100e-9, 550e-9, 1.5e-6, 10e-6, 1e-3})
        interface_oracle(1, 1.8, 0.02, wavelength, wavelength/10);
    const auto zero = spike::optics::normal_interface(1, 1.5, 0, 1e-6, 1e6);
    require(zero.alpha_per_m == 0 && zero.absorbed_fraction_to_depth == 0 &&
            !zero.depth_saturated, "exact zero loss");
    const auto depth_zero = spike::optics::normal_interface(1, 1.5, 3, 1e-6, 0);
    require(depth_zero.absorbed_fraction_to_depth == 0, "exact zero depth");
    const auto tiny = spike::optics::normal_interface(1, 1, 1e-20, 1, 1);
    require(tiny.absorbed_fraction_to_depth > 0, "tiny absorption retained");
    close(tiny.absorbed_fraction_to_depth / tiny.interface_entry_fraction,
          4 * std::numbers::pi_v<long double> * 1e-20L, 1e-34L, "tiny loss relative oracle");
    const auto opaque = spike::optics::normal_interface(1, 1, 1, 1e-6, 1);
    require(opaque.depth_saturated && opaque.forward_fraction_at_depth == 0 &&
            opaque.saturation_fraction_error_bound > 0 &&
            opaque.saturation_fraction_error_bound < 1e-300, "declared opacity bound");
    for (double n0 : {1e-12, 1.0, 1e12})
        for (double n : {1e-12, 0.7, 1e12})
            for (double k : {0.0, 1e-12, 1.0, 1e12})
                interface_oracle(n0, n, k, 1e-6, 1e-8);
}
void ports() {
    using spike::optics::balanced_ports;
    const auto single = balanced_ports({1,0}, {0,0});
    close(std::norm(single.out1), 0.5L, 2e-15L, "single split one");
    close(std::norm(single.out2), 0.5L, 2e-15L, "single split two");
    const auto dark = balanced_ports({1,0}, {0,1});
    require(dark.out1 == std::complex<double>(0,0), "coherent dark port");
    close(std::norm(dark.out2), 2, 2e-15L, "coherent bright port");
    const auto reverse = balanced_ports({1,0}, {0,-1});
    require(reverse.out2 == std::complex<double>(0,0), "phase reversal dark port");
    const auto zero = balanced_ports({0,0}, {0,0});
    require(zero.relative_power_defect == 0, "zero-input power");
    for (double scale : {1e-100, 1.0, 1e99}) {
        const std::complex<double> a(2*scale, -3*scale), b(-4*scale, 5*scale);
        const auto r = balanced_ports(a,b);
        close(r.out1.real()/scale, -3/std::sqrt(2.0L), 3e-15L, "port scalar real oracle");
        close(r.out1.imag()/scale, -7/std::sqrt(2.0L), 3e-15L, "port scalar imaginary oracle");
        require(r.relative_power_defect <= spike::optics::power_tolerance,
                "arbitrary coherent power");
        const auto twice = balanced_ports(r.out1, r.out2);
        require(std::abs(twice.out1-std::complex<double>(-b.imag(),b.real()))/scale < 1e-14,
                "twice-applied unitary port swap");
    }
    require(balanced_ports({1e100,-1e100}, {1e100,1e100}).relative_power_defect <=
            spike::optics::power_tolerance, "maximum port amplitude");
}
void invalid() {
    using spike::optics::normal_interface;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    for (double value : {nan, inf, -inf, 0.0, -1.0, 1e-13, 1e13}) {
        rejected([=]{normal_interface(value,1,0,1e-6,0);}, "incident index admission");
        rejected([=]{normal_interface(1,value,0,1e-6,0);}, "transmitted index admission");
    }
    for (double value : {nan, inf, -1.0, 1e13})
        rejected([=]{normal_interface(1,1,value,1e-6,0);}, "gain/extinction admission");
    for (double value : {nan, inf, -1.0, 0.0, 1e-16, 1e4})
        rejected([=]{normal_interface(1,1,0,value,0);}, "wavelength admission");
    for (double value : {nan, inf, -1.0, 1e7})
        rejected([=]{normal_interface(1,1,0,1e-6,value);}, "depth admission");
    const double sub = std::numeric_limits<double>::denorm_min();
    rejected([=]{normal_interface(1,1,sub,1e3,1);}, "unrepresentable positive alpha");
    rejected([=]{normal_interface(1,1,sub,1,sub);}, "unrepresentable positive optical depth");
    for (double value : {nan, inf, -inf, 1e101, -1e101}) {
        rejected([=]{spike::optics::balanced_ports({value,0},{0,0});}, "port real admission");
        rejected([=]{spike::optics::balanced_ports({0,0},{0,value});}, "port imaginary admission");
    }
}
} // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2, "optional argument is a JSON summary path");
        interfaces(); ports(); invalid();
        const std::string summary = "{\"contract\":\"spike/native-optics-reference-test/v1\","
            "\"status\":\"passed\",\"checks\":" + std::to_string(checks) +
            ",\"production_qualified\":false,\"material_data\":\"synthetic\","
            "\"power_tolerance\":1e-12,\"opaque_optical_depth\":700}\n";
        if (argc == 2) {
            const std::filesystem::path path(argv[1]);
            const auto parent = path.has_parent_path() ? path.parent_path() :
                std::filesystem::current_path();
            require(std::filesystem::is_directory(parent), "summary parent must already exist");
            std::ofstream output(path, std::ios::out | std::ios::trunc);
            if (!output) throw std::runtime_error("cannot open summary output");
            output << summary;
            output.close();
            if (!output) throw std::runtime_error("cannot complete summary output");
        }
        std::cout << summary;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native optics reference failed: " << error.what() << '\n';
        return 1;
    }
}
