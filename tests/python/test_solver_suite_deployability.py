# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic

import unittest

from python.spike_core.capability_ledger import native_capability_ledger
from python.spike_core.solver_suite_deployability import CONTRACT, build_solver_suite_deployability


class SolverSuiteDeployabilityTests(unittest.TestCase):
    def test_current_suite_fails_closed_and_orders_shared_dependencies(self):
        report = build_solver_suite_deployability()
        self.assertEqual(report["contract"], CONTRACT)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["deployable"])
        self.assertEqual(report["summary"], {"total": 9, "deployable": 0, "blocked": 9})
        by_id = {item["id"]: item for item in report["capabilities"]}
        self.assertEqual(by_id["pi.ac_broadband"]["state"], "qualification_blocked")
        self.assertEqual(by_id["thermal.solid"]["state"], "implementation_blocked")
        self.assertIn("thermal.solid", by_id["multiphysics.electrothermal"]["dependency_blockers"])
        self.assertLess(report["execution_order"].index("thermal.solid"), report["execution_order"].index("multiphysics.electrothermal"))

    def test_structured_thermal_reference_is_registered_without_product_promotion(self):
        workflow = next(item for item in native_capability_ledger()["workflows"] if item["id"] == "thermal.structured_solid_reference")
        self.assertEqual(workflow["release_state"], "experimental")
        self.assertEqual(workflow["validation_state"], "experimental")
        self.assertNotIn("release_qualification", workflow)

    def test_missing_required_workflow_fails_closed(self):
        ledger = native_capability_ledger()
        ledger = {**ledger, "workflows": [item for item in ledger["workflows"] if item["id"] != "emi.near_and_far_field"]}
        report = build_solver_suite_deployability(ledger)
        profile = next(item for item in report["capabilities"] if item["id"] == "emi_emc.fullwave")
        self.assertEqual(profile["state"], "ledger_incomplete")
        self.assertFalse(profile["deployable"])


if __name__ == "__main__":
    unittest.main()
