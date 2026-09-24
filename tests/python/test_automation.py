"""The Python scripting surface uses the worker's normal admission boundary."""

import unittest

from python.spike_core.automation import SpikeAutomation, SpikeAutomationError


class AutomationTests(unittest.TestCase):
    def test_calls_are_detached_json_and_run_in_order(self):
        seen = []
        source = {"value": [1]}

        def dispatch(request):
            seen.append(request)
            return {"ok": True, "result": {"method": request["method"]}}

        client = SpikeAutomation(dispatch)
        self.assertEqual(client.call("health", source), {"method": "health"})
        source["value"].append(2)
        self.assertEqual(seen[0]["params"], {"value": [1]})
        output = client.run_steps([
            {"name": "first", "method": "one"},
            {"name": "second", "method": "two", "params": {"limit": 2}},
        ])
        self.assertEqual(list(output), ["first", "second"])
        self.assertEqual([row["method"] for row in seen], ["health", "one", "two"])

    def test_errors_and_nonfinite_values_fail_closed(self):
        client = SpikeAutomation(lambda request: {"ok": False, "error": "blocked"})
        with self.assertRaisesRegex(SpikeAutomationError, "blocked"):
            client.call("solve")
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            client.call("solve", {"nan": float("nan")})
        with self.assertRaisesRegex(ValueError, "unique"):
            SpikeAutomation(lambda request: {"ok": True, "result": {}}).run_steps([{"name": "same", "method": "one"}, {"name": "same", "method": "two"}])

    def test_extension_invocation_preserves_worker_protocol(self):
        captured = []
        client = SpikeAutomation(lambda request: (captured.append(request) or {"ok": True, "result": {"contract": "spike/extension-result/v1"}}))
        result = client.invoke_extension("example", "analysis", design={"contract": "spike/v1", "design_id": "b"}, parameters={"variant": 2})
        self.assertEqual(result["contract"], "spike/extension-result/v1")
        self.assertEqual(captured[0]["params"]["context"]["design"]["design_id"], "b")
        self.assertEqual(captured[0]["params"]["context"]["parameters"], {"variant": 2})


if __name__ == "__main__":
    unittest.main()
