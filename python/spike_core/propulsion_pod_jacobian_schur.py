# SPDX-License-Identifier: Apache-2.0
"""Explicit experimental current-Jacobian diagonal-Schur preconditioner.

See docs/validation/PROPULSION_POD_JACOBIAN_SCHUR_20261024.md. This changes
only preconditioning: callers must check the unchanged full-system residual.
Native factor counts are post-allocation guards, not peak-memory guarantees.
"""
import hashlib
import json
from types import MappingProxyType

import numpy as np
from scipy.sparse import bmat, csc_matrix, diags, issparse
from scipy.sparse.linalg import LinearOperator, spilu, splu


class JacobianSimpleSchur:
    """Freeze current C, G and factors for one bordered real Jacobian.

    Unknown order is velocity, pressure, gauge multiplier. Pressure-pressure,
    velocity-gauge and multiplier diagonal blocks must be zero. C and G need
    not be transposes. The default requires positive current velocity diagonal;
    signed_current_nonzero_v1 explicitly permits finite negative entries and
    rejects zero/overflowing reciprocals. Neither policy implies an SPD Schur.
    Construction/factorization needs an external process
    memory/time limit at production scale; no factorization is cancellable here.
    """

    def __init__(self, matrix, n_velocity, n_pressure, gauge, *,
                 maximum_factor_nonzeros=30_000_000,
                 velocity_drop_tol=1e-4, velocity_fill_factor=10,
                 diagonal_policy='positive_current_v1'):
        if type(diagonal_policy) is not str or diagonal_policy not in (
                'positive_current_v1', 'signed_current_nonzero_v1'):
            raise ValueError('Explicit supported velocity diagonal policy required')
        for value, lower, upper, label in (
                (velocity_drop_tol, 1e-12, 1., 'velocity drop tolerance'),
                (velocity_fill_factor, 1., 20., 'velocity fill factor')):
            if (type(value) not in (float, int) or not np.isfinite(value)
                    or not lower <= value <= upper):
                raise ValueError('Finite bounded explicit ' + label + ' required')
        for value, cap, label in ((n_velocity, 200_000, 'velocity size'),
                                  (n_pressure, 5_000, 'pressure size'),
                                  (maximum_factor_nonzeros, 30_000_000,
                                   'factor budget')):
            if type(value) is not int or not 1 <= value <= cap:
                raise ValueError('Positive bounded integer required: ' + label)
        n, p = n_velocity, n_pressure
        size = n + p + 1
        if (not issparse(matrix) or matrix.shape != (size, size)
                or matrix.dtype.kind not in 'fi' or matrix.nnz > 30_000_000):
            raise ValueError('Bounded real sparse bordered matrix required')
        # Own snapshots prevent later input edits from mixing old factors/new C,G.
        A = csc_matrix(matrix, dtype=np.float64, copy=True)
        A.sum_duplicates()
        A.eliminate_zeros()
        if not np.isfinite(A.data).all():
            raise ValueError('Finite matrix required')
        g = np.asarray(gauge)
        if (g.shape != (p,) or g.dtype.kind not in 'fi'
                or not np.isfinite(g).all() or not np.any(g)):
            raise ValueError('Finite nonzero real gauge vector required')
        g = g.astype(np.float64, copy=True)
        if (A[n:n+p, n:n+p].nnz or A[:n, -1:].nnz
                or A[-1:, :n].nnz or A[-1, -1] != 0):
            raise ValueError('Unsupported nonzero bordered block')
        if (not np.array_equal(A[n:n+p, -1].toarray().ravel(), g)
                or not np.array_equal(A[-1, n:n+p].toarray().ravel(), g)):
            raise ValueError('Matrix gauge blocks must equal supplied gauge')
        velocity = A[:n, :n].tocsc()
        C = A[n:n+p, :n].tocsc()
        G = A[:n, n:n+p].tocsc()
        diagonal = velocity.diagonal()
        if diagonal_policy == 'positive_current_v1' and np.any(diagonal <= 0):
            raise ValueError('Positive finite current velocity diagonal required')
        if diagonal_policy == 'signed_current_nonzero_v1' and np.any(diagonal == 0):
            raise ValueError('Finite nonzero signed current velocity diagonal required')
        with np.errstate(over='ignore', divide='ignore'):
            inverse_diagonal = 1.0 / diagonal
        if not np.isfinite(inverse_diagonal).all():
            raise ValueError('Finite inverse velocity diagonal required')
        negative_schur = -(C @ diags(inverse_diagonal) @ G)
        if not np.isfinite(negative_schur.data).all():
            raise ValueError('Finite approximate Schur matrix required')
        border = csc_matrix(g[:, None])
        schur_matrix = bmat([[negative_schur, border],
                            [border.T, csc_matrix((1, 1))]], format='csc')

        def check_count(*factors):
            counts = [int(factor.nnz) for factor in factors]
            if any(value < 0 for value in counts) or sum(counts) > maximum_factor_nonzeros:
                raise ValueError('Combined native factor storage budget exceeded')
            return sum(counts)

        try:
            schur = splu(schur_matrix)
            check_count(schur)
            ilu = spilu(velocity, drop_tol=velocity_drop_tol,
                        fill_factor=velocity_fill_factor)
            count = check_count(schur, ilu)
        except RuntimeError as error:
            raise ValueError('Current-Jacobian preconditioner factorization failed') from error

        def apply(rhs):
            r = np.asarray(rhs)
            column = r.shape == (size, 1)
            if (r.shape not in ((size,), (size, 1)) or r.dtype.kind not in 'fi'
                    or not np.isfinite(r).all()):
                raise ValueError('Finite real full bordered right-hand side required')
            r = r.astype(np.float64, copy=False).reshape(size)
            yu = ilu.solve(r[:n])
            pressure_multiplier = schur.solve(np.r_[r[n:n+p] - C @ yu, r[-1]])
            result = np.r_[yu - ilu.solve(G @ pressure_multiplier[:-1]),
                           pressure_multiplier]
            if not np.isfinite(result).all():
                raise ValueError('Nonfinite preconditioner result')
            return result[:, None] if column else result

        self.factor_nonzeros = count
        self.schur_matrix_nonzeros = schur_matrix.nnz
        options = {'diagonal_policy': diagonal_policy,
                   'velocity_drop_tol': float(velocity_drop_tol),
                   'velocity_fill_factor': float(velocity_fill_factor),
                   'maximum_factor_nonzeros': maximum_factor_nonzeros}
        self.factor_options = MappingProxyType(options)
        self.factor_options_sha256 = hashlib.sha256(json.dumps(
            options, sort_keys=True, separators=(',', ':'), allow_nan=False
        ).encode('ascii')).hexdigest()
        self.preconditioner = LinearOperator((size, size), matvec=apply,
                                             dtype=np.float64)
