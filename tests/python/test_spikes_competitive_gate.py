import copy
from pathlib import Path
import unittest

from python.spikes.competitive_gate import (
    REQUIRED_GATES,
    load_competitive_gate,
    validate_competitive_gate,
)


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "docs" / "validation" / "spikes-ngspice-competitive-gate.json"


class CompetitiveGateTests(unittest.TestCase):
    def test_checked_in_gate_is_complete_and_blocks_a_claim(self):
        gate = load_competitive_gate(GATE)
        self.assertEqual(len(gate["gates"]), len(REQUIRED_GATES))
        self.assertEqual(gate["status"], "blocked")
        self.assertFalse(gate["claim_eligible"])

    def test_premature_claim_or_unevidenced_pass_fails_closed(self):
        gate = load_competitive_gate(GATE)
        premature = copy.deepcopy(gate)
        premature["claim_eligible"] = True
        with self.assertRaises(ValueError):
            validate_competitive_gate(premature)

        unevidenced = copy.deepcopy(gate)
        unevidenced["gates"][0]["status"] = "passed"
        unevidenced["summary"] = {
            "required_gates": len(REQUIRED_GATES),
            "passed_gates": 1,
            "blocked_gates": len(REQUIRED_GATES) - 1,
        }
        with self.assertRaises(ValueError):
            validate_competitive_gate(unevidenced)


if __name__ == "__main__":
    unittest.main()
