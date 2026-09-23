/**
 * @file test_peec.cpp
 * @brief Unit tests for PEEC solver
 * @version 0.1.7.0
 */

#include "peec/peec_solver.hpp"
#include <cmath>
#include <cassert>
#include <iomanip>
#include <iostream>


using namespace spike::peec;

// Test 1: Self-inductance of a straight wire
void test_self_inductance() {
  std::cout << "\n=== Test 1: Self-Inductance ===" << std::endl;

  PEECSolver solver;

  // Create a 10mm long, 0.5mm wide, 0.035mm thick trace (typical PCB trace)
  Filament fil;
  fil.start = Point3D(0, 0, 0);
  fil.end = Point3D(10, 0, 0); // 10mm long
  fil.width = 0.5;             // 0.5mm wide
  fil.thickness = 0.035;       // 35μm (1oz copper)
  fil.node_p = 0;
  fil.node_n = 1;
  fil.conductivity = 5.8e7; // Copper

  solver.add_filament(fil);

  // Compute inductance matrix
  auto L = solver.compute_partial_inductance();

  double L_self = L.coeff(0, 0); // Self-inductance

  std::cout << "Filament: 10mm x 0.5mm x 0.035mm" << std::endl;
  std::cout << "Self-inductance: " << std::scientific << std::setprecision(4)
            << L_self << " H" << std::endl;
  std::cout << "                 " << std::fixed << std::setprecision(2)
            << L_self * 1e9 << " nH" << std::endl;

  // Expected: ~10-20 nH for a 10mm trace
  if (L_self > 5e-9 && L_self < 30e-9) {
    std::cout << "✓ PASS: Self-inductance in expected range" << std::endl;
  } else {
    std::cout << "✗ FAIL: Self-inductance out of range" << std::endl;
  }
  assert(L_self > 5e-9 && L_self < 30e-9);
}

// Test 2: Mutual inductance of parallel traces
void test_mutual_inductance_parallel() {
  std::cout << "\n=== Test 2: Mutual Inductance (Parallel) ===" << std::endl;

  PEECSolver solver;

  // Two parallel traces, 1mm apart
  Filament fil1, fil2;

  fil1.start = Point3D(0, 0, 0);
  fil1.end = Point3D(10, 0, 0);
  fil1.width = 0.5;
  fil1.thickness = 0.035;
  fil1.node_p = 0;
  fil1.node_n = 1;
  fil1.conductivity = 5.8e7;

  fil2.start = Point3D(0, 1, 0); // 1mm spacing
  fil2.end = Point3D(10, 1, 0);
  fil2.width = 0.5;
  fil2.thickness = 0.035;
  fil2.node_p = 2;
  fil2.node_n = 3;
  fil2.conductivity = 5.8e7;

  solver.add_filament(fil1);
  solver.add_filament(fil2);

  auto L = solver.compute_partial_inductance();

  double L11 = L.coeff(0, 0);
  double L12 = L.coeff(0, 1);
  double L22 = L.coeff(1, 1);

  std::cout << "Two parallel traces, 10mm long, 1mm apart" << std::endl;
  std::cout << "L11 (self): " << std::fixed << std::setprecision(2) << L11 * 1e9
            << " nH" << std::endl;
  std::cout << "L12 (mutual): " << L12 * 1e9 << " nH" << std::endl;
  std::cout << "L22 (self): " << L22 * 1e9 << " nH" << std::endl;
  std::cout << "Coupling coefficient k = L12/sqrt(L11*L22): "
            << std::setprecision(3) << L12 / std::sqrt(L11 * L22) << std::endl;

  // Mutual inductance should be positive and less than self-inductance
  if (L12 > 0 && L12 < L11 && L12 < L22) {
    std::cout << "✓ PASS: Mutual inductance has correct properties"
              << std::endl;
  } else {
    std::cout << "✗ FAIL: Mutual inductance incorrect" << std::endl;
  }
  assert(L12 > 0 && L12 < L11 && L12 < L22);
}

