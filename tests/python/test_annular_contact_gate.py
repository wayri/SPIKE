# SPDX-License-Identifier: Apache-2.0
"""Supplementary source-bound acceptance cannot become whole-stage completion."""
from copy import deepcopy
import json
import unittest
from scripts.parity_annular_contact_gate import ROOT, validate_receipt


class AnnularContactGateTests(unittest.TestCase):
    def test_receipt_and_rejected_completion_or_detached_execution(self):
        receipt = json.loads((ROOT/"docs/validation/parity/PI01-S02-annular-contact-20261021.json").read_text())
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
