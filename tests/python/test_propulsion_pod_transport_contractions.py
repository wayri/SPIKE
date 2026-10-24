# SPDX-License-Identifier: Apache-2.0
"""Coefficient and independently differentiated volume-residual oracles."""
import unittest

import numpy as np

from python.spike_core.propulsion_pod_inertial_cfd import _quadrature, _p2_values, _gradients
from python.spike_core.propulsion_pod_transport_contractions import volume_transport_contractions


def fixture(cells=11, order=4):
    rng = np.random.default_rng(671)
    q, weight = _quadrature(order)
    n = _p2_values(q)
    edges = np.eye(3)[None]+rng.normal(0, .08, (cells, 3, 3))
    bg = np.vstack([-np.ones(3), np.eye(3)])@np.linalg.inv(edges)
    grad = np.array([_gradients(q, g) for g in bg])
    weights = abs(np.linalg.det(edges))[:, None]/6*weight
    u = rng.normal(0, .7, (cells, 10, 3))
    frame = rng.normal(0, .4, (cells, len(q), 3))
    return n, grad, weights, u, frame


def fields(n, grad, u, frame):
    uq = np.einsum('qi,cia->cqa', n, u)
    gu = np.einsum('cia,cqib->cqab', u, grad)
    return uq, gu, uq-frame


def original(n, grad, weights, uq, gu, w, rho, jacobian=True):
    adv = np.einsum('cqb,cqjb->cqj', w, grad)
    skew = .5*rho*(np.einsum('qi,cqj,cq->cij', n, adv, weights)
                   -np.einsum('cqi,qj,cq->cij', adv, n, weights))
    mass = np.einsum('qi,qj,cq->cij', n, n, weights)
    extra = .5*rho*(np.einsum('qi,qj,cqab,cq->ciajb', n, n, gu, weights)
                    -np.einsum('cqib,qj,cqa,cq->ciajb', grad, n, uq, weights)) if jacobian else None
    return skew, mass, extra


def direct_volume_residual(n, grad, weights, u, frame, rho):
    """Evaluate weak advective form itself, without a transport matrix."""
    uq, gu, w = fields(n, grad, u, frame)
    advection = np.einsum('cqab,cqb->cqa', gu, w)
    test_advection = np.einsum('cqib,cqb->cqi', grad, w)
    return .5*rho*(np.einsum('qi,cqa,cq->cia', n, advection, weights)
                   -np.einsum('cqi,cqa,cq->cia', test_advection, uq, weights))


