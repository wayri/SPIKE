// SPDX-License-Identifier: MIT
// Copyright (c) 2026 SigHarmonic
#pragma once

#include "volume_inductance.hpp"
#include <array>
#include <complex>
#include <cstddef>
#include <string>
#include <variant>
#include <vector>

namespace spike::peec::spectral {
using volume::RectangularVolume;
using volume::Vector;

// Straight, arbitrarily placed hollow cylinder; uniform axial current density
// per ampere = direction / (pi * (outer_radius_m^2 - inner_radius_m^2)).
struct StraightAnnularVolume {
  Vector center_m{};
  Vector direction{0, 0, 1};
  double length_m = 0;
  double inner_radius_m = 0;
  double outer_radius_m = 0;
};
using Basis = std::variant<RectangularVolume, StraightAnnularVolume>;
using FourierVector = std::array<std::complex<double>, 3>;

// Integral b(x) exp(-i k.x) dx, in metres, for current density b per ampere.
// Wavevector k is in radians/metre. Analytic shape transform, evaluated in
// ordinary floating point; transcendental/roundoff error is not certified.
FourierVector fourier_basis(const Basis &basis, const Vector &wavevector);

struct Options {
  double radial_cutoff_per_m = 20000;
  std::size_t radial_panels = 128;
  std::size_t polar_order = 24;
  std::size_t azimuthal_panels = 48;
  std::size_t maximum_nodes = 2000000;
  std::size_t maximum_feature_evaluations = 10000000;
  double permeability_h_per_m = 1.2566370614359172954e-6;
};

struct Result {
  double finite_domain_energy_j = 0;
  // Mathematical bound mu/(2 K^2) ||J||_2^2, using the triangle inequality
  // for the norm so overlapping bases are safe. Ordinary floating arithmetic
  // is NOT an outward-rounded enclosure of this analytic bound.
  double radial_tail_bound_j = 0;
  double current_l2_squared_bound_a2_per_m = 0;
  std::size_t nodes = 0;
  std::size_t feature_evaluations = 0;
  bool evaluated = false;
  bool finite_domain_quadrature_certified = false;
  std::string failure_code;
};

// EXPERIMENTAL prescribed-current PEEC energy only. No assembled L matrix,
// full-wave claim, convergence claim, or certified total-energy interval.
// Positive common quadrature weights produce a reciprocal PSD Gram form in
// exact arithmetic, including self, touching, overlap and mixed geometries.
// W_K = mu/(2(2pi)^3) int_0^K int_S2 |sum I_i b_hat_i(r omega)|^2 dOmega dr.
// The radial midpoint / polar Gauss / azimuthal trapezoidal quadrature has NO
// certified discretization error here. W_K + tail_bound is NOT a certified
// upper bound on exact energy. Passivity of this discrete form establishes
// neither accuracy nor physical current continuity/return-path completeness.
// Work O(N * radial_panels * polar_order * azimuthal_panels), storage O(N+p).
// Malformed inputs throw invalid_argument; resource/numeric failure is explicit.
// Independent derivation: Fourier transform of 1/r is 4pi/|k|^2; Parseval
// gives int_|k|>K |J_hat|^2/|k|^2 <= (2pi)^3 ||J||_2^2/K^2.
// References: https://dlmf.nist.gov/1.14 and https://dlmf.nist.gov/10.22 .
// Clean-room implementation; no external implementation source was consulted.
Result prescribed_current_energy(const std::vector<Basis> &bases,
    const std::vector<double> &currents_a, const Options &options = {});
} // namespace spike::peec::spectral
