import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from python.spikes.competitive_gate import validate_competitive_gate
from python.spikes.parity_report import generate_parity_report


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "artifacts" / "spikes-competitive-benchmark-2026-08-30.json"
QUALIFICATION = ROOT / "artifacts" / "spikes-qualification-report-2026-08-30.json"


class ParityReportTests(unittest.TestCase):
    @unittest.skipUnless(BENCHMARK.is_file() and QUALIFICATION.is_file(), "evidence unavailable")
    def test_real_evidence_fails_closed_with_all_ten_gates_evaluated(self):
        report = generate_parity_report(BENCHMARK, QUALIFICATION)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["claim_eligible"])
        self.assertEqual(report["summary"], {
            "required_gates": 10, "passed_gates": 0, "blocked_gates": 10,
        })
        gate = validate_competitive_gate(report["competitive_gate"])
        self.assertEqual(len(gate["gates"]), 10)
        compatibility = gate["gates"][0]
        self.assertTrue(compatibility["checks"][0]["passed"])
        self.assertIn("corpus.spice3_language", compatibility["blocking_checks"])

    def test_contract_mismatch_is_rejected(self):
        with TemporaryDirectory() as directory:
            wrong = Path(directory) / "wrong.json"
            wrong.write_text(json.dumps({"contract": "wrong/v1"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                generate_parity_report(wrong, QUALIFICATION)


if __name__ == "__main__":
    unittest.main()
