"""Integrated Python workspace execution and result admission."""

import unittest
import os
from pathlib import Path
from unittest.mock import patch

from python.spike_core.script_runtime import run_python_script
from python.spike_core.extensions import ExtensionRegistry


DESIGN = {"contract": "spike/v1", "design_id": "script-board", "name": "Script board",
          "source_format": "test", "units": "mm", "layers": [], "nets": [], "tracks": [],
          "vias": [], "pads": [], "zones": [], "components": [], "stackup": [],
          "issues": [], "metadata": {}}


class PythonWorkspaceTest(unittest.TestCase):
    def test_worker_method_runs_script(self):
        from python.spike_core.service import handle
        response = handle({"method": "run_python_script", "params": {"code": "print('worker route')"}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["contract"], "spike/python-script-result/v1")
        self.assertIn("worker route", response["result"]["stdout"])

    def test_script_can_invoke_session_trusted_external_adapter(self):
        from python.spike_core import service
        examples = Path(__file__).resolve().parents[2] / "extension_sdk" / "examples"
        registry = ExtensionRegistry()
        registry.discover([examples])
        registry.trust("org.example.field-data-adapter")
        code = """reply = spike.invoke_extension(
    'org.example.field-data-adapter', 'import-voltage-field',
    {'samples': [{'x_mm': 1, 'y_mm': 2, 'value': 3.3}]})
print(reply['data']['analysis_result']['fields']['visualization']['scalar_fields']['voltage_v'][0]['value'])"""
        with patch.dict(os.environ, {"SPIKE_EXTENSION_PATH": str(examples)}), patch.object(service, "_extension_registry", registry):
            response = service.handle({"method": "run_python_script", "params": {"code": code, "design": DESIGN}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "completed")
        self.assertIn("3.3", response["result"]["stdout"])
        self.assertEqual(response["result"]["published_result"]["provenance"]["script_upstream_extension_id"],
                         "org.example.field-data-adapter")

    def test_script_sees_board_calls_worker_and_captures_output(self):
        result = run_python_script({"code": "print(spike.design['design_id'])\nprint(spike.call('health')['contract'])",
                                    "design": DESIGN})
        self.assertEqual(result["status"], "completed")
        self.assertIn("script-board", result["stdout"])
        self.assertIn("spike/worker-health/v1", result["stdout"])

    def test_published_scalar_field_is_design_bound(self):
        result = run_python_script({"code": "spike.publish_scalar_field('voltage_v', "
            "[{'x_mm': 1, 'y_mm': 2, 'value': 3.3}])", "design": DESIGN})
        self.assertEqual(result["status"], "completed")
        published = result["published_result"]
        self.assertEqual(published["provenance"]["design_id"], "script-board")
        self.assertEqual(published["provenance"]["extension_id"], "spike.python-workspace")
        self.assertEqual(published["fields"]["visualization"]["scalar_fields"]["voltage_v"][0]["value"], 3.3)

    def test_failure_is_reported_and_does_not_publish(self):
        result = run_python_script({"code": "print('before')\nraise ValueError('bad script')", "design": DESIGN})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["return_code"], 1)
        self.assertIn("before", result["stdout"])
        self.assertIn("ValueError: bad script", result["stderr"])
        self.assertIsNone(result.get("published_result"))

    def test_rejects_nonfinite_published_field(self):
        result = run_python_script({"code": "spike.publish_scalar_field('voltage_v', "
            "[{'x_mm': 1, 'y_mm': 2, 'value': float('nan')}])", "design": DESIGN})
        self.assertEqual(result["status"], "failed")
        self.assertIn("non-finite", result["stderr"])

    def test_rejects_published_result_for_another_board(self):
        code = """spike.publish_result({
    'contract': 'spike/v1', 'analysis_id': 'wrong-board', 'status': 'completed',
    'mode': 'dc', 'model_status': 'unvalidated', 'summary': {}, 'fields': {},
    'networks': {}, 'probes': [], 'issues': [],
    'provenance': {'design_id': 'another-board', 'design_digest_sha256': '0' * 64,
                   'solver': 'script-test'}})"""
        result = run_python_script({"code": code, "design": DESIGN})
        self.assertEqual(result["status"], "failed")
        self.assertIn("does not match", result["stderr"])
        self.assertIsNone(result.get("published_result"))

    def test_script_timeout(self):
        result = run_python_script({"code": "while True: pass", "timeout_seconds": 1})
        self.assertEqual(result["status"], "failed")
        self.assertIn("exceeded", result["stderr"])


if __name__ == "__main__":
    unittest.main()
