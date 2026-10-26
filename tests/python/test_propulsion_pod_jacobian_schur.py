# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import bmat, csc_matrix, diags
from scipy.sparse.linalg import gmres

from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_jacobian_schur import JacobianSimpleSchur


def fixture(nondiagonal=False):
    velocity = np.diag([2., 3., 4., 5.])
    if nondiagonal:
        velocity += np.array([[0, .3, 0, -.2], [-.1, 0, .5, 0],
                              [.2, -.1, 0, .1], [0, .2, -.3, 0]])
    C = np.array([[1., -1., 0., 0.], [0., 1., -1., 0.], [-1., 0., 1., 0.]])
    transform = np.array([[1., .2, -.2], [0, 1., 0], [.1, 0, .9]])
    G = C.T @ transform
    gauge = np.array([1., 2., 4.])
    A = np.zeros((8, 8))
    A[:4, :4], A[:4, 4:7], A[4:7, :4] = velocity, G, C
    A[4:7, 7], A[7, 4:7] = gauge, gauge
    return csc_matrix(A), gauge


class CurrentJacobianSchur(unittest.TestCase):
    def test_diagonal_velocity_dense_full_border_oracle(self):
        A, gauge = fixture()
        C, G = A[4:7, :4].toarray(), A[:4, 4:7].toarray()
        self.assertGreater(np.linalg.norm(G - C.T), .1)
        self.assertGreater(np.linalg.norm(C.T @ gauge), 1.)
        schur = -C @ np.diag(1 / A.diagonal()[:4]) @ G
        self.assertGreater(np.linalg.norm(schur - schur.T), .01)
        owner = JacobianSimpleSchur(A, 4, 3, gauge)
        rng = np.random.default_rng(24023)
        for _ in range(6):
            rhs = rng.normal(size=8)  # Includes nonzero gauge equation rhs.
            result = owner.preconditioner @ rhs
            np.testing.assert_allclose(result, np.linalg.solve(A.toarray(), rhs),
                                       rtol=3e-14, atol=3e-14)
            np.testing.assert_allclose(A @ result, rhs, rtol=3e-14, atol=3e-14)
        column = rhs[:, None]
        np.testing.assert_allclose(owner.preconditioner @ column, result[:, None])

    def test_nondiagonal_velocity_full_gmres_residual(self):
        A, gauge = fixture(True)
        owner = JacobianSimpleSchur(A, 4, 3, gauge)
        rhs = np.array([.3, -1., 4., 2., -3., .1, .9, 2.3])
        # This is an approximate inverse; success must come from the full solve.
        self.assertGreater(np.linalg.norm(A @ (owner.preconditioner @ rhs) - rhs), 1e-3)
        history = []
        x, info = gmres(A, rhs, M=owner.preconditioner, rtol=1e-12, atol=0,
                        restart=8, maxiter=4, callback=history.append,
                        callback_type='pr_norm')
        self.assertEqual(info, 0)
        self.assertLess(np.linalg.norm(A @ x - rhs) / np.linalg.norm(rhs), 1e-12)
        np.testing.assert_allclose(x, np.linalg.solve(A.toarray(), rhs), atol=1e-12)
        self.assertGreater(len(history), 1)

    def test_snapshot_and_current_diagonal_rebuild(self):
        A, gauge = fixture()
        old = JacobianSimpleSchur(A, 4, 3, gauge)
        rhs = np.arange(8.) - 2
        expected = old.preconditioner @ rhs
        A[0, 0] *= 7
        new = JacobianSimpleSchur(A, 4, 3, gauge)
        gauge[:] = -100
        np.testing.assert_array_equal(old.preconditioner @ rhs, expected)
        self.assertGreater(np.linalg.norm(new.preconditioner @ rhs - expected), .01)
        np.testing.assert_allclose(A @ (new.preconditioner @ rhs), rhs, atol=2e-14)
        current_expected = new.preconditioner @ rhs
        A[0, 4] += 1
        A[4, 0] += 2
        np.testing.assert_array_equal(old.preconditioner @ rhs, expected)
        np.testing.assert_array_equal(new.preconditioner @ rhs, current_expected)

    def test_malformed_blocks_and_diagonal_gates(self):
        A, g = fixture()
        for row, col, value in ((0, 0, 0.), (0, 0, -1.), (0, 0, np.nan),
                                (0, 0, 1e-320), (4, 4, .1), (0, 7, .1),
                                (7, 0, .1), (7, 7, .1), (4, 7, .1),
                                (7, 4, .1)):
            bad = A.toarray()
            bad[row, col] = value
            with self.subTest(row=row, col=col, value=value):
                with self.assertRaises(ValueError):
                    JacobianSimpleSchur(csc_matrix(bad), 4, 3, g)
        for gauge in (np.zeros(3), np.ones(2), [1, np.inf, 4], g.astype(complex)):
            with self.assertRaises(ValueError):
                JacobianSimpleSchur(A, 4, 3, gauge)
        for nv, npres in ((True, 3), (4, 0), (200001, 3), (4, 5001), (3, 3)):
            with self.assertRaises(ValueError):
                JacobianSimpleSchur(A, nv, npres, g)
        with self.assertRaises(ValueError):
            JacobianSimpleSchur(A.toarray(), 4, 3, g)
        with self.assertRaises(ValueError):
            JacobianSimpleSchur(A.astype(complex), 4, 3, g)

    def test_factor_budget_and_singular_factor_gates(self):
        A, g = fixture()
        for budget in (0, True, 30_000_001, 1):
            with self.assertRaises(ValueError):
                JacobianSimpleSchur(A, 4, 3, g, maximum_factor_nonzeros=budget)
        count = JacobianSimpleSchur(A, 4, 3, g).factor_nonzeros
        with self.assertRaisesRegex(ValueError, 'Combined native factor'):
            JacobianSimpleSchur(A, 4, 3, g, maximum_factor_nonzeros=count-1)
        bad = A.toarray()
        bad[:4, 4:7] = 0
        with self.assertRaisesRegex(ValueError, 'factorization failed'):
            JacobianSimpleSchur(csc_matrix(bad), 4, 3, g)
        bad = A.toarray()
        bad[:4, :4] = [[2, 0, 0, 2], [0, 3, 0, 0], [0, 0, 4, 0], [2, 0, 0, 2]]
        with self.assertRaisesRegex(ValueError, 'factorization failed'):
            JacobianSimpleSchur(csc_matrix(bad), 4, 3, g)
        # A backend failure must remain a rejected candidate, not a fallback.
        with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_jacobian_schur.spilu',
                   side_effect=RuntimeError('test backend failure')):
            with self.assertRaisesRegex(ValueError, 'factorization failed'):
                JacobianSimpleSchur(A, 4, 3, g)

    def test_rhs_gates(self):
        A, g = fixture()
        owner = JacobianSimpleSchur(A, 4, 3, g)
        for rhs in (np.full(8, np.nan), np.ones(8, dtype=complex), np.ones(7)):
            with self.assertRaises(ValueError):
                owner.preconditioner @ rhs

    def test_explicit_factor_options_preserve_default_and_bind_identity(self):
        A, g = fixture()
        default = JacobianSimpleSchur(A, 4, 3, g)
        explicit = JacobianSimpleSchur(A, 4, 3, g, velocity_drop_tol=1e-4,
                                      velocity_fill_factor=10.)
        stronger = JacobianSimpleSchur(A, 4, 3, g, velocity_drop_tol=1e-6,
                                      velocity_fill_factor=20)
        self.assertEqual(default.factor_options_sha256, explicit.factor_options_sha256)
        self.assertNotEqual(default.factor_options_sha256, stronger.factor_options_sha256)
        self.assertEqual(dict(default.factor_options), {'diagonal_policy':'positive_current_v1', 'velocity_drop_tol':1e-4,
            'velocity_fill_factor':10., 'maximum_factor_nonzeros':30_000_000})
        with self.assertRaises(TypeError):
            stronger.factor_options['velocity_fill_factor'] = 10
        rhs = np.arange(8.) - 1
        np.testing.assert_array_equal(default.preconditioner @ rhs, explicit.preconditioner @ rhs)
        np.testing.assert_allclose(stronger.preconditioner @ rhs,
                                   np.linalg.solve(A.toarray(), rhs), atol=3e-14)
        for name, values in (
                ('velocity_drop_tol', [True, 0., 1e-13, 1.01, np.inf, np.nan, '1e-6']),
                ('velocity_fill_factor', [True, .99, 20.01, np.inf, np.nan, '20'])):
            for value in values:
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        JacobianSimpleSchur(A, 4, 3, g, **{name:value})
        with self.assertRaisesRegex(ValueError, 'Combined native factor'):
            JacobianSimpleSchur(A, 4, 3, g, velocity_drop_tol=1e-6,
                               velocity_fill_factor=20, maximum_factor_nonzeros=1)

    def test_signed_diagonal_full_indefinite_oracle_and_default_rejection(self):
        A, g = fixture()
        A[0, 0] = -2.
        A[3, 3] = -5.
        signed = JacobianSimpleSchur(A, 4, 3, g,
            diagonal_policy='signed_current_nonzero_v1')
        rng = np.random.default_rng(52410)
        for _ in range(4):
            rhs = rng.normal(size=8)
            np.testing.assert_allclose(signed.preconditioner @ rhs,
                np.linalg.solve(A.toarray(), rhs), rtol=4e-14, atol=4e-14)
            np.testing.assert_allclose(A @ (signed.preconditioner @ rhs), rhs,
                                       rtol=4e-14, atol=4e-14)
        with self.assertRaisesRegex(ValueError, 'Positive finite'):
            JacobianSimpleSchur(A, 4, 3, g)
        for value in (0., -0., 1e-320, -1e-320, np.nan, np.inf, -np.inf):
            bad = A.copy()
            bad[0, 0] = value
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    JacobianSimpleSchur(bad, 4, 3, g,
                        diagonal_policy='signed_current_nonzero_v1')

    def test_policy_identity_unknown_rejection_and_positive_numeric_parity(self):
        import hashlib
        import json
        A, g = fixture(True)
        default = JacobianSimpleSchur(A, 4, 3, g)
        positive = JacobianSimpleSchur(A, 4, 3, g, diagonal_policy='positive_current_v1')
        signed = JacobianSimpleSchur(A, 4, 3, g, diagonal_policy='signed_current_nonzero_v1')
        rhs = np.arange(8.) + .125
        np.testing.assert_array_equal(default.preconditioner @ rhs, positive.preconditioner @ rhs)
        np.testing.assert_array_equal(default.preconditioner @ rhs, signed.preconditioner @ rhs)
        self.assertEqual(default.factor_options_sha256, positive.factor_options_sha256)
        self.assertNotEqual(default.factor_options_sha256, signed.factor_options_sha256)
        old_options = dict(default.factor_options)
        del old_options['diagonal_policy']
        old_hash = hashlib.sha256(json.dumps(old_options, sort_keys=True,
                                 separators=(',', ':')).encode('ascii')).hexdigest()
        self.assertNotEqual(default.factor_options_sha256, old_hash)
        for policy in ('signed', 'absolute_current_v1', '', None, True, 1, ['positive_current_v1']):
            with self.subTest(policy=policy):
                with self.assertRaisesRegex(ValueError, 'diagonal policy'):
                    JacobianSimpleSchur(A, 4, 3, g, diagonal_policy=policy)
        with self.assertRaisesRegex(ValueError, 'Combined native factor'):
            JacobianSimpleSchur(A, 4, 3, g, diagonal_policy='signed_current_nonzero_v1',
                               maximum_factor_nonzeros=1)


if __name__ == '__main__':
    unittest.main()
