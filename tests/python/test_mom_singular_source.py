# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent analytic and invariant checks for the bounded source kernel."""

import math
import unittest

import numpy as np

from python.spike_core.solvers.electromagnetics.fields.mom_singular_source import MomSourceIntegrationError, integrate_triangle_green


TRIANGLE = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])


class MomSingularSourceTests(unittest.TestCase):
    def test_vertex_singularity_has_exact_static_moments(self):
        result = integrate_triangle_green(TRIANGLE, [0, 0, 0], relative_tolerance=1e-10)
        scalar = math.sqrt(2) * math.asinh(1) / (4 * math.pi)
        first = math.asinh(1) / (2 * math.sqrt(2) * 4 * math.pi)
        self.assertEqual(result.interaction, "on_surface")
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.scalar_m.real, scalar, delta=scalar * 1e-10)
        np.testing.assert_allclose(result.relative_first_m2, [first, first, 0], atol=1e-11)
        self.assertEqual(result.scalar_m.imag, 0.)

    def test_zero_gap_limit_and_outgoing_phase(self):
        exact = integrate_triangle_green(TRIANGLE, [0, 0, 0], wave_number_rad_m=2)
        near = integrate_triangle_green(TRIANGLE, [0, 0, 1e-4], wave_number_rad_m=2)
        self.assertEqual(near.interaction, "near")
        self.assertLess(abs(exact.scalar_m - near.scalar_m), 2e-5)
        low = integrate_triangle_green(TRIANGLE, [0, 0, 0], wave_number_rad_m=1e-3)
        # The leading imaginary term is -ik times triangle area / (4 pi).
        self.assertAlmostEqual(low.scalar_m.imag, -1e-3 * .5 / (4 * math.pi), delta=1e-11)

    def test_hypotenuse_midpoint_has_independent_static_oracle(self):
        # Two nonzero fan sectors each contribute asinh(1)/(4*pi).
        result = integrate_triangle_green(TRIANGLE, [.5, .5, 0.])
        expected = math.asinh(1) / (2 * math.pi)
        self.assertEqual(result.interaction, "on_surface")
        self.assertAlmostEqual(result.scalar_m.real, expected, delta=expected * 1e-9)

    def test_rotation_translation_and_frequency_scaling(self):
        reference = integrate_triangle_green(TRIANGLE, [0, 0, 0], wave_number_rad_m=2)
        rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        translation = np.array([3., -7., 2.])
        moved = integrate_triangle_green(TRIANGLE @ rotation.T + translation, translation, wave_number_rad_m=2)
        self.assertAlmostEqual(abs(reference.scalar_m - moved.scalar_m), 0., delta=1e-12)
        np.testing.assert_allclose(moved.relative_first_m2, rotation @ reference.relative_first_m2, rtol=1e-11, atol=1e-12)
        for scale in (1e-3, 1e3):
            with self.subTest(scale=scale):
                scaled = integrate_triangle_green(TRIANGLE * scale, [0, 0, 0], wave_number_rad_m=2 / scale)
                self.assertAlmostEqual(abs(scaled.scalar_m / scale - reference.scalar_m), 0., delta=1e-10)
                np.testing.assert_allclose(np.array(scaled.relative_first_m2) / scale**2, reference.relative_first_m2, rtol=1e-9, atol=1e-11)

    def test_far_static_monopole_limit(self):
        distance = 100.
        result = integrate_triangle_green(TRIANGLE, [0, 0, distance])
        leading = .5 / (4 * math.pi * distance)
        self.assertLess(abs(result.scalar_m.real / leading - 1.), 2e-5)
        self.assertEqual(result.interaction, "separated")
        # Source edges must be formed before subtracting a distant observation;
        # otherwise the 1 mm triangle loses area and can falsely converge.
        tiny = TRIANGLE * 1e-3
        far = integrate_triangle_green(tiny, [1e12, 1e12, 1e12])
        monopole = 5e-7 / (4 * math.pi * math.sqrt(3) * 1e12)
        self.assertAlmostEqual(far.scalar_m.real / monopole, 1., delta=1e-12)

    def test_invalid_and_unresolved_inputs_reject(self):
        bad_cases = [
            (TRIANGLE, [0, 0, 0], {"wave_number_rad_m": -1}),
            (TRIANGLE, [0, 0, 0], {"wave_number_rad_m": float("nan")}),
            (TRIANGLE, [0, 0, 0], {"wave_number_rad_m": True}),
            (TRIANGLE, [0, 0, 0], {"wave_number_rad_m": 100}),
            (TRIANGLE, [0, 0, 0], {"max_order": 4}),
            (TRIANGLE, [0, 0, 0], {"relative_tolerance": 1e-15}),
            (TRIANGLE, [0.5, -1e-5, 0], {}),
            ([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [0, 0, 0], {}),
            (TRIANGLE, [0, 0, float("inf")], {}),
            ([[False, 0, 0], [True, 0, 0], [0, 1, 0]], [0, 0, 0], {}),
            (TRIANGLE, [False, 0, 0], {}),
        ]
        for vertices, observation, options in bad_cases:
            with self.subTest(options=options, observation=observation), self.assertRaises(MomSourceIntegrationError):
                integrate_triangle_green(vertices, observation, **options)


if __name__ == "__main__":
    unittest.main()
