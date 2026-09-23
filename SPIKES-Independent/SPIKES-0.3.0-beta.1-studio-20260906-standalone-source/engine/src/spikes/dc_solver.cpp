#include "spikes/dc_solver.hpp"
#include "spikes/osdi_device.hpp"

#include <Eigen/OrderingMethods>
#include <Eigen/IterativeLinearSolvers>
#include <Eigen/SparseCore>
#include <Eigen/SparseLU>
#include <Eigen/SparseQR>
#include <unsupported/Eigen/IterativeSolvers>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

#if defined(_OPENMP)
#include <omp.h>
#endif

namespace spikes {
namespace {

constexpr double pivot_relative_tolerance =
    64.0 * std::numeric_limits<double>::epsilon();
constexpr double boltzmann_over_electron_charge = 8.617333262145e-5;
constexpr double maximum_exponential_argument = 80.0;

using SparseMatrix = Eigen::SparseMatrix<double, Eigen::ColMajor, int>;
using SparseTriplet = Eigen::Triplet<double, int>;

struct SparseLinearWorkspace {
  Eigen::SparseLU<SparseMatrix, Eigen::COLAMDOrdering<int>> lu;
  Eigen::SparseQR<SparseMatrix, Eigen::COLAMDOrdering<int>> qr;
  std::vector<int> outer_pattern;
  std::vector<int> inner_pattern;
  std::vector<int> qr_outer_pattern;
  std::vector<int> qr_inner_pattern;
  bool symbolic_ready{false};
  bool qr_symbolic_ready{false};
  std::size_t symbolic_analyses{0};
  std::size_t numeric_factorizations{0};
};

[[nodiscard]] bool is_ground_name(std::string_view name) {
  return name == "0" || name == "GND" || name == "gnd";
}

[[nodiscard]] std::size_t matrix_index(std::size_t row, std::size_t column,
                                       std::size_t order) {
  return row * order + column;
}

void stamp_matrix(std::vector<double> &matrix, std::size_t order, NodeId row,
                  NodeId column, double value) {
  if (row != ground_node && column != ground_node) {
    matrix[matrix_index(static_cast<std::size_t>(row - 1),
                        static_cast<std::size_t>(column - 1), order)] += value;
  }
}

void stamp_sparse(std::vector<SparseTriplet> &triplets, NodeId row,
                  NodeId column, double value) {
  if (row != ground_node && column != ground_node) {
    triplets.emplace_back(static_cast<int>(row - 1),
                          static_cast<int>(column - 1), value);
  }
}

void stamp_sparse_index(std::vector<SparseTriplet> &triplets,
                        std::size_t row, std::size_t column, double value) {
  triplets.emplace_back(static_cast<int>(row), static_cast<int>(column), value);
}

void add_sparse(SparseMatrix &matrix, NodeId row, NodeId column,
                double value) {
  if (row != ground_node && column != ground_node) {
    matrix.coeffRef(static_cast<int>(row - 1),
                    static_cast<int>(column - 1)) += value;
  }
}

[[nodiscard]] std::vector<double> sparse_to_dense(const SparseMatrix &matrix) {
  const auto order = static_cast<std::size_t>(matrix.rows());
  std::vector<double> dense(order * order, 0.0);
  for (int column = 0; column < matrix.outerSize(); ++column) {
    for (SparseMatrix::InnerIterator entry(matrix, column); entry; ++entry) {
      dense[matrix_index(static_cast<std::size_t>(entry.row()),
                         static_cast<std::size_t>(entry.col()), order)] =
          entry.value();
    }
  }
  return dense;
}

void stamp_vector(std::vector<double> &values, NodeId node, double value) {
  if (node != ground_node) {
    values[static_cast<std::size_t>(node - 1)] += value;
  }
}

[[nodiscard]] double vector_inf_norm(const std::vector<double> &values) {
  double norm = 0.0;
  for (const double value : values) {
    norm = std::max(norm, std::abs(value));
  }
  return norm;
}

struct LinearSolution {
  SolveStatus status{SolveStatus::numerical_failure};
  std::string message;
  std::vector<double> values;
  std::size_t pivot_swaps{0};
  LinearSolverMethod method{LinearSolverMethod::dense_lu};
  std::size_t iterations{0};
  std::size_t threads{1};
  std::size_t symbolic_analyses{0};
  std::size_t numeric_factorizations{0};
};

[[nodiscard]] LinearSolution solve_dense(std::vector<double> matrix,
                                         std::vector<double> rhs,
                                         std::size_t order) {
  LinearSolution result;
  result.values = std::move(rhs);
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }

  for (std::size_t column = 0; column < order; ++column) {
    std::size_t pivot_row = column;
    double pivot_magnitude = 0.0;
    double column_scale = 0.0;
    for (std::size_t row = column; row < order; ++row) {
      const double magnitude =
          std::abs(matrix[matrix_index(row, column, order)]);
      column_scale = std::max(column_scale, magnitude);
      if (magnitude > pivot_magnitude) {
        pivot_magnitude = magnitude;
        pivot_row = row;
      }
    }
    if (!std::isfinite(pivot_magnitude) || column_scale == 0.0 ||
        pivot_magnitude <= pivot_relative_tolerance * column_scale) {
      result.status = SolveStatus::singular;
      result.message = "singular or underconstrained MNA system";
      result.values.clear();
      return result;
    }
    if (pivot_row != column) {
      for (std::size_t j = column; j < order; ++j) {
        std::swap(matrix[matrix_index(column, j, order)],
                  matrix[matrix_index(pivot_row, j, order)]);
      }
      std::swap(result.values[column], result.values[pivot_row]);
      ++result.pivot_swaps;
    }

    const double pivot = matrix[matrix_index(column, column, order)];
    for (std::size_t row = column + 1; row < order; ++row) {
      const double multiplier = matrix[matrix_index(row, column, order)] / pivot;
      matrix[matrix_index(row, column, order)] = 0.0;
      for (std::size_t j = column + 1; j < order; ++j) {
        matrix[matrix_index(row, j, order)] -=
            multiplier * matrix[matrix_index(column, j, order)];
      }
      result.values[row] -= multiplier * result.values[column];
    }
  }

  for (std::size_t reverse = order; reverse-- > 0;) {
    double value = result.values[reverse];
    for (std::size_t column = reverse + 1; column < order; ++column) {
      value -= matrix[matrix_index(reverse, column, order)] *
               result.values[column];
    }
    result.values[reverse] =
        value / matrix[matrix_index(reverse, reverse, order)];
    if (!std::isfinite(result.values[reverse])) {
      result.status = SolveStatus::numerical_failure;
      result.message = "non-finite value produced by linear solve";
      result.values.clear();
      return result;
    }
  }
  result.status = SolveStatus::converged;
  result.message = "linear system solved";
  return result;
}

[[nodiscard]] bool matrix_is_symmetric(const std::vector<double> &matrix,
                                       std::size_t order) {
  for (std::size_t row = 0; row < order; ++row) {
    for (std::size_t column = row + 1; column < order; ++column) {
      const double left = matrix[matrix_index(row, column, order)];
      const double right = matrix[matrix_index(column, row, order)];
      const double scale = std::max({std::abs(left), std::abs(right),
                                     std::numeric_limits<double>::min()});
      if (std::abs(left - right) >
          64.0 * std::numeric_limits<double>::epsilon() * scale) {
        return false;
      }
    }
  }
  return true;
}

[[nodiscard]] double parallel_dot(const std::vector<double> &left,
                                  const std::vector<double> &right,
                                  std::size_t threads) {
  double sum = 0.0;
  const std::int64_t count = static_cast<std::int64_t>(left.size());
#if defined(_OPENMP)
#pragma omp parallel for reduction(+ : sum) schedule(static)                 \
    num_threads(static_cast<int>(threads)) if (threads > 1 && count >= 128)
#endif
  for (std::int64_t index = 0; index < count; ++index) {
    sum += left[static_cast<std::size_t>(index)] *
           right[static_cast<std::size_t>(index)];
  }
  return sum;
}

[[nodiscard]] std::vector<double>
parallel_matrix_vector(const std::vector<double> &matrix,
                       const std::vector<double> &values, std::size_t order,
                       std::size_t threads) {
  std::vector<double> result(order, 0.0);
  const std::int64_t row_count = static_cast<std::int64_t>(order);
#if defined(_OPENMP)
#pragma omp parallel for schedule(static) num_threads(static_cast<int>(threads)) \
    if (threads > 1 && row_count >= 128)
#endif
  for (std::int64_t signed_row = 0; signed_row < row_count; ++signed_row) {
    const auto row = static_cast<std::size_t>(signed_row);
    double sum = 0.0;
    for (std::size_t column = 0; column < order; ++column) {
      sum += matrix[matrix_index(row, column, order)] * values[column];
    }
    result[row] = sum;
  }
  return result;
}

[[nodiscard]] LinearSolution
solve_conjugate_gradient(const std::vector<double> &matrix,
                         const std::vector<double> &rhs, std::size_t order,
                         const SolverOptions &options) {
  LinearSolution result;
  result.method = LinearSolverMethod::conjugate_gradient;
  result.threads = options.linear_threads;
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }
  if (!matrix_is_symmetric(matrix, order)) {
    result.status = SolveStatus::numerical_failure;
    result.message = "conjugate gradient requires a symmetric matrix";
    return result;
  }
  std::vector<double> inverse_diagonal(order, 0.0);
  for (std::size_t index = 0; index < order; ++index) {
    const double diagonal = matrix[matrix_index(index, index, order)];
    if (!std::isfinite(diagonal) || diagonal <= 0.0) {
      result.status = SolveStatus::numerical_failure;
      result.message =
          "conjugate gradient requires a positive-definite MNA matrix";
      return result;
    }
    inverse_diagonal[index] = 1.0 / diagonal;
  }
  result.values.assign(order, 0.0);
  std::vector<double> residual = rhs;
  const double threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
  if (vector_inf_norm(residual) <= threshold) {
    result.status = SolveStatus::converged;
    result.message = "preconditioned conjugate gradient solved linear system";
    return result;
  }
  std::vector<double> preconditioned(order, 0.0);
  for (std::size_t index = 0; index < order; ++index) {
    preconditioned[index] = inverse_diagonal[index] * residual[index];
  }
  std::vector<double> direction = preconditioned;
  double weighted_norm =
      parallel_dot(residual, preconditioned, options.linear_threads);
  if (!std::isfinite(weighted_norm) || weighted_norm <= 0.0) {
    result.status = SolveStatus::numerical_failure;
    result.message = "conjugate gradient positive-definite check failed";
    result.values.clear();
    return result;
  }
  for (std::size_t iteration = 0;
       iteration < options.max_linear_iterations; ++iteration) {
    const auto product = parallel_matrix_vector(
        matrix, direction, order, options.linear_threads);
    const double curvature =
        parallel_dot(direction, product, options.linear_threads);
    if (!std::isfinite(curvature) || curvature <= 0.0) {
      result.status = SolveStatus::numerical_failure;
      result.message =
          "conjugate gradient detected a non-positive-definite matrix";
      result.values.clear();
      result.iterations = iteration;
      return result;
    }
    const double alpha = weighted_norm / curvature;
    for (std::size_t index = 0; index < order; ++index) {
      result.values[index] += alpha * direction[index];
      residual[index] -= alpha * product[index];
    }
    result.iterations = iteration + 1;
    if (vector_inf_norm(residual) <= threshold) {
      result.status = SolveStatus::converged;
      result.message = "preconditioned conjugate gradient solved linear system";
      return result;
    }
    for (std::size_t index = 0; index < order; ++index) {
      preconditioned[index] = inverse_diagonal[index] * residual[index];
    }
    const double next_weighted_norm =
        parallel_dot(residual, preconditioned, options.linear_threads);
    if (!std::isfinite(next_weighted_norm) || next_weighted_norm <= 0.0) {
      result.status = SolveStatus::numerical_failure;
      result.message = "conjugate gradient residual became invalid";
      result.values.clear();
      return result;
    }
    const double beta = next_weighted_norm / weighted_norm;
    for (std::size_t index = 0; index < order; ++index) {
      direction[index] = preconditioned[index] + beta * direction[index];
    }
    weighted_norm = next_weighted_norm;
  }
  result.status = SolveStatus::nonconverged;
  result.message = "maximum conjugate-gradient iterations reached";
  result.values.clear();
  return result;
}

