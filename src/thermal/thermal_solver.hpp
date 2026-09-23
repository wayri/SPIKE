/**
 * @file thermal_solver.hpp
 * @brief Thermal FEM/FDM Solver Interface
 * @version 0.1.7.0
 */

#pragma once

#include <Eigen/Dense>
#include <Eigen/Sparse>
#include <vector>

namespace spike {
namespace thermal {

class ThermalSolver {
public:
  ThermalSolver();
  ~ThermalSolver();

  void set_grid(int nx, int ny, double dx, double dy);
  void add_heat_source(int x_idx, int y_idx, double power_W);
  void set_ambient(double t_amb, double h_conv);

  Eigen::VectorXd solve_steady_state(const Eigen::VectorXd &heat_sources);
  
  Eigen::VectorXd solve_transient(const Eigen::VectorXd &heat_sources,
                                  const Eigen::VectorXd &T_initial,
                                  double time_step, int num_steps);

  double get_temperature(int x_idx, int y_idx) const;
  void clear();

private:
  int nx_, ny_;
  double dx_, dy_;
  double T_ambient_;
  double h_conv_;
  Eigen::VectorXd Q_; // Power (W)
  Eigen::VectorXd T_; // Temperature (K)
};

} // namespace thermal
} // namespace spike
