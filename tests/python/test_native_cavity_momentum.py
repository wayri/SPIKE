# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Independent exact discrete momentum oracles; no continuum qualification."""
from copy import deepcopy
from fractions import Fraction as Q
import json
import math
import random
import subprocess
import unittest

from python.spike_core.solvers.thermal_fluid.flow import native_cht as cht
from python.spike_core.solvers.thermal_fluid.flow.native_cavity_momentum import (
    _operators, validate_native_cavity_momentum,
)


def payload(n=8, lid=0, reynolds=100):
    settings, scales = cht.settings({"contract": cht.REQUEST, "n": n,
        "lid_velocity_m_s": lid, "dynamic_viscosity_pa_s": 1. / reynolds,
        "hot_temperature_k": 300., "cold_temperature_k": 300.})
    raw = {"face_u": [0.] * (n * (n + 1)), "face_v": [0.] * (n * (n + 1)),
           "pressure": [0.] * (n * n), "flow_dt": .001}
    return raw, settings, scales


class NativeCavityMomentumOracleTests(unittest.TestCase):
    def test_rest_state_is_exact_and_experimental_target_is_reported(self):
        evidence = validate_native_cavity_momentum(*payload())
        self.assertEqual(evidence["independent_momentum_residual_linf"], 0.)
        self.assertTrue(evidence["independent_momentum_verified"])
        self.assertEqual(evidence["independent_momentum_arithmetic"],
                         "exact_rational_binary_inputs")

    def test_missing_lid_motion_has_exact_wall_diffusion_defect(self):
        n = 8
        ru, rv, _, _, beta = _operators(n, 100., Q(1),
            [Q(0)] * 72, [Q(0)] * 72, [Q(0)] * 64)
        self.assertEqual(ru[:(n - 1) * (n - 1)], [0] * ((n - 1) * (n - 1)))
        self.assertEqual(ru[(n - 1) * (n - 1):], [2 * beta] * (n - 1))
        self.assertEqual(rv, [0] * (n * (n - 1)))
        with self.assertRaisesRegex(ValueError, "momentum balance"):
            validate_native_cavity_momentum(*payload(lid=1))

    def test_affine_pressure_gradient_is_exact_in_both_axes(self):
        n = 8
        p = [Q(3) * Q(2 * i + 1, 2 * n) - Q(2) * Q(2 * j + 1, 2 * n)
             for j in range(n) for i in range(n)]
        ru, rv, _, _, _ = _operators(n, 17., Q(0), [Q(0)] * 72, [Q(0)] * 72, p)
        self.assertEqual(ru, [-3] * (n * (n - 1)))
        self.assertEqual(rv, [2] * (n * (n - 1)))

    def test_interior_polynomial_convection_and_pressure_exact_solution(self):
        # u=a*x,v=-a*y => div(q)=0 and C=(a*a*x,a*a*y).
        # P=-(a*a/2)*(x*x+y*y) cancels C exactly at interior dual faces.
        n, a = 8, Q(1, 4)
        u = [a * Q(i, n) for j in range(n) for i in range(n + 1)]
        v = [-a * Q(j, n) for j in range(n + 1) for i in range(n)]
        for pressure_factor in (Q(0), -a * a / 2):
            p = [pressure_factor * (Q(2 * i + 1, 2 * n)**2 + Q(2 * j + 1, 2 * n)**2)
                 for j in range(n) for i in range(n)]
            ru, rv, _, _, _ = _operators(n, 17., Q(0), u, v, p)
            for j in range(1, n - 1):
                for i in range(1, n):
                    self.assertEqual(ru[j * (n - 1) + i - 1],
                        -(a * a + 2 * pressure_factor) * Q(i, n))
            for j in range(1, n):
                for i in range(1, n - 1):
                    self.assertEqual(rv[(j - 1) * n + i],
                        -(a * a + 2 * pressure_factor) * Q(j, n))

    def test_interior_quadratic_diffusion_exact_in_both_components(self):
        n, nu = 8, Q(1. / 17.)
        # A unidirectional quadratic transverse profile has zero convection
        # and Laplacian=2; no native stencil is used to obtain this oracle.
        u = [Q(2 * j + 1, 2 * n)**2 for j in range(n) for i in range(n + 1)]
        v = [Q(2 * i + 1, 2 * n)**2 for j in range(n + 1) for i in range(n)]
        ru, _, _, _, _ = _operators(n, 17., Q(0), u, [Q(0)] * 72, [Q(0)] * 64)
        _, rv, _, _, _ = _operators(n, 17., Q(0), [Q(0)] * 72, v, [Q(0)] * 64)
        for j in range(1, n - 1):
            self.assertEqual(ru[j * (n - 1):(j + 1) * (n - 1)], [2 * nu] * (n - 1))
        for j in range(1, n):
            self.assertEqual(rv[(j - 1) * n + 1:j * n - 1], [2 * nu] * (n - 2))

    def test_lipschitz_bound_covers_closed_fields_and_reflected_ghosts(self):
        random_source = random.Random(20261025)
        for n in (8, 12):
            with self.subTest(n=n):
                states = []
                for _ in range(2):
                    u = [Q(random_source.randrange(-16, 17), 32)
                         if 0 < i < n else Q(0) for j in range(n) for i in range(n + 1)]
                    v = [Q(random_source.randrange(-16, 17), 32)
                         if 0 < j < n else Q(0) for j in range(n + 1) for i in range(n)]
                    states.append((u, v))
                delta = max(abs(b - a) for a, b in zip(
                    states[0][0] + states[0][1], states[1][0] + states[1][1]))
                first = _operators(n, 17., Q(1), *states[0], [Q(0)] * (n * n))
                last = _operators(n, 17., Q(1), *states[1], [Q(0)] * (n * n))
                _, _, amplitude, alpha, beta = last
                bound = (8 * alpha * (amplitude + delta) + 8 * beta) * delta
                for a, b in zip(first[0] + first[1], last[0] + last[1]):
                    self.assertLessEqual(abs(b - a), bound)

    def test_mean_zero_pressure_corruption_cannot_reuse_zero_residual(self):
        raw, settings, scales = payload()
        raw["pressure"][0], raw["pressure"][1] = 1., -1.
        raw["steady_rate_linf"] = raw["poisson_residual_linf"] = 0.
        with self.assertRaisesRegex(ValueError, "momentum balance"):
            validate_native_cavity_momentum(raw, settings, scales)

    def test_invalid_fields_and_nonfinite_derived_products_reject(self):
        for field in ("pressure", "face_u", "face_v"):
            for value in (math.inf, math.nan, True, 10**1000):
                raw, settings, scales = payload()
                raw[field][0] = value
                with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(ValueError):
                    validate_native_cavity_momentum(raw, settings, scales)
        raw, settings, scales = payload(lid=1)
        raw["face_u"][2 * 9 + 3], raw["face_u"][3 * 9 + 3] = 1e307, -1e307
        raw["face_v"][3 * 8 + 2], raw["face_v"][3 * 8 + 3] = -1e307, 1e307
        with self.assertRaises(ValueError):
            validate_native_cavity_momentum(raw, settings, scales)
        raw["face_u"] = []
        with self.assertRaises(ValueError):
            validate_native_cavity_momentum(raw, settings, scales)

    def test_timestep_cannot_enlarge_the_derived_gate(self):
        for dt in (0., -1., math.nan, math.inf, 1e100):
            raw, settings, scales = payload(lid=1)
            raw["flow_dt"] = dt
            with self.subTest(dt=dt), self.assertRaisesRegex(ValueError, "timestep"):
                validate_native_cavity_momentum(raw, settings, scales)

    def test_requested_tolerance_not_claimed_rate_sets_target(self):
        raw, settings, scales = payload()
        first = validate_native_cavity_momentum(raw, settings, scales)
        raw["steady_rate_linf"] = 1e200
        self.assertEqual(validate_native_cavity_momentum(raw, settings, scales), first)


