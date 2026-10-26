// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "cavity.hpp"

namespace spike::airflow {
struct ChtSettings {
    Settings flow;
    double peclet = 10, solid_k_ratio = 10;
    double hot_k = 310, cold_k = 300;
    double thermal_tolerance = 1e-9;
    int max_thermal_iterations = 100000;
};
struct ChtResult {
    bool converged = false;
    Result flow;
    int thermal_iterations = 0;
    double thermal_residual = 0, hot_flux = 0, cold_flux = 0;
    double balance_raw = 0, balance_relative = 0, theta_min = 0, theta_max = 0;
    std::vector<double> theta;
    // Interface integrated face flux is positive upward, scaled by k_fluid*dT.
    std::vector<double> interface_bottom_theta, interface_top_theta;
    std::vector<double> interface_bottom_flux, interface_top_flux;
};
ChtResult solve_cht(const ChtSettings& settings);
}
