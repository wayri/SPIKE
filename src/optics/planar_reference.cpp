// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "planar_reference.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace spike::optics {
namespace {
void bounded(double value, double lower, double upper, const char* name) {
    if (!std::isfinite(value) || value < lower || value > upper)
        throw std::invalid_argument(name);
}
void resolved_positive(double value, const char* name) {
    if (!std::isfinite(value) || value <= 0)
        throw std::runtime_error(name);
}
} // namespace

InterfaceResult normal_interface(double n0, double n, double kappa,
                                 double lambda_vac_m, double depth_m) {
    bounded(n0, 1e-12, 1e12, "incident index outside admitted range");
    bounded(n, 1e-12, 1e12, "transmitted real index outside admitted range");
    bounded(kappa, 0, 1e12, "extinction index outside passive admitted range");
    bounded(lambda_vac_m, 1e-15, 1e3, "vacuum wavelength outside admitted range");
    bounded(depth_m, 0, 1e6, "depth outside admitted range");

    // Scale before squared norms. No normalization of computed power results.
    const double scale = std::max({n0, n, kappa});
    const double x = n0 / scale, y = n / scale, z = kappa / scale;
    const std::complex<double> denominator(x + y, z);
    InterfaceResult result;
    result.r = std::complex<double>(x - y, -z) / denominator;
    result.t = (2 * x) / denominator;
    result.reflectance = std::norm(result.r);
    result.interface_entry_fraction = 4 * x * y / std::norm(denominator);
    result.alpha_per_m = kappa * (4 * std::numbers::pi / lambda_vac_m);
    if (kappa > 0)
        resolved_positive(result.alpha_per_m, "unrepresentable positive attenuation");
    result.optical_depth = result.alpha_per_m * depth_m;
    if (kappa > 0 && depth_m > 0)
        resolved_positive(result.optical_depth, "unrepresentable positive optical depth");

    result.depth_saturated = result.optical_depth >= opaque_optical_depth;
    if (result.depth_saturated) {
        result.forward_fraction_at_depth = 0;
        result.absorbed_fraction_to_depth = result.interface_entry_fraction;
        // exp(-700) < 1e-300; round the conservative product upward.
        result.saturation_fraction_error_bound = std::nextafter(
            result.interface_entry_fraction * 1e-300,
            std::numeric_limits<double>::infinity());
    } else {
        result.forward_fraction_at_depth = result.interface_entry_fraction *
            std::exp(-result.optical_depth);
        result.absorbed_fraction_to_depth = result.interface_entry_fraction *
            (-std::expm1(-result.optical_depth));
    }
    const double interface_defect = std::abs(result.reflectance +
        result.interface_entry_fraction - 1);
    const double depth_defect = std::abs(result.reflectance +
        result.forward_fraction_at_depth + result.absorbed_fraction_to_depth - 1);
    result.power_defect = std::max(interface_defect, depth_defect);
    if (!std::isfinite(result.power_defect) || result.power_defect > power_tolerance)
        throw std::runtime_error("interface power closure failed");
    return result;
}

BalancedPortResult balanced_ports(std::complex<double> a,
                                 std::complex<double> b) {
    for (double value : {a.real(), a.imag(), b.real(), b.imag()})
        bounded(value, -1e100, 1e100, "port amplitude outside admitted range");
    const double inv_sqrt2 = 1 / std::numbers::sqrt2;
    BalancedPortResult result;
    result.out1 = { (a.real() - b.imag()) * inv_sqrt2,
                    (a.imag() + b.real()) * inv_sqrt2 };
    result.out2 = { (-a.imag() + b.real()) * inv_sqrt2,
                    (a.real() + b.imag()) * inv_sqrt2 };
    const double scale = std::max({std::abs(a.real()), std::abs(a.imag()),
                                  std::abs(b.real()), std::abs(b.imag())});
    if (scale == 0) return result;
    // Scaled power also checks the actual rounded output for tiny inputs.
    const double input = std::norm(a / scale) + std::norm(b / scale);
    const double output = std::norm(result.out1 / scale) + std::norm(result.out2 / scale);
    result.relative_power_defect = std::abs(output - input) / input;
    if (!std::isfinite(result.relative_power_defect) ||
        result.relative_power_defect > power_tolerance)
        throw std::runtime_error("balanced port power closure failed");
    return result;
}
} // namespace spike::optics
