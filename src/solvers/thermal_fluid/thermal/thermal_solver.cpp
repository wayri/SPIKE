/**
 * @file thermal_solver.cpp
 * @brief Thermal FEM/FDM Solver Implementation
 * @version 0.1.7.0
 */

#include "thermal_solver.hpp"
#include <iostream>
#include <stdexcept>

namespace spike {
namespace thermal {

ThermalSolver::ThermalSolver() : nx_(0), ny_(0), dx_(0.001), dy_(0.001), T_ambient_(298.15), h_conv_(10.0) {}

ThermalSolver::~ThermalSolver() {}

void ThermalSolver::set_grid(int nx, int ny, double dx, double dy) {
    nx_ = nx;
    ny_ = ny;
    dx_ = dx;
    dy_ = dy;
    Q_ = Eigen::VectorXd::Zero(nx_ * ny_);
    T_ = Eigen::VectorXd::Constant(nx_ * ny_, T_ambient_);
}

void ThermalSolver::add_heat_source(int x_idx, int y_idx, double power_W) {
    if (x_idx >= 0 && x_idx < nx_ && y_idx >= 0 && y_idx < ny_) {
        Q_(y_idx * nx_ + x_idx) += power_W;
    }
}

void ThermalSolver::set_ambient(double t_amb, double h) {
    T_ambient_ = t_amb;
    h_conv_ = h;
}

Eigen::VectorXd ThermalSolver::solve_steady_state(const Eigen::VectorXd &heat_sources) {
    if (nx_ == 0 || ny_ == 0) {
        // Fallback for direct vector calls without grid setup
        nx_ = std::sqrt(heat_sources.size());
        ny_ = nx_;
        dx_ = 0.001; dy_ = 0.001;
    }
    
    Q_ = heat_sources;
    
    int n_nodes = nx_ * ny_;
    std::vector<Eigen::Triplet<double>> triplets;
    Eigen::VectorXd rhs = Eigen::VectorXd::Zero(n_nodes);
    
    // Effective thermal conductivity (approximate homogenized FR4 + Cu)
    double k_eff = 20.0; // W/mK
    // Board thickness
    double t_board = 0.0016; // 1.6mm
    
    double R_x = dx_ / (k_eff * dy_ * t_board);
    double R_y = dy_ / (k_eff * dx_ * t_board);
    
    double G_x = 1.0 / R_x;
    double G_y = 1.0 / R_y;
    double G_conv = h_conv_ * (dx_ * dy_) * 2.0; // Top and bottom convection
    
    for (int y = 0; y < ny_; ++y) {
        for (int x = 0; x < nx_; ++x) {
            int i = y * nx_ + x;
            double diag_G = G_conv;
            
            // Left
            if (x > 0) {
                triplets.push_back(Eigen::Triplet<double>(i, i - 1, -G_x));
                diag_G += G_x;
            }
            // Right
            if (x < nx_ - 1) {
                triplets.push_back(Eigen::Triplet<double>(i, i + 1, -G_x));
                diag_G += G_x;
            }
            // Top
            if (y > 0) {
                triplets.push_back(Eigen::Triplet<double>(i, i - nx_, -G_y));
                diag_G += G_y;
            }
            // Bottom
            if (y < ny_ - 1) {
                triplets.push_back(Eigen::Triplet<double>(i, i + nx_, -G_y));
                diag_G += G_y;
            }
            
            triplets.push_back(Eigen::Triplet<double>(i, i, diag_G));
            rhs(i) = Q_(i) + G_conv * T_ambient_;
        }
    }
    
    Eigen::SparseMatrix<double> K(n_nodes, n_nodes);
    K.setFromTriplets(triplets.begin(), triplets.end());
    
    // Solve K * T = rhs
    Eigen::SimplicialLDLT<Eigen::SparseMatrix<double>> solver;
    solver.compute(K);
    
    if (solver.info() != Eigen::Success) {
        throw std::runtime_error("Thermal solver: Matrix decomposition failed");
    }
    
    T_ = solver.solve(rhs);
    return T_;
}

Eigen::VectorXd ThermalSolver::solve_transient(const Eigen::VectorXd &heat_sources,
                               const Eigen::VectorXd &T_initial,
                               double time_step, int num_steps) {
    throw std::runtime_error("solve_transient: Not yet implemented");
}

double ThermalSolver::get_temperature(int x_idx, int y_idx) const {
    if (x_idx >= 0 && x_idx < nx_ && y_idx >= 0 && y_idx < ny_) {
        return T_(y_idx * nx_ + x_idx);
    }
    return T_ambient_;
}

void ThermalSolver::clear() {
    Q_.setZero();
    T_.setConstant(T_ambient_);
}

} // namespace thermal
} // namespace spike
