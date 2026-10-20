# SPDX-License-Identifier: Apache-2.0
"""Stage promotion must bind executed tests, source tree and raw ladder."""
from copy import deepcopy
import json
import unittest
from scripts.parity_finite_contact_gate import ROOT, validate_receipt
from scripts.parity_stage_evidence import validate_done_import_stage


class FiniteContactEvidenceTests(unittest.TestCase):
    def test_actual_receipt_and_corruption_controls(self):
        backlog = json.loads((ROOT/"docs/parity-capability-backlog-v1.json").read_text())
        evidence = next(s["evidence"] for s in backlog["stages"] if s["id"] == "PI01-S02A")
        original = json.loads((ROOT/evidence).read_text())
        validate_receipt(original, ROOT)
        validate_done_import_stage({"id": "PI01-S02A", "evidence": evidence}, ROOT)
        for mutate in (lambda r: r.__setitem__("production_qualified", True),
                       lambda r: r.__setitem__("status", "failed"),
                       lambda r: r["sources_after"].__setitem__("python/spike_core/dc_rt0_density.py", "0"*64),
                       lambda r: r["sources_before"].pop("python/spike_core/peec_conforming_dc.py"),
                       lambda r: r["tests"].__setitem__("skipped", [r["tests"]["names"][0]]),
                       lambda r: r["tests"].__setitem__("run", 0),
                       lambda r: r.__setitem__("log_sha256", "0"*64),
                       lambda r: r.__setitem__("report_sha256", "0"*64)):
            bad = deepcopy(original); mutate(bad)
            with self.assertRaises(ValueError):
                validate_receipt(bad, ROOT)


if __name__ == "__main__":
    unittest.main()
