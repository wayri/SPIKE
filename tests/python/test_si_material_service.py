# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Worker preparation preserves native source and requires exact bound inputs."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from python.spike_core.service_si_models import handle_si_model_request
from tests.python import test_si_material_scenario as fixtures


class MaterialServiceTests(unittest.TestCase):
    def test_exact_wrapper_and_bounded_controls(self):
        design = fixtures.uniform_design()
        params = {"design": design, "request": fixtures.scenario_request(design)}
        response = handle_si_model_request("prepare_si_material_scenario", params)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["design"]["source"], design["source"])
        self.assertNotIn("spike.si_material_scenario", design.get("metadata", {}))
        self.assertFalse(handle_si_model_request("prepare_si_material_scenario", {**params, "execute": True})["ok"])
        with patch("python.spike_core.service_si_materials.MAX_INLINE_BYTES", 1):
            self.assertFalse(handle_si_model_request("prepare_si_material_scenario", params)["ok"])

    def test_fresh_json_line_process(self):
        design = fixtures.uniform_design()
        message = {"id": "si-material", "method": "prepare_si_material_scenario",
                   "params": {"design": design, "request": fixtures.scenario_request(design)}}
        run = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
            input=json.dumps(message)+"\n", cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=30, check=True)
        response = json.loads(run.stdout)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["design"]["source"], design["source"])
