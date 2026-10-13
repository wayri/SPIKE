# SPDX-License-Identifier: Apache-2.0
"""Integrated assistant worker routing and offline contract tools."""
import unittest
from unittest.mock import patch
from python.spike_core.service import handle

class AssistantServiceTests(unittest.TestCase):
    def test_catalog_and_schema_validation_use_installed_files(self):
        response = handle({"method": "assistant_schema", "params": {}})
        self.assertTrue(response["ok"])
        self.assertIn("analysis-spec-v1.schema.json", response["result"]["schemas"])
        response = handle({"method": "assistant_schema", "params": {"name": "analysis-spec-v1.schema.json"}})
        self.assertTrue(response["ok"])
        self.assertIn("schema", response["result"])
        response = handle({"method": "assistant_validate_schema", "params": {"name": "analysis-spec-v1.schema.json", "document": {}}})
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["valid"])
        self.assertTrue(response["result"]["validation_is_not_solver_admission"])

    def test_arbitrary_catalog_paths_unknown_methods_and_fields_fail(self):
        for params in ({"name": "../../secrets.txt"}, {"filename": "README.md"}):
            response = handle({"method": "assistant_schema", "params": params})
            self.assertFalse(response["ok"])
        response = handle({"method": "assistant_arbitrary_dispatch", "params": {}})
        self.assertFalse(response["ok"])

    def test_turn_routes_inert_response_without_executing_tool(self):
        reply = {"provider": "ollama", "model": "fixture", "message": {"role": "assistant", "content": "", "tool_calls": [{"id": "one", "name": "spike_report", "arguments": {}}]}}
        with patch("python.spike_core.assistant_provider.assistant_turn", return_value=reply) as turn:
            response = handle({"method": "assistant_turn", "params": {"provider": "ollama", "model": "fixture", "messages": [{"role": "user", "content": "SPIKE UNTRUSTED PROJECT EVIDENCE: {}"}], "tools": [], "share_project_context": True, "allow_cloud": False}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"], reply)
        turn.assert_called_once()

if __name__ == "__main__":
    unittest.main()
