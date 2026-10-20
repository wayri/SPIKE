# SPDX-License-Identifier: Apache-2.0
"""Supplementary source-bound acceptance cannot become whole-stage completion."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.parity_annular_contact_gate import ROOT, validate_receipt


class AnnularContactGateTests(unittest.TestCase):
    def test_receipt_and_rejected_completion_or_detached_execution(self):
        # Native source bindings include absolute paths. Execute the unchanged
        # acceptance runner in this checkout; historical receipts keep their
        # original execution identity instead of being rewritten after a move.
        temporary_root = ROOT / ".local" / "test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="annular-gate-", dir=temporary_root)
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        output, log, report = (directory / name for name in ("receipt.json", "tests.log", "report.json"))
        execution = subprocess.run(
            [sys.executable, str(ROOT / "scripts/parity_annular_contact_gate.py"),
             "--output", str(output), "--log", str(log), "--report", str(report)],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        details = execution.stdout + execution.stderr
        if log.exists():
            details += log.read_text(encoding="utf-8")
        self.assertEqual(execution.returncode, 0, details)
        receipt = json.loads(output.read_text(encoding="utf-8"))
        validate_receipt(receipt)
        for mutate in (lambda r: r.__setitem__("stage_complete", True),
                       lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r.__setitem__("status", "failed"),
                       lambda r: r.__setitem__("report_sha256", "0"*64),
                       lambda r: r.__setitem__("previous_sha256", "0"*64),
                       lambda r: r["sources_before"].pop("python/spike_core/dc_annular_stack.py"),
                       lambda r: r["tests"].__setitem__("run", 0),
                       lambda r: r["tests"]["skipped"].append("omitted")):
            changed = deepcopy(receipt); mutate(changed)
            with self.assertRaises(ValueError): validate_receipt(changed)

    def test_backlog_keeps_full_stage_open_and_names_supplement(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        stage = next(s for s in backlog["stages"] if s["id"] == "PI01-S02")
        self.assertEqual(stage["status"], "in_progress")
        supplement = stage["supplementary_evidence"][0]
        self.assertEqual(supplement["evidence"], "docs/validation/parity/PI01-S02-annular-contact-20261021.json")
        self.assertFalse(supplement["stage_complete"])
        self.assertEqual(supplement["status"], "verified_bounded_increment")


if __name__ == "__main__": unittest.main()
