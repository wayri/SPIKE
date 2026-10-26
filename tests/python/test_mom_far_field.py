# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original supplied-current oracles; not scattering/solver validation.

Fixtures are synthetic unit-square/tetrahedron surfaces. Comparisons use
explicit affine simplex moments, not external meshes or solver output.
"""
from dataclasses import replace
import math
import unittest

import numpy as np

from python.spike_core.solvers.electromagnetics.fields.mom_surface_basis import build_surface_basis
from python.spike_core.solvers.electromagnetics.fields.mom_far_field import FarFieldError, MAX_DIRECTIONS, MAX_EDGES, SPEED_OF_LIGHT_M_PER_S, VACUUM_PERMEABILITY_H_PER_M, evaluate_far_field, evaluate_bistatic_rcs

POINTS = np.array([[0.,0.,0.], [1.,0.,0.], [1.,1.,0.], [0.,1.,0.]])
FACES = [[0,1,2], [0,2,3]]
DIRECTIONS = np.array([[0.,0.,1.], [1.,0.,0.], [.6,0.,.8]])


def moment(surface, coefficients):
    # Integral of the affine RWG; shared vertices cancel algebraically.
    total = np.zeros(3, dtype=complex)
    for edge, coefficient in zip(surface.edges, coefficients):
        total += coefficient * edge.length_m/3 * np.subtract(
            surface.vertices_m[edge.minus_free_vertex], surface.vertices_m[edge.plus_free_vertex])
    return total


def simplex_series_oracle(surface, coefficients, direction, k):
    """Taylor integral using exact barycentric monomial factorial moments.

    For alpha of degree n, integral(lambda**alpha)=2*A*alpha!/(n+2)!.
    Multiplying the exponential series by affine vertex values gives the
    (alpha_j+1)/(n+3)! sum below. At |k*s.x|<3, 36 terms give <1e-24
    truncation before roundoff for this fixture. This is not Gauss quadrature.
    """
    total = np.zeros(3, dtype=complex)
    for edge, coefficient in zip(surface.edges, coefficients):
        for face, free, sign in ((edge.plus_face, edge.plus_free_vertex, 1),
                                 (edge.minus_face, edge.minus_free_vertex, -1)):
            xyz = np.asarray([surface.vertices_m[v] for v in surface.triangles[face]])
            affine = sign*edge.length_m/(2*surface.areas_m2[face]) * (xyz-surface.vertices_m[free])
            q = 1j*k*(xyz @ direction)
            integral = np.zeros(3, dtype=complex)
            for n in range(36):
                for a in range(n+1):
                    for b in range(n-a+1):
                        c = n-a-b
                        value = q[0]**a*q[1]**b*q[2]**c / math.factorial(n+3)
                        integral += value*((a+1)*affine[0]+(b+1)*affine[1]+(c+1)*affine[2])
            total += coefficient*2*surface.areas_m2[face]*integral
    return total


class FarFieldTests(unittest.TestCase):
    def setUp(self):
        self.surface = build_surface_basis(POINTS, FACES)

    def field(self, coefficients=(1.+.4j,), **options):
        options.setdefault('frequency_hz', 1e8)
        options.setdefault('observation_directions', DIRECTIONS)
        return evaluate_far_field(self.surface, coefficients, **options)

    def test_planar_constant_phase_exact_oracle_and_units(self):
        result = self.field(observation_directions=[[0.,0.,1.]], frequency_hz=2.4e9)
        expected = moment(self.surface, [1.+.4j])
        np.testing.assert_allclose(result.radiation_integral_am[0], expected, rtol=1e-14, atol=1e-14)
        np.testing.assert_allclose(result.electric_amplitude_v[0],
                                   -1j*2.4e9*VACUUM_PERMEABILITY_H_PER_M/2*expected, rtol=1e-14, atol=1e-12)
        self.assertTrue(result.quadrature_converged)
        self.assertEqual(result.numerical_status, 'approximate')
        self.assertEqual(result.model_status, 'not_validated')
        self.assertFalse(result.executable_em_solver)
        self.assertFalse(result.scattering_solution_validated)
        self.assertEqual(result.quadrature_orders, (4,8))
        self.assertEqual(result.point_direction_evaluations, 160)

    def test_electrically_small_current_limit(self):
        result = self.field(frequency_hz=1e-3)
        exact = moment(self.surface, [1.+.4j])
        np.testing.assert_allclose(result.radiation_integral_am, np.tile(exact, (3,1)), atol=3e-11)

    def test_independent_simplex_series_and_refinement(self):
        direction = DIRECTIONS[2]
        frequency = SPEED_OF_LIGHT_M_PER_S / 2
        expected = simplex_series_oracle(self.surface, [1.+.4j], direction, math.pi)
        errors = []
        for initial in (2,4,8):
            result = self.field(frequency_hz=frequency, observation_directions=[direction],
                                quadrature_order=initial, max_quadrature_order=initial*2,
                                relative_tolerance=1e-14, absolute_tolerance_am=1e-16)
            errors.append(np.linalg.norm(np.asarray(result.radiation_integral_am)[0]-expected))
        self.assertLess(errors[1], errors[0]/100)
        self.assertLess(errors[2], 5e-14)
        self.assertTrue(result.quadrature_converged)
        self.assertLess(max(result.absolute_quadrature_change_am), 1e-14)

    def test_transversality_linearity_and_fourier_conjugate_symmetry(self):
        result = self.field(coefficients=[1.])
        electric = np.asarray(result.electric_amplitude_v)
        np.testing.assert_allclose(np.sum(electric*DIRECTIONS, axis=1), 0., atol=1e-14)
        opposite = self.field(coefficients=[1.], observation_directions=-DIRECTIONS)
        np.testing.assert_allclose(opposite.radiation_integral_am, np.conjugate(result.radiation_integral_am), atol=1e-14)
        # Fourier symmetry is appropriate here; arbitrary supplied currents
        # cannot establish scattering reciprocity without an excitation solve.
        multiple = self.field(coefficients=[2.-3j])
        np.testing.assert_allclose(multiple.electric_amplitude_v, (2-3j)*electric, rtol=1e-12, atol=1e-12)

    def test_folded_multiple_rwg_current_accumulation(self):
        points = [[0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.]]
        surface = build_surface_basis(points, [[0,2,1], [0,1,3], [0,3,2], [1,2,3]])
        coefficients = [.4-.2j, -.7+.1j, .8j, .2, -.3j, 1.2+.4j]
        frequency = SPEED_OF_LIGHT_M_PER_S/(2*math.pi)
        result = evaluate_far_field(surface, coefficients, frequency_hz=frequency,
                                    observation_directions=DIRECTIONS,
                                    relative_tolerance=1e-12, absolute_tolerance_am=1e-14)
        expected = [simplex_series_oracle(surface, coefficients, direction, 1.) for direction in DIRECTIONS]
        np.testing.assert_allclose(result.radiation_integral_am, expected, rtol=1e-12, atol=1e-13)
        self.assertTrue(result.quadrature_converged)
        small = evaluate_far_field(surface, coefficients, frequency_hz=1e-3, observation_directions=DIRECTIONS)
        np.testing.assert_allclose(small.radiation_integral_am,
                                   np.tile(moment(surface, coefficients), (3,1)), atol=5e-11)

    def test_translation_phase_and_rcs_invariance(self):
        displacement = np.array([.2,-.3,.7])
        shifted = build_surface_basis(POINTS+displacement, FACES)
        baseline = self.field()
        translated = evaluate_far_field(shifted, [1.+.4j], frequency_hz=baseline.frequency_hz,
                                        observation_directions=DIRECTIONS)
        k = 2*math.pi*baseline.frequency_hz/SPEED_OF_LIGHT_M_PER_S
        phase = np.exp(1j*k*(DIRECTIONS @ displacement))[:,None]
        np.testing.assert_allclose(translated.electric_amplitude_v, phase*np.asarray(baseline.electric_amplitude_v), atol=1e-12)
        kwargs = dict(frequency_hz=1e8, observation_directions=DIRECTIONS,
                      incident_propagation_direction=[0.,0.,-1.], incident_e_amplitude_v_per_m=2.)
        base_rcs = evaluate_bistatic_rcs(self.surface, [1.+.4j], **kwargs)
        translated_rcs = evaluate_bistatic_rcs(shifted, [1.+.4j], **kwargs)
        np.testing.assert_allclose(base_rcs.rcs_m2, translated_rcs.rcs_m2, rtol=1e-12)

    def test_rotation_and_scale_covariance_with_canonical_sign_mapping(self):
        rotation = np.array([[0.,-1.,0.], [0.,0.,-1.], [1.,0.,0.]])
        baseline = self.field()
        for scale in (.01,1.,100.):
            transform = lambda point: scale * (rotation @ point)
            transformed = build_surface_basis(np.asarray([transform(p) for p in POINTS]), FACES)
            old, new = self.surface.edges[0], transformed.edges[0]
            old_plus = transform(np.array(self.surface.vertices_m[old.plus_free_vertex]))
            sign = 1 if np.allclose(old_plus, transformed.vertices_m[new.plus_free_vertex]) else -1
            result = evaluate_far_field(transformed, [sign*(1.+.4j)], frequency_hz=1e8/scale,
                                        observation_directions=DIRECTIONS @ rotation.T)
            expected = scale*np.asarray(baseline.electric_amplitude_v) @ rotation.T
            np.testing.assert_allclose(result.electric_amplitude_v, expected, rtol=1e-11, atol=1e-12)

    def test_rcs_normalization_current_scaling_and_zero(self):
        kwargs = dict(frequency_hz=1e8, observation_directions=DIRECTIONS,
                      incident_propagation_direction=[0.,0.,-1.], incident_e_amplitude_v_per_m=2.)
        result = evaluate_bistatic_rcs(self.surface, [1.+.4j], **kwargs)
        expected = math.pi*np.sum(np.abs(result.far_field.electric_amplitude_v)**2, axis=1)
        np.testing.assert_allclose(result.rcs_m2, expected, rtol=1e-14)
        scaled = evaluate_bistatic_rcs(self.surface, [2.+.8j], **kwargs)
        np.testing.assert_allclose(scaled.rcs_m2, 4*np.asarray(result.rcs_m2), rtol=1e-12)
        zero = evaluate_bistatic_rcs(self.surface, [0j], **kwargs)
        self.assertEqual(zero.rcs_m2, (0.,0.,0.))
        self.assertFalse(result.scattering_solution_validated)

    def test_nonconvergence_is_reported_and_rcs_withheld(self):
        kwargs = dict(frequency_hz=3*SPEED_OF_LIGHT_M_PER_S/(2*math.pi),
                      observation_directions=[[1.,0.,0.]], quadrature_order=2,
                      max_quadrature_order=4, relative_tolerance=1e-15, absolute_tolerance_am=1e-20)
        result = self.field(**kwargs)
        self.assertFalse(result.quadrature_converged)
        self.assertEqual(result.numerical_status, 'failed_to_converge')
        self.assertGreater(result.absolute_quadrature_change_am[0], 1e-8)
        rcs = evaluate_bistatic_rcs(self.surface, [1.+.4j], incident_propagation_direction=[0.,0.,-1.],
                                    incident_e_amplitude_v_per_m=1., **kwargs)
        self.assertIsNone(rcs.rcs_m2)

    def test_reject_numeric_inputs_shapes_and_forged_metadata(self):
        for value in (0., -1., float('nan'), float('inf'), True, '1', 10**1000):
            with self.subTest(value=str(value)[:20]), self.assertRaises(FarFieldError):
                self.field(frequency_hz=value)
        for coefficients in ([], [1.,2.], [float('nan')], [complex(0, float('inf'))], [True], ['1']):
            with self.subTest(coefficients=coefficients), self.assertRaises(FarFieldError):
                self.field(coefficients=coefficients)
        for directions in ([], [[1.,1.,0.]], [[0.,0.,0.]], [[float('nan'),0.,1.]], [[True,0,0]], [[1.,0.]], ['abc']):
            with self.subTest(directions=directions), self.assertRaises(FarFieldError):
                self.field(observation_directions=directions)
        with self.assertRaises(FarFieldError):
            evaluate_far_field(replace(self.surface, areas_m2=(1.,1.)), [1.], frequency_hz=1e8, observation_directions=DIRECTIONS)
        for options in ({'quadrature_order':True}, {'max_quadrature_order':4}, {'max_quadrature_order':12},
                        {'relative_tolerance':0.}, {'absolute_tolerance_am':float('inf')}):
            with self.subTest(options=options), self.assertRaises(FarFieldError):
                self.field(**options)

    def test_resource_and_range_budgets(self):
        with self.assertRaises(FarFieldError):
            self.field(observation_directions=[[0.,0.,1.]]*(MAX_DIRECTIONS+1))
        with self.assertRaises(FarFieldError):
            self.field(frequency_hz=1e12, observation_directions=[[1.,0.,0.]])
        with self.assertRaises(FarFieldError):
            self.field(frequency_hz=1e308)
        with self.assertRaises(FarFieldError):
            self.field(coefficients=[1e308])
        remote = build_surface_basis(POINTS+[0.,0.,1e7], FACES)
        with self.assertRaises(FarFieldError):
            evaluate_far_field(remote, [1.], frequency_hz=1e8, observation_directions=[[0.,0.,1.]])
        with self.assertRaises(FarFieldError):
            evaluate_far_field(replace(self.surface, edges=self.surface.edges*(MAX_EDGES+1)), [],
                               frequency_hz=1e8, observation_directions=DIRECTIONS)
        # A modest valid mesh can exceed the work budget at 128 directions.
        points = np.concatenate([POINTS+[3*i,0,0] for i in range(64)])
        faces = [[v+4*i for v in face] for i in range(64) for face in FACES]
        many = build_surface_basis(points, faces)
        with self.assertRaises(FarFieldError):
            evaluate_far_field(many, [1.]*64, frequency_hz=1e8,
                               observation_directions=[[0.,0.,1.]]*128)

    def test_invalid_rcs_excitation_and_normalization_overflow(self):
        kwargs = dict(frequency_hz=1e8, observation_directions=DIRECTIONS,
                      incident_propagation_direction=[0.,0.,-1.], incident_e_amplitude_v_per_m=1.)
        for amplitude in (0., -1., float('nan'), True, '1', 1e-300):
            with self.subTest(amplitude=amplitude), self.assertRaises(FarFieldError):
                evaluate_bistatic_rcs(self.surface, [1.], **dict(kwargs, incident_e_amplitude_v_per_m=amplitude))
        with self.assertRaises(FarFieldError):
            evaluate_bistatic_rcs(self.surface, [1.], **dict(kwargs, incident_propagation_direction=[0.,0.,-2.]))


if __name__ == '__main__':
    unittest.main()
