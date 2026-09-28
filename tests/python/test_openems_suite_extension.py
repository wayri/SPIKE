# SPDX-License-Identifier: Apache-2.0
"""OpenEMS suite discovery, UI manifest and process preflight coverage."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.extensions import ExtensionManifest, ProcessExtension
from tests.python.test_external_engines import openems_design


ROOT = Path(__file__).resolve().parents[2] / "extensions" / "openems_suite"


class OpenemsSuiteExtensionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ExtensionManifest.from_dict(json.loads((ROOT / "spike-extension.json").read_text(encoding="utf-8")))
        self.extension = ProcessExtension(self.manifest, ROOT, trusted=True)

    def test_menu_items_are_declared_and_thermal_is_absent(self):
        self.assertEqual(self.manifest.ui["menu_items"], ["openems-pi", "openems-si"])
        self.assertEqual({item["id"] for item in self.manifest.contributes["applications"]}, {"openems-pi", "openems-si"})
        raw = self.manifest.to_dict()
        raw["ui"] = {"menu_items": ["missing-action"]}
        with self.assertRaisesRegex(ValueError, "menu_items"):
            ExtensionManifest.from_dict(raw)

    def test_pi_and_si_preflight_use_existing_adapter(self):
        design = openems_design().to_dict()
        for contribution, domain in (("openems-pi", "pi"), ("openems-si", "si")):
            result = self.extension.invoke(contribution, {"design": design, "parameters": {
                "operation": "preflight", "analysis": {
                    "net_names": ["RF"], "frequency_start_hz": 1e6,
                    "frequency_stop_hz": 1e9, "frequency_points": 11,
                },
            }})
            self.assertEqual(result["data"]["domain"], domain)
            self.assertEqual(result["data"]["validation"]["contract"], "spike/openems-preflight/v1")
            self.assertFalse(result["data"]["validation"]["can_run"])

    def test_missing_analysis_is_explicit_failure(self):
        with self.assertRaisesRegex(RuntimeError, "analysis must be a JSON object"):
            self.extension.invoke("openems-si", {"design": openems_design().to_dict(), "parameters": {}})

    def test_worker_catalog_discovers_trusted_bundle(self):
        from python.spike_core.service import handle

        response = handle({"method": "list_extensions", "params": {}})
        self.assertTrue(response["ok"])
        suite = next(item for item in response["result"]["extensions"] if item["id"] == "spike.openems-suite")
        self.assertTrue(suite["trusted"])
        self.assertTrue(suite["ui"]["menu_bar"])

    def test_prepare_creates_authenticated_case_in_private_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LOCALAPPDATA": directory, "SPIKE_STATE_HOME": str(Path(directory) / "state"),
        }):
            response = self.extension.invoke("openems-si", {"design": openems_design().to_dict(), "parameters": {
                "operation": "prepare", "analysis": {"net_names": ["RF"],
                    "frequency_start_hz": 1e6, "frequency_stop_hz": 1e9, "frequency_points": 11},
            }})
            case = response["data"]["case"]
            self.assertEqual(case["status"], "prepared_review_required")
            self.assertTrue(Path(case["case_dir"]).is_relative_to(Path(directory)))
            self.assertTrue((Path(case["case_dir"]) / "job.json").is_file())


if __name__ == "__main__":
    unittest.main()
