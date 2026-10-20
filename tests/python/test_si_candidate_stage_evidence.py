# SPDX-License-Identifier: Apache-2.0
"""Adversarial checks for bounded stage promotion, using executed evidence."""
from copy import deepcopy
import json
import unittest

from scripts.parity_si_candidate_gate import ROOT, validate_receipt
from scripts.parity_stage_evidence import validate_done_import_stage


class CandidateStageEvidenceTests(unittest.TestCase):
    def test_source_bound_receipt_and_dispatch_reject_tampering(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        evidence = next(stage["evidence"] for stage in backlog["stages"] if stage["id"] == "SI01-S01")
        original = json.loads((ROOT/evidence).read_text())
        validate_receipt(original, ROOT)
        validate_done_import_stage({"id": "SI01-S01", "evidence": evidence}, ROOT)
        for mutation in (lambda r: r.__setitem__("production_qualified", True),
                         lambda r: r.__setitem__("status", "failed"),
                         lambda r: r["tests"].__setitem__("skipped", [r["tests"]["names"][0]]),
                         lambda r: r["sources"].__setitem__("python/spike_core/si_candidate_study.py", "0"*64),
                         lambda r: r["sources"].pop("python/spike_core/si_workflow.py"),
                         lambda r: r["tests"].__setitem__("run", 0),
                         lambda r: r.__setitem__("log_sha256", "0"*64)):
            receipt = deepcopy(original); mutation(receipt)
            with self.assertRaises(ValueError): validate_receipt(receipt, ROOT)


if __name__ == "__main__":
    unittest.main()