@unittest.skipUnless(cht.executable_path().is_file(), "native CHT executable not built")
class NativeCavityMomentumExecutionTests(unittest.TestCase):
    def test_actual_moving_lid_grids_and_mean_zero_pressure_forgery(self):
        for n, reynolds in ((8, 1), (8, 100), (12, 100), (16, 100), (8, 400)):
            with self.subTest(n=n, reynolds=reynolds):
                _, settings, scales = payload(n=n, lid=1, reynolds=reynolds)
                run = subprocess.run([str(cht.executable_path()),
                    *map(str, cht.kernel_arguments(settings, scales))],
                    capture_output=True, text=True, check=True, timeout=60)
                raw = json.loads(run.stdout)
                self.assertEqual(raw["status"], "converged")
                evidence = validate_native_cavity_momentum(raw, settings, scales)
                self.assertTrue(evidence["independent_momentum_verified"])
                self.assertLessEqual(evidence["independent_momentum_residual_linf"],
                                     evidence["independent_momentum_residual_limit"])
                self.assertGreater(max(abs(value) for value in raw["face_u"]), 0.)
                forged = deepcopy(raw)
                forged["pressure"][0] += 1.
                forged["pressure"][1] -= 1.
                with self.assertRaisesRegex(ValueError, "momentum balance"):
                    validate_native_cavity_momentum(forged, settings, scales)


if __name__ == "__main__":
    unittest.main()