[[nodiscard]] LinearSolution
solve_restarted_gmres(const std::vector<double> &matrix,
                      const std::vector<double> &rhs, std::size_t order,
                      const SolverOptions &options) {
  LinearSolution result;
  result.method = LinearSolverMethod::gmres;
  result.threads = options.linear_threads;
  result.values.assign(order, 0.0);
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }

  std::vector<double> row_scale(order, 0.0);
  std::vector<double> scaled_rhs(order, 0.0);
  for (std::size_t row = 0; row < order; ++row) {
    double maximum = 0.0;
    for (std::size_t column = 0; column < order; ++column) {
      maximum = std::max(
          maximum, std::abs(matrix[matrix_index(row, column, order)]));
    }
    if (!std::isfinite(maximum) || maximum == 0.0) {
      result.status = SolveStatus::singular;
      result.message = "GMRES found an empty MNA row";
      result.values.clear();
      return result;
    }
    row_scale[row] = 1.0 / maximum;
    scaled_rhs[row] = row_scale[row] * rhs[row];
  }
  const auto scaled_product = [&](const std::vector<double> &values) {
    auto product = parallel_matrix_vector(
        matrix, values, order, options.linear_threads);
    for (std::size_t row = 0; row < order; ++row) {
      product[row] *= row_scale[row];
    }
    return product;
  };
  const auto original_residual = [&](const std::vector<double> &values) {
    auto product = parallel_matrix_vector(
        matrix, values, order, options.linear_threads);
    for (std::size_t row = 0; row < order; ++row) {
      product[row] = rhs[row] - product[row];
    }
    return product;
  };
  const double original_threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
  const double scaled_threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance *
          std::max(1.0, vector_inf_norm(scaled_rhs));
  const std::size_t restart =
      std::min<std::size_t>({40, order, options.max_linear_iterations});
  std::vector<double> residual = scaled_rhs;

  while (result.iterations < options.max_linear_iterations) {
    if (vector_inf_norm(original_residual(result.values)) <=
        original_threshold) {
      result.status = SolveStatus::converged;
      result.message = "row-equilibrated restarted GMRES solved linear system";
      return result;
    }
    const double beta = std::sqrt(std::max(
        0.0, parallel_dot(residual, residual, options.linear_threads)));
    if (!std::isfinite(beta) || beta == 0.0) {
      result.status = SolveStatus::numerical_failure;
      result.message = "GMRES residual norm became invalid";
      result.values.clear();
      return result;
    }

    std::vector<std::vector<double>> basis(
        restart + 1, std::vector<double>(order, 0.0));
    for (std::size_t index = 0; index < order; ++index) {
      basis[0][index] = residual[index] / beta;
    }
    std::vector<double> hessenberg((restart + 1) * restart, 0.0);
    std::vector<double> cosine(restart, 0.0);
    std::vector<double> sine(restart, 0.0);
    std::vector<double> transformed_rhs(restart + 1, 0.0);
    transformed_rhs[0] = beta;
    const auto h = [&](std::size_t row, std::size_t column) -> double & {
      return hessenberg[row * restart + column];
    };
    std::size_t used = 0;
    for (std::size_t column = 0;
         column < restart &&
         result.iterations + column < options.max_linear_iterations;
         ++column) {
      auto work = scaled_product(basis[column]);
      // Two-pass modified Gram-Schmidt limits loss of orthogonality on
      // ill-scaled circuit matrices.
      for (int pass = 0; pass < 2; ++pass) {
        for (std::size_t row = 0; row <= column; ++row) {
          const double projection = parallel_dot(
              work, basis[row], options.linear_threads);
          h(row, column) += projection;
          for (std::size_t index = 0; index < order; ++index) {
            work[index] -= projection * basis[row][index];
          }
        }
      }
      h(column + 1, column) = std::sqrt(std::max(
          0.0, parallel_dot(work, work, options.linear_threads)));
      const bool arnoldi_breakdown =
          h(column + 1, column) <=
          64.0 * std::numeric_limits<double>::epsilon();
      if (!arnoldi_breakdown) {
        for (std::size_t index = 0; index < order; ++index) {
          basis[column + 1][index] =
              work[index] / h(column + 1, column);
        }
      }
      for (std::size_t rotation = 0; rotation < column; ++rotation) {
        const double upper = h(rotation, column);
        const double lower = h(rotation + 1, column);
        h(rotation, column) =
            cosine[rotation] * upper + sine[rotation] * lower;
        h(rotation + 1, column) =
            -sine[rotation] * upper + cosine[rotation] * lower;
      }
      const double magnitude =
          std::hypot(h(column, column), h(column + 1, column));
      if (!std::isfinite(magnitude) || magnitude == 0.0) {
        result.status = SolveStatus::numerical_failure;
        result.message = "GMRES Hessenberg factorization broke down";
        result.values.clear();
        result.iterations += column;
        return result;
      }
      cosine[column] = h(column, column) / magnitude;
      sine[column] = h(column + 1, column) / magnitude;
      h(column, column) = magnitude;
      h(column + 1, column) = 0.0;
      const double prior = transformed_rhs[column];
      transformed_rhs[column] = cosine[column] * prior;
      transformed_rhs[column + 1] = -sine[column] * prior;
      used = column + 1;
      if (std::abs(transformed_rhs[column + 1]) <= scaled_threshold ||
          arnoldi_breakdown) {
        break;
      }
    }

    std::vector<double> coefficients(used, 0.0);
    for (std::size_t reverse = used; reverse-- > 0;) {
      double value = transformed_rhs[reverse];
      for (std::size_t column = reverse + 1; column < used; ++column) {
        value -= h(reverse, column) * coefficients[column];
      }
      if (!std::isfinite(h(reverse, reverse)) || h(reverse, reverse) == 0.0) {
        result.status = SolveStatus::numerical_failure;
        result.message = "GMRES triangular solve broke down";
        result.values.clear();
        result.iterations += used;
        return result;
      }
      coefficients[reverse] = value / h(reverse, reverse);
    }
    for (std::size_t column = 0; column < used; ++column) {
      for (std::size_t index = 0; index < order; ++index) {
        result.values[index] += coefficients[column] * basis[column][index];
      }
    }
    result.iterations += used;
    const auto unscaled_residual = original_residual(result.values);
    if (vector_inf_norm(unscaled_residual) <= original_threshold) {
      result.status = SolveStatus::converged;
      result.message = "row-equilibrated restarted GMRES solved linear system";
      return result;
    }
    auto product = scaled_product(result.values);
    for (std::size_t row = 0; row < order; ++row) {
      residual[row] = scaled_rhs[row] - product[row];
    }
  }
  result.status = SolveStatus::nonconverged;
  result.message = "maximum restarted-GMRES iterations reached";
  result.values.clear();
  return result;
}

[[nodiscard]] bool same_sparse_pattern(const SparseMatrix &matrix,
                                       const SparseLinearWorkspace &workspace) {
  if (!workspace.symbolic_ready ||
      workspace.outer_pattern.size() !=
          static_cast<std::size_t>(matrix.outerSize() + 1) ||
      workspace.inner_pattern.size() !=
          static_cast<std::size_t>(matrix.nonZeros())) {
    return false;
  }
  return std::equal(workspace.outer_pattern.begin(),
                    workspace.outer_pattern.end(), matrix.outerIndexPtr()) &&
         std::equal(workspace.inner_pattern.begin(),
                    workspace.inner_pattern.end(), matrix.innerIndexPtr());
}

void remember_sparse_pattern(const SparseMatrix &matrix,
                             SparseLinearWorkspace &workspace) {
  workspace.outer_pattern.assign(matrix.outerIndexPtr(),
                                 matrix.outerIndexPtr() + matrix.outerSize() + 1);
  workspace.inner_pattern.assign(matrix.innerIndexPtr(),
                                 matrix.innerIndexPtr() + matrix.nonZeros());
  workspace.symbolic_ready = true;
}

[[nodiscard]] bool
same_sparse_qr_pattern(const SparseMatrix &matrix,
                       const SparseLinearWorkspace &workspace) {
  if (!workspace.qr_symbolic_ready ||
      workspace.qr_outer_pattern.size() !=
          static_cast<std::size_t>(matrix.outerSize() + 1) ||
      workspace.qr_inner_pattern.size() !=
          static_cast<std::size_t>(matrix.nonZeros())) {
    return false;
  }
  return std::equal(workspace.qr_outer_pattern.begin(),
                    workspace.qr_outer_pattern.end(), matrix.outerIndexPtr()) &&
         std::equal(workspace.qr_inner_pattern.begin(),
                    workspace.qr_inner_pattern.end(), matrix.innerIndexPtr());
}

void remember_sparse_qr_pattern(const SparseMatrix &matrix,
                                SparseLinearWorkspace &workspace) {
  workspace.qr_outer_pattern.assign(
      matrix.outerIndexPtr(), matrix.outerIndexPtr() + matrix.outerSize() + 1);
  workspace.qr_inner_pattern.assign(
      matrix.innerIndexPtr(), matrix.innerIndexPtr() + matrix.nonZeros());
  workspace.qr_symbolic_ready = true;
}

[[nodiscard]] LinearSolution
solve_sparse_lu(const SparseMatrix &matrix, const std::vector<double> &rhs,
                const SolverOptions &options,
                SparseLinearWorkspace &workspace) {
  LinearSolution result;
  result.method = LinearSolverMethod::sparse_lu;
  result.threads = 1;
  const auto order = static_cast<std::size_t>(matrix.rows());
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }
  if (!same_sparse_pattern(matrix, workspace)) {
    workspace.lu.analyzePattern(matrix);
    ++workspace.symbolic_analyses;
    // Eigen reports status after numeric factorization; querying info() after
    // analyzePattern() reads no completed computation state.
    remember_sparse_pattern(matrix, workspace);
  }
  workspace.lu.factorize(matrix);
  ++workspace.numeric_factorizations;
  result.symbolic_analyses = workspace.symbolic_analyses;
  result.numeric_factorizations = workspace.numeric_factorizations;
  if (workspace.lu.info() != Eigen::Success) {
    result.status = SolveStatus::singular;
    result.message = "sparse LU found a singular or underconstrained MNA system";
    return result;
  }
  const Eigen::Map<const Eigen::VectorXd> mapped_rhs(rhs.data(),
                                                     matrix.rows());
  const Eigen::VectorXd solution = workspace.lu.solve(mapped_rhs);
  if (workspace.lu.info() != Eigen::Success || !solution.allFinite()) {
    result.status = SolveStatus::numerical_failure;
    result.message = "sparse LU produced an invalid solution";
    return result;
  }
  const Eigen::VectorXd residual = mapped_rhs - matrix * solution;
  const double residual_norm = residual.lpNorm<Eigen::Infinity>();
  const double threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
  if (!std::isfinite(residual_norm) || residual_norm > threshold) {
    result.status = SolveStatus::numerical_failure;
    result.message = "sparse LU failed the original-system residual gate";
    return result;
  }
  result.values.assign(solution.data(), solution.data() + solution.size());
  result.status = SolveStatus::converged;
  result.message = same_sparse_pattern(matrix, workspace)
                       ? "sparse LU solved with reusable symbolic ordering"
                       : "sparse LU solved linear system";
  return result;
}

