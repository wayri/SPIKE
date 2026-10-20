# SPDX-License-Identifier: Apache-2.0
"""Actual worker/CLI, strict schemas and retained physical cascade provenance."""
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
from examples.rlgc_coupled_cascade.run_cascade import request
from python.spike_core.service import handle
from tests.python.test_rlgc_coupled_cascade import physical_oracle, value

ROOT = Path(__file__).resolve().parents[2]


def validators():
    registry = Registry().with_resources((raw["$id"], Resource.from_contents(raw))
        for path in (ROOT/"schemas").glob("*.schema.json")
        if "$id" in (raw := json.loads(path.read_text(encoding="utf-8"))))
    return [Draft202012Validator(json.loads((ROOT/"schemas"/f"rlgc-coupled-cascade-{kind}-v1.schema.json").read_text()), registry=registry)
            for kind in ("request", "result")]


class CoupledCascadeContractTests(unittest.TestCase):
    def test_actual_worker_physical_chain_and_provenance(self):
        incoming, outgoing = validators(); raw = request(); before = deepcopy(raw); incoming.validate(raw)
        response = handle({"method": "run_rlgc_coupled_cascade", "params": {"request": raw}})
        self.assertTrue(response["ok"], response); out = response["result"]; outgoing.validate(out)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.assertEqual(out["input_digest"], digest)
        for k, point in enumerate(out["points"]):
            reflected = physical_oracle(raw, k)[0]
            incident = np.array([value(v) for v in raw["excitations"][k]["incident_waves"]])
            z = out["network"]["reference_impedance_ohm"]
            np.testing.assert_allclose([value(t["voltage_v"]) for t in point["boundary_values"]], np.sqrt(z)*(incident+reflected), atol=2e-11, rtol=2e-9)
            np.testing.assert_allclose([value(t["current_into_line_a"]) for t in point["boundary_values"]], (incident-reflected)/np.sqrt(z), atol=2e-11, rtol=2e-9)

    def test_saved_example_cli_and_catalog(self):
        _, outgoing = validators(); path = ROOT/"examples/rlgc_coupled_cascade/piecewise.request.json"
        self.assertEqual(json.loads(path.read_text()), request())
        catalog = json.loads((ROOT/"schemas/manifest.json").read_text())
        for kind in ("request", "result"):
            self.assertEqual(catalog["schemas"][f"spike/rlgc-coupled-cascade-{kind}/v1"], f"rlgc-coupled-cascade-{kind}-v1.schema.json")
        example = subprocess.run([sys.executable, str(ROOT/"examples/rlgc_coupled_cascade/run_cascade.py")], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(example.returncode, 0, example.stderr)
        expected = json.loads(example.stdout); outgoing.validate(expected)
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as folder:
            output = Path(folder)/"result.json"
            cli = subprocess.run([sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(output),
                                  "rlgc-coupled-cascade", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            actual = json.loads(output.read_text()); outgoing.validate(actual); self.assertEqual(actual, expected)

    def test_strict_contracts_and_coded_worker_rejections(self):
        incoming, outgoing = validators()
        for mutate in (lambda r: r.__setitem__("extra", 0), lambda r: r.__setitem__("sections", []),
                       lambda r: r["sections"][0]["pair"]["modes"]["odd"].__setitem__("length_m", -1),
                       lambda r: r["excitations"][0]["incident_waves"].pop()):
            raw = request(); mutate(raw); self.assertFalse(incoming.is_valid(raw))
            response = handle({"method": "run_rlgc_coupled_cascade", "params": {"request": raw}})
            self.assertFalse(response["ok"]); self.assertIn("COUPLED_CASCADE", json.dumps(response))
        response = handle({"method": "run_rlgc_coupled_cascade", "params": {"request": request(), "extra": 0}})
        self.assertFalse(response["ok"])
        out = handle({"method": "run_rlgc_coupled_cascade", "params": {"request": request()}})["result"]
        for mutate in (lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r["points"][0]["junctions"][0].__setitem__("extra", 0),
                       lambda r: r["points"][0]["power_balance"].__setitem__("conductor_loss_w", -1),
                       lambda r: r["sections"][0]["result"].__setitem__("production_qualified", True)):
            bad = deepcopy(out); mutate(bad); self.assertFalse(outgoing.is_valid(bad))


if __name__ == "__main__":
    unittest.main()
