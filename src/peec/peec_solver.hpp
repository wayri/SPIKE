/**
 * @file peec_solver.hpp
 * @brief PEEC (Partial Element Equivalent Circuit) Solver Interface
 * @version 0.1.6.0
 *
 * SPIKE: Signal, Power, and Integrity Knowledge Engine
 *
 * This module implements the PEEC method for extracting frequency-dependent
 * R, L, C matrices from 3D PCB geometry.
 *
 * Reference:
 *   Ruehli, A. E. (1974). "Equivalent Circuit Models for Three-Dimensional
 *   Multiconductor Systems." IEEE Trans. Microwave Theory Tech., MTT-22(3).
 *
 * @author Lead Systems Architect
 * @date 2026-02-07
 */

#pragma once

// Enable M_PI and other math constants on MSVC
#define _USE_MATH_DEFINES
#include <cmath>

#include <Eigen/Dense>
#include <Eigen/Sparse>
#include <complex>
#include <vector>


namespace spike {
namespace peec {

/**
 * @brief 3D Point in Cartesian coordinates (mm)
 */
struct Point3D {
  double x, y, z;

  Point3D() : x(0), y(0), z(0) {}
  Point3D(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

  // Vector operations
  Point3D operator-(const Point3D &other) const {
    return Point3D(x - other.x, y - other.y, z - other.z);
  }

  double norm() const { return std::sqrt(x * x + y * y + z * z); }
};

/**
 * @brief Rectangular filament for inductance calculation
 *
 * Represents a conductor segment with rectangular cross-section.
 * Used for partial inductance extraction.
 */
struct Filament {
  Point3D start;       ///< Start point (mm)
  Point3D end;         ///< End point (mm)
  double width;        ///< Width (mm)
  double thickness;    ///< Thickness (mm)
  int node_p;          ///< Positive node index
  int node_n;          ///< Negative node index
  double conductivity; ///< Conductivity (S/m), e.g., 5.8e7 for copper

  /// Get filament length
  double length() const { return (end - start).norm(); }

  /// Get cross-sectional area
  double area() const { return width * thickness; }

  /// Get DC resistance (Ohms)
  double resistance() const {
    // Geometry is stored in mm. Convert length and cross-sectional area to SI.
    return (length() * 1e-3) /
           (conductivity * width * 1e-3 * thickness * 1e-3);
  }
};

/**
 * @brief Surface patch for capacitance calculation
 */
struct Patch {
  Point3D center; ///< Center point (mm)
  Point3D normal; ///< Normal vector (unit)
  double area;    ///< Area (mm²)
  int node;       ///< Node index
};

/**
 * @brief PEEC Solver Types
 */
enum class SolverType {
  DENSE_DIRECT,     ///< Exact inversion (O(N^3)), good for < 2k elements
  SPARSE_ITERATIVE  ///< GMRES/ILU with thresholding, for > 10k elements
};

/**
 * @brief PEEC Solver Configuration
 */
struct PEECConfig {
  double mu_0 = 4.0 * M_PI * 1e-7; ///< Permeability of free space (H/m)
  double eps_0 = 8.854187817e-12;  ///< Permittivity of free space (F/m)
  double eps_r = 4.5;              ///< Relative permittivity (FR4 typical)

  int quad_order = 6; ///< Gaussian quadrature order
  bool use_analytic_singular =
      true; ///< Use analytic integration for self-terms

  int num_threads = 0; ///< OpenMP threads (0 = auto)

  bool enable_skin_effect = true; ///< Apply isolated-conductor skin loss
  bool enable_hammerstad_roughness = false; ///< Apply Hammerstad loss multiplier
  double roughness_rms_um = 0.0; ///< RMS copper roughness used by Hammerstad
  
  SolverType solver_type = SolverType::DENSE_DIRECT;
  double sparse_threshold = 1e-12; ///< Threshold for dropping mutual L terms
};

/**
 * @brief PEEC Solver Class
 *
 * Extracts R, L, C matrices from filament/patch geometry.
 */
class PEECSolver {
public:
  PEECSolver(const PEECConfig &config = PEECConfig());
  ~PEECSolver();

  /**
   * @brief Add a filament to the mesh
   */
  void add_filament(const Filament &fil);

  /**
   * @brief Add a patch to the mesh
   */
  void add_patch(const Patch &patch);

  /**
   * @brief Compute partial inductance matrix L_p
   *
   * @return Sparse matrix (n_filaments x n_filaments)
   */
  Eigen::SparseMatrix<double> compute_partial_inductance();

  /**
   * @brief Compute resistance matrix R with skin effect
   *
   * @param frequency Frequency in Hz
   * @return Sparse matrix (n_filaments x n_filaments)
   */
  Eigen::SparseMatrix<double> compute_resistance(double frequency = 0.0);

  /**
   * @brief Compute capacitance matrix C
   *
   * Uses method of moments with surface patches.
   *
   * @return Sparse matrix (n_patches x n_patches)
   */
  Eigen::SparseMatrix<double> compute_capacitance();

  /**
   * @brief Solve MNA system at a given frequency
   *
   * [G + jωC + Γ/(jω)] · V = I
   *
   * @param frequency Frequency (Hz)
   * @param current_sources Current excitation vector
   * @return Node voltage vector (complex)
   */
  Eigen::VectorXcd solve_frequency(double frequency,
                                   const Eigen::VectorXcd &current_sources);

  /**
   * @brief Get number of filaments
   */
  size_t num_filaments() const { return filaments_.size(); }

  /**
   * @brief Get number of patches
   */
  size_t num_patches() const { return patches_.size(); }

  /**
   * @brief Clear all geometry
   */
  void clear();

private:
  PEECConfig config_;
  std::vector<Filament> filaments_;
  std::vector<Patch> patches_;

  /**
   * @brief Compute mutual inductance between two filaments
   *
   * Uses 6-point Gaussian quadrature for non-neighboring elements.
   * Uses analytic integration for self/neighboring elements.
   */
  double compute_mutual_inductance(const Filament &fil_i,
                                   const Filament &fil_j);

  /**
   * @brief Check if two filaments are neighbors (share nodes)
   */
  bool are_neighbors(const Filament &fil_i, const Filament &fil_j) const;
};

} // namespace peec
} // namespace spike
