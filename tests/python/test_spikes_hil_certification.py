import unittest

from python.spikes.hil_certification import (
    HIL_GATE_CONTRACT,
    HilRequirements,
    evaluate_physical_hil_evidence,
)


class PhysicalHilGateTests(unittest.TestCase):
    def test_empty_or_simulated_evidence_is_blocked_with_named_checks(self):
        result = evaluate_physical_hil_evidence(
            {"execution_mode": "simulated", "synthetic": True},
            HilRequirements(100_000, 80_000, 10_000),
            evidence_root=".",
        )
        self.assertEqual(result["contract"], HIL_GATE_CONTRACT)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["certification_eligible"])
        blocked = {item["check"] for item in result["checks"] if item["status"] == "blocked"}
        self.assertTrue({"physical_execution", "raw_trace", "hard_realtime_timing", "fault_injection", "independent_attestation"} <= blocked)

    def test_requirements_reject_nonphysical_bounds(self):
        with self.assertRaises(ValueError):
            HilRequirements(0, 1, 1)
        with self.assertRaises(ValueError):
            HilRequirements(1, 1, 1, required_fault_tests=("watchdog_timeout", "watchdog_timeout"))


if __name__ == "__main__":
    unittest.main()
