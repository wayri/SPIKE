# SPDX-License-Identifier: Apache-2.0
"""Strict contracts and actual public source/load coupled-line workflows."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from examples.rlgc_reactive_pair.run_pair import request
from python.spike_core.service import handle
from tests.python.test_rlgc_reactive_pair import physical_oracle, value

ROOT = Path(__file__).resolve().parents[2]


def validators():
    registry = Registry().with_resources((raw["$id"], Resource.from_contents(raw))
        for path in (ROOT/"schemas").glob("*.schema.json")
        if "$id" in (raw := json.loads(path.read_text(encoding="utf-8"))))
    return [Draft202012Validator(json.loads((ROOT/"schemas"/f"rlgc-reactive-pair-{kind}-v1.schema.json").read_text()), registry=registry)
            for kind in ("request", "result")]


class ReactivePairContractTests(unittest.TestCase):
    def test_actual_worker_physics_schema_and_provenance(self):
        incoming, outgoing = validators(); raw = request(); before = deepcopy(raw); incoming.validate(raw)
        response = handle({"method": "run_rlgc_reactive_pair", "params": {"request": raw}})
        self.assertTrue(response["ok"], response); out = response["result"]; outgoing.validate(out)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.assertEqual(out["input_digest"], digest)
        for k, point in enumerate(out["points"]):
            _, voltage, current, source_current = physical_oracle(raw, k)
            np.testing.assert_allclose([value(t["voltage_v"]) for t in point["terminals"]], voltage, atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose([value(t["current_into_line_a"]) for t in point["terminals"]], current, atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose([value(t["source_current_a"]) for t in point["terminals"]], source_current, atol=2e-11, rtol=2e-9)

    def test_saved_example_cli_and_catalog(self):
        _, outgoing = validators(); path = ROOT/"examples/rlgc_reactive_pair/rlc.request.json"
        self.assertEqual(json.loads(path.read_text()), request())
        catalog = json.loads((ROOT/"schemas/manifest.json").read_text())
        for kind in ("request", "result"):
            self.assertEqual(catalog["schemas"][f"spike/rlgc-reactive-pair-{kind}/v1"], f"rlgc-reactive-pair-{kind}-v1.schema.json")
        example = subprocess.run([sys.executable, str(ROOT/"examples/rlgc_reactive_pair/run_pair.py")], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(example.returncode, 0, example.stderr)
        expected = json.loads(example.stdout); outgoing.validate(expected)
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as folder:
            output = Path(folder)/"result.json"
            cli = subprocess.run([sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(output),
                                  "rlgc-reactive-pair", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            actual = json.loads(output.read_text()); outgoing.validate(actual); self.assertEqual(actual, expected)

    def test_strict_schemas_and_coded_worker_rejection(self):
        incoming, outgoing = validators()
        for mutate in (lambda r: r.__setitem__("extra", 0),
                       lambda r: r["terminations"][0].__setitem__("resistance_ohm", 0),
                       lambda r: r["terminations"][0].__setitem__("inductance_h", -1),
                       lambda r: r["terminations"][0].__setitem__("capacitance_f", True),
                       lambda r: r["terminations"][0].__setitem__("port", True),
                       lambda r: r["sources"][0]["voltage_v"].pop()):
            raw = request(); mutate(raw)
            self.assertFalse(incoming.is_valid(raw))
            response = handle({"method": "run_rlgc_reactive_pair", "params": {"request": raw}})
            self.assertFalse(response["ok"]); self.assertIn("REACTIVE_PAIR", json.dumps(response))
        out = handle({"method": "run_rlgc_reactive_pair", "params": {"request": request()}})["result"]
        for mutate in (lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r["points"][0]["terminals"][0].__setitem__("extra", 0),
                       lambda r: r["points"][0]["power_balance"].__setitem__("terminal_resistor_heat_w", -1),
                       lambda r: r["points"][0]["terminals"][0].__setitem__("capacitor_average_energy_j", -1)):
            bad = deepcopy(out); mutate(bad)
            self.assertFalse(outgoing.is_valid(bad))


if __name__ == "__main__":
    unittest.main()