[[nodiscard]] LinearSolution
solve_sparse_qr(const SparseMatrix &matrix, const std::vector<double> &rhs,
                const SolverOptions &options,
                SparseLinearWorkspace &workspace) {
  LinearSolution result;
  result.method = LinearSolverMethod::sparse_qr;
  result.threads = 1;
  const auto order = static_cast<std::size_t>(matrix.rows());
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }
  if (!same_sparse_qr_pattern(matrix, workspace)) {
    workspace.qr.analyzePattern(matrix);
    ++workspace.symbolic_analyses;
    remember_sparse_qr_pattern(matrix, workspace);
  }
  workspace.qr.factorize(matrix);
  ++workspace.numeric_factorizations;
  result.symbolic_analyses = workspace.symbolic_analyses;
  result.numeric_factorizations = workspace.numeric_factorizations;
  if (workspace.qr.info() != Eigen::Success ||
      workspace.qr.rank() != matrix.cols()) {
    result.status = SolveStatus::singular;
    result.message = "sparse QR found a rank-deficient MNA system";
    return result;
  }
  const Eigen::Map<const Eigen::VectorXd> mapped_rhs(rhs.data(),
                                                     matrix.rows());
  const Eigen::VectorXd solution = workspace.qr.solve(mapped_rhs);
  if (workspace.qr.info() != Eigen::Success || !solution.allFinite()) {
    result.status = SolveStatus::numerical_failure;
    result.message = "sparse QR produced an invalid solution";
    return result;
  }
  const double residual_norm =
      (mapped_rhs - matrix * solution).lpNorm<Eigen::Infinity>();
  const double threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
  if (!std::isfinite(residual_norm) || residual_norm > threshold) {
    result.status = SolveStatus::numerical_failure;
    result.message = "sparse QR failed the original-system residual gate";
    return result;
  }
  result.values.assign(solution.data(), solution.data() + solution.size());
  result.status = SolveStatus::converged;
  result.message = "rank-revealing sparse QR solved linear system";
  return result;
}

[[nodiscard]] LinearSolution
solve_ilu_gmres(const SparseMatrix &matrix, const std::vector<double> &rhs,
                const SolverOptions &options) {
  LinearSolution result;
  result.method = LinearSolverMethod::ilu_gmres;
  result.threads = 1;
  result.numeric_factorizations = 1;
  const auto order = static_cast<std::size_t>(matrix.rows());
  if (order == 0) {
    result.status = SolveStatus::converged;
    result.message = "empty circuit";
    return result;
  }

  std::vector<double> row_scale(order, 0.0);
  for (int column = 0; column < matrix.outerSize(); ++column) {
    for (SparseMatrix::InnerIterator entry(matrix, column); entry; ++entry) {
      row_scale[static_cast<std::size_t>(entry.row())] = std::max(
          row_scale[static_cast<std::size_t>(entry.row())],
          std::abs(entry.value()));
    }
  }
  Eigen::VectorXd scaled_rhs(static_cast<Eigen::Index>(order));
  for (std::size_t row = 0; row < order; ++row) {
    if (!std::isfinite(row_scale[row]) || row_scale[row] == 0.0) {
      result.status = SolveStatus::singular;
      result.message = "ILU-GMRES found an empty MNA row";
      return result;
    }
    row_scale[row] = 1.0 / row_scale[row];
    scaled_rhs[static_cast<Eigen::Index>(row)] = row_scale[row] * rhs[row];
  }
  SparseMatrix scaled = matrix;
  for (int column = 0; column < scaled.outerSize(); ++column) {
    for (SparseMatrix::InnerIterator entry(scaled, column); entry; ++entry) {
      entry.valueRef() *= row_scale[static_cast<std::size_t>(entry.row())];
    }
  }

  Eigen::GMRES<SparseMatrix, Eigen::IncompleteLUT<double>> solver;
  solver.set_restart(static_cast<int>(std::min<std::size_t>(50, order)));
  solver.setMaxIterations(static_cast<int>(std::min<std::size_t>(
      options.max_linear_iterations,
      static_cast<std::size_t>(std::numeric_limits<int>::max()))));
  const double scaled_norm = scaled_rhs.lpNorm<Eigen::Infinity>();
  const double scaled_threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, scaled_norm);
  solver.setTolerance(std::max(std::numeric_limits<double>::epsilon(),
                               scaled_threshold /
                                   std::max(1.0, scaled_rhs.norm())));
  solver.preconditioner().setDroptol(1.0e-4);
  solver.preconditioner().setFillfactor(10);
  solver.compute(scaled);
  if (solver.info() != Eigen::Success) {
    result.status = SolveStatus::numerical_failure;
    result.message = "ILU preconditioner construction failed";
    return result;
  }
  const Eigen::VectorXd solution = solver.solve(scaled_rhs);
  result.iterations = static_cast<std::size_t>(solver.iterations());
  if (solver.info() != Eigen::Success || !solution.allFinite()) {
    result.status = SolveStatus::nonconverged;
    result.message = "ILU-preconditioned GMRES did not converge";
    return result;
  }
  const Eigen::Map<const Eigen::VectorXd> mapped_rhs(rhs.data(),
                                                     matrix.rows());
  const Eigen::VectorXd residual = mapped_rhs - matrix * solution;
  const double residual_norm = residual.lpNorm<Eigen::Infinity>();
  const double original_threshold = options.linear_absolute_tolerance +
      options.linear_relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
  if (!std::isfinite(residual_norm) || residual_norm > original_threshold) {
    result.status = SolveStatus::nonconverged;
    result.message = "ILU-GMRES failed the original-system residual gate";
    return result;
  }
  result.values.assign(solution.data(), solution.data() + solution.size());
  result.status = SolveStatus::converged;
  result.message = "row-equilibrated ILU-preconditioned sparse GMRES solved linear system";
  return result;
}

[[nodiscard]] LinearSolution solve_linear(const SparseMatrix &sparse_matrix,
                                          std::vector<double> rhs,
                                          std::size_t order,
                                          const SolverOptions &options,
                                          SparseLinearWorkspace &workspace) {
  if (options.linear_solver == LinearSolverMethod::sparse_lu) {
    return solve_sparse_lu(sparse_matrix, rhs, options, workspace);
  }
  if (options.linear_solver == LinearSolverMethod::ilu_gmres) {
    return solve_ilu_gmres(sparse_matrix, rhs, options);
  }
  if (options.linear_solver == LinearSolverMethod::sparse_qr) {
    return solve_sparse_qr(sparse_matrix, rhs, options, workspace);
  }
  if (options.linear_solver == LinearSolverMethod::automatic && order >= 1024) {
    auto iterative = solve_ilu_gmres(sparse_matrix, rhs, options);
    if (iterative.status == SolveStatus::converged) {
      return iterative;
    }
  }
  if (options.linear_solver == LinearSolverMethod::automatic && order >= 128) {
    return solve_sparse_lu(sparse_matrix, rhs, options, workspace);
  }

  auto matrix = sparse_to_dense(sparse_matrix);
  const bool automatic_candidate =
      options.linear_solver == LinearSolverMethod::automatic && order >= 64 &&
      matrix_is_symmetric(matrix, order);
  if (options.linear_solver == LinearSolverMethod::conjugate_gradient ||
      automatic_candidate) {
    auto iterative =
        solve_conjugate_gradient(matrix, rhs, order, options);
    if (iterative.status == SolveStatus::converged ||
        options.linear_solver == LinearSolverMethod::conjugate_gradient) {
      return iterative;
    }
  }
  const bool automatic_gmres_candidate =
      options.linear_solver == LinearSolverMethod::automatic && order >= 512;
  if (options.linear_solver == LinearSolverMethod::gmres ||
      automatic_gmres_candidate) {
    auto iterative = solve_restarted_gmres(matrix, rhs, order, options);
    if (iterative.status == SolveStatus::converged ||
        options.linear_solver == LinearSolverMethod::gmres) {
      return iterative;
    }
  }
  auto direct = solve_dense(std::move(matrix), std::move(rhs), order);
  direct.method = LinearSolverMethod::dense_lu;
  direct.threads = 1;
  return direct;
}

struct DiodePoint {
  double current_a;
  double conductance_s;
};

[[nodiscard]] DiodePoint diode_point(const DiodeModel &model,
                                     double junction_voltage_v);

struct SwitchPoint {
  double conductance_s;
  double conductance_derivative_s_per_v;
};

struct MosfetPoint {
  double drain_current_a;
  // Derivatives of drain current with respect to D, G, S, and B voltages.
  std::array<double, 4> derivative_s;
};

struct BjtPoint {
  // Collector, base, and emitter currents, positive into each terminal.
  std::array<double, 3> current_a;
  // Row-major derivatives for terminal currents versus C, B, and E voltage.
  std::array<std::array<double, 3>, 3> derivative_s;
};

struct WbgRawPoint {
  std::array<double, 4> current_a{};
  std::array<double, 4> charge_c{};
  double power_w{0.0};
  double junction_temperature_k{0.0};
};

void validate_wbg_model(const WbgFetElectrothermalModel &model) {
  const double values[] = {
      model.threshold_voltage_v,
      model.transconductance_a_per_v2,
      model.channel_length_modulation_per_v,
      model.mobility_temperature_exponent,
      model.threshold_temperature_coefficient_v_per_k,
      model.off_conductance_s,
      model.reverse_conduction_threshold_v,
      model.reverse_conductance_s,
      model.body_diode_saturation_current_a,
      model.body_diode_emission_coefficient,
      model.breakdown_voltage_v,
      model.breakdown_temperature_coefficient_v_per_k,
      model.avalanche_current_scale_a,
      model.avalanche_slope_v,
      model.gate_leakage_conductance_s,
      model.gate_source_capacitance_f,
      model.gate_drain_capacitance_f,
      model.drain_source_capacitance_f,
      model.ambient_temperature_k,
      model.thermal_resistance_k_per_w,
      model.thermal_capacitance_j_per_k,
      model.minimum_temperature_k,
      model.maximum_temperature_k,
      model.maximum_absolute_voltage_v,
      model.maximum_absolute_current_a,
  };
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      model.transconductance_a_per_v2 <= 0.0 ||
      model.channel_length_modulation_per_v < 0.0 ||
      model.mobility_temperature_exponent < 0.0 ||
      model.off_conductance_s <= 0.0 ||
      model.reverse_conduction_threshold_v < 0.0 ||
      model.reverse_conductance_s < 0.0 ||
      model.body_diode_saturation_current_a <= 0.0 ||
      model.body_diode_emission_coefficient <= 0.0 ||
      model.breakdown_voltage_v <= 0.0 ||
      model.avalanche_current_scale_a <= 0.0 ||
      model.avalanche_slope_v <= 0.0 ||
      model.gate_leakage_conductance_s < 0.0 ||
      model.gate_source_capacitance_f < 0.0 ||
      model.gate_drain_capacitance_f < 0.0 ||
      model.drain_source_capacitance_f < 0.0 ||
      model.ambient_temperature_k <= 0.0 ||
      model.thermal_resistance_k_per_w <= 0.0 ||
      model.thermal_capacitance_j_per_k <= 0.0 ||
      model.minimum_temperature_k <= 0.0 ||
      model.minimum_temperature_k >= model.maximum_temperature_k ||
      model.ambient_temperature_k < model.minimum_temperature_k ||
      model.ambient_temperature_k > model.maximum_temperature_k ||
      model.maximum_absolute_voltage_v <= model.breakdown_voltage_v ||
      model.maximum_absolute_current_a <= 0.0) {
    throw std::invalid_argument(
        "WBG electrothermal parameters violate their finite positive validity "
        "and technology bounds");
  }
}

