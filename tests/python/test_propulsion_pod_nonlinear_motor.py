# SPDX-License-Identifier: Apache-2.0
"""Small synthetic coupled variational oracles; no actual motor material data."""
import copy
import unittest

import numpy as np

from python.spike_core.propulsion_pod_magnetic_p2 import MU0
from python.spike_core.propulsion_pod_nonlinear_motor import NonlinearSeparatedMotor
from python.spike_core.propulsion_pod_nonlinear_p2 import NonlinearP2MagneticOperator
from python.spike_core.propulsion_pod_modal_gap import ModalGap
from python.spike_core.propulsion_pod_separated_motor import SeparatedMotor
from tests.python.test_propulsion_pod_separated_motor import fixture


def prepare(nonlinear=False, upper=2.):
    data = fixture()
    if nonlinear:
        data['rotor']['materials']['steel'] = {'mu_r': 2.}
        data['rotor']['solver_region_ids'][::3] = ['steel']*4
    motor = SeparatedMotor(data, stack_depth_m=.01, maximum_mode=2)
    nu = 1/(2*MU0)
    curve = [[0, 0], [.005, .005*nu], [upper, .005*nu+(upper-.005)*nu*5]]
    rop = NonlinearP2MagneticOperator(motor.rotor.op, {'steel': curve} if nonlinear else {}, quadrature_order=4)
    sop = NonlinearP2MagneticOperator(motor.stator.op, {'m': curve} if nonlinear else {}, quadrature_order=4)
    chi = {name: data[name]['winding_chi_per_m2'] for name in ('rotor', 'stator')}
    return NonlinearSeparatedMotor(motor, rop, sop, chi), data


def independent_linear_system(reference, data, angle, currents):
    """Explicit dense constrained FEM oracle only for this tiny fixture."""
    m = reference.gap.size
    total = 2*m+len(reference.rotor.interior)+len(reference.stator.interior)
    k, f = np.zeros((total, total)), np.zeros(total)
    transforms = []
    offset = 2*m
    for j, (name, domain) in enumerate((('rotor', reference.rotor), ('stator', reference.stator))):
        t = np.zeros((len(domain.op.nodes_m), total))
        t[domain.boundary, j*m:(j+1)*m] = domain.V
        t[domain.interior, offset+np.arange(len(domain.interior))] = 1.
        offset += len(domain.interior)
        source = domain.op.pm_load+domain.op.source_load(np.array(data[name]['winding_chi_per_m2'])@currents)
        k += t.T@(domain.op.stiffness@t)
        f += t.T@source
        transforms.append(t)
    k[:2*m, :2*m] += reference.gap.matrices(angle)[0]
    return k, f, transforms


