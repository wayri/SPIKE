# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from python.spike_core.propulsion_pod_magnetic_p2 import P2MagneticOperator, shape_values, QUADRATURE


def mesh(n=3):
    xy = np.array([(i/n, j/n) for j in range(n+1) for i in range(n+1)])
    triangles = []
    for j in range(n):
        for i in range(n):
            a = j*(n+1)+i; b = a+1; c = a+n+1; d = c+1
            triangles.extend([(a, b, d), (a, c, d)])  # deliberately mixed orientations
    return xy, np.array(triangles)


def boundary(operator, function):
    xy = operator.nodes_m
    indices = np.flatnonzero(np.any((xy == 0.) | (xy == 1.), axis=1))
    return {int(k): float(function(xy[k])) for k in indices}


class QuadraticMagneticTests(unittest.TestCase):
    def test_quadratic_poisson_and_harmonic_exact_patch(self):
        xy, tri = mesh()
        for sign in (1., -1.):
            op = P2MagneticOperator(xy, tri, ['air']*len(tri), {'air': {'permeability_h_m': 2.}}, .3)
            fun = lambda p: p[0]**2+sign*p[1]**2
            result = op.solve(np.full(len(tri), -(2+2*sign)/2), dirichlet_a_wb_per_m=boundary(op, fun))
            expected = np.array([fun(p) for p in op.nodes_m])
            np.testing.assert_allclose(result['potential_a_wb_per_m'], expected, atol=2e-14)
            points = np.einsum('qi,eia->eqa', QUADRATURE, xy[tri])
            B = np.stack([2*sign*points[:, :, 1], -2*points[:, :, 0]], axis=2)
            np.testing.assert_allclose(result['quadrature_b_t'], B, atol=3e-14)
            self.assertLess(result['diagnostics']['free_residual_a_m'], 1e-13)

    def test_tensor_permeability_exact_quadratic_and_field_positions(self):
        xy, tri = mesh(2); mu = np.array([[2., .4], [.4, 1.3]])
        op = P2MagneticOperator(xy, tri, ['m']*len(tri), {'m': {'permeability_h_m': mu.tolist(), 'remanence_t': [.2, -.3]}})
        H = np.array([[2., .7], [.7, -1.]])
        C = np.array([[0., 1.], [-1., 0.]])
        J = -np.trace(C.T@np.linalg.inv(mu)@C@H)
        fun = lambda p: .5*p@H@p+.2*p[0]-.3*p[1]
        r = op.solve(np.full(len(tri), J), dirichlet_a_wb_per_m=boundary(op, fun))
        np.testing.assert_allclose(r['potential_a_wb_per_m'], [fun(p) for p in op.nodes_m], atol=2e-14)
        bary = [[.2, .3, .5], [.7, .1, .2]]
        point = np.einsum('qi,eia->eqa', bary, xy[tri]); gradient = point@H+np.array([.2, -.3])
        np.testing.assert_allclose(op.evaluate_b(r['potential_a_wb_per_m'], bary), gradient@C.T, atol=2e-14)

    def test_basis_source_integrals_and_shared_midpoints(self):
        xy, tri = mesh(1); op = P2MagneticOperator(xy, tri, ['a']*2, {'a': {'permeability_h_m': 1.}}, .2)
        self.assertEqual(len(op.nodes_m), 9)
        self.assertEqual(len(set(op.triangles_p2[0]) & set(op.triangles_p2[1])), 3)
        self.assertEqual(len(op.boundary_dofs(range(4))), 8)  # interior diagonal midpoint stays free
        np.testing.assert_allclose(shape_values(QUADRATURE).sum(axis=1), 1., atol=1e-15)
        load = op.source_load([3., 3.])
        np.testing.assert_array_equal(load[:4], np.zeros(4))
        self.assertAlmostEqual(load.sum(), .6, places=15)
        np.testing.assert_allclose(shape_values(QUADRATURE).mean(axis=0), [0, 0, 0, 1/3, 1/3, 1/3], atol=1e-15)

    def test_pm_reference_reciprocity_virtual_work_and_factor_reuse(self):
        xy, tri = mesh(4); regions = ['left' if xy[t].mean(axis=0)[0] < .5 else 'right' for t in tri]
        materials = {'left': {'permeability_h_m': 1.3, 'remanence_t': [.2, .3]}, 'right': {'permeability_h_m': .7}}
        op = P2MagneticOperator(xy, tri, regions, materials, .4); fixed = boundary(op, lambda p: 0.)
        sources = np.column_stack([np.array(regions) == 'left', np.array(regions) == 'right']).astype(float)
        base = op.solve(dirichlet_a_wb_per_m=fixed); a0 = np.array(base['potential_a_wb_per_m'])
        loads = np.column_stack([op.source_load(sources[:, k]) for k in range(2)])
        psi = loads.T@a0
        responses = [np.array(op.solve(sources[:, k], dirichlet_a_wb_per_m=fixed)['potential_a_wb_per_m'])-a0 for k in range(2)]
        L = loads.T@np.column_stack(responses)
        np.testing.assert_allclose(L, L.T, atol=2e-16)
        self.assertGreater(np.linalg.eigvalsh(L).min(), 0.)
        currents = np.array([.7, -.4]); r = op.solve(sources@currents, dirichlet_a_wb_per_m=fixed)
        a = np.array(r['potential_a_wb_per_m'])
        np.testing.assert_allclose(loads.T@a, L@currents+psi, atol=1e-16)
        self.assertAlmostEqual(r['current_source_coenergy_j'], .5*currents@L@currents+currents@psi+base['current_source_coenergy_j'], places=14)
        h = 1e-5; direction = np.array([.3, .8])
        plus = op.solve(sources@(currents+h*direction), dirichlet_a_wb_per_m=fixed)['current_source_coenergy_j']
        minus = op.solve(sources@(currents-h*direction), dirichlet_a_wb_per_m=fixed)['current_source_coenergy_j']
        self.assertAlmostEqual((plus-minus)/(2*h), direction@(loads.T@a), places=10)
        self.assertEqual(op.factorization_count, 1)
        self.assertTrue(r['diagnostics']['factorization_reused'])
        expected_reference = .5*.4*.5*(.2**2+.3**2)/1.3
        self.assertAlmostEqual(op.pm_reference_j, expected_reference, places=15)

    def test_invalid_material_geometry_sources_and_gauge_fail(self):
        xy, tri = mesh(1)
        for mu in (-1., True, [[1., 2.], [2., 1.]], [[1., .1], [0., 1.]], float('nan')):
            with self.subTest(mu=mu), self.assertRaises(ValueError):
                P2MagneticOperator(xy, tri, ['a']*2, {'a': {'permeability_h_m': mu}})
        with self.assertRaises(ValueError): P2MagneticOperator(xy, np.vstack([tri, tri[0]]), ['a']*3, {'a': {'mu_r': 1.}})
        op = P2MagneticOperator(xy, tri, ['a']*2, {'a': {'mu_r': 1.}})
        for bc in ({}, {999: 0.}, {0: float('nan')}):
            with self.assertRaises(ValueError): op.solve(dirichlet_a_wb_per_m=bc)
        with self.assertRaises(ValueError): op.source_load([float('inf'), 0.])
        with self.assertRaises(ValueError): op.evaluate_b(np.zeros(len(op.nodes_m)), [[.2, .2, .2]])
        # Disconnected components cannot share one essential gauge by assertion.
        disjoint = P2MagneticOperator(np.vstack([xy, xy+[3., 0.]]), np.vstack([tri, tri+4]), ['a']*4, {'a': {'mu_r': 1.}})
        with self.assertRaisesRegex(ValueError, 'Every connected component'):
            disjoint.solve(dirichlet_a_wb_per_m={0: 0.})

    def test_rotating_constant_pm_virtual_work_retains_tensor_reference(self):
        xy, tri = mesh(2); regions = ['left' if xy[t].mean(axis=0)[0] < .5 else 'right' for t in tri]
        mu = np.array([[1.3, .2], [.2, .8]]); br0 = np.array([.2, .3]); theta = .37
        def rotation(t): return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        def operator(br):
            return P2MagneticOperator(xy, tri, regions, {'left': {'permeability_h_m': mu.tolist(), 'remanence_t': br.tolist()}, 'right': {'permeability_h_m': 1.}}, .4)
        br = rotation(theta)@br0; derivative = np.array([-br[1], br[0]])
        op = operator(br); fixed = boundary(op, lambda p: 0.); current = np.linspace(-.7, .4, len(tri))
        result = op.solve(current, dirichlet_a_wb_per_m=fixed); a = np.array(result['potential_a_wb_per_m'])
        derivative_load = operator(derivative).pm_load
        derivative_reference = .4*sum(op.areas[np.array(regions) == 'left'])*(derivative@np.linalg.inv(mu)@br)
        analytic = a@derivative_load-derivative_reference
        h = 1e-5
        plus = operator(rotation(theta+h)@br0).solve(current, dirichlet_a_wb_per_m=fixed)['current_source_coenergy_j']
        minus = operator(rotation(theta-h)@br0).solve(current, dirichlet_a_wb_per_m=fixed)['current_source_coenergy_j']
        self.assertAlmostEqual((plus-minus)/(2*h), analytic, places=10)
        self.assertGreater(abs(derivative_reference), .001)  # cannot pass by silently dropping c'


if __name__ == '__main__': unittest.main()
