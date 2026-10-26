# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Synthetic native CHT result-admission oracles, not physics qualification.

These independently authored payloads isolate protocol and finite-arithmetic
invariants without needing a compiled executable. Equal temperatures make the
passive thermal solution exactly zero in normalized units. Moving-lid payloads
are deliberately synthetic: admission does not independently certify momentum.
Actual native execution and numerical benchmarks remain in test_native_cht.py.
"""
import unittest

from python.spike_core.solvers.thermal_fluid.flow import native_cht as cht
from python.spike_core.solvers.thermal_fluid.flow.native_cht_result import admit_native_cht_result


def equal_temperature_payload(*, moving=False):
    settings, scales = cht.settings({
        "contract": cht.REQUEST, "n": 8,
        "lid_velocity_m_s": 1. if moving else 0.,
        "hot_temperature_k": 300., "cold_temperature_k": 300.,
    })
    echoed = ("n", "reynolds", "lid", "peclet", "solid_k_ratio", "hot_k", "cold_k",
              "max_flow_steps", "steady_tolerance", "thermal_tolerance",
              "max_thermal_iterations")
    raw = {"schema": "spike-native-cht-v1", "status": "converged", "rows": 12,
           "flow_steps": 10, "thermal_iterations": 1,
           **dict(zip(echoed, cht.kernel_arguments(settings, scales)))}
    for name in ("divergence_linf", "steady_rate_linf", "poisson_residual_linf",
                 "thermal_residual_linf", "hot_flux", "cold_flux", "balance_raw",
                 "balance_relative", "theta_min", "theta_max"):
        raw[name] = 0.
    # The rest branch uses the exact zero-state native diffusion timestep.
    raw["flow_dt"] = .001 if moving else .15 * (1 / 8) * (1 / 8)
    raw["flow_time"] = sum(raw["flow_dt"] for _ in range(raw["flow_steps"]))
    for name, count in (("theta", 96), ("u", 64), ("v", 64), ("pressure", 64),
                        ("face_u", 72), ("face_v", 72),
                        ("interface_bottom_theta", 8), ("interface_top_theta", 8),
                        ("interface_bottom_flux", 8), ("interface_top_flux", 8)):
        raw[name] = [0.] * count
    return raw, settings, scales


def add_closed_circulation(raw, amplitude):
    """Four internal faces forming a closed loop; each cell has zero divergence."""
    n = raw["n"]
    raw["face_u"][2 * (n + 1) + 3] = amplitude
    raw["face_u"][3 * (n + 1) + 3] = -amplitude
    raw["face_v"][3 * n + 2] = -amplitude
    raw["face_v"][3 * n + 3] = amplitude
    for j in range(n):
        for i in range(n):
            raw["u"][j * n + i] = (raw["face_u"][j * (n + 1) + i]
                + raw["face_u"][j * (n + 1) + i + 1]) / 2
            raw["v"][j * n + i] = (raw["face_v"][j * n + i]
                + raw["face_v"][(j + 1) * n + i]) / 2


class NativeChtResultInvariantTests(unittest.TestCase):
    def test_rest_fixture_is_admitted_without_promoting_qualification(self):
        result = admit_native_cht_result(*equal_temperature_payload())
        self.assertEqual(result["status"], "converged")
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["diagnostics"]["independent_thermal_residual_linf"], 0.)
        self.assertEqual(result["fields"]["thermal"]["temperature_k"], [300.] * 96)
        self.assertEqual(result["fields"]["fluid"]["gauge_pressure_pa"], [0.] * 64)

    def test_accepted_flow_requires_ten_settled_steps(self):
        for steps in (0, 1, 9):
            raw, settings, scales = equal_temperature_payload(moving=True)
            raw["flow_steps"] = steps
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                admit_native_cht_result(raw, settings, scales)

    def test_accepted_thermal_solve_requires_an_iteration(self):
        raw, settings, scales = equal_temperature_payload()
        raw["thermal_iterations"] = 0
        with self.assertRaises(ValueError):
            admit_native_cht_result(raw, settings, scales)

    def test_pressure_gauge_shift_is_rejected(self):
        # Use the moving branch so a rest-state check cannot mask a missing gauge check.
        raw, settings, scales = equal_temperature_payload(moving=True)
        raw["pressure"] = [1.] * 64
        with self.assertRaises(ValueError):
            admit_native_cht_result(raw, settings, scales)

    def test_zero_lid_rejects_mass_balanced_nonzero_circulation(self):
        raw, settings, scales = equal_temperature_payload()
        add_closed_circulation(raw, .1)
        with self.assertRaises(ValueError):
            admit_native_cht_result(raw, settings, scales)

    def test_zero_lid_rejects_mean_zero_nonzero_pressure(self):
        raw, settings, scales = equal_temperature_payload()
        raw["pressure"][0], raw["pressure"][1] = 1., -1.
        with self.assertRaises(ValueError):
            admit_native_cht_result(raw, settings, scales)

    def test_finite_faces_cannot_hide_overflow_in_thermal_residual(self):
        raw, settings, scales = equal_temperature_payload(moving=True)
        # Pe=100 times finite faces overflows; inf*zero theta becomes NaN.
        # max(previous, NaN) must not silently report an independent residual of zero.
        add_closed_circulation(raw, 1e307)
        with self.assertRaises(ValueError):
            admit_native_cht_result(raw, settings, scales)


if __name__ == "__main__":
    unittest.main()
