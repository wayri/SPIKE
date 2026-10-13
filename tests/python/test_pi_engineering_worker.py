# SPDX-License-Identifier: Apache-2.0
"""Public worker and MCP integration of the original PI engineering kernels."""
import json
import unittest

from python.spike_core.automation import SpikeAutomation
from python.spike_core.mcp_server import McpServer
from python.spike_core.service import handle
from tests.python.test_smps_converter import request as smps_request
from tests.python.test_capacitor_placement import request as capacitor_request
from tests.python.test_pi_return_path import design, request as return_request


class PiEngineeringWorkerTests(unittest.TestCase):
    def test_actual_worker_results_and_serialization(self):
        cases = [
            ("run_smps_converter", {"request": smps_request(losses=True)}, "spike/smps-converter-result/v1"),
            ("evaluate_capacitor_placement", {"request": capacitor_request()}, "spike/capacitor-placement-result/v1"),
            ("plan_pi_return_path", {"design": design(), "request": return_request()}, "spike/pi-return-path-result/v1"),
        ]
        for method, params, contract in cases:
            with self.subTest(method=method):
                response = handle({"method": method, "params": params})
                self.assertTrue(response["ok"], response)
                self.assertEqual(response["result"]["contract"], contract)
                json.dumps(response, allow_nan=False)

    def test_parameter_rejection_is_structured(self):
        for method in ("run_smps_converter", "evaluate_capacitor_placement", "plan_pi_return_path"):
            response = handle({"method": method, "params": {"request": {}, "unexpected": True}})
            self.assertFalse(response["ok"])
            self.assertEqual(response["code"], "PI_ENGINEERING_FIELDS")
            self.assertEqual(response["error_code"], "SPIKE-BE-PI-E-0120")
        response = handle({"method": "run_smps_converter", "params": {"request": {}}})
        self.assertFalse(response["ok"])
        self.assertTrue(response["code"])
        self.assertEqual(response["error_code"], "SPIKE-BE-PI-E-0121")

    def test_mcp_actual_worker_calls_and_no_writes(self):
        server = McpServer(SpikeAutomation())
        for name, params, contract in [
            ("spike_run_smps_converter", {"request": smps_request()}, "spike/smps-converter-result/v1"),
            ("spike_evaluate_capacitor_placement", {"request": capacitor_request()}, "spike/capacitor-placement-result/v1"),
            ("spike_plan_pi_return_path", {"design": design(), "request": return_request()}, "spike/pi-return-path-result/v1"),
        ]:
            response = server.call_tool(name, params)
            self.assertFalse(response["isError"], response)
            self.assertEqual(response["structuredContent"]["contract"], contract)


if __name__ == "__main__":
    unittest.main()
