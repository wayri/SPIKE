# SPDX-License-Identifier: Apache-2.0
"""Strict wire contracts and actual public worker/CLI integration checks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from python.spike_core import si_candidate_study as study
from tests.python.test_si_candidate_study import request
from python.spike_core.service import handle

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "schemas"


def validators():
    resources = []
    for folder in (ROOT/"schemas", HERE):
        for path in folder.glob("*.schema.json"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if "$id" in raw:
                resources.append((raw["$id"], Resource.from_contents(raw)))
    registry = Registry().with_resources(resources)
    return [Draft202012Validator(json.loads((HERE/f"si-candidate-study-{kind}-v1.schema.json").read_text()), registry=registry)
            for kind in ("request", "result")]


class CandidateContractTests(unittest.TestCase):
    def test_actual_results_validate_strict_contracts_and_digests(self):
        incoming, outgoing = validators()
        raw = request(); incoming.validate(raw)
        response = handle({"method": "run_si_candidate_study", "params": {"request": raw}})
        self.assertTrue(response["ok"], response)
        result = response["result"]; outgoing.validate(result)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result["input_digest"], digest)
        for source, child in zip(raw["cases"], result["cases"]):
            expected = hashlib.sha256(json.dumps(source["request"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            self.assertEqual(child["request_digest"], expected)
            expanded = child["result"]["request"]
            digest = hashlib.sha256(json.dumps(expanded, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            self.assertEqual(child["result"]["request_sha256"], digest)

    def test_actual_cli_example_and_catalog(self):
        _, outgoing = validators()
        catalog = json.loads((HERE/"manifest.json").read_text())
        for kind in ("request", "result"):
            self.assertEqual(catalog["schemas"][f"spike/si-candidate-study-{kind}/v1"], f"si-candidate-study-{kind}-v1.schema.json")
        example = subprocess.run([sys.executable, str(ROOT/"examples/si_candidate_study/run_study.py")],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(example.returncode, 0, example.stderr)
        expected = json.loads(example.stdout); outgoing.validate(expected)
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as folder:
            output = Path(folder)/"result.json"
            run = subprocess.run([sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(output),
                                  "si-candidate-study", str(ROOT/"examples/si_candidate_study/candidates.request.json")],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            actual = json.loads(output.read_text()); outgoing.validate(actual)
            self.assertEqual(actual, expected)

    def test_registered_worker_rejects_bad_population(self):
        raw = request(); raw["cases"].pop()
        response = handle({"method": "run_si_candidate_study", "params": {"request": raw}})
        self.assertFalse(response["ok"])
        self.assertIn("SI_CANDIDATE_STUDY", json.dumps(response))

    def test_schema_rejects_scope_unknowns_and_bad_status(self):
        incoming, outgoing = validators()
        for mutation in (lambda r: r.__setitem__("extra", 0),
                         lambda r: r["cases"][0]["request"].__setitem__("run_time_domain", True),
                         lambda r: r["cases"][0]["request"]["channel"].__setitem__("coupled", True),
                         lambda r: r["limits"][0].__setitem__("bound", True)):
            raw = request(); mutation(raw)
            self.assertFalse(incoming.is_valid(raw))
        result = study.run_si_candidate_study(request())
        for mutation in (lambda r: r.__setitem__("production_qualified", True),
                         lambda r: r["candidates"][0]["limits"][0]["worst"].__setitem__("extra", 0),
                         lambda r: r["cases"][0].__setitem__("status", "passed")):
            changed = deepcopy(result); mutation(changed)
            self.assertFalse(outgoing.is_valid(changed))

    def test_actual_temperature_conflict_retained_with_valid_wire_result(self):
        incoming, outgoing = validators()
        raw = request()
        child = raw["cases"][1]["request"]
        child["temperature_c"] = 85
        child["passives"] = [{"id": "Rterm", "port": 1, "connection": "shunt",
                              "model": {"kind": "resistor", "resistance_ohm": 1000, "temperature_c": 25}}]
        incoming.validate(raw)
        result = study.run_si_candidate_study(raw); outgoing.validate(result)
        self.assertEqual(result["assessment_status"], "incomplete")
        self.assertEqual(result["cases"][1]["status"], "failed")
        self.assertIn("temperature", result["cases"][1]["issue"]["message"].lower())
        self.assertEqual(result["feasible_candidate_ids"], ["long"])


if __name__ == "__main__":
    unittest.main()
