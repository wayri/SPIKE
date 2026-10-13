# SPDX-License-Identifier: Apache-2.0
"""Independent limiting, real-form diffusion and passivity checks."""
import math
import unittest

from python.spike_core.conductor_ac_loss import slab_internal_impedance_per_m

MU = 4e-7 * math.pi
PARAMETERS = {"conductivity_s_per_m": 5.8e7, "width_m": 0.001,
              "thickness_m": 35e-6, "relative_permeability": 1.0}


def solve(frequency=0.0, **changes):
    return slab_internal_impedance_per_m(frequency_hz=frequency, **dict(PARAMETERS, **changes))


def frequency_for_q(q):
    return (2*q/PARAMETERS["thickness_m"])**2/(math.pi*MU*PARAMETERS["conductivity_s_per_m"])


class ConductorAcLossTests(unittest.TestCase):
    def test_dc_resistance_and_low_frequency_internal_inductance(self):
        sigma, width, thickness = (PARAMETERS[k] for k in
                                   ("conductivity_s_per_m", "width_m", "thickness_m"))
        expected_r, expected_l = 1/(sigma*width*thickness), MU*thickness/(12*width)
        dc = solve(0)
        self.assertLess(abs(dc["impedance_ohm_per_m"].real/expected_r-1), 2e-14)
        self.assertEqual(dc["impedance_ohm_per_m"].imag, 0)
        self.assertIsNone(dc["skin_depth_m"])
        self.assertEqual(dc["regime"], "dc")
        self.assertLess(abs(dc["dc_internal_inductance_h_per_m"]/expected_l-1), 2e-14)
        for f in (1e-12, 1e-6, 0.001):
            z = solve(f)["impedance_ohm_per_m"]
            self.assertLess(abs(z.real/expected_r-1), 2e-14)
            self.assertLess(abs(z.imag/(2*math.pi*f*expected_l)-1), 2e-14)

    def test_interior_diffusion_matches_independent_real_expression(self):
        # Independent real sinh/sin form, without complex sqrt/coth/tanh.
        rdc = 1/(PARAMETERS["conductivity_s_per_m"]*PARAMETERS["width_m"]*PARAMETERS["thickness_m"])
        for q in (0.01, 0.1, 0.8, 2, 5, 19.9, 20.1):
            result = solve(frequency_for_q(q))
            divisor = math.cosh(2*q)-math.cos(2*q)
            expected = complex(q*(math.sinh(2*q)+math.sin(2*q))/divisor,
                               q*(math.sinh(2*q)-math.sin(2*q))/divisor)*rdc
            self.assertLess(abs(result["impedance_ohm_per_m"]-expected)/abs(expected), 2e-12)

    def test_high_frequency_two_face_skin_limit(self):
        f = 1e12
        delta = math.sqrt(1/(math.pi*f*MU*PARAMETERS["conductivity_s_per_m"]))
        expected = complex(1, 1)/(2*PARAMETERS["conductivity_s_per_m"]*PARAMETERS["width_m"]*delta)
        result = solve(f)
        self.assertEqual(result["regime"], "skin_limit")
        self.assertLess(abs(result["impedance_ohm_per_m"]/expected-1), 2e-14)
        self.assertLess(abs(result["skin_depth_m"]/delta-1), 2e-14)

    def test_finite_passive_frequency_sweep_and_width_scaling(self):
        previous = 0
        for i in range(181):
            result = solve(10**(-12+i/6))
            z = result["impedance_ohm_per_m"]
            self.assertTrue(math.isfinite(z.real) and math.isfinite(z.imag))
            self.assertGreater(z.real, 0)
            self.assertGreaterEqual(z.imag, 0)
            self.assertGreaterEqual(z.real, previous*(1-1e-14))
            self.assertGreater(result["skin_depth_m"], 0)
            previous = z.real
        z = solve(1e7)["impedance_ohm_per_m"]
        wider = solve(1e7, width_m=2*PARAMETERS["width_m"])["impedance_ohm_per_m"]
        self.assertLess(abs(2*wider/z-1), 2e-14)

    def test_roughness_bounds_dc_and_real_only_correction(self):
        f = 1e8
        smooth = solve(f)
        for roughness in (0, 1e-300, 1e-8, 1e-6, 1e-3, 1e300):
            rough = solve(f, roughness_rms_m=roughness)
            correction = rough["roughness_correction"]
            self.assertGreaterEqual(correction, 1)
            self.assertLessEqual(correction, 2)
            self.assertEqual(rough["reactance_ohm_per_m"], smooth["reactance_ohm_per_m"])
            self.assertAlmostEqual(rough["resistance_ohm_per_m"], smooth["resistance_ohm_per_m"]*correction)
        delta = smooth["skin_depth_m"]
        one_depth = solve(f, roughness_rms_m=delta)
        self.assertAlmostEqual(one_depth["roughness_correction"], 1+2/math.pi*math.atan(1.4), places=14)
        self.assertEqual(solve(0, roughness_rms_m=1e300)["roughness_correction"], 1)
        self.assertIn("causal broadband", " ".join(one_depth["limitations"]))

    def test_branch_thresholds_are_continuous(self):
        for q in (1e-3, 20):
            left = solve(frequency_for_q(q*(1-1e-8)))["impedance_ohm_per_m"]
            right = solve(frequency_for_q(q*(1+1e-8)))["impedance_ohm_per_m"]
            self.assertLess(abs(right-left)/abs(left), 3e-8)

    def test_invalid_and_unrepresentable_inputs_fail(self):
        for frequency in (-1, float("nan"), float("inf"), True, "100", 10**400):
            with self.subTest(frequency=str(frequency)[:20]), self.assertRaises(ValueError):
                solve(frequency)
        for field in ("conductivity_s_per_m", "width_m", "thickness_m", "relative_permeability"):
            for value in (0, -1, float("nan"), float("inf"), True, "1"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    solve(100, **{field: value})
        for value in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                solve(100, roughness_rms_m=value)
        with self.assertRaises(ValueError):
            solve(0, width_m=1e-300, conductivity_s_per_m=1e-300)


if __name__ == "__main__":
    unittest.main()
