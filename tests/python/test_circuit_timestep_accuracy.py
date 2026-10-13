# SPDX-License-Identifier: Apache-2.0
"""Independent ODE reference and invalid-input checks for the accuracy oracle."""
import math
import unittest

from scipy.integrate import solve_ivp

from scripts.benchmark_circuit_timestep_accuracy import ramp_response


class CircuitTimestepOracleTests(unittest.TestCase):
    def test_exact_response_matches_independent_ode_integration(self):
        rise, tau, sample = 1e-5, 1e-3, 1.01e-3
        # Integrate separately across the forcing kink; do not reuse the oracle equation.
        ramp = solve_ivp(lambda t, y: ((t / rise - y[0]) / tau,),
                         (0, rise), (0,), rtol=1e-11, atol=1e-13)
        constant = solve_ivp(lambda t, y: ((1 - y[0]) / tau,),
                             (rise, sample), ramp.y[:, -1], rtol=1e-11, atol=1e-13)
        self.assertTrue(ramp.success and constant.success)
        self.assertAlmostEqual(ramp_response(sample, rise, tau), constant.y[0, -1], places=10)

    def test_small_ramp_limit_is_stable(self):
        self.assertAlmostEqual(ramp_response(1, 1e-15, 1), 1 - math.exp(-1), places=14)

    def test_invalid_or_out_of_domain_time_is_rejected(self):
        for values in ((0, 1, 1), (0.5, 1, 1), (1, 0, 1), (1, 1, -1),
                       (math.nan, 1, 1), (1, 1, math.inf)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ramp_response(*values)


if __name__ == "__main__":
    unittest.main()
