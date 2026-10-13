# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest
from unittest.mock import patch

from python.spike_core.cosimulation import run_cosimulation, default_adapters
from python.spike_core.service_cosimulation import handle_cosimulation_request


def request():
    return {"contract": "spike/cosimulation-request/v1", "model_id": "fixture",
            "model_revision": "r1", "step_s": 0.1, "steps": 3,
            "participants": [
                {"id": "source", "adapter": "replay", "model_revision": "1", "model_status": "experimental",
                 "inputs": {}, "outputs": {"v": "V"}, "initial_outputs": {"v": 1},
                 "config": {"values": [{"v": 2}, {"v": 3}, {"v": 4}]}},
                {"id": "load", "adapter": "gain", "model_revision": "1", "model_status": "approximate",
                 "inputs": {"u": "V"}, "outputs": {"y": "V"}, "initial_outputs": {"y": 0},
                 "config": {"gain": 2}}],
            "connections": [{"source": ["source", "v"], "target": ["load", "u"]}]}


class CosimulationTests(unittest.TestCase):
    def test_explicit_lag_nonconstant_sequence_and_order(self):
        data = request()
        original = deepcopy(data)
        result = run_cosimulation(data)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([f["outputs"]["load"]["y"] for f in result["frames"]], [0, 2, 4, 6])
        self.assertAlmostEqual(result["frames"][-1]["time_s"], 0.3)
        self.assertEqual(data, original)
        data["participants"].reverse()
        self.assertEqual(result["frames"], run_cosimulation(data)["frames"])
        self.assertEqual(result["model_status"], "experimental")
        self.assertEqual(result["participant_provenance"][0]["model_status"], "approximate")

    def test_simultaneous_feedback(self):
        data = request()
        first = deepcopy(data["participants"][1])
        first.update(id="a", initial_outputs={"y": 1}, config={"gain": 1})
        second = deepcopy(first)
        second.update(id="b", initial_outputs={"y": 2})
        data.update(participants=[first, second], connections=[
            {"source": ["a", "y"], "target": ["b", "u"]},
            {"source": ["b", "y"], "target": ["a", "u"]}])
        result = run_cosimulation(data)
        self.assertEqual([f["outputs"]["a"]["y"] for f in result["frames"]], [1, 2, 1, 2])
        self.assertEqual([f["outputs"]["b"]["y"] for f in result["frames"]], [2, 1, 2, 1])

    def test_reject_bad_admission(self):
        variants = []
        for key, value in [("step_s", 0), ("step_s", True), ("step_s", float("nan")),
                           ("steps", 10001), ("steps", 1.5), ("model_revision", "")]:
            data = request(); data[key] = value; variants.append(data)
        data = request(); data["participants"][1]["inputs"]["u"] = "A"; variants.append(data)
        data = request(); data["connections"] *= 2; variants.append(data)
        data = request(); data["connections"] = []; variants.append(data)
        data = request(); data["participants"][0]["adapter"] = "arbitrary_script"; variants.append(data)
        data = request(); data["participants"][0]["model_status"] = "unsupported"; variants.append(data)
        data = request(); data["connections"][0]["source"][1] = "missing"; variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                result = run_cosimulation(data)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["frames"], [])

    def test_failure_does_not_commit_tick(self):
        class Broken:
            version = "test"
            def validate(self, participant, steps): pass
            def step(self, participant, inputs, state, tick, time_s, step_s):
                if tick == 2: raise RuntimeError("fixture failure")
                return {"y": 5}, {"tick": tick}
        adapters = default_adapters(); adapters["gain"] = Broken()
        result = run_cosimulation(request(), adapters=adapters)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_steps"], 1)
        self.assertEqual(len(result["frames"]), 2)
        self.assertIn("fixture failure", result["issues"][0]["message"])

    def test_cancellation_and_timeout_before_commit(self):
        result = run_cosimulation(request(), cancelled=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["completed_steps"], 0)
        with patch("python.spike_core.cosimulation.time.monotonic", side_effect=[0, 61]):
            result = run_cosimulation(request(), timeout_s=60)
        self.assertEqual(result["status"], "timed_out")
        self.assertEqual(result["completed_steps"], 0)

    def test_adapter_nonfinite_output(self):
        data = request(); data["participants"][0]["initial_outputs"]["v"] = 1e308
        data["participants"][1]["config"]["gain"] = 1e308
        result = run_cosimulation(data)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_steps"], 0)

    def test_adapter_cannot_mutate_configuration(self):
        class Mutating:
            version = "test"
            def validate(self, participant, steps): pass
            def step(self, participant, inputs, state, tick, time_s, step_s):
                participant["config"]["gain"] = 3
                return {"y": 0}, None
        adapters = default_adapters(); adapters["gain"] = Mutating()
        data = request()
        result = run_cosimulation(data, adapters=adapters)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_steps"], 0)
        self.assertEqual(data["participants"][1]["config"]["gain"], 2)

    def test_worker_and_cli(self):
        from python.spike_core.service import handle
        from python.spike_core.cli import build_parser, dispatch
        self.assertEqual(handle({"method": "run_cosimulation", "params": {"request": request()}})["result"]["status"], "completed")
        self.assertFalse(handle_cosimulation_request("run_cosimulation", {"request": request(), "code": "x"})["ok"])
        result, code = dispatch(build_parser().parse_args(["cosimulation-catalog"]))
        self.assertEqual(code, 0)
        self.assertIn("FMI", result["unsupported"])

    def test_schemas_demo_and_cli_exit_codes(self):
        import json
        import math
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from jsonschema import Draft202012Validator
        from python.spike_core.cli import build_parser, dispatch
        from examples.cosimulation.run_demo import run_demo
        root = Path(__file__).resolve().parents[2]
        validators = {}
        for kind in ("request", "result"):
            schema = json.loads((root / f"schemas/cosimulation-{kind}-v1.schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            validators[kind] = Draft202012Validator(schema)
        validators["request"].validate(request())
        validators["result"].validate(run_cosimulation(request()))
        validators["result"].validate(run_cosimulation({}))
        validators["result"].validate(run_cosimulation(request(), cancelled=lambda: True))
        demo = run_demo()
        self.assertAlmostEqual(demo["digital_twin"]["channels"][0]["rmse"], math.sqrt(0.025))
        self.assertEqual(demo["digital_twin"]["threshold_violation_count"], 1)
        parser = build_parser()
        for command, filename in [("cosimulation-run", "coupled-replay.json"),
                                  ("digital-twin-compare", "recorded-twin.json")]:
            result, code = dispatch(parser.parse_args([command, str(root / "examples/cosimulation" / filename)]))
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "completed")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}")
            result, code = dispatch(parser.parse_args(["cosimulation-run", str(path)]))
            self.assertNotEqual(code, 0)
            self.assertEqual(result["status"], "rejected")

    def test_cancellation_after_staging_and_byte_admission(self):
        # Callback checkpoints: before first, before second, before commit.
        with patch("python.spike_core.cosimulation.time.monotonic", return_value=0):
            checks = iter([False, False, True])
            result = run_cosimulation(request(), cancelled=lambda: next(checks))
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["completed_steps"], 0)
        self.assertEqual(len(result["frames"]), 1)
        data = request()
        data["steps"] = 10000
        data["participants"][0]["config"]["values"] = [{"v": 2}] * 10000
        data["participants"][0]["id"] = "s" * 256
        data["participants"][1]["id"] = "l" * 256
        data["connections"][0] = {"source": ["s" * 256, "v"], "target": ["l" * 256, "u"]}
        # Add long port IDs while retaining legal output-value count.
        name = "p" * 256
        data["participants"][0]["outputs"][name] = "V"
        data["participants"][0]["initial_outputs"][name] = 0
        data["participants"][0]["config"]["values"] = [{"v": 2, name: 0}] * 10000
        result = run_cosimulation(data)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("byte budget", result["issues"][0]["message"])


if __name__ == "__main__":
    unittest.main()
