# SPDX-License-Identifier: MIT
"""Independent KVL/I2R oracles for explicit-return harness operating points."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from python.spike_core.harness_pi import compile_harness_pi, run_harness_pi


def end(connector, pin):
    return {"connector": connector, "pin": pin}


def fixture():
    return {"contract": "spike/harness-pi-request/v1", "harness": {
        "contract": "spike/harness/v1", "id": "loop", "name": "Analytical two-wire loop",
        "connectors": [{"id": c, "pins": [{"id": "1"}, {"id": "2"}]} for c in ("source", "plug", "load")],
        "wires": [{"id": "feed", "from": end("plug", "1"), "to": end("load", "1"), "electrical": {"resistance_ohm": .1}},
                  {"id": "return", "from": end("load", "2"), "to": end("plug", "2"), "electrical": {"resistance_ohm": .2}}]},
        "ground": end("source", "2"),
        "contacts": [{"id": "feed-contact", "from": end("source", "1"), "to": end("plug", "1"), "resistance_ohm": .01},
                     {"id": "return-contact", "from": end("plug", "2"), "to": end("source", "2"), "resistance_ohm": .02}],
        "terminals": [{"id": "supply", "type": "voltage_source", "positive": end("source", "1"), "negative": end("source", "2"), "value": 12},
                      {"id": "sink", "type": "current_load", "positive": end("load", "1"), "negative": end("load", "2"), "value": 2}]}


class HarnessPiTests(unittest.TestCase):
    def test_worker_and_cli_share_execution(self):
        from python.spike_core.service import handle
        from python.spike_core.cli import main
        import tempfile
        response = handle({"id": "harness-pi-smoke", "method": "run_harness_pi", "params": {"request": fixture()}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "completed")
        with tempfile.TemporaryDirectory() as directory:
            request, output = Path(directory) / "request.json", Path(directory) / "result.json"
            request.write_text(json.dumps(fixture()), encoding="utf-8")
            code = main(["--quiet", "--output", str(output), "harness-pi", "--request", str(request)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.read_text())["request_digest"], response["result"]["request_digest"])

    def test_loop_voltage_drop_losses_and_energy(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        result = run_harness_pi(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        schema = Path(__file__).resolve().parents[2] / "schemas/harness-pi-result-v1.schema.json"
        Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(result)
        connections = {c["id"]: c for c in result["connections"]}
        self.assertAlmostEqual(connections["sink"]["voltage_v"], 12 - 2 * (.1 + .2 + .01 + .02), places=10)
        self.assertAlmostEqual(result["total_wire_loss_w"], 4 * (.1 + .2), places=10)
        self.assertAlmostEqual(result["total_contact_loss_w"], 4 * (.01 + .02), places=10)
        self.assertAlmostEqual(connections["supply"]["power_w"], -24, places=10)
        self.assertAlmostEqual(sum(result["native_result"]["data"]["element_power_w"].values()), 0, places=10)
        for wire in result["wires"]:
            self.assertAlmostEqual(wire["current_a"], 2, places=10)

    def test_dynamic_metadata_has_exact_dc_limit(self):
        raw = fixture()
        model = raw["harness"]["wires"][0]["electrical"]
        model.update(inductance_h=1e-6, capacitance_to_reference_f=1e-9, reference=end("source", "2"))
        result = run_harness_pi(raw)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["total_wire_loss_w"], 1.2, places=10)
        sink = next(c for c in result["connections"] if c["id"] == "sink")
        self.assertAlmostEqual(sink["voltage_v"], 11.34, places=10)

    def test_missing_return_does_not_become_current_source_ground(self):
        raw = fixture()
        raw["harness"]["wires"].pop()
        with self.assertRaisesRegex(ValueError, "missing explicit conductive return"):
            run_harness_pi(raw)

    def test_shunt_conductance_includes_dc_leakage(self):
        raw = fixture()
        model = raw["harness"]["wires"][0]["electrical"]
        model.update(conductance_to_reference_s=.01, reference=end("source", "2"))
        result = run_harness_pi(raw)
        self.assertEqual(result["status"], "completed")
        # Return path only carries the 2 A load; leakage flows from feed to
        # ground. KVL: Vf = 12 - .11 * (2 + .01*Vf).
        feed_voltage = (12 - .11 * 2) / (1 + .11 * .01)
        sink = next(c for c in result["connections"] if c["id"] == "sink")
        self.assertAlmostEqual(sink["voltage_v"], feed_voltage - 2 * .22, places=10)

    def test_conflicting_sources_preserve_failure(self):
        raw = fixture()
        duplicate = dict(raw["terminals"][0], id="conflicting", value=13)
        raw["terminals"].append(duplicate)
        result = run_harness_pi(raw)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("wires", result)
        self.assertTrue(result["native_result"]["issues"])

    def test_unknown_pin_and_missing_endpoint_rejected(self):
        raw = fixture()
        raw["terminals"][1]["negative"]["pin"] = "99"
        with self.assertRaisesRegex(ValueError, "unknown connector pin"):
            run_harness_pi(raw)
        raw = fixture()
        del raw["terminals"][1]["negative"]
        with self.assertRaisesRegex(ValueError, "negative"):
            run_harness_pi(raw)

    def test_short_and_invalid_contact_values_rejected(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            raw = fixture()
            raw["contacts"][0]["resistance_ohm"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_harness_pi(raw)
        raw = fixture()
        raw["contacts"][0]["to"] = raw["contacts"][0]["from"]
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            run_harness_pi(raw)

    def test_resource_limits_and_unknown_fields_rejected(self):
        raw = fixture()
        raw["resource_limits"] = {"maximum_nodes": 2}
        with self.assertRaisesRegex(ValueError, "resource limit"):
            run_harness_pi(raw)
        raw = fixture()
        raw["infer_ground"] = True
        with self.assertRaisesRegex(ValueError, "Additional properties"):
            run_harness_pi(raw)

    def test_duplicate_contact_and_source_ids_rejected(self):
        for category in ("contacts", "terminals"):
            raw = fixture()
            raw[category].append(copy.deepcopy(raw[category][0]))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                compile_harness_pi(raw)

    def test_cancellation_discards_output(self):
        with patch("python.spike_core.harness_pi.run_native_mna") as kernel:
            with self.assertRaisesRegex(ValueError, "cancelled"):
                run_harness_pi(fixture(), cancel_check=lambda: True)
            kernel.assert_not_called()
        calls = iter([False, False, True])
        with self.assertRaisesRegex(ValueError, "discarded"):
            run_harness_pi(fixture(), cancel_check=lambda: next(calls))


if __name__ == "__main__":
    unittest.main()