[[nodiscard]] DiodePoint bounded_diode(double saturation_current_a,
                                       double emission_coefficient,
                                       double temperature_k,
                                       double voltage_v) {
  return diode_point(
      DiodeModel{saturation_current_a, emission_coefficient, temperature_k},
      voltage_v);
}

[[nodiscard]] double avalanche_current(
    const WbgFetElectrothermalModel &model, double excess_voltage_v) {
  if (excess_voltage_v <= 0.0) {
    return 0.0;
  }
  const double argument = excess_voltage_v / model.avalanche_slope_v;
  if (argument <= maximum_exponential_argument) {
    return model.avalanche_current_scale_a * std::expm1(argument);
  }
  const double boundary = std::exp(maximum_exponential_argument);
  return model.avalanche_current_scale_a *
         (boundary * (1.0 + argument - maximum_exponential_argument) - 1.0);
}

[[nodiscard]] WbgRawPoint wbg_raw_point(
    const WbgFetElectrothermalModel &model,
    const std::array<double, 5> &voltage) {
  const double drain = voltage[0];
  const double gate = voltage[1];
  const double source = voltage[2];
  const double bulk = voltage[3];
  const double temperature = model.ambient_temperature_k + voltage[4];
  const bool forward = drain >= source;
  const double local_drain = forward ? drain : source;
  const double local_source = forward ? source : drain;
  const double vds = local_drain - local_source;
  const double vgs = gate - local_source;
  const double threshold =
      model.threshold_voltage_v +
      model.threshold_temperature_coefficient_v_per_k *
          (temperature - model.ambient_temperature_k);
  const double beta = model.transconductance_a_per_v2 *
                      std::pow(model.ambient_temperature_k / temperature,
                               model.mobility_temperature_exponent);
  const double overdrive = vgs - threshold;
  double channel = model.off_conductance_s * vds;
  if (overdrive > 0.0) {
    if (vds < overdrive) {
      channel += beta * (overdrive * vds - 0.5 * vds * vds);
    } else {
      channel += 0.5 * beta * overdrive * overdrive;
    }
    channel *= 1.0 + model.channel_length_modulation_per_v * vds;
  }
  double drain_current = forward ? channel : -channel;
  double gate_current = model.gate_leakage_conductance_s *
                        ((gate - source) + (gate - drain));
  double bulk_current = 0.0;
  drain_current -= model.gate_leakage_conductance_s * (gate - drain);
  double source_current =
      -drain_current - gate_current; // KCL before bulk-junction currents.

  const double raw_vds = drain - source;
  if (model.technology == WbgTechnology::gan_hemt &&
      raw_vds < -model.reverse_conduction_threshold_v) {
    const double reverse = model.reverse_conductance_s *
                           (-raw_vds -
                            model.reverse_conduction_threshold_v);
    drain_current -= reverse;
    source_current += reverse;
  }
  if (model.technology == WbgTechnology::sic_mosfet) {
    const double body_to_drain = bounded_diode(
        model.body_diode_saturation_current_a,
        model.body_diode_emission_coefficient, temperature, bulk - drain)
                                     .current_a;
    const double body_to_source = bounded_diode(
        model.body_diode_saturation_current_a,
        model.body_diode_emission_coefficient, temperature, bulk - source)
                                      .current_a;
    bulk_current += body_to_drain + body_to_source;
    drain_current -= body_to_drain;
    source_current -= body_to_source;
  }
  const double breakdown =
      model.breakdown_voltage_v +
      model.breakdown_temperature_coefficient_v_per_k *
          (temperature - model.ambient_temperature_k);
  const double avalanche =
      avalanche_current(model, std::abs(raw_vds) - breakdown);
  if (raw_vds >= 0.0) {
    drain_current += avalanche;
    source_current -= avalanche;
  } else {
    drain_current -= avalanche;
    source_current += avalanche;
  }

  // Charge-conserving linearized terminal charges. These are consumed by
  // direct qualification today and are reserved for native transient history
  // stamping in the next dynamic-model slice.
  const double qd = model.gate_drain_capacitance_f * (drain - gate) +
                    model.drain_source_capacitance_f * (drain - source);
  const double qg = model.gate_source_capacitance_f * (gate - source) +
                    model.gate_drain_capacitance_f * (gate - drain);
  const double qb = 0.0;
  const double qs = -(qd + qg + qb);
  const std::array<double, 4> currents{
      drain_current, gate_current, source_current, bulk_current};
  double power = drain * currents[0] + gate * currents[1] +
                 source * currents[2] + bulk * currents[3];
  // Roundoff at a zero-bias point must not create a thermal source.
  power = std::max(0.0, power);
  return {currents, {qd, qg, qs, qb}, power, temperature};
}

[[nodiscard]] BjtPoint bjt_ebers_moll_point(
    const BjtEbersMollModel &model, double collector_v, double base_v,
    double emitter_v) {
  const DiodeModel junction{model.saturation_current_a,
                            model.emission_coefficient, model.temperature_k};
  const auto forward = diode_point(junction, base_v - emitter_v);
  const auto reverse = diode_point(junction, base_v - collector_v);
  const double alpha_f = model.forward_alpha;
  const double alpha_r = model.reverse_alpha;
  BjtPoint point{};
  point.current_a = {
      alpha_f * forward.current_a - reverse.current_a,
      (1.0 - alpha_f) * forward.current_a +
          (1.0 - alpha_r) * reverse.current_a,
      -forward.current_a + alpha_r * reverse.current_a,
  };
  const double gf = forward.conductance_s;
  const double gr = reverse.conductance_s;
  point.derivative_s = {{
      {gr, alpha_f * gf - gr, -alpha_f * gf},
      {-(1.0 - alpha_r) * gr,
       (1.0 - alpha_f) * gf + (1.0 - alpha_r) * gr,
       -(1.0 - alpha_f) * gf},
      {-alpha_r * gr, -gf + alpha_r * gr, gf},
  }};
  return point;
}

[[nodiscard]] double mosfet_level1_current(const MosfetLevel1Model &model,
                                           double drain_v, double gate_v,
                                           double source_v, double bulk_v) {
  const bool forward = drain_v >= source_v;
  const double local_drain = forward ? drain_v : source_v;
  const double local_source = forward ? source_v : drain_v;
  const double vds = local_drain - local_source;
  const double vgs = gate_v - local_source;
  const double vsb = std::max(0.0, local_source - bulk_v);
  const double threshold =
      model.threshold_voltage_v +
      model.body_effect_sqrt_v *
          (std::sqrt(model.surface_potential_v + vsb) -
           std::sqrt(model.surface_potential_v));
  const double overdrive = vgs - threshold;
  double channel = 0.0;
  if (overdrive > 0.0) {
    const double beta = model.transconductance_a_per_v2 *
                        model.width_over_length;
    if (vds < overdrive) {
      channel = beta * (overdrive * vds - 0.5 * vds * vds);
    } else {
      channel = 0.5 * beta * overdrive * overdrive;
    }
    channel *= 1.0 + model.channel_length_modulation_per_v * vds;
  }
  const double current = channel + model.off_conductance_s * vds;
  return forward ? current : -current;
}

[[nodiscard]] MosfetPoint mosfet_level1_point(const MosfetLevel1Model &model,
                                              double drain_v, double gate_v,
                                              double source_v, double bulk_v) {
  const std::array<double, 4> voltage{drain_v, gate_v, source_v, bulk_v};
  MosfetPoint point{mosfet_level1_current(model, drain_v, gate_v, source_v,
                                          bulk_v), {}};
  for (std::size_t column = 0; column < voltage.size(); ++column) {
    const double step = std::cbrt(std::numeric_limits<double>::epsilon()) *
                        std::max(1.0, std::abs(voltage[column]));
    auto plus = voltage;
    auto minus = voltage;
    plus[column] += step;
    minus[column] -= step;
    point.derivative_s[column] =
        (mosfet_level1_current(model, plus[0], plus[1], plus[2], plus[3]) -
         mosfet_level1_current(model, minus[0], minus[1], minus[2], minus[3])) /
        (2.0 * step);
  }
  return point;
}

[[nodiscard]] SwitchPoint
switch_point(const VoltageControlledSwitchModel &model,
             double control_voltage_v) {
  const double on_conductance = 1.0 / model.on_resistance_ohm;
  const double off_conductance = 1.0 / model.off_resistance_ohm;
  const double normalized =
      (control_voltage_v - model.threshold_voltage_v) /
      model.transition_voltage_v;
  const double tangent = std::tanh(normalized);
  const double blend = 0.5 * (1.0 + tangent);
  const double derivative = 0.5 * (1.0 - tangent * tangent) /
                            model.transition_voltage_v;
  return {off_conductance + blend * (on_conductance - off_conductance),
          derivative * (on_conductance - off_conductance)};
}

[[nodiscard]] DiodePoint diode_point(const DiodeModel &model,
                                     double junction_voltage_v) {
  const double thermal_voltage = boltzmann_over_electron_charge *
                                 model.temperature_k *
                                 model.emission_coefficient;
  const double argument = junction_voltage_v / thermal_voltage;
  if (argument <= maximum_exponential_argument) {
    const double exponential = std::exp(argument);
    return {model.saturation_current_a * std::expm1(argument),
            model.saturation_current_a * exponential / thermal_voltage};
  }

  // C1 continuation prevents overflow while preserving the value and exact
  // analytical derivative at the exponential limiting boundary.
  const double boundary = std::exp(maximum_exponential_argument);
  return {model.saturation_current_a *
              (boundary * (1.0 + argument - maximum_exponential_argument) -
               1.0),
          model.saturation_current_a * boundary / thermal_voltage};
}

[[nodiscard]] double critical_voltage(const DiodeModel &model) {
  const double thermal_voltage = boltzmann_over_electron_charge *
                                 model.temperature_k *
                                 model.emission_coefficient;
  return thermal_voltage *
         std::log(thermal_voltage /
                  (std::sqrt(2.0) * model.saturation_current_a));
}

[[nodiscard]] double limit_junction_voltage(double proposed, double previous,
                                            const DiodeModel &model) {
  const double thermal_voltage = boltzmann_over_electron_charge *
                                 model.temperature_k *
                                 model.emission_coefficient;
  const double critical = critical_voltage(model);
  if (proposed <= critical ||
      std::abs(proposed - previous) <= 2.0 * thermal_voltage) {
    return proposed;
  }
  if (previous > 0.0) {
    const double argument = 1.0 + (proposed - previous) / thermal_voltage;
    return argument > 0.0
               ? previous + thermal_voltage * std::log(argument)
               : critical;
  }
  return proposed > 0.0
             ? thermal_voltage * std::log(proposed / thermal_voltage)
             : critical;
}

struct ElectrothermalResistorPoint {
  double current_a{0.0};
  double conductance_s{0.0};
  double current_temperature_derivative_a_per_k{0.0};
  double power_w{0.0};
  double power_voltage_derivative_a{0.0};
  double power_temperature_derivative_w_per_k{0.0};
};

