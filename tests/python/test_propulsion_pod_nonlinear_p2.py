# SPDX-License-Identifier: Apache-2.0
"""Independent analytic and variational oracles for supplied-law P2."""
import math
import unittest

import numpy as np
from scipy.integrate import dblquad

from python.spike_core.propulsion_pod_magnetic_p2 import P2MagneticOperator
from python.spike_core.propulsion_pod_nonlinear_p2 import NonlinearP2MagneticOperator, triangle_quadrature


def square(n=2, materials=None, depth=.7):
    xy = np.array([(i/n, j/n) for j in range(n+1) for i in range(n+1)])
    tri = []
    for j in range(n):
        for i in range(n):
            a = j*(n+1)+i
            tri.extend([(a, a+1, a+n+2), (a, a+n+1, a+n+2)])
    tri = np.array(tri)
    regions = ['left' if xy[t].mean(axis=0)[0] < .5 else 'right' for t in tri]
    materials = materials or {'left': {'permeability_h_m': 1.}, 'right': {'permeability_h_m': 1.}}
    return P2MagneticOperator(xy, np.array(tri), regions, materials, depth)


def boundary(base, function):
    return {int(i): float(function(p)) for i, p in enumerate(base.nodes_m)
            if np.any((p == 0.) | (p == 1.))}


