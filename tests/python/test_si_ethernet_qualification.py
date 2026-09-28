# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import json
import unittest

from python.spike_core.si_ethernet_qualification import (
    SUPPORTED_MODES,
    assess_10gbe_evidence,
)


class EthernetQualificationBoundaryTests(unittest.TestCase):
    def test_existing_reference_is_only_kr_exploratory_numerical_evidence(self):
        result = assess_10gbe_evidence(
            "10GBASE-KR",
            ["linear_nrz_10_3125_gbd_reference"],
            reference_rate_hz=10_312_500_000.0,
        )
        self.assertEqual(result["exploratory_scope"], "kr_linear_nrz_numerical_foundation")
        self.assertIn("differential_channel_fixture", result["missing_evidence"])
        self.assertFalse(result["pcb_channel_extraction_qualified"])
        self.assertFalse(result["can_claim_protocol_compliance"])

    def test_same_rate_does_not_qualify_base_t_or_optical_modes(self):
        evidence = ["linear_nrz_10_3125_gbd_reference"]
        for mode in ("10GBASE-T", "10GBASE-SR", "10GBASE-LR"):
            with self.subTest(mode=mode):
                result = assess_10gbe_evidence(mode, evidence, reference_rate_hz=10_312_500_000.0)
                self.assertEqual(result["exploratory_scope"], "none")
                self.assertFalse(result["evidence_inventory_complete"])
                self.assertEqual(result["compliance_status"], "not_evaluated")

    def test_inventory_completeness_never_self_asserts_compliance(self):
        for mode in SUPPORTED_MODES:
            initial = assess_10gbe_evidence(mode, [])
            complete = assess_10gbe_evidence(mode, initial["missing_evidence"])
            self.assertTrue(complete["evidence_inventory_complete"])
            self.assertFalse(complete["production_qualified"])
            self.assertFalse(complete["can_claim_protocol_compliance"])
            json.dumps(complete, allow_nan=False)

    def test_unknown_or_ambiguous_mode_is_rejected(self):
        for mode in ("10GbE", "BASE-R", "SFI", ""):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "mode must be"):
                assess_10gbe_evidence(mode, [])


if __name__ == "__main__":
    unittest.main()
