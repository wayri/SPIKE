# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import json
import unittest
from scripts.qualify_actuator_reference import qualification_report


class ActuatorReferenceTests(unittest.TestCase):
    def test_all_runs_and_fault_injection(self):
        report = qualification_report()
        self.assertEqual(report["status"], "pass", report["criteria"])
        self.assertEqual(len(report["runs"]), 11)
        self.assertEqual(len(report["criteria"]), 9)
        self.assertFalse(report["production_qualified"])
        json.dumps(report, allow_nan=False)