class NonlinearP2Tests(unittest.TestCase):
    def test_stable_energy_difference_across_supplied_knots(self):
        from decimal import Decimal, localcontext
        base=square(1,depth=.7)
        op=NonlinearP2MagneticOperator(base,{r:[[0,0],[.2,.2],[2,5.6]] for r in ('left','right')})
        # Affine potentials give constant B, so the independent integral is
        # exactly the area under H(b), with no quadrature approximation.
        x=base.nodes_m[:,0]
        with localcontext() as context:
            context.prec=60
            def primitive(b):
                b=Decimal.from_float(b);k=Decimal.from_float(.2)
                if b<=k:return b*b/2
                slope=(Decimal.from_float(5.6)-k)/(Decimal(2)-k)
                return k*k/2+k*(b-k)+slope*(b-k)**2/2
            for r0,r1 in ((.19,.21),(.2,.2+1e-12),(.2,.2-1e-12),(.31,.31+1e-12),(0.,0.)):
                expected=float(Decimal.from_float(.7)*(primitive(r1)-primitive(r0)))
                actual=op.energy_difference(-r0*x,-r1*x)
                self.assertAlmostEqual(actual,expected,delta=3e-17 if abs(r1-r0)>.001 else 2e-17)
                self.assertAlmostEqual(actual,-op.energy_difference(-r1*x,-r0*x),delta=2e-17)
        with self.assertRaisesRegex(ValueError,'B-H range'):op.energy_difference(-x,-3*x)

    def test_positive_quadrature_polynomial_moments(self):
        for order in (2, 3, 6):
            l, weights = triangle_quadrature(order)
            self.assertTrue(np.all(weights > 0))
            self.assertAlmostEqual(weights.sum(), 1., places=14)
            for i in range(2*order-1):
                for j in range(2*order-1-i):
                    # Analytic reference triangle monomial integral, normalized.
                    exact = 2*math.factorial(i)*math.factorial(j)/math.factorial(i+j+2)
                    self.assertAlmostEqual(weights@(l[:, 1]**i*l[:, 2]**j), exact, places=14)

    def test_linear_limit_preserves_tensor_pm_source_and_boundary_work(self):
        base = square(materials={'left': {'permeability_h_m': [[1.3, .2], [.2, .8]],
                                                 'remanence_t': [.2, -.1]},
                                 'right': {'permeability_h_m': 2.}})
        op = NonlinearP2MagneticOperator(base, {'right': [[0, 0], [10, 5]]})
        current = np.linspace(-.2, .3, len(base.triangles))
        fixed = boundary(base, lambda p: .1*p[0]+.2*p[1])
        linear = base.solve(current, dirichlet_a_wb_per_m=fixed)
        nonlinear = op.solve(current, dirichlet_a_wb_per_m=fixed)
        np.testing.assert_allclose(nonlinear['potential_a_wb_per_m'], linear['potential_a_wb_per_m'], atol=2e-14)
        for key in ('magnetic_energy_j', 'current_source_coenergy_j', 'pm_reference_j'):
            self.assertAlmostEqual(nonlinear[key], linear[key], places=14)
        np.testing.assert_allclose(nonlinear['tangent_a_m2_per_wb'].toarray(), base.stiffness.toarray(), atol=2e-14)
        a = nonlinear['potential_a_wb_per_m']
        work = sum(a[i]*value for i, value in nonlinear['dirichlet_reaction_a_m'].items())
        self.assertAlmostEqual(nonlinear['magnetic_material_coenergy_j']-nonlinear['current_source_coenergy_j'], work, places=14)
        self.assertGreater(abs(work), .001)

    def test_energy_gradient_consistent_tangent_and_positive_gauged_spectrum(self):
        base = square()
        op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.2, .2], [2, 5.6]] for r in ('left', 'right')})
        x, y = base.nodes_m.T
        a = .3*x+.4*y+.1*x*y
        direction = np.sin(np.arange(len(a))*.71)*.03
        j = np.linspace(-.2, .3, len(base.triangles))
        state = op.assemble(a, j)
        eps = 2e-5
        plus, minus = op.assemble(a+eps*direction, j), op.assemble(a-eps*direction, j)
        self.assertAlmostEqual((plus['potential_j']-minus['potential_j'])/(2*eps),
                               state['residual_a_m']@direction, delta=2e-11)
        np.testing.assert_allclose((plus['residual_a_m']-minus['residual_a_m'])/(2*eps),
                                   state['tangent_a_m2_per_wb']@direction, rtol=2e-9, atol=2e-11)
        k = state['tangent_a_m2_per_wb'].toarray()
        np.testing.assert_allclose(k, k.T, atol=2e-14)
        self.assertGreater(np.linalg.eigvalsh(k[1:, 1:]).min(), .001)
        # Explicitly evaluate the independently derived scalar primitive.
        b = np.linalg.norm(state['quadrature_b_t'], axis=2)
        np.testing.assert_allclose(state['quadrature_energy_j_per_m3'], 1.5*b*b-.4*b+.04, atol=2e-16)

    def test_piecewise_nonlinear_manufactured_quadratic_patch(self):
        base = square(4)
        curves = {r: [[0, 0], [.5, .5], [2, 5]] for r in ('left', 'right')}
        op = NonlinearP2MagneticOperator(base, curves)
        fixed = boundary(base, lambda p: -.5*p[0]**2)
        result = op.solve({'left': 1., 'right': 3.}, dirichlet_a_wb_per_m=fixed)
        np.testing.assert_allclose(result['potential_a_wb_per_m'], -.5*base.nodes_m[:, 0]**2, atol=2e-11)
        # w=.5*x^2 below .5; above .5, w=1.5*x^2-x+.25.
        energy = base.depth*(.5*.5**3/3+(1.5*(1-.5**3)/3-(1-.5**2)/2+.25*.5))
        self.assertAlmostEqual(result['magnetic_energy_j'], energy, delta=2e-11)
        self.assertGreater(result['diagnostics']['iterations'], 1)
        self.assertFalse(result['diagnostics']['material_qualified'])

    def test_two_material_layers_constant_h_exact_continuum(self):
        base = square(4)
        op = NonlinearP2MagneticOperator(base, {'left': [[0, 0], [.1, .05], [.4, .5]],
                                               'right': [[0, 0], [.1, .1], [.4, 1.]]})
        bl, br = .2, 2/15
        fun = lambda p: -bl*min(p[0], .5)-br*max(p[0]-.5, 0)
        result = op.solve(dirichlet_a_wb_per_m=boundary(base, fun))
        np.testing.assert_allclose(result['potential_a_wb_per_m'], [fun(p) for p in base.nodes_m], atol=3e-11)
        np.testing.assert_allclose(result['quadrature_h_a_per_m'][:, :, 1], .2, atol=2e-10)
        # Independent areas under two trapezoids in each supplied curve.
        wl = .1*.05/2+.1*(.05+.2)/2
        wr = .1*.1/2+(br-.1)*(.1+.2)/2
        self.assertAlmostEqual(result['magnetic_energy_j'], base.depth*(wl+wr)/2, delta=2e-11)

    def test_nonlinear_quadrature_refines_against_adaptive_scalar_integral(self):
        base = square(2)
        x, y = base.nodes_m.T
        a = .3*x+.4*y+.1*x*y
        def energy(y, x):
            b = math.hypot(.4+.1*x, .3+.1*y)
            return 1.5*b*b-.4*b+.04
        exact = base.depth*dblquad(energy, 0, 1, lambda x: 0, lambda x: 1,
                                   epsabs=1e-13, epsrel=1e-13)[0]
        errors = []
        for order in (2, 4, 8):
            op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.2, .2], [2, 5.6]]
                                                       for r in ('left', 'right')}, quadrature_order=order)
            errors.append(abs(op.assemble(a)['magnetic_energy_j']-exact))
        self.assertLess(errors[1], errors[0]*.001)
        self.assertLess(errors[2], 2e-14)

    def test_range_guard_checks_element_vertices_not_just_quadrature(self):
        base = square(2)
        op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [1, 1]] for r in ('left', 'right')}, quadrature_order=2)
        a = -.525*base.nodes_m[:, 0]**2
        self.assertLess(np.linalg.norm(base.evaluate_b(a, op.barycentric), axis=2).max(), 1.)
        with self.assertRaisesRegex(ValueError, 'element vertex'):
            op.assemble(a)

    def test_zero_and_knot_tangent_match_one_sided_energy_derivatives(self):
        base = square()
        op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.5, .5], [2, 5]] for r in ('left', 'right')})
        zero = op.assemble(np.zeros(len(base.nodes_m)))
        np.testing.assert_allclose(zero['tangent_a_m2_per_wb'].toarray(), base.stiffness.toarray(), atol=1e-14)
        self.assertEqual(zero['magnetic_energy_j'], 0.)
        x = base.nodes_m[:, 0]
        # A=-b*x gives B=(0,b); w(.5)=.125, right radial slope=3.
        knot = op.assemble(-.5*x)
        eps = 1e-5
        plus = op.assemble(-(.5+eps)*x)
        self.assertAlmostEqual(knot['magnetic_energy_j'], base.depth*.125, places=14)
        derivative = (plus['residual_a_m']-knot['residual_a_m'])/eps
        # Scalar radial derivative against v=-x isolates exact one-sided dH/db.
        self.assertAlmostEqual(float((-x)@derivative), base.depth*3., delta=1e-9)
        # Near the knot floating arithmetic can select either tangent; verify
        # its radial response lies in the valid generalized derivative interval.
        response = float(x@(knot['tangent_a_m2_per_wb']@x))
        self.assertGreaterEqual(response, base.depth*(1-1e-13))
        self.assertLessEqual(response, base.depth*3*(1+1e-13))

    def test_constitutive_identity_binds_laws_quadrature_and_detaches_metadata(self):
        base = square()
        curve = [[0., 0.], [.5, .5], [2., 5.]]
        op = NonlinearP2MagneticOperator(base, {'left': curve})
        same = NonlinearP2MagneticOperator(base, {'left': curve})
        altered = NonlinearP2MagneticOperator(base, {'left': [[0, 0], [.5, 1.], [2, 5.]]})
        finer = NonlinearP2MagneticOperator(base, {'left': curve}, quadrature_order=6)
        self.assertEqual(op.constitutive_sha256, same.constitutive_sha256)
        self.assertNotEqual(op.constitutive_sha256, altered.constitutive_sha256)
        self.assertNotEqual(op.constitutive_sha256, finer.constitutive_sha256)
        identity = op.constitutive_identity()
        law = identity['constitutive_model']['region_laws']['left']
        self.assertEqual(law['bh_curve'], curve)
        self.assertEqual(law['curve_columns'], ['B_t', 'H_a_per_m'])
        self.assertEqual(law['admitted_b_range_t'], [0., 2.])
        self.assertEqual(law['provenance'], 'caller-supplied-unverified')
        self.assertFalse(law['material_qualified'])
        curve[1][1] = 200.
        law['bh_curve'][1][1] = 300.
        result = op.assemble(np.zeros(len(base.nodes_m)))
        self.assertEqual(result['constitutive_model']['region_laws']['left']['bh_curve'][1][1], .5)
        self.assertEqual(result['constitutive_sha256'], same.constitutive_sha256)

    def test_wrapped_or_owned_mutation_requires_a_new_operator(self):
        base = square()
        op = NonlinearP2MagneticOperator(base, {'left': [[0, 0], [2, 2]]})
        initial = np.zeros(len(base.nodes_m))
        op.assemble(initial)
        base.nu[0, 0, 0] *= 2
        with self.assertRaisesRegex(ValueError, 'dependencies changed'):
            op.assemble(initial)
        base = square()
        op = NonlinearP2MagneticOperator(base, {'left': [[0, 0], [2, 2]]})
        with self.assertRaises(ValueError): op.materials['left'][1].b[1] = 3.
        op.materials['left'][1].slopes = np.array([9.])
        with self.assertRaisesRegex(ValueError, 'dependencies changed'):
            op.solve(dirichlet_a_wb_per_m=boundary(base, lambda p: 0.))

    def test_nonlinear_tangent_source_reciprocity_and_coenergy_derivative(self):
        base = square(3)
        op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.01, .01], [2, 10]] for r in ('left', 'right')})
        sources = np.array([[r == 'left', r == 'right'] for r in base.region_ids], dtype=float)
        fixed = boundary(base, lambda p: 0.)
        currents = np.array([1.2, -.3])
        result = op.solve(sources@currents, dirichlet_a_wb_per_m=fixed)
        loads = np.column_stack([base.source_load(sources[:, j]) for j in range(2)])
        free = np.setdiff1d(np.arange(len(base.nodes_m)), list(fixed))
        k = result['tangent_a_m2_per_wb'][free][:, free].toarray()
        l = loads[free].T@np.linalg.solve(k, loads[free])
        np.testing.assert_allclose(l, l.T, atol=1e-16)
        eps = 1e-4
        plus = op.solve(sources@(currents+[eps, 0]), dirichlet_a_wb_per_m=fixed)
        minus = op.solve(sources@(currents-[eps, 0]), dirichlet_a_wb_per_m=fixed)
        self.assertAlmostEqual((plus['current_source_coenergy_j']-minus['current_source_coenergy_j'])/(2*eps),
                               loads[:, 0]@result['potential_a_wb_per_m'], delta=1e-10)
        np.testing.assert_allclose(loads.T@(plus['potential_a_wb_per_m']-minus['potential_a_wb_per_m'])/(2*eps),
                                   l[:, 0], rtol=2e-6, atol=1e-10)

    def test_rejections_and_failed_solve_preserve_initial_state(self):
        base = square()
        for curves in ({'missing': [[0, 0], [1, 1]]}, {'left': [[0, 0], [1, 0]]},
                       {'left': [[0, 0], [1, 1], [2, .5]]}):
            with self.assertRaises(ValueError): NonlinearP2MagneticOperator(base, curves)
        pm = square(materials={'left': {'mu_r': 1., 'remanence_t': [.1, 0]}, 'right': {'mu_r': 1.}})
        with self.assertRaisesRegex(ValueError, 'remanence'):
            NonlinearP2MagneticOperator(pm, {'left': [[0, 0], [1, 1]]})
        for order in (1, 17, True):
            with self.assertRaises(ValueError): triangle_quadrature(order)
        with self.assertRaisesRegex(ValueError, 'budget'):
            NonlinearP2MagneticOperator(base, {}, maximum_quadrature_points=1)
        op = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.01, .01], [2, 10]] for r in ('left', 'right')})
        initial = np.zeros(len(base.nodes_m))
        with self.assertRaisesRegex(ValueError, 'did not converge'):
            op.solve(np.ones(len(base.triangles)), dirichlet_a_wb_per_m=boundary(base, lambda p: 0.),
                     initial_a_wb_per_m=initial, maximum_iterations=1)
        np.testing.assert_array_equal(initial, 0.)
        for fixed in ({}, {False: 0.}, {0: float('nan')}):
            with self.assertRaises(ValueError): op.solve(dirichlet_a_wb_per_m=fixed)
        narrow = NonlinearP2MagneticOperator(base, {r: [[0, 0], [.001, .001]] for r in ('left', 'right')})
        with self.assertRaisesRegex(ValueError, 'did not converge|line search failed'):
            narrow.solve(np.ones(len(base.triangles)), dirichlet_a_wb_per_m=boundary(base, lambda p: 0.),
                         initial_a_wb_per_m=initial, maximum_iterations=2)
        np.testing.assert_array_equal(initial, 0.)


if __name__ == '__main__':
    unittest.main()
