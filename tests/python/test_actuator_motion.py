# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import json
import math
import json
from pathlib import Path
from pathlib import Path
import unittest

import numpy as np

from python.spike_core.actuator_force_map import CONTRACT as FORCE_CONTRACT
from python.spike_core.actuator_motion import CONTRACT, simulate_actuator_motion


def force_map(force=1.0):
    x = np.linspace(-2.0, 2.0, 9)
    return {"contract": FORCE_CONTRACT, "kind": "permanent_magnet",
            "position_m": x.tolist(), "force_n": np.full_like(x, force).tolist(),
            "coenergy_j": (force * x).tolist(), "fixed_excitation": {"current_a": 1.0},
            "provenance": "Original constant-force analytical motion test",
            "relative_tolerance": 1e-10, "absolute_force_tolerance_n": 1e-10}


def request(**updates):
    value = {"contract": CONTRACT, "force_map": force_map(), "mass_kg": 2.0,
             "damping_n_s_per_m": 0.0, "spring_n_per_m": 0.0,
             "spring_equilibrium_position_m": 0.0, "initial_position_m": 0.0,
             "initial_velocity_m_per_s": 0.0, "duration_s": 0.5, "time_step_s": 0.01}
    value.update(updates)
    return value


class ActuatorMotionTests(unittest.TestCase):
    def test_all_three_motion_examples_against_forced_oscillator(self):
        from scripts.qualify_actuator_motion import qualification_report
        report = qualification_report()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(report["cases"]), 3)
        self.assertFalse(report["production_qualified"])

    def test_public_schema_and_example_execute(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        root = Path(__file__).resolve().parents[2]
        docs = [json.loads((root / "schemas" / name).read_text()) for name in
                ("actuator-force-map-v1.schema.json", "actuator-motion-v1.schema.json")]
        registry = Registry().with_resources((d["$id"], Resource.from_contents(d)) for d in docs)
        item = json.loads((root / "examples/actuator/voice-coil-motion.json").read_text())
        Draft202012Validator.check_schema(docs[1])
        Draft202012Validator(docs[1], registry=registry).validate(item)
        result = simulate_actuator_motion(item)
        self.assertEqual(result["termination"], "duration_reached")
        self.assertLess(abs(result["energy_balance_residual_j"]), 1e-12)

    def test_checked_in_cli_example_executes(self):
        root = Path(__file__).resolve().parents[2]
        item = json.loads((root / "examples/actuator/voice-coil-motion.json").read_text())
        result = simulate_actuator_motion(item)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["termination"], "duration_reached")

    def test_constant_force_matches_analytical_motion(self):
        result = simulate_actuator_motion(request())
        self.assertEqual(result["termination"], "duration_reached")
        self.assertAlmostEqual(result["position_m"][-1], 0.0625, places=12)
        self.assertAlmostEqual(result["velocity_m_per_s"][-1], 0.25, places=12)
        self.assertAlmostEqual(result["energy_balance_residual_j"], 0.0, places=13)
        self.assertAlmostEqual(result["force_map_work_j"], result["midpoint_actuator_work_j"], places=13)
        self.assertFalse(result["production_qualified"])

    def test_spring_damped_oscillator_has_second_order_convergence(self):
        # m*x''+c*x'+k*x=0, underdamped closed-form displacement.
        m, c, k, duration = 1.5, 0.8, 12.0, 0.7
        omega0 = math.sqrt(k / m); alpha = c / (2 * m)
        omega = math.sqrt(omega0**2 - alpha**2)
        exact = math.exp(-alpha * duration) * (math.cos(omega * duration) + alpha / omega * math.sin(omega * duration))
        errors = []
        for h in (0.04, 0.02, 0.01):
            result = simulate_actuator_motion(request(force_map=force_map(0.0), mass_kg=m,
                damping_n_s_per_m=c, spring_n_per_m=k, initial_position_m=1.0,
                duration_s=duration, time_step_s=h))
            errors.append(abs(result["position_m"][-1] - exact))
            self.assertLess(abs(result["energy_balance_residual_j"]), 2e-12)
            self.assertGreater(result["damping_dissipation_j"], 0)
        self.assertGreater(errors[0] / errors[1], 3.8)
        self.assertGreater(errors[1] / errors[2], 3.8)

    def test_stroke_event_terminates_without_extrapolation(self):
        result = simulate_actuator_motion(request(force_map=force_map(4.0), mass_kg=1.0,
                                                  duration_s=2.0, time_step_s=0.3))
        self.assertEqual(result["termination"], "stroke_boundary_reached")
        self.assertEqual(result["boundary"], "maximum")
        self.assertEqual(result["position_m"][-1], 2.0)
        self.assertAlmostEqual(result["time_s"][-1], 1.0, places=12)
        self.assertAlmostEqual(result["energy_balance_residual_j"], 0.0, places=11)

    def test_input_and_resource_admission(self):
        cases = [("mass_kg", 0), ("damping_n_s_per_m", -1),
                 ("initial_position_m", 3), ("time_step_s", float("nan")),
                 ("unknown", 1)]
        for key, value in cases:
            item = request(); item[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                simulate_actuator_motion(item)
        with self.assertRaisesRegex(ValueError, "100000"):
            simulate_actuator_motion(request(duration_s=2.0, time_step_s=1e-6))
        with self.assertRaisesRegex(ValueError, "numerical range"):
            simulate_actuator_motion(request(duration_s=1e308, time_step_s=1e-15))
        with self.assertRaisesRegex(ValueError, "mechanical energy"):
            simulate_actuator_motion(request(mass_kg=1.0, initial_velocity_m_per_s=1e308))

    def test_decimal_duration_does_not_create_a_sliver_step(self):
        for duration, step in ((1.0, 0.1), (0.14, 0.01)):
            result = simulate_actuator_motion(request(force_map=force_map(0.0), mass_kg=1.0,
                initial_velocity_m_per_s=0.5, duration_s=duration, time_step_s=step))
            self.assertAlmostEqual(result["velocity_m_per_s"][-1], 0.5, places=14)
            self.assertAlmostEqual(result["energy_balance_residual_j"], 0.0, places=14)
            self.assertLessEqual(len(result["time_s"]), round(duration / step) + 1)

    def test_intra_step_turning_point_stroke_event_is_detected(self):
        result = simulate_actuator_motion(request(force_map=force_map(-8.0), mass_kg=1.0,
            initial_velocity_m_per_s=6.0, duration_s=1.5, time_step_s=1.5))
        self.assertEqual(result["termination"], "stroke_boundary_reached")
        self.assertEqual(result["boundary"], "maximum")
        self.assertAlmostEqual(result["time_s"][-1], 0.5, places=12)
        self.assertEqual(result["position_m"][-1], 2.0)

    def test_piecewise_map_work_is_distinct_from_midpoint_quadrature(self):
        mapped = force_map(0.0)
        x = np.asarray(mapped["position_m"])
        mapped["force_n"] = np.abs(x).tolist()
        mapped["coenergy_j"] = (0.5 * x * np.abs(x)).tolist()
        mapped["relative_tolerance"] = 0.1
        mapped["absolute_force_tolerance_n"] = 0.2
        result = simulate_actuator_motion(request(force_map=mapped, mass_kg=10.0,
            initial_position_m=-0.2, initial_velocity_m_per_s=1.0,
            duration_s=0.4, time_step_s=0.4))
        self.assertNotEqual(result["force_quadrature_error_j"], 0.0)
        self.assertAlmostEqual(result["energy_balance_residual_j"], 0.0, places=12)

    def test_inconsistent_map_and_nonunique_step_are_rejected(self):
        item = request(); item["force_map"]["force_n"] = [-1.0] * 9
        with self.assertRaisesRegex(ValueError, "consistent"):
            simulate_actuator_motion(item)
        rising = force_map(0.0)
        rising["force_n"] = np.linspace(-2, 2, 9).tolist()
        rising["coenergy_j"] = (np.linspace(-2, 2, 9) ** 2 / 2).tolist()
        item = request(force_map=rising, mass_kg=0.01, time_step_s=1.0)
        with self.assertRaisesRegex(ValueError, "unique"):
            simulate_actuator_motion(item)

    def test_request_is_not_mutated(self):
        item = request(); original = copy.deepcopy(item)
        simulate_actuator_motion(item)
        self.assertEqual(item, original)


if __name__ == "__main__":
    unittest.main()
