# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Actual process dispatch and independently specified two-eye identity case."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from python.spike_core.service_si_models import handle_si_model_request
from python.spike_core.service_si_pam3 import simulate_pam3_request


def request():
    return {"contract": "spike/si-pam3-request/v1", "symbols": [0, 1, 2] * 32,
            "levels_v": [-0.4, 0.0, 0.4], "channel_impulse": [1.0],
            "symbol_rate_hz": 20e9, "samples_per_ui": 8}


class Pam3ProcessTests(unittest.TestCase):
    def test_identity_decisions_and_two_eyes(self):
        result = simulate_pam3_request(request())
        self.assertEqual(len(result["eyes"]), 2)
        self.assertEqual(result["errors"]["observed_symbol_errors"], 0)
        self.assertEqual(result["errors"]["expected_symbol_error_rate_gaussian"], 0)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source"]["modulation"], "PAM3")
        self.assertEqual(result["compliance_status"], "not_evaluated")
        self.assertEqual(len(result["request_sha256"]), 64)

    def test_strict_wrapper_and_physical_input_rejection(self):
        for patch in ({"levels_v": [0, 0.4, -0.4]}, {"symbols": [True] * 96},
                      {"channel_impulse": [float("nan")]}, {"qualification": "passed"},
                      {"levels_v": [0.0, 0.4]}, {"symbols": [0.0, 1.0, 2.0] * 32},
                      {"symbol_rate_hz": "2000000000"}, {"samples_per_ui": "8"}):
            with self.subTest(patch=patch):
                value = copy.deepcopy(request()); value.update(patch)
                self.assertFalse(handle_si_model_request("simulate_si_pam3", {"request": value})["ok"])
        self.assertFalse(handle_si_model_request("simulate_si_pam3", {"request": request(), "execute": True})["ok"])

    def test_fresh_worker(self):
        message = {"id": "pam3", "method": "simulate_si_pam3", "params": {"request": request()}}
        run = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
            input=json.dumps(message) + "\n", cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=30, check=True)
        response = json.loads(run.stdout)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["errors"]["observed_symbol_errors"], 0)

    def test_registered_schema_and_rejections(self):
        from jsonschema import Draft202012Validator, ValidationError
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / "schemas/manifest.json").read_text())
        filename = manifest["schemas"][request()["contract"]]
        schema = json.loads((root / "schemas" / filename).read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(request())
        for change in ({"symbols": [3]}, {"levels_v": [0, 1]}, {"execute": True}, {"samples_per_ui": 1}):
            value = {**request(), **change}
            with self.subTest(change=change), self.assertRaises(ValidationError):
                validator.validate(value)


if __name__ == "__main__":
    unittest.main()