[[nodiscard]] ElectrothermalResistorPoint electrothermal_resistor_point(
    const ElectrothermalResistorModel &model, double voltage_v,
    double temperature_rise_k) {
  const double temperature = model.ambient_temperature_k + temperature_rise_k;
  const double scale = 1.0 +
                       model.temperature_coefficient_per_k *
                           temperature_rise_k;
  if (!std::isfinite(voltage_v) || !std::isfinite(temperature_rise_k) ||
      temperature < model.minimum_temperature_k ||
      temperature > model.maximum_temperature_k || !(scale > 0.0)) {
    throw std::out_of_range(
        "electrothermal resistor is outside its temperature envelope");
  }
  const double resistance = model.resistance_ohm * scale;
  const double conductance = 1.0 / resistance;
  const double conductance_temperature_derivative =
      -model.resistance_ohm * model.temperature_coefficient_per_k /
      (resistance * resistance);
  return {
      voltage_v * conductance,
      conductance,
      voltage_v * conductance_temperature_derivative,
      voltage_v * voltage_v * conductance,
      2.0 * voltage_v * conductance,
      voltage_v * voltage_v * conductance_temperature_derivative,
  };
}

struct SystemEvaluation {
  std::vector<double> residual;
  SparseMatrix jacobian;
};

} // namespace

WbgFetElectrothermalPoint evaluate_wbg_fet_electrothermal(
    const WbgFetElectrothermalModel &model, double drain_voltage_v,
    double gate_voltage_v, double source_voltage_v, double bulk_voltage_v,
    double temperature_rise_k) {
  validate_wbg_model(model);
  const std::array<double, 5> voltage{drain_voltage_v, gate_voltage_v,
                                      source_voltage_v, bulk_voltage_v,
                                      temperature_rise_k};
  if (!std::all_of(voltage.begin(), voltage.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::invalid_argument("WBG terminal values must be finite");
  }
  const double device_voltages[] = {
      drain_voltage_v - source_voltage_v,
      gate_voltage_v - source_voltage_v,
      bulk_voltage_v - drain_voltage_v,
      bulk_voltage_v - source_voltage_v,
  };
  if (std::any_of(std::begin(device_voltages), std::end(device_voltages),
                  [&model](double value) {
                    return std::abs(value) >
                           model.maximum_absolute_voltage_v;
                  })) {
    throw std::out_of_range("WBG terminal difference is outside the model envelope");
  }
  const double temperature = model.ambient_temperature_k + temperature_rise_k;
  if (temperature < model.minimum_temperature_k ||
      temperature > model.maximum_temperature_k) {
    throw std::out_of_range("WBG temperature is outside the model envelope");
  }

  const auto base = wbg_raw_point(model, voltage);
  WbgFetElectrothermalPoint point{};
  point.terminal_current_a = base.current_a;
  point.terminal_charge_c = base.charge_c;
  point.dissipated_power_w = base.power_w;
  point.junction_temperature_k = base.junction_temperature_k;
  for (const double current : point.terminal_current_a) {
    if (!std::isfinite(current) ||
        std::abs(current) > model.maximum_absolute_current_a) {
      throw std::out_of_range("WBG current is outside the model envelope");
    }
  }

  for (std::size_t column = 0; column < voltage.size(); ++column) {
    const double step = std::cbrt(std::numeric_limits<double>::epsilon()) *
                        std::max(1.0, std::abs(voltage[column]));
    auto plus = voltage;
    auto minus = voltage;
    plus[column] += step;
    minus[column] -= step;
    const auto positive = wbg_raw_point(model, plus);
    const auto negative = wbg_raw_point(model, minus);
    for (std::size_t row = 0; row < point.terminal_current_a.size(); ++row) {
      point.current_jacobian[row][column] =
          (positive.current_a[row] - negative.current_a[row]) / (2.0 * step);
    }
    point.power_jacobian[column] =
        (positive.power_w - negative.power_w) / (2.0 * step);
    if (column < 4) {
      for (std::size_t row = 0; row < point.terminal_charge_c.size(); ++row) {
        point.charge_jacobian[row][column] =
            (positive.charge_c[row] - negative.charge_c[row]) /
            (2.0 * step);
      }
    }
  }
  return point;
}

double OperatingPointResult::node_voltage(std::string_view name) const {
  if (is_ground_name(name)) {
    return 0.0;
  }
  const auto found = std::find_if(
      node_voltages_.begin(), node_voltages_.end(),
      [name](const NodeVoltage &value) { return value.name == name; });
  if (found == node_voltages_.end()) {
    throw std::out_of_range("unknown circuit node");
  }
  return found->voltage_v;
}

double OperatingPointResult::element_current(std::string_view id) const {
  const auto found = std::find_if(
      elements_.begin(), elements_.end(),
      [id](const ElementOperatingPoint &value) { return value.id == id; });
  if (found == elements_.end()) {
    throw std::out_of_range("unknown circuit element");
  }
  return found->current_a;
}

double OperatingPointResult::element_power(std::string_view id) const {
  const auto found = std::find_if(
      elements_.begin(), elements_.end(),
      [id](const ElementOperatingPoint &value) { return value.id == id; });
  if (found == elements_.end()) {
    throw std::out_of_range("unknown circuit element");
  }
  return found->power_w;
}

Circuit::Circuit() : node_names_{"0"} {}

NodeId Circuit::node(std::string_view name) {
  if (name.empty()) {
    throw std::invalid_argument("node name must not be empty");
  }
  if (is_ground_name(name)) {
    return ground_node;
  }
  const auto found = std::find(node_names_.begin(), node_names_.end(), name);
  if (found != node_names_.end()) {
    return static_cast<NodeId>(std::distance(node_names_.begin(), found));
  }
  if (node_names_.size() > std::numeric_limits<NodeId>::max()) {
    throw std::length_error("circuit node limit exceeded");
  }
  node_names_.emplace_back(name);
  return static_cast<NodeId>(node_names_.size() - 1);
}

void Circuit::add_resistor(std::string id, std::string positive_node,
                           std::string negative_node, double resistance_ohm) {
  if (!std::isfinite(resistance_ohm) || resistance_ohm <= 0.0) {
    throw std::invalid_argument("resistance must be finite and greater than zero");
  }
  add_element(ElementType::resistor, std::move(id), std::move(positive_node),
              std::move(negative_node), resistance_ohm);
}

void Circuit::add_current_source(std::string id, std::string positive_node,
                                 std::string negative_node, double current_a) {
  if (!std::isfinite(current_a)) {
    throw std::invalid_argument("source current must be finite");
  }
  add_element(ElementType::current_source, std::move(id),
              std::move(positive_node), std::move(negative_node), current_a);
}

void Circuit::add_voltage_source(std::string id, std::string positive_node,
                                 std::string negative_node, double voltage_v) {
  if (!std::isfinite(voltage_v)) {
    throw std::invalid_argument("source voltage must be finite");
  }
  add_element(ElementType::voltage_source, std::move(id),
              std::move(positive_node), std::move(negative_node), voltage_v);
}

namespace {

void validate_pulse(const PulseWaveform &waveform) {
  const double values[] = {
      waveform.initial_value, waveform.pulsed_value, waveform.delay_s,
      waveform.rise_time_s, waveform.fall_time_s, waveform.pulse_width_s,
      waveform.period_s};
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      waveform.delay_s < 0.0 || waveform.rise_time_s < 0.0 ||
      waveform.fall_time_s < 0.0 || waveform.pulse_width_s < 0.0 ||
      waveform.period_s <= 0.0 ||
      waveform.rise_time_s + waveform.pulse_width_s +
              waveform.fall_time_s >
          waveform.period_s) {
    throw std::invalid_argument(
        "PULSE values must be finite, times nonnegative, period positive, "
        "and rise + width + fall no greater than period");
  }
}

void validate_pwl(const std::vector<PwlPoint> &points) {
  if (points.empty()) {
    throw std::invalid_argument("PWL source requires at least one point");
  }
  double prior = -1.0;
  for (const auto &point : points) {
    if (!std::isfinite(point.time_s) || point.time_s < 0.0 ||
        !std::isfinite(point.value) || point.time_s <= prior) {
      throw std::invalid_argument(
          "PWL point times must be finite, nonnegative, and strictly "
          "increasing; values must be finite");
    }
    prior = point.time_s;
  }
}

} // namespace

void Circuit::add_pulse_current_source(std::string id,
                                       std::string positive_node,
                                       std::string negative_node,
                                       PulseWaveform waveform) {
  validate_pulse(waveform);
  add_element(ElementType::current_source, std::move(id),
              std::move(positive_node), std::move(negative_node),
              waveform.initial_value);
  elements_.back().waveform_type = WaveformType::pulse;
  elements_.back().pulse = waveform;
}

void Circuit::add_pulse_voltage_source(std::string id,
                                       std::string positive_node,
                                       std::string negative_node,
                                       PulseWaveform waveform) {
  validate_pulse(waveform);
  add_element(ElementType::voltage_source, std::move(id),
              std::move(positive_node), std::move(negative_node),
              waveform.initial_value);
  elements_.back().waveform_type = WaveformType::pulse;
  elements_.back().pulse = waveform;
}

void Circuit::add_pwl_current_source(std::string id,
                                     std::string positive_node,
                                     std::string negative_node,
                                     std::vector<PwlPoint> points) {
  validate_pwl(points);
  const double initial = points.front().value;
  add_element(ElementType::current_source, std::move(id),
              std::move(positive_node), std::move(negative_node), initial);
  elements_.back().waveform_type = WaveformType::pwl;
  elements_.back().pwl = std::move(points);
}

void Circuit::add_pwl_voltage_source(std::string id,
                                     std::string positive_node,
                                     std::string negative_node,
                                     std::vector<PwlPoint> points) {
  validate_pwl(points);
  const double initial = points.front().value;
  add_element(ElementType::voltage_source, std::move(id),
              std::move(positive_node), std::move(negative_node), initial);
  elements_.back().waveform_type = WaveformType::pwl;
  elements_.back().pwl = std::move(points);
}

void Circuit::add_voltage_controlled_switch(
    std::string id, std::string positive_node, std::string negative_node,
    std::string control_positive_node, std::string control_negative_node,
    VoltageControlledSwitchModel model) {
  if (!std::isfinite(model.on_resistance_ohm) ||
      !std::isfinite(model.off_resistance_ohm) ||
      !std::isfinite(model.threshold_voltage_v) ||
      !std::isfinite(model.transition_voltage_v) ||
      model.on_resistance_ohm <= 0.0 ||
      model.off_resistance_ohm <= model.on_resistance_ohm ||
      model.transition_voltage_v <= 0.0) {
    throw std::invalid_argument(
        "switch Ron must be positive, Roff greater than Ron, and threshold "
        "and positive transition voltage finite");
  }
  const NodeId control_positive = node(control_positive_node);
  const NodeId control_negative = node(control_negative_node);
  if (control_positive == control_negative) {
    throw std::invalid_argument("switch control terminals must be different nodes");
  }
  add_element(ElementType::voltage_controlled_switch, std::move(id),
              std::move(positive_node), std::move(negative_node), 0.0);
  elements_.back().control_positive_node = control_positive;
  elements_.back().control_negative_node = control_negative;
  elements_.back().switch_model = model;
}

void Circuit::add_diode(std::string id, std::string anode_node,
                        std::string cathode_node, DiodeModel model) {
  if (!std::isfinite(model.saturation_current_a) ||
      model.saturation_current_a <= 0.0 ||
      !std::isfinite(model.emission_coefficient) ||
      model.emission_coefficient <= 0.0 || !std::isfinite(model.temperature_k) ||
      model.temperature_k <= 0.0) {
    throw std::invalid_argument("diode parameters must be finite and positive");
  }
  add_element(ElementType::diode, std::move(id), std::move(anode_node),
              std::move(cathode_node), 0.0);
  elements_.back().diode = model;
}

