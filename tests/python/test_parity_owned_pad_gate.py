# SPDX-License-Identifier: Apache-2.0
"""Reject stale, incomplete and foreign owned-pad evidence contracts."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import parity_owned_pad_gate as gate


class OwnedPadReceiptTests(unittest.TestCase):
    def test_valid_contract_and_tamper_rejection(self):
        # This manufactured contract tests the validator, not numerical physics.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source.py").write_text("original", encoding="utf-8")
            (root / "run.log").write_text("Ran 1 tests in 0.1s\n\nOK\n", encoding="utf-8")
            sources = {"source.py": gate.digest(root / "source.py")}
            example = unittest.FunctionTestCase(lambda: None)
            tests = unittest.TestSuite([example])
            receipt = {"contract": "spike/owned-pad-stage-evidence/v1",
                "stage_id": gate.STAGE, "status": "passed", "production_qualified": False,
                "sources_before": sources, "sources_after": dict(sources),
                "tests": {"names": gate.names(tests), "run": 1, "failures": [],
                    "errors": [], "skipped": [], "expected_failures": [], "unexpected_successes": []},
                "log": "run.log", "log_sha256": gate.digest(root / "run.log")}
            with patch.object(gate, "SOURCES", ("source.py",)), patch.object(gate, "suite", return_value=tests), patch.object(gate, "validate_board"):
                gate.validate_receipt(receipt, root)
                for key, value in (("stage_id", "PI99-S99"), ("status", "failed"),
                                   ("production_qualified", True), ("log", "../foreign.log")):
                    invalid = copy.deepcopy(receipt)
                    invalid[key] = value
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        gate.validate_receipt(invalid, root)
                for key, value in (("run", 0), ("names", []), ("skipped", ["example"]),
                                   ("errors", ["example"]), ("expected_failures", ["example"])):
                    invalid = copy.deepcopy(receipt)
                    invalid["tests"][key] = value
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        gate.validate_receipt(invalid, root)
                (root / "source.py").write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "stale or foreign"):
                    gate.validate_receipt(receipt, root)

    def test_missing_board_evidence_rejected(self):
        for value in (None, {}, {"report.json": {"path": "foreign", "sha256": "missing"}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.validate_board(value)


if __name__ == "__main__":
    unittest.main()
