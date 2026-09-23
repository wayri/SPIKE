# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import json
import math
from pathlib import Path
import unittest

import numpy as np

from python.spike_core.voice_coil_drive import CONTRACT, simulate_voice_coil_drive


def request(**updates):
    value = {
        "contract": CONTRACT, "resistance_ohm": 4.0, "inductance_h": 0.02,
        "force_constant_n_per_a": 2.0, "mass_kg": 0.1,
        "damping_n_s_per_m": 0.4, "spring_n_per_m": 30.0,
        "spring_equilibrium_position_m": 0.0, "voltage_v": 1.5,
        "initial_current_a": 0.0, "initial_position_m": 0.0,
        "initial_velocity_m_per_s": 0.0, "duration_s": 0.1, "time_step_s": 1e-4,
        "provenance": "Original MIT SigHarmonic numerical test",
    }
    value.update(updates)
    return value


class VoiceCoilDriveTests(unittest.TestCase):
    def test_uncoupled_rl_matches_analytical_solution(self):
        item = request(force_constant_n_per_a=0.0, spring_n_per_m=0.0,
                       damping_n_s_per_m=0.0, initial_velocity_m_per_s=0.25)
        result = simulate_voice_coil_drive(item)
        exact = item["voltage_v"] / item["resistance_ohm"] * (
            1.0 - math.exp(-item["resistance_ohm"] * item["duration_s"] / item["inductance_h"]))
        self.assertLess(abs(result["current_a"][-1] - exact), 2e-5)
        self.assertAlmostEqual(result["position_m"][-1], 0.025, places=12)
        self.assertLess(abs(result["energy_balance_residual_j"]), 2e-13)

    def test_lossless_unforced_system_conserves_total_energy(self):
        result = simulate_voice_coil_drive(request(
            resistance_ohm=0.0, damping_n_s_per_m=0.0, voltage_v=0.0,
            initial_current_a=0.7, initial_position_m=0.012,
            initial_velocity_m_per_s=-0.3, duration_s=0.4, time_step_s=0.002))
        self.assertAlmostEqual(result["initial_stored_energy_j"],
                               result["final_stored_energy_j"], places=12)
        self.assertLess(abs(result["energy_balance_residual_j"]), 2e-13)
        self.assertEqual(result["resistive_dissipation_j"], 0.0)
        self.assertEqual(result["mechanical_damping_dissipation_j"], 0.0)

    def test_back_emf_opposes_positive_initial_velocity(self):
        result = simulate_voice_coil_drive(request(
            resistance_ohm=0.0, damping_n_s_per_m=0.0, spring_n_per_m=0.0,
            voltage_v=0.0, initial_velocity_m_per_s=1.0,
            duration_s=1e-4, time_step_s=1e-4))
        self.assertLess(result["current_a"][-1], 0.0)
        self.assertLess(result["velocity_m_per_s"][-1], 1.0)
        self.assertLess(abs(result["energy_balance_residual_j"]), 1e-14)

    def test_second_order_convergence_against_independent_eigen_solution(self):
        item = request(duration_s=0.073, initial_current_a=0.2,
                       initial_position_m=0.004, initial_velocity_m_per_s=-0.1)
        r, l, kf = item["resistance_ohm"], item["inductance_h"], item["force_constant_n_per_a"]
        m, c, k = item["mass_kg"], item["damping_n_s_per_m"], item["spring_n_per_m"]
        matrix = np.array([[-r/l, 0, -kf/l], [0, 0, 1], [kf/m, -k/m, -c/m]], float)
        steady = np.linalg.solve(matrix, -np.array([item["voltage_v"]/l, 0, 0]))
        initial = np.array([item["initial_current_a"], item["initial_position_m"],
                            item["initial_velocity_m_per_s"]])
        values, vectors = np.linalg.eig(matrix)
        exact = steady + vectors @ (np.exp(values * item["duration_s"]) *
                                    np.linalg.solve(vectors, initial - steady))
        errors = []
        # Normalize each unlike physical state independently before combining
        # errors; amperes, metres, and metres/second are not commensurate.
        scales = np.maximum(np.abs(np.real_if_close(exact)), np.array([1.0, 0.01, 1.0]))
        for step in (0.004, 0.002, 0.001):
            result = simulate_voice_coil_drive(dict(item, time_step_s=step))
            actual = np.array([result["current_a"][-1], result["position_m"][-1],
                               result["velocity_m_per_s"][-1]])
            errors.append(float(np.linalg.norm((actual - np.real_if_close(exact)) / scales)))
        self.assertGreater(errors[0] / errors[1], 3.5)
        self.assertGreater(errors[1] / errors[2], 3.5)

    def test_exact_uniform_indexed_grid_has_no_sliver(self):
        result = simulate_voice_coil_drive(request(duration_s=1.0, time_step_s=0.3))
        self.assertEqual(result["step_count"], 4)
        self.assertEqual(result["time_s"], [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(result["actual_time_step_s"], 0.25)

    def test_example_executes_and_input_is_not_mutated(self):
        root = Path(__file__).resolve().parents[2]
        item = json.loads((root / "examples/actuator/voice-coil-drive.json").read_text())
        original = copy.deepcopy(item)
        result = simulate_voice_coil_drive(item)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(item, original)
        self.assertFalse(result["production_qualified"])

    def test_invalid_extreme_and_resource_requests_fail(self):
        cases = [
            {"inductance_h": 0.0}, {"mass_kg": -1.0}, {"resistance_ohm": -1.0},
            {"time_step_s": float("nan")}, {"voltage_v": True}, {"unknown": 1},
            {"provenance": ""},
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(ValueError):
                simulate_voice_coil_drive(request(**update))
        with self.assertRaisesRegex(ValueError, "finite representable"):
            simulate_voice_coil_drive(request(voltage_v=10**400))
        with self.assertRaisesRegex(ValueError, "limit is 100000"):
            simulate_voice_coil_drive(request(duration_s=1.0, time_step_s=1e-6))
        with self.assertRaisesRegex(ValueError, "ill-conditioned"):
            simulate_voice_coil_drive(request(
                inductance_h=1e-12, mass_kg=1e-12, force_constant_n_per_a=1e6,
                duration_s=1.0, time_step_s=1.0))


if __name__ == "__main__":
    unittest.main()
