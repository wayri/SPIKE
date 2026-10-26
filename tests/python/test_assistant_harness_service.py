# SPDX-License-Identifier: Apache-2.0
"""Harness request routing keeps validation errors actionable and bounded."""
import tempfile
import unittest
from pathlib import Path
from python.spike_core.service_assistant import handle_assistant_request


class HarnessServiceTests(unittest.TestCase):
    def test_readonly_csv_roundtrip_and_safe_recovery_error(self):
        base = Path(__file__).resolve().parents[2] / "build"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            target = Path(folder)
            self.assertTrue(target.resolve().is_relative_to(base.resolve()))
            (target / "data.csv").write_text("value_V\n3.2\n3.3\n3.4\n", encoding="utf-8")
            reply = handle_assistant_request("assistant_work_files", {"root": folder, "action": "csv_summary", "relativeName": "data.csv", "column": "value_V", "units": "V"})
            self.assertTrue(reply["ok"], reply)
            self.assertEqual(reply["result"]["statistics"]["count"], 3)
            self.assertAlmostEqual(reply["result"]["statistics"]["mean"], 3.3)
            invalid = handle_assistant_request("assistant_work_files", {"root": folder, "action": "csv_summary", "relativeName": "data.csv", "column": "value_V"})
            self.assertFalse(invalid["ok"])
            self.assertIn("units", invalid["error"])
            self.assertNotIn(folder, invalid["error"])
            unknown = handle_assistant_request("assistant_work_files", {"root": folder, "action": "read", "relativeName": "data.csv", "shell": "do not dispatch"})
            self.assertFalse(unknown["ok"])
