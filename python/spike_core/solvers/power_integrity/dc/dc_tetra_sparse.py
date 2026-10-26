# SPDX-License-Identifier: Apache-2.0
"""Bounded factor reuse for the explicit experimental scalable DC profile."""
import math
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import LinearOperator, eigsh, splu
from .dc_tetra_rt0_input import require


def local_hybrid(data):
    """Source-free scalar RT0: H=(sigma/V) N N^T, outward face area N.

    This Gram form avoids inverse-mass projection cancellation in thin cells.
    Geometry gradients are the independently audited barycentric gradients.
    """
    gradients = np.asarray([g for _, g in data['geometry_audit']['geometry']])
    normals = -3*data['volumes'][:, None, None]*gradients
    h = (data['sigma']/data['volumes'])[:, None, None]*(normals@normals.transpose(0, 2, 1))
    require(np.isfinite(h).all() and np.isfinite(normals).all(), 'Nonfinite tetrahedral Gram operator')
    return h, normals


def solve_trace(matrix, rhs, check=lambda: None):
    """Reuse one LU for shift-invert conditioning and residual correction.

    Spectral estimates and residuals are screens, not a certified condition bound.
    The process supervisor must enforce factorization peak memory/time limits.
    """
    n = matrix.shape[0]
    require(0 < n <= 200000 and matrix.shape == (n, n) and matrix.nnz <= 800000,
            "Scalable DC trace matrix budget exceeded")
    require(np.isfinite(matrix.data).all() and np.isfinite(rhs).all(), "Nonfinite scalable trace system")
    difference = matrix-matrix.T
    scale = float(np.max(np.abs(matrix.data)))
    require(not difference.nnz or np.max(np.abs(difference.data)) <= 128*np.finfo(float).eps*scale,
            "Scalable trace operator lost symmetry")
    check(); factor = splu(matrix, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.,
                           options={"SymmetricMode": True, "Equil": False})
    # With a common symmetric permutation, positive elimination pivots are
    # the LDL^T positivity screen; nearest-zero Ritz values alone miss negative modes.
    require(np.array_equal(factor.perm_r, factor.perm_c)
            and np.all(np.isfinite(factor.U.diagonal())) and np.all(factor.U.diagonal() > 0),
            "Scalable trace symmetric positive-pivot screen failed")
    discrepancy = factor.U-diags(factor.U.diagonal())@factor.L.T
    require(not discrepancy.nnz or np.max(np.abs(discrepancy.data))
            <= 1e-8*np.max(np.abs(factor.U.data)), "Scalable trace LDL transpose consistency failed")
    fill = factor.L.nnz+factor.U.nnz
    require(fill <= 16000000, "Scalable DC retained LU fill budget exceeded")
    check()
    if n <= 128:
        spectrum = np.linalg.eigvalsh(matrix.toarray())
        lower, upper = float(spectrum[0]), float(spectrum[-1])
        residual = 0.
    else:
        initial = np.random.default_rng(173).normal(size=n)
        inverse = LinearOperator(matrix.shape, matvec=factor.solve, dtype=float)
        low, lv = eigsh(matrix, k=1, sigma=0., which="LM", OPinv=inverse,
                       v0=initial, tol=1e-9, maxiter=5000)
        check()
        high, hv = eigsh(matrix, k=1, which="LA", v0=initial, tol=1e-9, maxiter=5000)
        errors = [float(np.linalg.norm(matrix@v[:, 0]-w[0]*v[:, 0])) for w, v in ((low, lv), (high, hv))]
        require(max(errors) <= 1e-8*max(abs(float(high[0])), scale), "Scalable trace eigenpair residual failed")
        lower, upper = float(low[0])-errors[0], float(high[0])+errors[1]
        residual = max(errors)
    require(math.isfinite(lower) and math.isfinite(upper) and lower > 0 and upper/lower <= 1e12,
            "Scalable trace operator exceeds conditioning budget")
    solution = factor.solve(rhs)
    corrections = 0
    for _ in range(3):
        check(); remainder = rhs-matrix@solution
        denominator = np.linalg.norm(rhs, ord=np.inf)
        if np.linalg.norm(remainder, ord=np.inf) <= 1e-12*denominator:
            break
        solution += factor.solve(remainder); corrections += 1
    require(np.isfinite(solution).all(), "Nonfinite scalable trace solution")
    return solution, {"scaled_condition_estimate": upper/lower,
        "condition_method": "LU_reused_shift_invert_with_Ritz_residuals_not_certified",
        "condition_eigenpair_maximum_residual": residual, "trace_matrix_nnz": matrix.nnz,
        "lu_factor_nnz": int(fill), "iterative_corrections": corrections}
