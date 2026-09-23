/**
 * @file peec_solver.cpp
 * @brief PEEC partial-element extraction kernel
 * @version 0.1.6.0
 *
 * The matrix extraction routines are operational. The current frequency solve
 * remains an approximation until a topology-correct PEEC MNA assembly replaces
 * the one-filament/one-node mapping.
 */

#include "peec_solver.hpp"
#include <algorithm>
#include <omp.h>
#include <stdexcept>

namespace spike {
namespace peec {

PEECSolver::PEECSolver(const PEECConfig &config) : config_(config) {
  // Set OpenMP thread count
  if (config_.num_threads > 0) {
    omp_set_num_threads(config_.num_threads);
  }
}

PEECSolver::~PEECSolver() { clear(); }

void PEECSolver::add_filament(const Filament &fil) {
  if (fil.length() <= 0.0 || fil.width <= 0.0 || fil.thickness <= 0.0 ||
      fil.conductivity <= 0.0) {
    throw std::invalid_argument(
        "PEEC filaments require positive length, width, thickness, and conductivity.");
  }
  filaments_.push_back(fil);
}

void PEECSolver::add_patch(const Patch &patch) { patches_.push_back(patch); }

Eigen::SparseMatrix<double> PEECSolver::compute_partial_inductance() {
  const size_t n = filaments_.size();

  // Allocate sparse matrix
  Eigen::SparseMatrix<double> L_p(n, n);
  std::vector<Eigen::Triplet<double>> triplets;
  triplets.reserve(n * n); // Reserve for dense-ish matrix

// Parallel computation of inductance matrix
#pragma omp parallel
  {
    std::vector<Eigen::Triplet<double>> local_triplets;

#pragma omp for schedule(dynamic)
    for (int i = 0; i < static_cast<int>(n); ++i) {
      for (size_t j = 0; j <= static_cast<size_t>(i); ++j) {
        // Compute mutual inductance L_ij
        double L_ij = compute_mutual_inductance(filaments_[i], filaments_[j]);

        // Store in triplet format (symmetric matrix)
        local_triplets.emplace_back(i, static_cast<int>(j), L_ij);
        if (i != static_cast<int>(j)) {
          local_triplets.emplace_back(static_cast<int>(j), i, L_ij); // Symmetry
        }
      }
    }

// Merge local triplets into global list
#pragma omp critical
    {
      triplets.insert(triplets.end(), local_triplets.begin(),
                      local_triplets.end());
    }
  }

  // Build sparse matrix from triplets
  L_p.setFromTriplets(triplets.begin(), triplets.end());

  return L_p;
}

Eigen::SparseMatrix<double> PEECSolver::compute_resistance(double frequency) {
  const size_t n = filaments_.size();
  Eigen::SparseMatrix<double> R(n, n);
  std::vector<Eigen::Triplet<double>> triplets;
  triplets.reserve(n);

  const double mu_0 = config_.mu_0;
  
  for (size_t i = 0; i < n; ++i) {
    const auto& fil = filaments_[i];
    double r_dc = fil.resistance();
    double r_val = r_dc;
    
    // Isolated-conductor skin loss using the exact one-dimensional slab
    // internal impedance through the thinner cross-section dimension. This
    // gives a smooth DC-to-skin transition and is appropriate for thin PCB
    // traces and via-wall surrogates. It does not model proximity-effect
    // redistribution from nearby conductors.
    if (frequency > 0.0 && config_.enable_skin_effect) {
      double omega = 2.0 * M_PI * frequency;
      double delta = std::sqrt(2.0 / (omega * mu_0 * fil.conductivity));
      double w = fil.width * 1e-3;
      double t = fil.thickness * 1e-3;
      const double narrow = std::min(w, t);
      const double broad = std::max(w, t);
      const double normalized_depth = narrow / (2.0 * delta);
      double resistance_per_m = 0.0;
      if (normalized_depth > 40.0) {
        resistance_per_m =
            1.0 / (2.0 * fil.conductivity * broad * delta);
      } else {
        const std::complex<double> propagation(1.0, 1.0);
        const std::complex<double> argument =
            propagation * normalized_depth;
        const std::complex<double> coth_argument =
            std::cosh(argument) / std::sinh(argument);
        const std::complex<double> impedance_per_m =
            propagation * coth_argument /
            (2.0 * fil.conductivity * broad * delta);
        resistance_per_m = impedance_per_m.real();
      }
      r_val = std::max(r_dc, fil.length() * 1e-3 * resistance_per_m);

      if (config_.enable_hammerstad_roughness &&
          config_.roughness_rms_um > 0.0) {
        const double roughness_m = config_.roughness_rms_um * 1e-6;
        const double ratio = roughness_m / std::max(delta, 1e-30);
        const double correction =
            1.0 + (2.0 / M_PI) * std::atan(1.4 * ratio * ratio);
        r_val *= correction;
      }
    }
    
    triplets.emplace_back(static_cast<int>(i), static_cast<int>(i), r_val);
  }
  
  R.setFromTriplets(triplets.begin(), triplets.end());
  return R;
}

Eigen::SparseMatrix<double> PEECSolver::compute_capacitance() {
  const size_t n = patches_.size();
  if (n == 0) return Eigen::SparseMatrix<double>(0, 0);

  // Build Potential Coefficient matrix P
  Eigen::MatrixXd P(n, n);
  const double coeff = 1.0 / (4.0 * M_PI * config_.eps_0 * config_.eps_r);

#pragma omp parallel for schedule(dynamic)
  for (int i = 0; i < static_cast<int>(n); ++i) {
    for (int j = 0; j < static_cast<int>(n); ++j) {
      if (i == j) {
        // Self potential coefficient (approximate for rectangular patch)
        // P_ii = (1 / 4*pi*eps) * (2/sqrt(Area)) * something ... 
        // Simple circular approx: equivalent radius r = sqrt(Area/pi)
        // P_ii = coeff * 2 * pi * r / Area = coeff / r
        double r_eq = std::sqrt((patches_[i].area * 1e-6) / M_PI);
        P(i, j) = coeff / r_eq;
      } else {
        // Mutual potential (point charge approximation)
        Point3D dr = patches_[i].center - patches_[j].center;
        double dist = dr.norm() * 1e-3;
        if (dist < 1e-9) dist = 1e-9;
        P(i, j) = coeff / dist;
      }
    }
  }

  // Solve P*C = I instead of explicitly inverting P.  This routine remains a
  // capability-gated patch approximation; callers must validate panel shape,
  // convergence, and conductor grouping before treating it as sign-off data.
  P = (P + P.transpose()) * 0.5;
  Eigen::LDLT<Eigen::MatrixXd> factor(P);
  if (factor.info() != Eigen::Success) {
    throw std::runtime_error("Capacitance potential matrix factorization failed.");
  }
  Eigen::MatrixXd C_dense = factor.solve(Eigen::MatrixXd::Identity(n, n));
  if (factor.info() != Eigen::Success || !C_dense.allFinite()) {
    throw std::runtime_error("Capacitance potential matrix solve failed.");
  }
  C_dense = (C_dense + C_dense.transpose()) * 0.5;

  Eigen::SparseMatrix<double> C(n, n);
  std::vector<Eigen::Triplet<double>> triplets;
  for (int i = 0; i < C_dense.rows(); ++i) {
    for (int j = 0; j < C_dense.cols(); ++j) {
      if (std::abs(C_dense(i, j)) > config_.sparse_threshold) {
        triplets.emplace_back(i, j, C_dense(i, j));
      }
    }
  }
  C.setFromTriplets(triplets.begin(), triplets.end());
  return C;
}

Eigen::VectorXcd
PEECSolver::solve_frequency(double frequency,
                            const Eigen::VectorXcd &current_sources) {
  if (frequency <= 0) {
    throw std::invalid_argument("Frequency must be strictly positive for AC MNA.");
  }

  // 1. Build L, C, R matrices
  Eigen::SparseMatrix<double> L_p = compute_partial_inductance();
  Eigen::SparseMatrix<double> C = compute_capacitance();
  Eigen::SparseMatrix<double> R = compute_resistance(frequency);

  // 2. Compute Gamma = L^-1
  // Convert sparse L_p to dense for inversion (stub for direct solving)
  Eigen::MatrixXd L_dense = Eigen::MatrixXd(L_p);
  Eigen::MatrixXd Gamma_dense;
  
  if (config_.solver_type == SolverType::DENSE_DIRECT || L_p.rows() < 5000) {
    Gamma_dense = L_dense.inverse();
  } else {
    // In future: Use iterative approach or H-matrix to avoid full O(N^3)
    Gamma_dense = L_dense.inverse(); 
  }
  
  // 3. Assemble Y(w) = G + jwC + Gamma/(jw)
  // Note: this is a simplified MNA mapped to the filament nodes.
  // In a full PEEC solver, nodes map to filament ends and patches.
  // For this stub, we assume N nodes = N filaments.
  size_t n = filaments_.size();
  Eigen::MatrixXcd Y(n, n);
  double omega = 2.0 * M_PI * frequency;
  std::complex<double> jw(0, omega);

  for (size_t i = 0; i < n; ++i) {
    for (size_t k = 0; k < n; ++k) {
      double g_val = (i == k) ? (1.0 / R.coeff(i, i)) : 0.0;
      double c_val = (i < C.rows() && k < C.cols()) ? C.coeff(i, k) : 0.0;
      double gamma_val = Gamma_dense(i, k);
      
      Y(i, k) = g_val + jw * c_val + gamma_val / jw;
    }
  }

  // 4. Solve Y * V = I
  Eigen::VectorXcd V;
  if (config_.solver_type == SolverType::DENSE_DIRECT || n < 2000) {
     Eigen::PartialPivLU<Eigen::MatrixXcd> solver(Y);
     V = solver.solve(current_sources);
  } else {
     // Use iterative BiCGSTAB for large systems
     Eigen::SparseMatrix<std::complex<double>> Y_sparse = Y.sparseView(1e-10);
     Eigen::BiCGSTAB<Eigen::SparseMatrix<std::complex<double>>> solver;
     solver.compute(Y_sparse);
     V = solver.solve(current_sources);
  }

  return V;
}

void PEECSolver::clear() {
  filaments_.clear();
  patches_.clear();
}

double PEECSolver::compute_mutual_inductance(const Filament &fil_i,
                                             const Filament &fil_j) {
  // Neumann formula: M = (μ₀/4π) ∫∫ (dl_i · dl_j) / R
  // where R = |r_i - r_j| is the distance between integration points

  const double mu_0 = config_.mu_0;
  const double coeff = mu_0 / (4.0 * M_PI);

  // Check if this is self-inductance
  if (&fil_i == &fil_j) {
    // Self-inductance: Use Rosa's formula for rectangular conductor
    // L_self = (μ₀·l/2π) · [ln(2l/(w+t)) + 0.5 + 0.2235·(w+t)/l]
    // Reference: Rosa & Grover, "Formulas and Tables for the Calculation of
    // Mutual and Self-Inductance"

    const double l = fil_i.length() * 1e-3; // Convert mm to m
    const double w = fil_i.width * 1e-3;
    const double t = fil_i.thickness * 1e-3;
    const double gmd = w + t; // Geometric mean distance approximation

    if (l < 1e-12)
      return 0.0; // Degenerate filament

    double L_self = (mu_0 * l / (2.0 * M_PI)) *
                    (std::log(2.0 * l / gmd) + 0.5 + 0.2235 * (gmd / l));

    return L_self;
  }

  // Mutual inductance: First apply a spatial threshold to enforce sparsity
  // Calculate midpoints of both filaments
  Point3D c_i((fil_i.start.x + fil_i.end.x) * 0.5,
              (fil_i.start.y + fil_i.end.y) * 0.5,
              (fil_i.start.z + fil_i.end.z) * 0.5);
  Point3D c_j((fil_j.start.x + fil_j.end.x) * 0.5,
              (fil_j.start.y + fil_j.end.y) * 0.5,
              (fil_j.start.z + fil_j.end.z) * 0.5);
  
  // Use 6-point Gaussian quadrature. Do not silently discard long-range
  // coupling; solver-level acceleration must preserve a documented error bound.
  // Gauss-Legendre quadrature points and weights for [-1, 1]
  const int n_quad = 6;
  const double quad_points[6] = {-0.9324695142031521, -0.6612093864662645,
                                 -0.2386191860831969, 0.2386191860831969,
                                 0.6612093864662645,  0.9324695142031521};
  const double quad_weights[6] = {0.1713244923791704, 0.3607615730481386,
                                  0.4679139345726910, 0.4679139345726910,
                                  0.3607615730481386, 0.1713244923791704};

  // Filament direction vectors (unit vectors)
  Point3D dl_i = fil_i.end - fil_i.start;
  Point3D dl_j = fil_j.end - fil_j.start;

  const double len_i = dl_i.norm();
  const double len_j = dl_j.norm();

  if (len_i < 1e-12 || len_j < 1e-12)
    return 0.0; // Degenerate filament

  // Normalize direction vectors
  dl_i.x /= len_i;
  dl_i.y /= len_i;
  dl_i.z /= len_i;
  dl_j.x /= len_j;
  dl_j.y /= len_j;
  dl_j.z /= len_j;

  // Dot product of direction vectors
  const double dl_dot = dl_i.x * dl_j.x + dl_i.y * dl_j.y + dl_i.z * dl_j.z;

  // Double integration using Gaussian quadrature
  double integral = 0.0;

  for (int qi = 0; qi < n_quad; ++qi) {
    // Map quadrature point to filament i
    const double t_i = 0.5 * (1.0 + quad_points[qi]);
    Point3D r_i;
    r_i.x = fil_i.start.x + t_i * (fil_i.end.x - fil_i.start.x);
    r_i.y = fil_i.start.y + t_i * (fil_i.end.y - fil_i.start.y);
    r_i.z = fil_i.start.z + t_i * (fil_i.end.z - fil_i.start.z);

    for (int qj = 0; qj < n_quad; ++qj) {
      // Map quadrature point to filament j
      const double t_j = 0.5 * (1.0 + quad_points[qj]);
      Point3D r_j;
      r_j.x = fil_j.start.x + t_j * (fil_j.end.x - fil_j.start.x);
      r_j.y = fil_j.start.y + t_j * (fil_j.end.y - fil_j.start.y);
      r_j.z = fil_j.start.z + t_j * (fil_j.end.z - fil_j.start.z);

      // Distance between points (mm)
      const Point3D dr = r_i - r_j;
      const double R = dr.norm() * 1e-3; // Convert mm to m

      // Avoid singularity for very close points
      if (R < 1e-9)
        continue;

      // Integrand: (dl_i · dl_j) / R
      const double integrand = dl_dot / R;

      // Accumulate with quadrature weights
      integral += quad_weights[qi] * quad_weights[qj] * integrand;
    }
  }

  // Scale by filament lengths and coefficient
  // Factor of 0.25 from mapping [-1,1] to [0,1] for both integrals
  const double len_i_m = len_i * 1e-3; // Convert mm to m
  const double len_j_m = len_j * 1e-3;

  double M = coeff * len_i_m * len_j_m * integral * 0.25;

  return M;
}

bool PEECSolver::are_neighbors(const Filament &fil_i,
                               const Filament &fil_j) const {
  // Two filaments are neighbors if they share a node
  return (fil_i.node_p == fil_j.node_p || fil_i.node_p == fil_j.node_n ||
          fil_i.node_n == fil_j.node_p || fil_i.node_n == fil_j.node_n);
}

} // namespace peec
} // namespace spike
