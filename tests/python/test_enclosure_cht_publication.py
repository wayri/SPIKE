# SPDX-License-Identifier: Apache-2.0
"""Wire-size budget includes JSON formatting and the worker envelope."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_cfd


class EnclosureChtPublicationTests(unittest.TestCase):
    def test_actual_headless_worker_and_rejected_domain(self):
        from python.spike_core.headless import run_request
        from tests.python.test_enclosure_cht import fixture
        request = fixture((2, 2, 2))
        for model, status in (("creeping", "completed"), ("SST", "blocked")):
            request["flow"]["model"] = model
            response = run_request({"method": "run_enclosure_cht",
                "params": {"request": request}}, timeout_seconds=45)
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["status"], status, response)
            if status == "blocked":
                self.assertNotIn("fields", response["result"])

    def test_schema_catalog_registration(self):
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads((root/"schemas/manifest.json").read_text())["schemas"]
        for kind in ("request", "result"):
            self.assertEqual(catalog[f"spike/enclosure-cht-{kind}/v1"],
                             f"enclosure-cht-{kind}-v1.schema.json")

    def test_oversized_process_envelope_is_rejected_without_partial_fields(self):
        parent = Path(__file__).resolve().parents[2]/"build"
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            request, output = root/"request.json", root/"result.json"
            request.write_text("{}", encoding="utf-8")
            payload = {"ok": True, "result": {"status": "completed",
                "fields": {"payload": "x"*(8*1024**2)}}}
            argv = ["run_cfd.py", "--engine", "enclosure-cht", "--request",
                    str(request), "--output", str(output)]
            with patch.object(run_cfd, "handle_cfd_request", return_value=payload), \
                    patch("sys.argv", argv):
                code = run_cfd.main()
            self.assertEqual(code, 3)
            self.assertLess(output.stat().st_size, 8*1024**2)
            result = json.loads(output.read_text(encoding="utf-8"))["result"]
            self.assertEqual(result["status"], "blocked")
            self.assertNotIn("fields", result)
            self.assertIn("8 MiB", result["issues"][0]["message"])
