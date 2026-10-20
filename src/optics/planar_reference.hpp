// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <complex>

namespace spike::optics {
inline constexpr double power_tolerance = 1e-12;
inline constexpr double opaque_optical_depth = 700.0;

struct InterfaceResult {
    std::complex<double> r, t; // Electric-field amplitudes in one fixed basis.
    double reflectance = 0;
    double interface_entry_fraction = 0; // Not finite-slab transmittance.
    double forward_fraction_at_depth = 0;
    double absorbed_fraction_to_depth = 0;
    double alpha_per_m = 0;
    double optical_depth = 0;
    double power_defect = 0; // Maximum absolute incident-power closure defect.
    bool depth_saturated = false;
    double saturation_fraction_error_bound = 0;
};

// Monochromatic exp(i*k*z-i*omega*t), normal incidence, mu_r=1 on both sides.
// Smooth planar interface: real lossless n0; homogeneous local isotropic
// passive half-space N=n+i*kappa. No coatings, gain, roughness or emissivity.
// Bounds: n0,n [1e-12,1e12], kappa [0,1e12], vacuum wavelength [1e-15,1e3] m,
// depth [0,1e6] m. Positive unrepresentable attenuation/depth fails closed.
// At optical depth >=700, forward flux is set to zero; the reported bound
// applies separately to forward and absorbed incident-power fractions.
InterfaceResult normal_interface(double n0, double n, double kappa,
                                 double lambda_vac_m, double depth_m);

struct BalancedPortResult {
    std::complex<double> out1, out2; // Power-normalized amplitudes, sqrt(W).
    double relative_power_defect = 0;
};

// Separate ideal reciprocal lossless network; not an interface/coating model.
// Identical-frequency coherent ports with declared orthogonal output modes.
// Each real/imaginary input component must be finite and <=1e100 in magnitude.
BalancedPortResult balanced_ports(std::complex<double> a,
                                 std::complex<double> b);
} // namespace spike::optics
