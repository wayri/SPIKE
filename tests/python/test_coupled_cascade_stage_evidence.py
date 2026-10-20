# SPDX-License-Identifier: Apache-2.0
"""Adversarial promotion checks on the actual source-bound termination stage."""
from copy import deepcopy
import json
import unittest
from scripts.parity_coupled_cascade_gate import ROOT, validate_receipt
from scripts.parity_stage_evidence import validate_done_import_stage


class CoupledCascadeEvidenceTests(unittest.TestCase):
    def test_actual_receipt_and_corruption_controls(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        evidence = next(stage["evidence"] for stage in backlog["stages"] if stage["id"] == "SI02-S10")
        original = json.loads((ROOT/evidence).read_text()); validate_receipt(original, ROOT)
        validate_done_import_stage({"id": "SI02-S10", "evidence": evidence}, ROOT)
        for mutate in (lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r.__setitem__("status", "failed"),
                       lambda r: r["sources_after"].__setitem__("python/spike_core/rlgc_coupled_cascade.py", "0"*64),
                       lambda r: r["sources_before"].pop("python/spike_core/rlgc_coupled_pair.py"),
                       lambda r: r["tests"].__setitem__("skipped", [r["tests"]["names"][0]]),
                       lambda r: r["tests"].__setitem__("run", 0),
                       lambda r: r.__setitem__("log_sha256", "0"*64)):
            bad = deepcopy(original); mutate(bad)
            with self.assertRaises(ValueError): validate_receipt(bad, ROOT)


if __name__ == "__main__":
    unittest.main()
