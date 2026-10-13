# SPDX-License-Identifier: Apache-2.0
"""Public worker admission, progress correlation and actual native dispatch."""
import contextlib
import io
import json
import unittest
from python.spike_core.service import handle
from python.spike_core.automation import SpikeAutomation
from python.spike_core.mcp_server import McpServer


class PwmWorkerTests(unittest.TestCase):
    def test_strict_preflight_and_mcp(self):
        request = {"contract": "spike/pwm-electrothermal-request/v1", "parameters": {}}
        result = handle({"method": "validate_pwm_electrothermal", "params": {"request": request}})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["status"], "accepted")
        for params in ({}, {"request": request, "executable": "not-allowed"}):
            rejected = handle({"method": "run_pwm_electrothermal", "params": params})
            self.assertFalse(rejected["ok"])
            self.assertIn("PWM_FIELDS", rejected["error_detail"]["detail"])
        response = McpServer(SpikeAutomation()).call_tool("spike_validate_pwm_electrothermal", {"request": request})
        self.assertFalse(response["isError"], response)

    def test_actual_run_and_correlated_progress(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            response = handle({"id": "pwm-test", "method": "run_pwm_electrothermal", "params": {
                "request": {"contract": "spike/pwm-electrothermal-request/v1", "parameters": {"cycles": 4}}}})
        self.assertTrue(response["ok"], response)
        result = response["result"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["windows"]), 4)
        json.dumps(result, allow_nan=False)
        frames = [json.loads(line.split(":", 1)[1]) for line in stderr.getvalue().splitlines() if line.startswith("SPIKE_PROGRESS:")]
        self.assertTrue(frames)
        self.assertTrue(all(frame["operation_id"] == "pwm-test" for frame in frames))
        self.assertEqual(frames[-1]["frame"]["completed_cycles"], 4)
        uncorrelated = handle({"method": "run_pwm_electrothermal", "params": {
            "request": {"contract": "spike/pwm-electrothermal-request/v1", "parameters": {"cycles": 1}}}})
        self.assertTrue(uncorrelated["ok"], uncorrelated)
