# SPDX-License-Identifier: Apache-2.0
"""Adversarial fixtures for the SI01-S02 evidence validator."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts import verify_si_candidate_constraints as gate


class CandidateConstraintEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=gate.ROOT / ".tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in gate.SOURCES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic validator source", encoding="utf-8")
        expected = gate.names(gate.suite())
        self.log = self.root / "stage.log"
        lines = [f"{name.rsplit('.', 1)[-1]} (...) ... ok" for name in expected]
        self.log.write_text("\n".join(lines) + f"\nRan {len(expected)} tests in 0.001s\n\nOK\n",
                            encoding="utf-8")
        snapshot = {name: gate.digest(self.root / name) for name in gate.SOURCES}
        self.receipt = {"contract": "spike/si-candidate-constraint-evidence/v1",
            "stage_id": "SI01-S02", "status": "passed", "stage_complete": True,
            "workflow": "offline_reviewed_export", "sources_before": snapshot,
            "sources_after": deepcopy(snapshot),
            "tests": {"names": expected, "run": gate.EXPECTED_TEST_COUNT,
                      "failures": [], "errors": [], "skipped": [],
                      "expected_failures": [], "unexpected_successes": []},
            "log": {"path": self.log.name, "sha256": gate.digest(self.log)},
            **{flag: False for flag in gate.FLAGS}}

    def test_identity_scope_and_execution_tampering_rejected(self):
        gate.validate_receipt(self.receipt, self.root)
        changes = [lambda value: value.update(stage_complete=False),
                   lambda value: value.update(family_complete=True),
                   lambda value: value.update(workflow="other"),
                   lambda value: value["tests"].update(run=5),
                   lambda value: value["tests"]["names"].pop(),
                   lambda value: value["tests"].update(skipped=["omitted"]),
                   lambda value: value["tests"].update(expected_failures=["expected"]),
                   lambda value: value["tests"].update(unexpected_successes=["unexpected"])]
        for change in changes:
            receipt = deepcopy(self.receipt)
            change(receipt)
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.validate_receipt(receipt, self.root)

    def test_source_coverage_hash_and_drift_tampering_rejected(self):
        changes = [lambda value: value["sources_before"].pop(gate.SOURCES[0]),
                   lambda value: value["sources_after"].update({gate.SOURCES[0]: "0" * 64})]
        for change in changes:
            receipt = deepcopy(self.receipt)
            change(receipt)
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.validate_receipt(receipt, self.root)
        (self.root / gate.SOURCES[0]).write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            gate.validate_receipt(self.receipt, self.root)

    def test_log_path_hash_and_content_tampering_rejected(self):
        for change in (lambda value: value["log"].update(path="../outside.log"),
                       lambda value: value["log"].update(sha256="0" * 64)):
            receipt = deepcopy(self.receipt)
            change(receipt)
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.validate_receipt(receipt, self.root)
        self.log.write_text("Ran 6 tests in 0.001s\nFAILED\n", encoding="utf-8")
        self.receipt["log"]["sha256"] = gate.digest(self.log)
        with self.assertRaises(ValueError):
            gate.validate_receipt(self.receipt, self.root)


if __name__ == "__main__":
    unittest.main()
