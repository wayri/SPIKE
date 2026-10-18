# SPDX-License-Identifier: Apache-2.0
"""Evidence gates must not confuse algebraic execution with board readiness."""
import copy
import unittest

from scripts.check_board_pisi_readiness import dc_evidence, refinement_evidence


class BoardPiSiEvidenceTests(unittest.TestCase):
    def result(self):
        return {"status": "completed", "model_status": "approximate", "summary": {
            "total_load_current_a": 2.0, "max_load_voltage_drop_v": .01,
            "total_network_loss_w": .02, "max_scaled_linear_residual": 1e-12}}

    def test_resistance_normalizes_excitation_and_checks_power(self):
        result = dc_evidence(self.result())
        self.assertAlmostEqual(result["resistance_ohm"], .005)
        self.assertEqual(result["power_balance_error_w"], 0)
        self.assertEqual(result["model_status"], "approximate")

    def test_failed_solver_is_not_completed(self):
        self.assertFalse(dc_evidence({"status": "failed"})["completed"])

    def test_nonfinite_negative_and_residual_fail(self):
        for key, value in [("max_load_voltage_drop_v", float("nan")),
                           ("total_load_current_a", -1),
                           ("max_scaled_linear_residual", 1e-3)]:
            result = copy.deepcopy(self.result())
            result["summary"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                dc_evidence(result)

    def test_low_residual_cannot_hide_energy_error(self):
        result = self.result()
        result["summary"]["total_network_loss_w"] = .03
        with self.assertRaisesRegex(ValueError, "power conservation"):
            dc_evidence(result)

    def test_refinement_requires_three_completed_levels(self):
        self.assertFalse(refinement_evidence([])["passed"])
        self.assertFalse(refinement_evidence([{"completed": False}] * 3)["passed"])

    def test_refinement_rejects_nonconvergent_and_worsening_trends(self):
        for resistances in [[1.1, 1.05, 1], [1.025, 1.02, 1]]:
            rows = [{"completed": True, "resistance_ohm": r} for r in resistances]
            self.assertFalse(refinement_evidence(rows)["passed"])

    def test_small_nonworsening_changes_are_narrow_mesh_evidence(self):
        rows = [{"completed": True, "resistance_ohm": r} for r in [1.02, 1.005, 1]]
        evidence = refinement_evidence(rows)
        self.assertTrue(evidence["passed"])
        self.assertIn("no independent", evidence["scope"])


if __name__ == "__main__":
    unittest.main()
