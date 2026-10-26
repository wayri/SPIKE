# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_si_board_protocol_readiness as verifier
from python.spike_core.spider_v2 import Via
from tests.python import test_si_channel as channel_fixtures


class BoardProtocolReadinessTests(unittest.TestCase):
    def fixture(self):
        design = channel_fixtures.SiUniformChannelTests().coupled_design()
        design.nets[0].name = "PAIR_P"
        design.nets[-1].name = "PAIR_N"
        return design

    def test_real_extractor_admits_original_straight_fixture_not_protocol(self):
        result = verifier.attempt_pair(self.fixture(), "PAIR")
        self.assertEqual(result["channel_admission"]["status"], "admitted")
        extraction = result["channel_admission"]["extraction"]
        # Independent Ohmic relation for the authored fixture, SI units.
        expected = 1 / (58_000_000 * 0.00035 * 0.000035)
        self.assertAlmostEqual(extraction["rlgc_per_m"]["resistance_ohm_per_m"][0][0], expected, places=12)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["compliance_status"], "not_evaluated")

    def test_via_is_preserved_and_rejected_by_real_extractor(self):
        design = self.fixture()
        design.vias.append(Via(id="via", net_id=design.nets[0].id,
            center_mm=(20, 0), diameter_mm=0.6, drill_mm=0.3,
            start_layer_id="layer-signal", end_layer_id="layer-reference"))
        before = design.to_dict()
        result = verifier.attempt_pair(design, "PAIR")
        self.assertEqual(result["channel_admission"]["status"], "rejected")
        self.assertIn("Vias", result["channel_admission"]["reason"])
        self.assertEqual(result["nets"][0]["via_count"], 1)
        self.assertEqual(design.to_dict(), before)

    def test_both_modes_preserve_geometry_and_record_their_rejections(self):
        design = self.fixture()
        from python.spike_core.spider_v2 import Track
        design.tracks[0].end_mm = (25, 0)
        design.tracks.append(Track(id="bend", net_id=design.nets[0].id,
            layer_id="layer-signal", start_mm=(25, 0), end_mm=(50, 5), width_mm=0.35))
        result = verifier.attempt_pair(design, "PAIR")
        self.assertIn("straight path", result["path_modes"]["strict_uniform"]["reason"])
        self.assertIn("same segment count", result["path_modes"]["piecewise_planar"]["reason"])
        self.assertEqual(result["request"]["path_mode"], "strict_uniform")
        piecewise = result["path_modes"]["piecewise_planar"]["request"]
        self.assertEqual(piecewise["coupled_separation_tolerance_mm"], 0.0)
        self.assertEqual(piecewise["coupled_skew_tolerance_mm"], 0.0)

    def test_missing_partner_is_not_substituted(self):
        design = self.fixture()
        design.nets[-1].name = "CLOCK_N"
        with self.assertRaisesRegex(ValueError, "Exact SERDES net"):
            verifier.attempt_pair(design, "PAIR")

    def test_nominal_material_preparation_preserves_source_and_dielectric(self):
        design = self.fixture().to_dict()
        design["materials"][0]["material_class"] = "copper"
        design["materials"][0]["conductivity_s_per_m"] = None
        before = deepcopy(design)
        result = verifier.prepare_nominal_copper(design)
        self.assertEqual(design, before)
        self.assertEqual(result["design"]["materials"][1], before["materials"][1])
        self.assertEqual(result["design"]["materials"][0]["conductivity_s_per_m"], 58_000_000)
        self.assertEqual(result["design"]["source"], before["source"])

    def test_unknown_material_class_is_not_relabelled_copper(self):
        with self.assertRaisesRegex(ValueError, "reclassification is forbidden"):
            verifier.prepare_nominal_copper(self.fixture().to_dict())

    def test_unexpected_extractor_failure_is_not_reported_as_physical_rejection(self):
        with patch.object(verifier, "extract_coupled_path_rlgc", side_effect=RuntimeError("bug")):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                verifier.attempt_pair(self.fixture(), "PAIR")

    def test_mismatched_source_is_rejected_before_import(self):
        with patch.object(Path, "read_bytes", return_value=b"different source"):
            with self.assertRaisesRegex(ValueError, "pinned source identity mismatch"):
                verifier.evaluate_board("marble")

    def test_evidence_cannot_overwrite_and_cli_never_claims_qualification(self):
        temp_root = verifier.ROOT / ".local" / "test-temp" / "board-protocol-readiness"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
            output = Path(temporary) / "evidence.json"
            result = {"boards": {}}
            with patch.object(verifier, "build_evidence", return_value=result):
                self.assertEqual(verifier.main(["--output", str(output)]), 2)
            with self.assertRaises(FileExistsError):
                verifier.write_evidence(output, result)


if __name__ == "__main__":
    unittest.main()