// Test 3: Mutual inductance of perpendicular traces
void test_mutual_inductance_perpendicular() {
  std::cout << "\n=== Test 3: Mutual Inductance (Perpendicular) ==="
            << std::endl;

  PEECSolver solver;

  // Two perpendicular traces
  Filament fil1, fil2;

  fil1.start = Point3D(0, 5, 0);
  fil1.end = Point3D(10, 5, 0); // Horizontal
  fil1.width = 0.5;
  fil1.thickness = 0.035;
  fil1.node_p = 0;
  fil1.node_n = 1;
  fil1.conductivity = 5.8e7;

  fil2.start = Point3D(5, 0, 0);
  fil2.end = Point3D(5, 10, 0); // Vertical
  fil2.width = 0.5;
  fil2.thickness = 0.035;
  fil2.node_p = 2;
  fil2.node_n = 3;
  fil2.conductivity = 5.8e7;

  solver.add_filament(fil1);
  solver.add_filament(fil2);

  auto L = solver.compute_partial_inductance();

  double L12 = L.coeff(0, 1);

  std::cout << "Two perpendicular traces crossing at center" << std::endl;
  std::cout << "L12 (mutual): " << std::scientific << std::setprecision(4)
            << L12 << " H" << std::endl;
  std::cout << "              " << std::fixed << std::setprecision(4)
            << L12 * 1e9 << " nH" << std::endl;

  // Perpendicular traces should have very small mutual inductance
  if (std::abs(L12) < 1e-9) { // Less than 1 nH
    std::cout << "✓ PASS: Perpendicular mutual inductance near zero"
              << std::endl;
  } else {
    std::cout << "✗ FAIL: Perpendicular mutual inductance too large"
              << std::endl;
  }
  assert(std::abs(L12) < 1e-9);
}

// Test 4: Matrix symmetry
void test_matrix_symmetry() {
  std::cout << "\n=== Test 4: Matrix Symmetry ===" << std::endl;

  PEECSolver solver;

  // Create 3 random filaments
  for (int i = 0; i < 3; ++i) {
    Filament fil;
    fil.start = Point3D(i * 5.0, 0, 0);
    fil.end = Point3D(i * 5.0 + 10, 0, 0);
    fil.width = 0.5;
    fil.thickness = 0.035;
    fil.node_p = i * 2;
    fil.node_n = i * 2 + 1;
    fil.conductivity = 5.8e7;
    solver.add_filament(fil);
  }

  auto L = solver.compute_partial_inductance();

  // Check symmetry
  bool symmetric = true;
  double max_error = 0.0;

  for (int i = 0; i < 3; ++i) {
    for (int j = 0; j < 3; ++j) {
      double error = std::abs(L.coeff(i, j) - L.coeff(j, i));
      max_error = std::max(max_error, error);
      if (error > 1e-15) {
        symmetric = false;
      }
    }
  }

  std::cout << "Maximum symmetry error: " << std::scientific << max_error
            << std::endl;

  if (symmetric) {
    std::cout << "✓ PASS: Matrix is symmetric" << std::endl;
  } else {
    std::cout << "✗ FAIL: Matrix is not symmetric" << std::endl;
  }
  assert(symmetric);
}

// Test 5: AC resistance is continuous, monotonic, and roughness-aware.
void test_frequency_dependent_resistance() {
  std::cout << "\n=== Test 5: Frequency-Dependent Resistance ===" << std::endl;

  Filament fil;
  fil.start = Point3D(0, 0, 0);
  fil.end = Point3D(100, 0, 0);
  fil.width = 1.0;
  fil.thickness = 0.035;
  fil.node_p = 0;
  fil.node_n = 1;
  fil.conductivity = 5.8e7;

  PEECConfig smooth_config;
  PEECSolver smooth(smooth_config);
  smooth.add_filament(fil);
  const double r_dc = smooth.compute_resistance(0.0).coeff(0, 0);
  const double r_1mhz = smooth.compute_resistance(1e6).coeff(0, 0);
  const double r_100mhz = smooth.compute_resistance(1e8).coeff(0, 0);
  assert(r_1mhz >= r_dc);
  assert(r_100mhz >= r_1mhz);

  PEECConfig rough_config;
  rough_config.enable_hammerstad_roughness = true;
  rough_config.roughness_rms_um = 2.0;
  PEECSolver rough(rough_config);
  rough.add_filament(fil);
  const double r_rough = rough.compute_resistance(1e8).coeff(0, 0);
  assert(r_rough > r_100mhz);

  std::cout << "Rdc=" << r_dc << " R1MHz=" << r_1mhz
            << " R100MHz=" << r_100mhz << " Rrough=" << r_rough
            << std::endl;
}

int main() {
  std::cout << "========================================" << std::endl;
  std::cout << "  SPIKE PEEC Solver Unit Tests" << std::endl;
  std::cout << "  Version 0.1.7.0" << std::endl;
  std::cout << "========================================" << std::endl;

  test_self_inductance();
  test_mutual_inductance_parallel();
  test_mutual_inductance_perpendicular();
  test_matrix_symmetry();
  test_frequency_dependent_resistance();

  std::cout << "\n========================================" << std::endl;
  std::cout << "  All tests completed!" << std::endl;
  std::cout << "========================================\n" << std::endl;

  return 0;
}
