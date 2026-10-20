# SPDX-License-Identifier: Apache-2.0
"""Actual generic worker registration and v2 wire-publication regression."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_cfd
from tests.python.test_enclosure_cht_v2 import fixture

ROOT = Path(__file__).resolve().parents[2]


class EnclosureChtV2WorkerTests(unittest.TestCase):
    def test_actual_headless_worker_and_catalog(self):
        from python.spike_core.headless import run_request
        from jsonschema import Draft202012Validator
        request = fixture(refined=True)
        request["materials"][0]["density_kg_m3"] = 200000.
        response = run_request({"method": "run_enclosure_cht_v2",
            "params": {"request": request}}, timeout_seconds=45)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "completed", response)
        schema = json.loads((ROOT/"schemas/enclosure-cht-result-v2.schema.json").read_text())
        Draft202012Validator(schema).validate(response["result"])
        catalog = json.loads((ROOT/"schemas/manifest.json").read_text())["schemas"]
        for kind in ("request", "result"):
            self.assertEqual(catalog[f"spike/enclosure-cht-{kind}/v2"],
                             f"enclosure-cht-{kind}-v2.schema.json")

    def test_oversized_v2_wire_result_has_correct_contract_and_no_fields(self):
        (ROOT/"build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as directory:
            request, output = Path(directory)/"request.json", Path(directory)/"result.json"
            request.write_text("{}", encoding="utf-8")
            response = {"ok": True, "result": {"status": "completed",
                "fields": {"payload": "x"*(8*1024**2)}}}
            argv = ["run_cfd.py", "--engine", "enclosure-cht-v2", "--request",
                    str(request), "--output", str(output)]
            with patch.object(run_cfd, "handle_cfd_request", return_value=response), patch("sys.argv", argv):
                self.assertEqual(run_cfd.main(), 3)
            result = json.loads(output.read_text(encoding="utf-8"))["result"]
            self.assertEqual(result["contract"], "spike/enclosure-cht-result/v2")
            self.assertEqual(result["status"], "blocked")
            self.assertNotIn("fields", result)
            self.assertLess(output.stat().st_size, 8*1024**2)
