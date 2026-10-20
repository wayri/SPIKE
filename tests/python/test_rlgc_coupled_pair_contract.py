# SPDX-License-Identifier: Apache-2.0
"""Actual worker/CLI, strict schemas and coupled-physics wire contracts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from examples.rlgc_coupled_pair.run_pair import request
from python.spike_core.service import handle
from tests.python.test_rlgc_coupled_pair import physical_oracle, matrix

ROOT = Path(__file__).resolve().parents[2]


def validators():
    registry = Registry().with_resources((raw["$id"], Resource.from_contents(raw))
        for path in (ROOT/"schemas").glob("*.schema.json")
        if "$id" in (raw := json.loads(path.read_text(encoding="utf-8"))))
    return [Draft202012Validator(json.loads((ROOT/"schemas"/f"rlgc-coupled-pair-{kind}-v1.schema.json").read_text()), registry=registry)
            for kind in ("request", "result")]


class CoupledPairContractTests(unittest.TestCase):
    def test_actual_worker_direct_physical_oracle_and_schemas(self):
        incoming, outgoing = validators(); raw = request(); before = deepcopy(raw); incoming.validate(raw)
        response = handle({"method": "run_rlgc_coupled_pair", "params": {"request": raw}})
        self.assertTrue(response["ok"], response)
        out = response["result"]; outgoing.validate(out)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for k, record in enumerate(out["network"]["s_parameters"]):
            expected, _, _ = physical_oracle(raw, k)
            np.testing.assert_allclose(matrix(record), expected, atol=2e-11, rtol=2e-9)

    def test_example_cli_catalog_and_preserved_models(self):
        _, outgoing = validators()
        catalog = json.loads((ROOT/"schemas/manifest.json").read_text())
        for kind in ("request", "result"):
            self.assertEqual(catalog["schemas"][f"spike/rlgc-coupled-pair-{kind}/v1"], f"rlgc-coupled-pair-{kind}-v1.schema.json")
        path = ROOT/"examples/rlgc_coupled_pair/symmetric-pair.request.json"
        self.assertEqual(json.loads(path.read_text()), request())
        run = subprocess.run([sys.executable, str(ROOT/"examples/rlgc_coupled_pair/run_pair.py")],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        expected = json.loads(run.stdout); outgoing.validate(expected)
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as folder:
            output = Path(folder)/"result.json"
            cli = subprocess.run([sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(output),
                                  "rlgc-coupled-pair", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            actual = json.loads(output.read_text()); outgoing.validate(actual)
            self.assertEqual(actual, expected)
            for mode in ("even", "odd"):
                self.assertEqual(actual["modes"][mode]["source_request"]["line_request"], request()["modes"][mode])

    def test_strict_wire_rejections_and_worker_failure(self):
        incoming, outgoing = validators()
        for mutate in (lambda r: r.__setitem__("extra", 0),
                       lambda r: r["excitations"][0]["incident_waves"][0].__setitem__("real", True),
                       lambda r: r["modes"]["odd"].__setitem__("length_m", False),
                       lambda r: r["excitations"][0]["incident_waves"].pop()):
            raw = request(); mutate(raw)
            self.assertFalse(incoming.is_valid(raw))
            response = handle({"method": "run_rlgc_coupled_pair", "params": {"request": raw}})
            self.assertFalse(response["ok"]); self.assertIn("COUPLED_PAIR", json.dumps(response))
        good = handle({"method": "run_rlgc_coupled_pair", "params": {"request": request()}})["result"]
        for mutate in (lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r["points"][0]["probe_values"][0]["pair"].__setitem__("extra", 0),
                       lambda r: r["network"]["s_parameters"][0].pop()):
            bad = deepcopy(good); mutate(bad)
            self.assertFalse(outgoing.is_valid(bad))


if __name__ == "__main__":
    unittest.main()