void Circuit::add_dynamic_diode(std::string id, std::string anode_node,
                                std::string cathode_node,
                                DynamicDiodeModel model) {
  const auto &junction = model.junction;
  if (!std::isfinite(junction.saturation_current_a) ||
      junction.saturation_current_a <= 0.0 ||
      !std::isfinite(junction.emission_coefficient) ||
      junction.emission_coefficient <= 0.0 ||
      !std::isfinite(junction.temperature_k) ||
      junction.temperature_k <= 0.0 ||
      !std::isfinite(model.transit_time_s) || model.transit_time_s <= 0.0 ||
      !std::isfinite(model.junction_capacitance_f) ||
      model.junction_capacitance_f < 0.0 ||
      !std::isfinite(model.initial_stored_charge_c) ||
      model.initial_stored_charge_c < 0.0) {
    throw std::invalid_argument(
        "dynamic diode junction parameters and transit time must be positive; "
        "capacitance and initial stored charge must be finite and nonnegative");
  }
  add_element(ElementType::dynamic_diode, std::move(id),
              std::move(anode_node), std::move(cathode_node), 0.0);
  elements_.back().diode = junction;
  elements_.back().dynamic_diode = model;
}

void Circuit::add_electrothermal_resistor(
    std::string id, std::string positive_node, std::string negative_node,
    std::string thermal_node, ElectrothermalResistorModel model) {
  const double values[] = {
      model.resistance_ohm,
      model.temperature_coefficient_per_k,
      model.ambient_temperature_k,
      model.thermal_resistance_k_per_w,
      model.thermal_capacitance_j_per_k,
      model.minimum_temperature_k,
      model.maximum_temperature_k,
  };
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      model.resistance_ohm <= 0.0 ||
      model.thermal_resistance_k_per_w <= 0.0 ||
      model.thermal_capacitance_j_per_k <= 0.0 ||
      model.ambient_temperature_k <= 0.0 ||
      model.minimum_temperature_k <= 0.0 ||
      model.minimum_temperature_k >= model.maximum_temperature_k ||
      model.ambient_temperature_k < model.minimum_temperature_k ||
      model.ambient_temperature_k > model.maximum_temperature_k ||
      1.0 + model.temperature_coefficient_per_k *
                    (model.minimum_temperature_k -
                     model.ambient_temperature_k) <=
          0.0 ||
      1.0 + model.temperature_coefficient_per_k *
                    (model.maximum_temperature_k -
                     model.ambient_temperature_k) <=
          0.0) {
    throw std::invalid_argument(
        "electrothermal resistor parameters violate their finite positive "
        "validity envelope");
  }
  const NodeId thermal = node(thermal_node);
  if (thermal == ground_node) {
    throw std::invalid_argument(
        "electrothermal resistor thermal node must be non-ground");
  }
  add_element(ElementType::electrothermal_resistor, std::move(id),
              std::move(positive_node), std::move(negative_node), 0.0);
  if (thermal == elements_.back().positive_node ||
      thermal == elements_.back().negative_node) {
    elements_.pop_back();
    throw std::invalid_argument(
        "electrothermal resistor thermal node must not alias an electrical "
        "terminal");
  }
  elements_.back().thermal_node = thermal;
  elements_.back().electrothermal_resistor = model;
}

void Circuit::add_mosfet_level1(std::string id, std::string drain_node,
                                std::string gate_node,
                                std::string source_node,
                                std::string bulk_node,
                                MosfetLevel1Model model) {
  const double values[] = {
      model.threshold_voltage_v,
      model.transconductance_a_per_v2,
      model.channel_length_modulation_per_v,
      model.body_effect_sqrt_v,
      model.surface_potential_v,
      model.width_over_length,
      model.off_conductance_s,
  };
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      model.transconductance_a_per_v2 <= 0.0 ||
      model.channel_length_modulation_per_v < 0.0 ||
      model.body_effect_sqrt_v < 0.0 || model.surface_potential_v <= 0.0 ||
      model.width_over_length <= 0.0 || model.off_conductance_s <= 0.0) {
    throw std::invalid_argument(
        "MOSFET Level-1 parameters must be finite; KP, PHI, W/L, and GOFF "
        "must be positive; LAMBDA and GAMMA must be nonnegative");
  }
  const NodeId gate = node(gate_node);
  const NodeId bulk = node(bulk_node);
  add_element(ElementType::mosfet_level1, std::move(id),
              std::move(drain_node), std::move(source_node), 0.0);
  elements_.back().control_positive_node = gate;
  elements_.back().control_negative_node = bulk;
  elements_.back().mosfet_level1 = model;
}

void Circuit::add_bjt_ebers_moll(std::string id, std::string collector_node,
                                 std::string base_node,
                                 std::string emitter_node,
                                 BjtEbersMollModel model) {
  const double values[] = {
      model.saturation_current_a, model.forward_alpha, model.reverse_alpha,
      model.emission_coefficient, model.temperature_k};
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      model.saturation_current_a <= 0.0 || model.forward_alpha <= 0.0 ||
      model.forward_alpha >= 1.0 || model.reverse_alpha <= 0.0 ||
      model.reverse_alpha >= 1.0 || model.emission_coefficient <= 0.0 ||
      model.temperature_k <= 0.0) {
    throw std::invalid_argument(
        "Ebers-Moll Is, emission coefficient, and temperature must be "
        "positive and both transport alphas must lie strictly in (0,1)");
  }
  const NodeId base = node(base_node);
  add_element(ElementType::bjt_ebers_moll, std::move(id),
              std::move(collector_node), std::move(emitter_node), 0.0);
  elements_.back().control_positive_node = base;
  elements_.back().bjt_ebers_moll = model;
}

void Circuit::add_wbg_fet_electrothermal(
    std::string id, std::string drain_node, std::string gate_node,
    std::string source_node, std::string bulk_node, std::string thermal_node,
    WbgFetElectrothermalModel model) {
  validate_wbg_model(model);
  const NodeId gate = node(gate_node);
  const NodeId bulk = node(bulk_node);
  const NodeId thermal = node(thermal_node);
  if (thermal == ground_node || thermal == gate || thermal == bulk) {
    throw std::invalid_argument(
        "WBG thermal node must be a distinct non-ground unknown");
  }
  add_element(ElementType::wbg_fet_electrothermal, std::move(id),
              std::move(drain_node), std::move(source_node), 0.0);
  if (thermal == elements_.back().positive_node ||
      thermal == elements_.back().negative_node) {
    elements_.pop_back();
    throw std::invalid_argument(
        "WBG thermal node must not alias an electrical terminal");
  }
  elements_.back().control_positive_node = gate;
  elements_.back().control_negative_node = bulk;
  elements_.back().thermal_node = thermal;
  elements_.back().wbg_fet_electrothermal = model;
}

void Circuit::add_capacitor(std::string id, std::string positive_node,
                            std::string negative_node, double capacitance_f,
                            double initial_voltage_v) {
  if (!std::isfinite(capacitance_f) || capacitance_f <= 0.0 ||
      !std::isfinite(initial_voltage_v)) {
    throw std::invalid_argument(
        "capacitance must be finite and positive and initial voltage finite");
  }
  add_element(ElementType::capacitor, std::move(id), std::move(positive_node),
              std::move(negative_node), capacitance_f);
  elements_.back().initial_condition = initial_voltage_v;
}

void Circuit::add_inductor(std::string id, std::string positive_node,
                           std::string negative_node, double inductance_h,
                           double initial_current_a) {
  if (!std::isfinite(inductance_h) || inductance_h <= 0.0 ||
      !std::isfinite(initial_current_a)) {
    throw std::invalid_argument(
        "inductance must be finite and positive and initial current finite");
  }
  add_element(ElementType::inductor, std::move(id), std::move(positive_node),
              std::move(negative_node), inductance_h);
  elements_.back().initial_condition = initial_current_a;
}

void Circuit::add_saturating_inductor(std::string id,
                                      std::string positive_node,
                                      std::string negative_node,
                                      SaturatingInductorModel model) {
  const double values[] = {
      model.unsaturated_inductance_h, model.saturated_inductance_h,
      model.saturation_current_a, model.initial_current_a};
  if (!std::all_of(std::begin(values), std::end(values),
                   [](double value) { return std::isfinite(value); }) ||
      model.unsaturated_inductance_h <= 0.0 ||
      model.saturated_inductance_h <= 0.0 ||
      model.saturated_inductance_h > model.unsaturated_inductance_h ||
      model.saturation_current_a <= 0.0) {
    throw std::invalid_argument(
        "saturating inductor requires finite positive L0, Lsat, Isat; Lsat "
        "must not exceed L0");
  }
  add_element(ElementType::saturating_inductor, std::move(id),
              std::move(positive_node), std::move(negative_node), 0.0);
  elements_.back().initial_condition = model.initial_current_a;
  elements_.back().saturating_inductor = model;
}

void Circuit::add_osdi_device(std::string id,
                              std::vector<std::string> terminal_nodes,
                              std::shared_ptr<OsdiDeviceInstance> device) {
  if (id.empty() || device == nullptr ||
      terminal_nodes.size() != device->terminal_count()) {
    throw std::invalid_argument(
        "OSDI device requires an id and exactly its descriptor terminal count");
  }
  const auto duplicate = std::find_if(
      elements_.begin(), elements_.end(),
      [&id](const Element &element) { return element.id == id; });
  if (duplicate != elements_.end()) {
    throw std::invalid_argument("element id must be unique");
  }
  std::vector<NodeId> nodes;
  nodes.reserve(device->node_count());
  for (const auto &terminal : terminal_nodes) {
    nodes.push_back(node(terminal));
  }
  for (std::size_t index = terminal_nodes.size(); index < device->node_count();
       ++index) {
    nodes.push_back(node("@" + id + ":osdi:" + std::to_string(index)));
  }
  Element element{ElementType::osdi_device, std::move(id), nodes.front(),
                  nodes.size() > 1 ? nodes[1] : ground_node, 0.0, 0.0, {}};
  element.osdi_device = std::move(device);
  element.osdi_nodes = std::move(nodes);
  elements_.push_back(std::move(element));
}

void Circuit::add_element(ElementType type, std::string id,
                          std::string positive_node, std::string negative_node,
                          double value) {
  if (id.empty()) {
    throw std::invalid_argument("element id must not be empty");
  }
  const auto duplicate = std::find_if(
      elements_.begin(), elements_.end(),
      [&id](const Element &element) { return element.id == id; });
  if (duplicate != elements_.end()) {
    throw std::invalid_argument("element id must be unique");
  }
  const NodeId positive = node(positive_node);
  const NodeId negative = node(negative_node);
  if (positive == negative) {
    throw std::invalid_argument("element terminals must be different nodes");
  }
  elements_.push_back(
      Element{type, std::move(id), positive, negative, value, 0.0, {}});
}

std::size_t Circuit::node_count() const noexcept { return node_names_.size(); }
std::size_t Circuit::element_count() const noexcept { return elements_.size(); }

OperatingPointResult solve_operating_point(const Circuit &circuit) {
  return solve_operating_point(circuit, SolverOptions{});
}