class NonlinearCoupledMotorTests(unittest.TestCase):
    def test_linear_limit_matches_independent_full_system(self):
        coupled, data = prepare()
        angle, currents = .31, np.array([12000., -8000., -4000.])
        k, f, transforms = independent_linear_system(coupled.motor, data, angle, currents)
        expected = np.linalg.solve(k, f)
        actual = coupled.evaluate(currents, angle, include_field=True)
        self.assertAlmostEqual(actual['coenergy_j'], .5*f@expected-coupled.motor.reference, delta=1e-10)
        for name, t in zip(('rotor', 'stator'), transforms):
            np.testing.assert_allclose(actual['local_domain_potential_wb_per_m'][name], t@expected, atol=2e-14)
        linear = coupled.motor.evaluate(currents, angle)
        for key in ('coenergy_j', 'magnetic_energy_j', 'torque_n_m'):
            self.assertAlmostEqual(actual[key], linear[key], delta=1e-10)
        np.testing.assert_allclose(actual['flux_linkage_wb_turn'], linear['flux_linkage_wb_turn'], atol=2e-14)
        self.assertEqual(actual['diagnostics']['iterations'], 1)
        self.assertEqual(actual['diagnostics']['cg_iterations'], [1])

    def test_linear_preconditioner_inverts_arbitrary_rhs(self):
        coupled, data = prepare()
        angle = .29
        k, _, _ = independent_linear_system(coupled.motor, data, angle, np.zeros(3))
        ntrace = 2*coupled.motor.gap.size
        # Oracle ordering is traces first, implementation ordering traces last.
        order = np.r_[np.arange(ntrace, coupled.size), np.arange(ntrace)]
        k = k[np.ix_(order, order)]
        rhs = np.cos(np.arange(coupled.size)*.7)
        inverse = coupled._preconditioner(ModalGap(coupled.motor.gap, angle), lambda: None)
        np.testing.assert_allclose(k@(inverse@rhs), rhs, atol=2e-12)
        np.testing.assert_allclose(inverse@rhs, np.linalg.solve(k, rhs), atol=1e-15)

    def test_nonlinear_common_energy_flux_and_torque_derivatives(self):
        coupled, _ = prepare(nonlinear=True)
        angle, currents = .31, np.array([12000., -8000., -4000.])
        result = coupled.evaluate(currents, angle, include_field=True, absolute_tolerance_a_m=1e-10,
                                  relative_tolerance=1e-11)
        self.assertGreater(result['diagnostics']['iterations'], 1)
        self.assertGreater(max(result['diagnostics']['cg_iterations']), 1)
        self.assertAlmostEqual(result['magnetic_energy_j']+result['coenergy_j'],
                               currents@result['flux_linkage_wb_turn'], places=11)
        linear = coupled.motor.evaluate(currents, angle)
        self.assertGreater(abs(result['coenergy_j']-linear['coenergy_j']), .01)
        h = 1e-4
        plus = coupled.evaluate(currents, angle+h, absolute_tolerance_a_m=1e-10, relative_tolerance=1e-11)
        minus = coupled.evaluate(currents, angle-h, absolute_tolerance_a_m=1e-10, relative_tolerance=1e-11)
        self.assertAlmostEqual((plus['coenergy_j']-minus['coenergy_j'])/(2*h), result['torque_n_m'], delta=2e-7)
        for j in range(3):
            delta = np.eye(3)[j]*.1
            plus = coupled.evaluate(currents+delta, angle, absolute_tolerance_a_m=1e-10, relative_tolerance=1e-11)
            minus = coupled.evaluate(currents-delta, angle, absolute_tolerance_a_m=1e-10, relative_tolerance=1e-11)
            self.assertAlmostEqual((plus['coenergy_j']-minus['coenergy_j'])/.2,
                                   result['flux_linkage_wb_turn'][j], delta=2e-9)
        coefficients = np.r_[result['rotor_fourier_coefficients'], result['stator_fourier_coefficients']]
        # Independent scalar rotation energy derivative, held field fixed.
        gap = coupled.motor.gap
        held_plus = .5*coefficients@gap.matrices(angle+h)[0]@coefficients
        held_minus = .5*coefficients@gap.matrices(angle-h)[0]@coefficients
        self.assertAlmostEqual(-(held_plus-held_minus)/(2*h), result['torque_n_m'], delta=2e-7)
        self.assertFalse(result['physical_qualified'])
        self.assertFalse(result['diagnostics']['quadrature_converged'])

    def test_snapshot_and_failed_trials_do_not_mutate_inputs(self):
        coupled, _ = prepare(nonlinear=True)
        initial = np.zeros(coupled.size)
        with self.assertRaisesRegex(ValueError, 'did not converge'):
            coupled.evaluate([12000., -8000., -4000.], .3, initial_unknowns=initial, maximum_iterations=1)
        np.testing.assert_array_equal(initial, 0.)
        result = coupled.evaluate([12000., -8000., -4000.], .3, include_field=True)
        for value in (result['unknown_potential_wb_per_m'], result['rotor_fourier_coefficients'],
                      result['local_domain_potential_wb_per_m']['rotor']):
            with self.assertRaises(ValueError): value[0] = 0.
        original = result['unknown_potential_wb_per_m'].copy()
        warm = coupled.evaluate([12000., -8000., -4000.], .3,
                                initial_unknowns=result['unknown_potential_wb_per_m'])
        self.assertEqual(warm['diagnostics']['iterations'], 0)
        np.testing.assert_array_equal(result['unknown_potential_wb_per_m'], original)

    def test_source_identity_operator_alignment_and_budget_rejection(self):
        coupled, data = prepare()
        chi = {name: data[name]['winding_chi_per_m2'] for name in ('rotor', 'stator')}
        wrong = copy.deepcopy(chi)
        wrong['rotor'][0][0] *= 2
        with self.assertRaisesRegex(ValueError, 'source.*identity'):
            NonlinearSeparatedMotor(coupled.motor, *coupled.operators, wrong)
        with self.assertRaisesRegex(ValueError, 'exact prepared motor domain'):
            NonlinearSeparatedMotor(coupled.motor, coupled.operators[1], coupled.operators[0], chi)
        with self.assertRaisesRegex(ValueError, 'unknown budget'):
            NonlinearSeparatedMotor(coupled.motor, *coupled.operators, chi, maximum_unknowns=1)
        for args in ({'angle_rad': True}, {'angle_rad': float('nan')}, {'initial_unknowns': [0.]},
                     {'maximum_iterations': True}, {'maximum_cg_iterations': 0}, {'maximum_seconds': 601},
                     {'currents_a': [1, 2]}, {'currents_a': [0, float('inf'), 0]}):
            params = {'currents_a': [0, 0, 0], 'angle_rad': .2, **args}
            with self.assertRaises(ValueError): coupled.evaluate(**params)
        with self.assertRaisesRegex(ValueError, 'time budget'):
            coupled.evaluate([0, 0, 0], .2, maximum_seconds=1e-12)
        narrow, _ = prepare(nonlinear=True, upper=.0051)
        with self.assertRaisesRegex(ValueError, 'B-H range'):
            narrow.evaluate([0, 0, 0], .2, initial_unknowns=np.ones(narrow.size))
        with self.assertRaisesRegex(ValueError, 'CG failed'):
            narrow.evaluate([12000., -8000., -4000.], .2, maximum_cg_iterations=1)
        data['stator']['outer_boundary_vertex_ids'] = []
        with self.assertRaisesRegex(ValueError, 'fixed outer gauge'):
            SeparatedMotor(data, maximum_mode=2)

    def test_strong_source_cannot_hide_weak_source_identity_mismatch(self):
        data = fixture()
        for name in ('rotor', 'stator'):
            chi = np.array(data[name]['winding_chi_per_m2'])
            chi[:, 0] *= 1e12
            data[name]['winding_chi_per_m2'] = chi.tolist()
        motor = SeparatedMotor(data, stack_depth_m=.01, maximum_mode=2)
        operators = [NonlinearP2MagneticOperator(domain.op, {}) for domain in (motor.rotor, motor.stator)]
        chi = {name: np.array(data[name]['winding_chi_per_m2']) for name in ('rotor', 'stator')}
        NonlinearSeparatedMotor(motor, *operators, chi)
        chi['stator'][:, 2] *= 2
        with self.assertRaisesRegex(ValueError, 'source.*identity'):
            NonlinearSeparatedMotor(motor, *operators, chi)

    def test_nonlinear_law_identity_is_separate_from_prepared_linear_identity(self):
        motor, data = prepare(nonlinear=True)
        current, theta = [12000., -8000., -4000.], .31
        original = motor.evaluate(current, theta)
        chi = {name: data[name]['winding_chi_per_m2'] for name in ('rotor', 'stator')}
        curve = [[0, 0], [.005, .005/(2*MU0)], [2, 2/(2*MU0)]]
        alternative = NonlinearSeparatedMotor(motor.motor, motor.operators[0],
                       NonlinearP2MagneticOperator(motor.motor.stator.op, {'m': curve}), chi)
        changed = alternative.evaluate(current, theta)
        self.assertEqual(original['prepared_linear_model_identity'], changed['prepared_linear_model_identity'])
        self.assertEqual(original['geometry_sha256'], changed['geometry_sha256'])
        self.assertNotIn('spec_sha256', original)
        self.assertNotEqual(original['constitutive_sha256'], changed['constitutive_sha256'])
        self.assertGreater(abs(original['coenergy_j']-changed['coenergy_j']), .01)
        descriptor = changed['constitutive_model']['domains']['stator']['constitutive_model']['region_laws']['m']
        self.assertEqual(descriptor['bh_curve'], curve)
        self.assertEqual(descriptor['admitted_b_range_t'], [0., 2.])
        descriptor['bh_curve'][1][1] = 999.
        again = alternative.evaluate(current, theta)
        self.assertEqual(again['constitutive_model']['domains']['stator']['constitutive_model']['region_laws']['m']['bh_curve'], curve)

    def test_repeated_evaluation_rejects_changed_domain_trace_gap_or_source_identity(self):
        for mutation in ('domain', 'trace', 'gap', 'source', 'factor'):
            with self.subTest(mutation=mutation):
                motor, _ = prepare()
                motor.evaluate([0, 0, 0], .2)
                if mutation == 'domain': motor.motor.rotor.op.br[0, 0] += .01
                if mutation == 'trace': motor.motor.rotor.V[0, 0] += .1
                if mutation == 'gap': motor.motor.gap.a *= 1.01
                if mutation == 'source': motor.motor.spec_sha256 = 'changed'
                if mutation == 'factor': motor.motor.rotor.factor = object()
                with self.assertRaisesRegex(ValueError, 'dependencies changed'):
                    motor.evaluate([0, 0, 0], .2)

    def test_explicit_mode_budget_options_and_early_dense_rejection(self):
        from unittest.mock import patch
        coupled,data=prepare();chi={name:data[name]['winding_chi_per_m2'] for name in ('rotor','stator')}
        for options in ({'maximum_fourier_mode':True},{'maximum_fourier_mode':-1},
                        {'maximum_fourier_mode':1025},{'maximum_fourier_mode':2.},
                        {'maximum_dense_reference_bytes':True},{'maximum_dense_reference_bytes':0},
                        {'maximum_dense_reference_bytes':512*1024**2+1},
                        {'maximum_dense_reference_bytes':1}):
            with patch.object(coupled.motor.rotor.op,'source_load',side_effect=AssertionError('Late rejection')):
                with self.assertRaises(ValueError):NonlinearSeparatedMotor(coupled.motor,*coupled.operators,chi,**options)
        default=coupled.evaluate([12000.,-8000.,-4000.],.31)
        explicit=NonlinearSeparatedMotor(coupled.motor,*coupled.operators,chi,maximum_fourier_mode=1024)
        result=explicit.evaluate([12000.,-8000.,-4000.],.31)
        self.assertEqual(default['solver_options']['maximum_fourier_mode'],255)
        self.assertNotEqual(default['solver_options_sha256'],result['solver_options_sha256'])
        self.assertEqual(default['constitutive_sha256'],result['constitutive_sha256'])
        for key in ('coenergy_j','magnetic_energy_j','torque_n_m'):
            self.assertEqual(default[key],result[key])
        np.testing.assert_array_equal(default['flux_linkage_wb_turn'],result['flux_linkage_wb_turn'])
        self.assertEqual(result['resource_plan']['dense_reference_allowance_bytes'],3*8*(2*coupled.motor.gap.size)**2)
        result['solver_options']['maximum_fourier_mode']=0
        self.assertEqual(explicit.evaluate([0,0,0],.2)['solver_options']['maximum_fourier_mode'],1024)
        explicit._solver_options['maximum_fourier_mode']=255
        with self.assertRaisesRegex(ValueError,'dependencies changed'):explicit.evaluate([0,0,0],.2)
        from python.spike_core.propulsion_pod_annular_gap import AnnularGap
        original=coupled.motor.gap
        coupled.motor.gap=AnnularGap(original.a,original.b,original.depth,256)
        with self.assertRaisesRegex(ValueError,'default 255'):
            NonlinearSeparatedMotor(coupled.motor,*coupled.operators,chi)


if __name__ == '__main__':
    unittest.main()
