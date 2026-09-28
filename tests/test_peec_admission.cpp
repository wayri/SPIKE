// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// Independently authored API-admission regressions. These checks do not
// establish physical validity of the legacy filament/patch approximation.
#include "peec/peec_solver.hpp"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace spike::peec;

namespace {
void require(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}

void require_rejected(const std::function<void()> &action) {
  try {
    action();
  } catch (const std::exception &) {
    return;
  }
  throw std::runtime_error("invalid input was accepted");
}

Filament copper() {
  return {Point3D(0, 0, 0), Point3D(10, 0, 0), 1.0, 0.035,
          0, 1, 5.8e7};
}

void finite_filaments() {
  const double invalid[] = {std::numeric_limits<double>::quiet_NaN(),
                            std::numeric_limits<double>::infinity(),
                            -std::numeric_limits<double>::infinity()};
  for (double value : invalid) {
    for (int field = 0; field < 9; ++field) {
      auto fil = copper();
      double *members[] = {&fil.start.x, &fil.start.y, &fil.start.z,
                           &fil.end.x, &fil.end.y, &fil.end.z,
                           &fil.width, &fil.thickness, &fil.conductivity};
      *members[field] = value;
      PEECSolver solver;
      require_rejected([&] { solver.add_filament(fil); });
      require(solver.num_filaments() == 0, "rejected filament mutated solver");
    }
  }
}

void finite_config() {
  const double invalid[] = {0.0, -1.0,
                            std::numeric_limits<double>::quiet_NaN(),
                            std::numeric_limits<double>::infinity()};
  for (double value : invalid) {
    for (int field = 0; field < 3; ++field) {
      PEECConfig config;
      double *members[] = {&config.mu_0, &config.eps_0, &config.eps_r};
      *members[field] = value;
      require_rejected([&] { PEECSolver solver(config); });
    }
  }
  for (double value : {-1.0, std::numeric_limits<double>::quiet_NaN(),
                       std::numeric_limits<double>::infinity()}) {
    PEECConfig roughness;
    roughness.roughness_rms_um = value;
    require_rejected([&] { PEECSolver solver(roughness); });
    PEECConfig threshold;
    threshold.sparse_threshold = value;
    require_rejected([&] { PEECSolver solver(threshold); });
  }
}

void supported_config() {
  PEECConfig config;
  config.quad_order = 12;
  require_rejected([&] { PEECSolver solver(config); });
  config = PEECConfig{};
  config.use_analytic_singular = false;
  require_rejected([&] { PEECSolver solver(config); });
  config = PEECConfig{};
  config.num_threads = -1;
  require_rejected([&] { PEECSolver solver(config); });
}

void resistance_frequency() {
  PEECSolver solver;
  solver.add_filament(copper());
  const double expected = 0.01 / (5.8e7 * 0.001 * 0.000035);
  require(std::abs(solver.compute_resistance().coeff(0, 0) - expected) <
              1e-14 * expected, "DC resistance changed");
  for (double frequency : {-1.0, std::numeric_limits<double>::quiet_NaN(),
                            std::numeric_limits<double>::infinity()}) {
    require_rejected([&] { solver.compute_resistance(frequency); });
  }
}

void finite_patches() {
  const Patch valid{Point3D(0, 0, 0), Point3D(0, 0, 1), 1.0, 0};
  for (double area : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN(),
                       std::numeric_limits<double>::infinity()}) {
    auto patch = valid;
    patch.area = area;
    PEECSolver solver;
    require_rejected([&] { solver.add_patch(patch); });
    require(solver.num_patches() == 0, "rejected patch mutated solver");
  }
  for (int field = 0; field < 6; ++field) {
    auto patch = valid;
    double *members[] = {&patch.center.x, &patch.center.y, &patch.center.z,
                         &patch.normal.x, &patch.normal.y, &patch.normal.z};
    *members[field] = std::numeric_limits<double>::quiet_NaN();
    PEECSolver solver;
    require_rejected([&] { solver.add_patch(patch); });
  }
}

void capacitance_passivity() {
  PEECConfig config;
  config.sparse_threshold = 0.0;
  PEECSolver solver(config);
  solver.add_patch({Point3D(0, 0, 0), Point3D(0, 0, 1), 1.0, 0});
  solver.add_patch({Point3D(0.1, 0, 0), Point3D(0, 0, 1), 1.0, 1});
  // Point mutual potential exceeds self potential, making P indefinite.
  require_rejected([&] { solver.compute_capacitance(); });
}

void capacitance_diagonal() {
  PEECSolver solver;
  solver.add_patch({Point3D(0, 0, 0), Point3D(0, 0, 1), 1.0, 0});
  const auto capacitance = solver.compute_capacitance();
  require(capacitance.coeff(0, 0) > 0.0,
          "default threshold erased positive self capacitance");
}

void singular_lines_and_short_segments() {
  PEECSolver duplicated;
  duplicated.add_filament(copper());
  duplicated.add_filament(copper());
  require_rejected([&] { duplicated.compute_partial_inductance(); });
  auto tiny = copper();
  tiny.end.x = 1e-10;
  PEECSolver short_segment;
  short_segment.add_filament(tiny);
  require(short_segment.compute_partial_inductance().coeff(0, 0) > 0,
          "positive short segment was silently erased");
}

void frequency_solve_admission() {
  PEECSolver solver;
  solver.add_filament(copper());
  Eigen::VectorXcd rhs = Eigen::VectorXcd::Ones(1);
  bool unsupported = false;
  try {
    solver.solve_frequency(1e6, rhs);
  } catch (const std::logic_error &) {
    unsupported = true;
  }
  require(unsupported, "legacy non-topological frequency solve was enabled");
  for (double frequency : {0.0, -1.0,
                            std::numeric_limits<double>::quiet_NaN(),
                            std::numeric_limits<double>::infinity()}) {
    require_rejected([&] { solver.solve_frequency(frequency, rhs); });
  }
  rhs[0] = std::numeric_limits<double>::quiet_NaN();
  require_rejected([&] { solver.solve_frequency(1e6, rhs); });
  rhs = Eigen::VectorXcd::Ones(2);
  require_rejected([&] { solver.solve_frequency(1e6, rhs); });
}
} // namespace

int main(int argc, char **argv) {
  const std::vector<std::pair<std::string, std::function<void()>>> tests{
      {"finite_filaments", finite_filaments},
      {"finite_config", finite_config},
      {"supported_config", supported_config},
      {"resistance_frequency", resistance_frequency},
      {"finite_patches", finite_patches},
      {"capacitance_passivity", capacitance_passivity},
      {"capacitance_diagonal", capacitance_diagonal},
      {"singular_lines_and_short_segments", singular_lines_and_short_segments},
      {"frequency_solve_admission", frequency_solve_admission}};
  int failures = 0;
  for (const auto &[name, test] : tests) {
    if (argc > 1 && name != argv[1]) continue;
    try {
      test();
      std::cout << "PASS " << name << '\n';
    } catch (const std::exception &error) {
      ++failures;
      std::cerr << "FAIL " << name << ": " << error.what() << '\n';
    }
  }
  return failures == 0 ? 0 : 1;
}
