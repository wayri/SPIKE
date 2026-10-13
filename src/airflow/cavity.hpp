// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <vector>

namespace spike::airflow {
struct Settings {
    int n = 32;
    double reynolds = 100.0;
    int max_steps = 100000;
    double steady_tolerance = 1e-7;
    double lid = 1.0; // Native zero-lid option is reserved for an analytical test.
};
struct Result {
    bool converged = false;
    int steps = 0;
    double time = 0, dt = 0, divergence = 0, steady_rate = 0;
    double poisson_residual = 0;
    std::vector<double> u, v, pressure;
};
// Cell-centred Neumann negative Laplacian, and zero-mean conjugate-gradient solve.
std::vector<double> negative_laplacian(const std::vector<double>& p, int n);
double solve_pressure(const std::vector<double>& rhs, int n,
                      std::vector<double>& p, double tolerance);
Result solve_cavity(const Settings& settings);
}