OperatingPointResult solve_operating_point(const Circuit &circuit,
                                           const SolverOptions &options) {
  OperatingPointResult output;
  if (options.max_newton_iterations == 0 || options.max_backtracks == 0 ||
      !std::isfinite(options.absolute_tolerance) ||
      options.absolute_tolerance <= 0.0 ||
      !std::isfinite(options.relative_tolerance) ||
      options.relative_tolerance < 0.0 || options.max_linear_iterations == 0 ||
      !std::isfinite(options.linear_absolute_tolerance) ||
      options.linear_absolute_tolerance <= 0.0 ||
      !std::isfinite(options.linear_relative_tolerance) ||
      options.linear_relative_tolerance < 0.0 || options.linear_threads == 0 ||
      (options.linear_solver != LinearSolverMethod::automatic &&
       options.linear_solver != LinearSolverMethod::dense_lu &&
       options.linear_solver != LinearSolverMethod::conjugate_gradient &&
       options.linear_solver != LinearSolverMethod::gmres &&
       options.linear_solver != LinearSolverMethod::sparse_lu &&
       options.linear_solver != LinearSolverMethod::ilu_gmres &&
       options.linear_solver != LinearSolverMethod::sparse_qr)) {
    output.status_ = SolveStatus::numerical_failure;
    output.message_ = "invalid nonlinear solver options";
    return output;
  }

  const std::size_t node_unknowns = circuit.node_names_.size() - 1;
  const std::size_t voltage_sources = static_cast<std::size_t>(std::count_if(
      circuit.elements_.begin(), circuit.elements_.end(),
      [](const Circuit::Element &element) {
        return element.type == Circuit::ElementType::voltage_source ||
               element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor;
      }));
  const bool nonlinear = std::any_of(
      circuit.elements_.begin(), circuit.elements_.end(),
      [](const Circuit::Element &element) {
        return element.type == Circuit::ElementType::diode ||
               element.type == Circuit::ElementType::dynamic_diode ||
               element.type == Circuit::ElementType::electrothermal_resistor ||
               element.type == Circuit::ElementType::voltage_controlled_switch ||
               element.type == Circuit::ElementType::mosfet_level1 ||
               element.type == Circuit::ElementType::bjt_ebers_moll ||
               element.type == Circuit::ElementType::wbg_fet_electrothermal ||
               element.type == Circuit::ElementType::osdi_device;
      });
  const std::size_t order = node_unknowns + voltage_sources;
  output.diagnostics_.matrix_order = order;

  std::vector<SparseTriplet> linear_triplets;
  linear_triplets.reserve(circuit.elements_.size() * 8);
  std::vector<double> rhs(order, 0.0);
  std::size_t source_index = 0;
  for (const auto &element : circuit.elements_) {
    if (element.type == Circuit::ElementType::resistor) {
      const double conductance = 1.0 / element.value;
      stamp_sparse(linear_triplets, element.positive_node,
                   element.positive_node, conductance);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.negative_node, conductance);
      stamp_sparse(linear_triplets, element.positive_node,
                   element.negative_node, -conductance);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.positive_node, -conductance);
    } else if (element.type == Circuit::ElementType::current_source) {
      stamp_vector(rhs, element.positive_node, -element.value);
      stamp_vector(rhs, element.negative_node, element.value);
    } else if (element.type == Circuit::ElementType::voltage_source ||
               element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor) {
      const std::size_t branch = node_unknowns + source_index++;
      if (element.positive_node != ground_node) {
        const std::size_t node_index = element.positive_node - 1;
        stamp_sparse_index(linear_triplets, node_index, branch, 1.0);
        stamp_sparse_index(linear_triplets, branch, node_index, 1.0);
      }
      if (element.negative_node != ground_node) {
        const std::size_t node_index = element.negative_node - 1;
        stamp_sparse_index(linear_triplets, node_index, branch, -1.0);
        stamp_sparse_index(linear_triplets, branch, node_index, -1.0);
      }
      if (element.type == Circuit::ElementType::voltage_source) {
        rhs[branch] += element.value;
      }
    } else if (element.type == Circuit::ElementType::diode ||
               element.type == Circuit::ElementType::dynamic_diode) {
      // Explicit zero stamps reserve the complete nonlinear Jacobian pattern.
      // Numeric Newton updates therefore never trigger symbolic reordering.
      stamp_sparse(linear_triplets, element.positive_node,
                   element.positive_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.negative_node, 0.0);
      stamp_sparse(linear_triplets, element.positive_node,
                   element.negative_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.positive_node, 0.0);
    } else if (element.type ==
               Circuit::ElementType::electrothermal_resistor) {
      const NodeId terminals[] = {element.positive_node,
                                  element.negative_node,
                                  element.thermal_node};
      for (const NodeId row : terminals) {
        for (const NodeId column : terminals) {
          stamp_sparse(linear_triplets, row, column, 0.0);
        }
      }
    } else if (element.type ==
               Circuit::ElementType::voltage_controlled_switch) {
      stamp_sparse(linear_triplets, element.positive_node,
                   element.positive_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.negative_node, 0.0);
      stamp_sparse(linear_triplets, element.positive_node,
                   element.negative_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.positive_node, 0.0);
      stamp_sparse(linear_triplets, element.positive_node,
                   element.control_positive_node, 0.0);
      stamp_sparse(linear_triplets, element.positive_node,
                   element.control_negative_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.control_positive_node, 0.0);
      stamp_sparse(linear_triplets, element.negative_node,
                   element.control_negative_node, 0.0);
    } else if (element.type == Circuit::ElementType::mosfet_level1) {
      const NodeId terminals[] = {
          element.positive_node, element.control_positive_node,
          element.negative_node, element.control_negative_node};
      for (const NodeId column : terminals) {
        stamp_sparse(linear_triplets, element.positive_node, column, 0.0);
        stamp_sparse(linear_triplets, element.negative_node, column, 0.0);
      }
    } else if (element.type == Circuit::ElementType::bjt_ebers_moll) {
      const NodeId terminals[] = {element.positive_node,
                                  element.control_positive_node,
                                  element.negative_node};
      for (const NodeId row : terminals) {
        for (const NodeId column : terminals) {
          stamp_sparse(linear_triplets, row, column, 0.0);
        }
      }
    } else if (element.type ==
               Circuit::ElementType::wbg_fet_electrothermal) {
      const NodeId terminals[] = {
          element.positive_node, element.control_positive_node,
          element.negative_node, element.control_negative_node,
          element.thermal_node};
      for (const NodeId row : terminals) {
        for (const NodeId column : terminals) {
          stamp_sparse(linear_triplets, row, column, 0.0);
        }
      }
    } else if (element.type == Circuit::ElementType::osdi_device) {
      for (const auto &[row, column] :
           element.osdi_device->jacobian_pattern()) {
        stamp_sparse(linear_triplets, element.osdi_nodes[row],
                     element.osdi_nodes[column], 0.0);
      }
    }
  }

  SparseMatrix linear_matrix(static_cast<int>(order), static_cast<int>(order));
  linear_matrix.setFromTriplets(linear_triplets.begin(), linear_triplets.end());
  linear_matrix.makeCompressed();
  output.diagnostics_.matrix_nonzeros =
      static_cast<std::size_t>(linear_matrix.nonZeros());

  auto evaluate = [&](const std::vector<double> &state) {
    SystemEvaluation evaluation{std::vector<double>(order, 0.0), linear_matrix};
    if (order != 0) {
      const Eigen::Map<const Eigen::VectorXd> mapped_state(
          state.data(), static_cast<Eigen::Index>(order));
      const Eigen::Map<const Eigen::VectorXd> mapped_rhs(
          rhs.data(), static_cast<Eigen::Index>(order));
      const Eigen::VectorXd residual = linear_matrix * mapped_state - mapped_rhs;
      std::copy(residual.data(), residual.data() + residual.size(),
                evaluation.residual.begin());
    }
    auto voltage = [&state](NodeId node_id) {
      return node_id == ground_node ? 0.0 : state[node_id - 1];
    };
    for (const auto &element : circuit.elements_) {
      if (element.type == Circuit::ElementType::diode ||
          element.type == Circuit::ElementType::dynamic_diode) {
        const auto point = diode_point(
            element.diode,
            voltage(element.positive_node) - voltage(element.negative_node));
        stamp_vector(evaluation.residual, element.positive_node, point.current_a);
        stamp_vector(evaluation.residual, element.negative_node, -point.current_a);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.positive_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.negative_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.negative_node, -point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.positive_node, -point.conductance_s);
      } else if (element.type ==
                 Circuit::ElementType::electrothermal_resistor) {
        const double across = voltage(element.positive_node) -
                              voltage(element.negative_node);
        const auto point = electrothermal_resistor_point(
            element.electrothermal_resistor, across,
            voltage(element.thermal_node));
        stamp_vector(evaluation.residual, element.positive_node,
                     point.current_a);
        stamp_vector(evaluation.residual, element.negative_node,
                     -point.current_a);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.positive_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.negative_node, -point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.positive_node, -point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.negative_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.thermal_node,
                   point.current_temperature_derivative_a_per_k);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.thermal_node,
                   -point.current_temperature_derivative_a_per_k);

        const double thermal_residual =
            voltage(element.thermal_node) /
                element.electrothermal_resistor.thermal_resistance_k_per_w -
            point.power_w;
        stamp_vector(evaluation.residual, element.thermal_node,
                     thermal_residual);
        add_sparse(evaluation.jacobian, element.thermal_node,
                   element.positive_node,
                   -point.power_voltage_derivative_a);
        add_sparse(evaluation.jacobian, element.thermal_node,
                   element.negative_node,
                   point.power_voltage_derivative_a);
        add_sparse(
            evaluation.jacobian, element.thermal_node, element.thermal_node,
            1.0 /
                    element.electrothermal_resistor.thermal_resistance_k_per_w -
                point.power_temperature_derivative_w_per_k);
      } else if (element.type ==
                 Circuit::ElementType::voltage_controlled_switch) {
        const double across = voltage(element.positive_node) -
                              voltage(element.negative_node);
        const double control = voltage(element.control_positive_node) -
                               voltage(element.control_negative_node);
        const auto point = switch_point(element.switch_model, control);
        const double current = point.conductance_s * across;
        const double transconductance =
            point.conductance_derivative_s_per_v * across;
        stamp_vector(evaluation.residual, element.positive_node, current);
        stamp_vector(evaluation.residual, element.negative_node, -current);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.positive_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.negative_node, point.conductance_s);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.negative_node, -point.conductance_s);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.positive_node, -point.conductance_s);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.control_positive_node, transconductance);
        add_sparse(evaluation.jacobian, element.positive_node,
                   element.control_negative_node, -transconductance);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.control_positive_node, -transconductance);
        add_sparse(evaluation.jacobian, element.negative_node,
                   element.control_negative_node, transconductance);
      } else if (element.type == Circuit::ElementType::mosfet_level1) {
        const NodeId terminals[] = {
            element.positive_node, element.control_positive_node,
            element.negative_node, element.control_negative_node};
        const auto point = mosfet_level1_point(
            element.mosfet_level1, voltage(terminals[0]),
            voltage(terminals[1]), voltage(terminals[2]),
            voltage(terminals[3]));
        stamp_vector(evaluation.residual, element.positive_node,
                     point.drain_current_a);
        stamp_vector(evaluation.residual, element.negative_node,
                     -point.drain_current_a);
        for (std::size_t column = 0; column < point.derivative_s.size();
             ++column) {
          add_sparse(evaluation.jacobian, element.positive_node,
                     terminals[column], point.derivative_s[column]);
          add_sparse(evaluation.jacobian, element.negative_node,
                     terminals[column], -point.derivative_s[column]);
        }
      } else if (element.type == Circuit::ElementType::bjt_ebers_moll) {
        const NodeId terminals[] = {element.positive_node,
                                    element.control_positive_node,
                                    element.negative_node};
        const auto point = bjt_ebers_moll_point(
            element.bjt_ebers_moll, voltage(terminals[0]),
            voltage(terminals[1]), voltage(terminals[2]));
        for (std::size_t row = 0; row < point.current_a.size(); ++row) {
          stamp_vector(evaluation.residual, terminals[row],
                       point.current_a[row]);
          for (std::size_t column = 0;
               column < point.derivative_s[row].size(); ++column) {
            add_sparse(evaluation.jacobian, terminals[row], terminals[column],
                       point.derivative_s[row][column]);
          }
        }
      } else if (element.type ==
                 Circuit::ElementType::wbg_fet_electrothermal) {
        const NodeId terminals[] = {
            element.positive_node, element.control_positive_node,
            element.negative_node, element.control_negative_node,
            element.thermal_node};
        const auto point = evaluate_wbg_fet_electrothermal(
            element.wbg_fet_electrothermal, voltage(terminals[0]),
            voltage(terminals[1]), voltage(terminals[2]),
            voltage(terminals[3]), voltage(terminals[4]));
        for (std::size_t row = 0; row < point.terminal_current_a.size();
             ++row) {
          stamp_vector(evaluation.residual, terminals[row],
                       point.terminal_current_a[row]);
          for (std::size_t column = 0;
               column < point.current_jacobian[row].size(); ++column) {
            add_sparse(evaluation.jacobian, terminals[row], terminals[column],
                       point.current_jacobian[row][column]);
          }
        }
        const double thermal_residual =
            voltage(element.thermal_node) /
                element.wbg_fet_electrothermal.thermal_resistance_k_per_w -
            point.dissipated_power_w;
        stamp_vector(evaluation.residual, element.thermal_node,
                     thermal_residual);
        for (std::size_t column = 0; column < point.power_jacobian.size();
             ++column) {
          double derivative = -point.power_jacobian[column];
          if (column == 4) {
            derivative +=
                1.0 /
                element.wbg_fet_electrothermal.thermal_resistance_k_per_w;
          }
          add_sparse(evaluation.jacobian, element.thermal_node,
                     terminals[column], derivative);
        }
      } else if (element.type == Circuit::ElementType::osdi_device) {
        std::vector<double> osdi_voltages;
        osdi_voltages.reserve(element.osdi_nodes.size());
        for (const NodeId node_id : element.osdi_nodes) {
          osdi_voltages.push_back(voltage(node_id));
        }
        const auto osdi = element.osdi_device->evaluate_dc(osdi_voltages);
        if (osdi.residual.size() != element.osdi_nodes.size()) {
          throw std::runtime_error("OSDI residual size changed after registration");
        }
        for (std::size_t row = 0; row < osdi.residual.size(); ++row) {
          stamp_vector(evaluation.residual, element.osdi_nodes[row],
                       osdi.residual[row]);
        }
        for (const auto &entry : osdi.jacobian) {
          add_sparse(evaluation.jacobian, element.osdi_nodes[entry.row],
                     element.osdi_nodes[entry.column], entry.value);
        }
      }
    }
    evaluation.jacobian.makeCompressed();
    return evaluation;
  };

  std::vector<double> state(order, 0.0);
  SparseLinearWorkspace sparse_workspace;
  if (!nonlinear) {
    auto solved = solve_linear(linear_matrix, rhs, order, options,
                               sparse_workspace);
    output.status_ = solved.status;
    output.message_ = std::move(solved.message);
    output.diagnostics_.pivot_swaps = solved.pivot_swaps;
    output.diagnostics_.linear_solver_used = solved.method;
    output.diagnostics_.linear_iterations = solved.iterations;
    output.diagnostics_.linear_threads = solved.threads;
    output.diagnostics_.symbolic_analyses = solved.symbolic_analyses;
    output.diagnostics_.numeric_factorizations = solved.numeric_factorizations;
    if (!solved.values.empty() || order == 0) {
      state = std::move(solved.values);
    }
  } else {
    output.status_ = SolveStatus::nonconverged;
    const double convergence_threshold =
        options.absolute_tolerance +
        options.relative_tolerance * std::max(1.0, vector_inf_norm(rhs));
    auto current = evaluate(state);
    double current_norm = vector_inf_norm(current.residual);
    for (std::size_t iteration = 0;
         iteration < options.max_newton_iterations &&
         current_norm > convergence_threshold;
         ++iteration) {
      std::vector<double> negative_residual = current.residual;
      for (double &value : negative_residual) {
        value = -value;
      }
      auto direction = solve_linear(current.jacobian,
                                    std::move(negative_residual), order,
                                    options, sparse_workspace);
      output.diagnostics_.pivot_swaps += direction.pivot_swaps;
      output.diagnostics_.linear_solver_used = direction.method;
      output.diagnostics_.linear_iterations += direction.iterations;
      output.diagnostics_.linear_threads = direction.threads;
      output.diagnostics_.symbolic_analyses = direction.symbolic_analyses;
      output.diagnostics_.numeric_factorizations =
          direction.numeric_factorizations;
      output.diagnostics_.nonlinear_iterations = iteration + 1;
      if (direction.status != SolveStatus::converged) {
        output.status_ = direction.status;
        output.message_ = std::move(direction.message);
        break;
      }

      double damping = 1.0;
      auto node_voltage = [](const std::vector<double> &values, NodeId node_id) {
        return node_id == ground_node ? 0.0 : values[node_id - 1];
      };
      for (const auto &element : circuit.elements_) {
        if (element.type != Circuit::ElementType::diode &&
            element.type != Circuit::ElementType::dynamic_diode) {
          continue;
        }
        const double old_voltage =
            node_voltage(state, element.positive_node) -
            node_voltage(state, element.negative_node);
        const double delta_voltage =
            node_voltage(direction.values, element.positive_node) -
            node_voltage(direction.values, element.negative_node);
        const double proposed = old_voltage + delta_voltage;
        const double limited =
            limit_junction_voltage(proposed, old_voltage, element.diode);
        if (limited != proposed && delta_voltage != 0.0) {
          damping = std::min(damping,
                             std::clamp((limited - old_voltage) / delta_voltage,
                                        1.0e-12, 1.0));
          ++output.diagnostics_.junction_limit_steps;
        }
      }
      for (const auto &element : circuit.elements_) {
        if (element.type !=
            Circuit::ElementType::electrothermal_resistor) {
          continue;
        }
        const auto &model = element.electrothermal_resistor;
        const double old_rise = node_voltage(state, element.thermal_node);
        const double delta_rise =
            node_voltage(direction.values, element.thermal_node);
        const double proposed = old_rise + delta_rise;
        const double margin = 1.0e-9;
        const double lower = model.minimum_temperature_k -
                             model.ambient_temperature_k + margin;
        const double upper = model.maximum_temperature_k -
                             model.ambient_temperature_k - margin;
        const double limited = std::clamp(proposed, lower, upper);
        if (limited != proposed && delta_rise != 0.0) {
          damping = std::min(
              damping,
              std::clamp((limited - old_rise) / delta_rise, 1.0e-12, 1.0));
        }
      }

      bool accepted = false;
      std::vector<double> candidate(order, 0.0);
      SystemEvaluation candidate_evaluation;
      for (std::size_t backtrack = 0; backtrack < options.max_backtracks;
           ++backtrack) {
        for (std::size_t index = 0; index < order; ++index) {
          candidate[index] = state[index] + damping * direction.values[index];
        }
        candidate_evaluation = evaluate(candidate);
        const double candidate_norm =
            vector_inf_norm(candidate_evaluation.residual);
        if (std::isfinite(candidate_norm) && candidate_norm < current_norm) {
          current_norm = candidate_norm;
          accepted = true;
          break;
        }
        damping *= 0.5;
        ++output.diagnostics_.damping_steps;
      }
      if (!accepted) {
        output.status_ = SolveStatus::nonconverged;
        output.message_ = "Newton damping failed to reduce the residual";
        break;
      }
      state = std::move(candidate);
      current = std::move(candidate_evaluation);
    }

    output.diagnostics_.residual_inf_norm = current_norm;
    if (current_norm <= convergence_threshold) {
      output.status_ = SolveStatus::converged;
      output.message_ = "nonlinear operating point converged";
    } else if (output.status_ != SolveStatus::singular &&
               output.status_ != SolveStatus::numerical_failure) {
      output.status_ = SolveStatus::nonconverged;
      if (output.message_.empty()) {
        output.message_ = "maximum Newton iterations reached";
      }
    }
  }

  if (output.status_ != SolveStatus::converged) {
    return output;
  }

  const auto final_evaluation = evaluate(state);
  output.diagnostics_.residual_inf_norm =
      vector_inf_norm(final_evaluation.residual);
  output.node_voltages_.reserve(circuit.node_names_.size());
  output.node_voltages_.push_back(NodeVoltage{ground_node, "0", 0.0});
  for (std::size_t index = 1; index < circuit.node_names_.size(); ++index) {
    output.node_voltages_.push_back(NodeVoltage{
        static_cast<NodeId>(index), circuit.node_names_[index], state[index - 1]});
  }

  auto voltage = [&state](NodeId node_id) {
    return node_id == ground_node ? 0.0 : state[node_id - 1];
  };
  output.elements_.reserve(circuit.elements_.size());
  source_index = 0;
  for (const auto &element : circuit.elements_) {
    const double across =
        voltage(element.positive_node) - voltage(element.negative_node);
    double current = 0.0;
    if (element.type == Circuit::ElementType::resistor) {
      current = across / element.value;
    } else if (element.type == Circuit::ElementType::current_source) {
      current = element.value;
    } else if (element.type == Circuit::ElementType::voltage_source ||
               element.type == Circuit::ElementType::inductor ||
               element.type == Circuit::ElementType::saturating_inductor) {
      current = state[node_unknowns + source_index++];
    } else if (element.type == Circuit::ElementType::diode ||
               element.type == Circuit::ElementType::dynamic_diode) {
      current = diode_point(element.diode, across).current_a;
    } else if (element.type ==
               Circuit::ElementType::voltage_controlled_switch) {
      const double control = voltage(element.control_positive_node) -
                             voltage(element.control_negative_node);
      current = switch_point(element.switch_model, control).conductance_s * across;
    } else if (element.type == Circuit::ElementType::mosfet_level1) {
      current = mosfet_level1_current(
          element.mosfet_level1, voltage(element.positive_node),
          voltage(element.control_positive_node), voltage(element.negative_node),
          voltage(element.control_negative_node));
    } else if (element.type == Circuit::ElementType::bjt_ebers_moll) {
      current = bjt_ebers_moll_point(
                    element.bjt_ebers_moll, voltage(element.positive_node),
                    voltage(element.control_positive_node),
                    voltage(element.negative_node))
                    .current_a[0];
    } else if (element.type ==
               Circuit::ElementType::wbg_fet_electrothermal) {
      const auto point = evaluate_wbg_fet_electrothermal(
          element.wbg_fet_electrothermal, voltage(element.positive_node),
          voltage(element.control_positive_node),
          voltage(element.negative_node),
          voltage(element.control_negative_node),
          voltage(element.thermal_node));
      current = point.terminal_current_a[0];
      output.elements_.push_back(ElementOperatingPoint{
          element.id, across, current, point.dissipated_power_w});
      continue;
    } else if (element.type ==
               Circuit::ElementType::electrothermal_resistor) {
      const auto point = electrothermal_resistor_point(
          element.electrothermal_resistor, across,
          voltage(element.thermal_node));
      current = point.current_a;
      output.elements_.push_back(ElementOperatingPoint{
          element.id, across, current, point.power_w});
      continue;
    } else if (element.type == Circuit::ElementType::osdi_device) {
      std::vector<double> osdi_voltages;
      osdi_voltages.reserve(element.osdi_nodes.size());
      for (const NodeId node_id : element.osdi_nodes) {
        osdi_voltages.push_back(voltage(node_id));
      }
      const auto osdi = element.osdi_device->evaluate_dc(osdi_voltages);
      current = osdi.residual.empty() ? 0.0 : osdi.residual.front();
    } else {
      // Ideal capacitors are open circuits at the DC operating point.
      current = 0.0;
    }
    output.elements_.push_back(
        ElementOperatingPoint{element.id, across, current, across * current});
  }
  return output;
}

} // namespace spikes
