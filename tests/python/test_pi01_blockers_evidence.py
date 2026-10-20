# SPDX-License-Identifier: Apache-2.0
"""Partial evidence must not silently become whole-stage completion."""
from copy import deepcopy
import json
import unittest
from scripts.parity_pi01_blockers_gate import ROOT, validate_receipt, validate_land_report


class PI01BlockerEvidenceTests(unittest.TestCase):
    def test_current_partial_evidence_and_corruption_controls(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        stage = next(s for s in backlog["stages"] if s["id"] == "PI01-S02")
        self.assertEqual(stage["status"], "in_progress")
        receipt = json.loads((ROOT/stage["evidence"]).read_text())
        validate_receipt(receipt)
        for mutate in (lambda r: r.__setitem__("stage_complete", True),
                       lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r.__setitem__("status", "failed"),
                       lambda r: r.__setitem__("report_sha256", "0"*64),
                       lambda r: r.__setitem__("finite_sha256", "0"*64),
                       lambda r: r["sources_before"].pop("python/spike_core/dc_axial_ownership.py"),
                       lambda r: r["tests"].__setitem__("run", 0)):
            changed = deepcopy(receipt); mutate(changed)
            with self.assertRaises(ValueError):
                validate_receipt(changed)

    def test_land_subreports_require_actual_ordered_fields_and_inputs(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        stage = next(s for s in backlog["stages"] if s["id"] == "PI01-S02")
        receipt = json.loads((ROOT/stage["evidence"]).read_text())
        raw = json.loads((ROOT/receipt["report"]).read_text())
        validate_land_report(raw)
        for mutate in (lambda r: r["land_refinement"].reverse(),
                       lambda r: r["land_refinement"].pop(),
                       lambda r: r["land_transition"]["cells"][0].__setitem__("joule_heat_w", 1.),
                       lambda r: r["land_transition"]["contacts"][0].__setitem__("attachment_id", "other")):
            changed = deepcopy(raw); mutate(changed)
            with self.assertRaises(ValueError):
                validate_land_report(changed)


if __name__ == "__main__":
    unittest.main()
