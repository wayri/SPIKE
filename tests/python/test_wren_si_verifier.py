# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_wren_si_scenario as verifier


class WrenSiVerifierTests(unittest.TestCase):
    @staticmethod
    def evaluated_row(status="admitted"):
        return {
            "channel_admission": {"status": status},
            "path_modes": {
                "strict_uniform": {"status": "rejected"},
                "piecewise_planar": {"status": status},
            },
            "production_qualified": False,
        }

    def test_build_evidence_uses_pinned_native_source_and_explicit_scenario(self):
        with patch.object(verifier, "evaluate", return_value=self.evaluated_row()) as evaluate:
            evidence = verifier.build_evidence("/WR_CLK.ABSCAL")

        name, spec = evaluate.call_args.args
        self.assertEqual(name, "wren_ie_native")
        self.assertEqual(spec["path"], verifier.BOARD_PATH)
        self.assertEqual(spec["sha256"], verifier.BOARD_SHA256)
        self.assertEqual(spec["conversion_losslessness_verified"], None)
        self.assertEqual(spec["reference_layer"], "In1.Cu")
        self.assertEqual(evaluate.call_args.kwargs["reference_zone_id"], verifier.REFERENCE_ZONE_ID)
        self.assertEqual(evaluate.call_args.kwargs["copper_scenario"], verifier.COPPER_SCENARIO)
        self.assertTrue(evidence["channel_admission_passed"])
        self.assertFalse(evidence["production_qualified"])
        self.assertFalse(evidence["source_provenance"]["legacy_converted_white_rabbit_switch"])
        self.assertEqual(evidence["source_provenance"]["hardware_commit"], verifier.HARDWARE_COMMIT)
        self.assertEqual(evidence["source_provenance"]["license_id"], "CERN-OHL-W-2.0+")
        self.assertEqual(set(evidence["source_sha256"]), set(verifier.HASHED_OWNERS))

    def test_rejected_geometry_remains_a_failed_admission(self):
        with patch.object(verifier, "evaluate", return_value=self.evaluated_row("rejected")):
            evidence = verifier.build_evidence("/WR_CLK.PPS")
        self.assertFalse(evidence["channel_admission_passed"])
        self.assertEqual(evidence["board"]["channel_admission"]["status"], "rejected")

    def test_unknown_signal_candidate_is_rejected_before_evaluation(self):
        with patch.object(verifier, "evaluate") as evaluate:
            with self.assertRaisesRegex(ValueError, "Unsupported bounded WREN"):
                verifier.build_evidence("invented-net")
        evaluate.assert_not_called()

    def test_output_is_fresh_and_json_serializable(self):
        evidence = {
            "contract": "spike/si-native-wren-admission-evidence/v1",
            "channel_admission_passed": False,
        }
        temp_root = verifier.ROOT / ".local" / "test-temp" / "release-full-20261023"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            output = Path(directory) / "evidence.json"
            verifier.write_evidence(output, evidence)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), evidence)
            with self.assertRaises(FileExistsError):
                verifier.write_evidence(output, evidence)


if __name__ == "__main__":
    unittest.main()
