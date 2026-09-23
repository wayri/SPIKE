/**
 * @file sparse_solver.hpp
 * @brief Sparse Linear System Solvers
 * @version 0.1.6.0
 *
 * Provides high-performance sparse matrix solvers using Eigen.
 * Includes direct (LU, Cholesky) and iterative (CG, BiCGSTAB) methods.
 */

#pragma once

#include <Eigen/IterativeLinearSolvers>
#include <Eigen/Sparse>


namespace spike {
namespace math {

/**
 * @brief Solve sparse linear system Ax = b
 *
 * Uses SparseLU for general matrices.
 *
 * @param A Coefficient matrix (n x n)
 * @param b Right-hand side (n)
 * @return Solution vector x (n)
 */
template <typename T>
Eigen::VectorX<T> solve_sparse_lu(const Eigen::SparseMatrix<T> &A,
                                  const Eigen::VectorX<T> &b) {
  Eigen::SparseLU<Eigen::SparseMatrix<T>> solver;
  solver.compute(A);

  if (solver.info() != Eigen::Success) {
    throw std::runtime_error("SparseLU decomposition failed");
  }

  return solver.solve(b);
}

/**
 * @brief Solve symmetric positive-definite system using Conjugate Gradient
 *
 * @param A Coefficient matrix (n x n, SPD)
 * @param b Right-hand side (n)
 * @param tol Convergence tolerance
 * @param max_iter Maximum iterations
 * @return Solution vector x (n)
 */
template <typename T>
Eigen::VectorX<T> solve_cg(const Eigen::SparseMatrix<T> &A,
                           const Eigen::VectorX<T> &b, double tol = 1e-6,
                           int max_iter = 1000) {
  Eigen::ConjugateGradient<Eigen::SparseMatrix<T>> solver;
  solver.setTolerance(tol);
  solver.setMaxIterations(max_iter);
  solver.compute(A);

  if (solver.info() != Eigen::Success) {
    throw std::runtime_error("CG solver initialization failed");
  }

  return solver.solve(b);
}

} // namespace math
} // namespace spike
