# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Declared PAM3 cannot silently execute through the NRZ/PAM4 engine."""
import unittest
from unittest.mock import patch

from python.spike_core.si_protocol_suites import validate_si_protocol_suite, plan_si_protocol_analysis
from python.spike_core.si_protocol_test_runner import preflight_si_suite_resources, SiProtocolTestRunnerError
from tests.python.test_si_protocol_suites import fixture


class Pam3AdmissionTests(unittest.TestCase):
    def test_inventory_is_valid_but_numerical_planning_remains_blocked(self):
        suite = fixture(); suite["encoding"] = "PAM3"
        self.assertFalse(validate_si_protocol_suite(suite)["compliance_claimed"])
        available = [item for analysis in suite["analyses"] for item in analysis["requiredCapabilities"]]
        plan = plan_si_protocol_analysis(suite, available + ["pam3_execution"])
        self.assertEqual(plan["stages"][0]["status"], "configurable")
        self.assertEqual(plan["stages"][1]["status"], "blocked")
        self.assertIn("pam3_execution", plan["stages"][1]["missing_capabilities"])

    def test_execution_rejects_before_lane_validation_or_field_allocation(self):
        suite = fixture(); suite["encoding"] = "PAM3"
        raw = {"contract": "spike/si-protocol-test-suite-request/v1", "suite": suite, "lanes": []}
        with patch("python.spike_core.si_protocol_test_runner.analyze_uniform_design_channel") as solve:
            with self.assertRaisesRegex(SiProtocolTestRunnerError, "PAM3 execution is not implemented"):
                preflight_si_suite_resources(raw)
            solve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
