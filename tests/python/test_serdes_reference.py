# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import json
import unittest

from scripts.qualify_serdes_reference import BIT_RATE_HZ, qualification_report


class SerdesReferenceQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = qualification_report()

    def test_all_bounded_criteria_pass(self):
        self.assertEqual(self.report["status"], "pass", self.report["criteria"])
        self.assertTrue(all(item["pass"] for item in self.report["criteria"]))

    def test_scope_cannot_be_misread_as_compliance(self):
        self.assertEqual(self.report["bit_rate_hz"], BIT_RATE_HZ)
        self.assertFalse(self.report["production_qualified"])
        self.assertEqual(self.report["compliance_status"], "not_evaluated")
        self.assertIn("No 10GBASE-T PHY", self.report["limitations"][1])
        json.dumps(self.report, allow_nan=False)

    def test_time_grid_and_failure_gate_are_explicit(self):
        criteria = {item["id"]: item for item in self.report["criteria"]}
        self.assertAlmostEqual(criteria["exact_10g_rate_grid"]["actual_hz"], BIT_RATE_HZ, delta=0.01)
        self.assertEqual(criteria["insufficient_bandwidth_rejected"]["status"], "blocked")
        self.assertIn("at least 8 samples/UI", criteria["insufficient_bandwidth_rejected"]["reason"])

    def test_time_domain_has_an_absolute_oracle(self):
        criterion = next(item for item in self.report["criteria"] if item["id"] == "matched_time_domain_eye")
        self.assertAlmostEqual(criterion["actual_eye_height_v"], 0.4, delta=1e-10)
        self.assertEqual(criterion["delay_ui"], 1.0)

    def test_reproducibility_identity_is_recorded(self):
        self.assertEqual(len(self.report["request_sha256"]), 11)
        self.assertTrue(all(len(value) == 64 for value in self.report["request_sha256"].values()))
        self.assertEqual(self.report["runtime"]["numpy_version"], __import__("numpy").__version__)

    def test_fixed_band_frequency_grid_refinement_preserves_exact_rate(self):
        criterion = next(item for item in self.report["criteria"]
                         if item["id"] == "fixed_band_frequency_grid_refinement_sensitivity")
        deltas = criterion["successive_delta_v"]
        self.assertEqual(criterion["frequency_points"], [257, 513, 1025, 2049, 4097, 8193])
        self.assertEqual(len(criterion["represented_bit_rate_hz"]), 6)
        for rate in criterion["represented_bit_rate_hz"]:
            self.assertAlmostEqual(rate, BIT_RATE_HZ, delta=0.01)
        self.assertLessEqual(deltas[-1], criterion["engineering_gate"]["final_delta_limit_v"])
        self.assertFalse(criterion["engineering_gate"]["monotonic_delta_contraction_required"])
        self.assertFalse(criterion["engineering_gate"]["normative"])
        self.assertFalse(criterion["engineering_gate"]["is_error_bound"])


if __name__ == "__main__":
    unittest.main()