class VolumeTransportContractionTests(unittest.TestCase):
    def test_original_coefficient_parity_for_all_existing_quadrature_orders(self):
        for order in (4, 5, 6):
            n, grad, weights, u, frame = fixture(order=order)
            args = n, grad, weights, *fields(n, grad, u, frame), 1.225
            expected = original(*args)
            for chunk in (1, 4, 128):
                actual = volume_transport_contractions(*args, chunk_cells=chunk)
                for a, b in zip(actual, expected):
                    self.assertLess(np.linalg.norm(a-b)/np.linalg.norm(b), 2e-15)
                    np.testing.assert_allclose(a, b, rtol=5e-13, atol=2e-16)

    def test_full_volume_newton_derivative_matches_independent_weak_residual(self):
        n, grad, weights, u, frame = fixture(cells=5)
        rho = 1.225
        skew, _, extra = volume_transport_contractions(n, grad, weights, *fields(n, grad, u, frame), rho)
        residual = np.einsum('cij,cja->cia', skew, u)
        np.testing.assert_allclose(residual, direct_volume_residual(n, grad, weights, u, frame, rho),
                                   rtol=2e-13, atol=1e-16)
        direction = np.random.default_rng(105).normal(0, .2, u.shape)
        eps = 1e-6
        finite_difference = (direct_volume_residual(n, grad, weights, u+eps*direction, frame, rho)
                             -direct_volume_residual(n, grad, weights, u-eps*direction, frame, rho))/(2*eps)
        jacobian = (np.einsum('cij,cja->cia', skew, direction)
                    +np.einsum('ciajb,cjb->cia', extra, direction))
        self.assertLess(np.linalg.norm(finite_difference-jacobian)/np.linalg.norm(finite_difference), 2e-9)
        # The advecting-velocity term is essential; dropping it must fail.
        frozen = np.einsum('cij,cja->cia', skew, direction)
        self.assertGreater(np.linalg.norm(finite_difference-frozen)/np.linalg.norm(finite_difference), .1)

    def test_skew_energy_mass_symmetry_and_existing_coriolis_layout(self):
        n, grad, weights, u, frame = fixture(cells=3)
        rho = .7
        skew, mass, extra = volume_transport_contractions(n, grad, weights, *fields(n, grad, u, frame), rho)
        np.testing.assert_allclose(skew, -skew.swapaxes(1, 2), atol=1e-16)
        np.testing.assert_allclose(mass, mass.swapaxes(1, 2), atol=1e-16)
        self.assertTrue(np.all(np.linalg.eigvalsh(mass) > 0))
        omega = np.array([.2, -.3, .5])
        cross = np.array([[0., -omega[2], omega[1]], [omega[2], 0., -omega[0]], [-omega[1], omega[0], 0.]])
        block = (skew[:, :, None, :, None]*np.eye(3)[None, None, :, None, :]
                 +rho*mass[:, :, None, :, None]*cross[None, None, :, None, :])
        work = np.einsum('cia,ciajb,cjb->c', u, block, u)
        np.testing.assert_allclose(work, 0., atol=1e-15)
        direct = original(n, grad, weights, *fields(n, grad, u, frame), rho)
        original_block = (direct[0][:, :, None, :, None]*np.eye(3)[None, None, :, None, :]
                          +rho*direct[1][:, :, None, :, None]*cross[None, None, :, None, :])
        np.testing.assert_allclose((block+extra).reshape(-1, 30, 30),
                                   (original_block+direct[2]).reshape(-1, 30, 30), rtol=1e-12, atol=2e-16)

    def test_no_jacobian_noncontiguous_inputs_and_inputs_unchanged(self):
        n, grad, weights, u, frame = fixture(cells=9)
        arrays = [n, grad, weights, *fields(n, grad, u, frame)]
        arrays = [np.repeat(a, 2, axis=0)[::2] for a in arrays]
        copies = [a.copy() for a in arrays]
        for a in arrays:
            a.setflags(write=False)
        result = volume_transport_contractions(*arrays, 1.225, jacobian=False, chunk_cells=4)
        expected = original(*arrays, 1.225, jacobian=False)
        self.assertIsNone(result[2])
        for a, b in zip(result[:2], expected[:2]):
            np.testing.assert_allclose(a, b, rtol=5e-13, atol=2e-16)
        for a, b in zip(arrays, copies):
            np.testing.assert_array_equal(a, b)

    def test_shape_finite_type_and_allocation_budget_rejection(self):
        n, grad, weights, u, frame = fixture(cells=3)
        arrays = [n, grad, weights, *fields(n, grad, u, frame)]
        for options in ({'chunk_cells': 0}, {'chunk_cells': 257}, {'chunk_cells': True},
                        {'maximum_cells': 2}, {'maximum_output_bytes': 1}, {'jacobian': 1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                volume_transport_contractions(*arrays, 1.225, **options)
        for density in (-1., 0., True, float('inf')):
            with self.assertRaises(ValueError): volume_transport_contractions(*arrays, density)
        for index in range(6):
            changed = [a.copy() for a in arrays]
            changed[index].flat[0] = float('nan')
            with self.assertRaisesRegex(ValueError, 'Finite'):
                volume_transport_contractions(*changed, 1.225)
        changed = [a.copy() for a in arrays]
        changed[2][0, 0] = 0.
        with self.assertRaises(ValueError): volume_transport_contractions(*changed, 1.225)
        changed = [*arrays]
        changed[1] = changed[1][:, :, :, :2]
        with self.assertRaises(ValueError): volume_transport_contractions(*changed, 1.225)
        changed = [*arrays]
        changed[0] = changed[0].astype(np.float32)
        with self.assertRaisesRegex(ValueError, 'float64'):
            volume_transport_contractions(*changed, 1.225)


if __name__ == '__main__':
    unittest.main()
