from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.sparselizard_validation import evaluate_sparselizard_validation


class SparseLizardValidationTests(unittest.TestCase):
    def evidence(self, fixture_id: str, metrics: dict[str, float]) -> dict:
        return {
            "contract": "spike/sparselizard-validation-evidence/v1",
            "engine_id": "external.sparselizard", "fixture_id": fixture_id,
            "status": "completed", "metrics": metrics,
            "convergence": {"passed": True, "levels": [{"cells": 100}, {"cells": 400}, {"cells": 1600}]},
            "provenance": {
                "solver_version": "fixture", "adapter_version": "fixture",
                "runtime_sha256": "a" * 64, "case_sha256": "b" * 64, "result_sha256": "c" * 64,
            },
        }

    def test_absent_evidence_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "python.spike_core.sparselizard_validation.detect_sparselizard_runtime",
            return_value={"available": True, "signature_verified": True, "manifest": {"backend": {"mumps_registered": True}}},
        ):
            report = evaluate_sparselizard_validation(directory)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["summary"]["blocked"], 5)

    def test_one_valid_fixture_passes_without_promoting_incomplete_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pcb-dc-copper-bar-v1.json"
            path.write_text(json.dumps(self.evidence("pcb-dc-copper-bar-v1", {
                "resistance_ohm": 0.009852216748768473,
            })), encoding="utf-8")
            with patch(
                "python.spike_core.sparselizard_validation.detect_sparselizard_runtime",
                return_value={"available": True, "signature_verified": True, "manifest": {"backend": {"mumps_registered": True}}},
            ):
                report = evaluate_sparselizard_validation(directory)
        self.assertEqual(report["fixtures"][0]["status"], "passed")
        self.assertEqual(report["status"], "blocked")

    def test_out_of_tolerance_or_malformed_evidence_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pcb-dc-copper-bar-v1.json"
            path.write_text(json.dumps(self.evidence("pcb-dc-copper-bar-v1", {"resistance_ohm": 1.0})), encoding="utf-8")
            with patch(
                "python.spike_core.sparselizard_validation.detect_sparselizard_runtime",
                return_value={"available": True, "manifest": {"backend": {"mumps_registered": True}}},
            ):
                report = evaluate_sparselizard_validation(directory)
        self.assertEqual(report["fixtures"][0]["status"], "failed")
        self.assertEqual(report["status"], "failed")

    def test_unsigned_runtime_cannot_promote_a_complete_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {
                "pcb-dc-copper-bar-v1": {"resistance_ohm": 0.009852216748768473},
                "pcb-ac-rlcg-two-conductor-v1": {
                    "resistance_1mhz_ohm": 0.0108,
                    "loop_inductance_h": 0.000000016,
                    "capacitance_f": 0.0000000062,
                },
                "pcb-thermal-slab-v1": {"temperature_rise_k": 10.0},
                "pcb-electrostatic-parallel-plate-v1": {"capacitance_f": 0.00000000035416675125},
                "pcb-harmonic-loop-field-v1": {"magnetic_flux_density_t": 0.00006283185307179586},
            }
            for fixture_id, metrics in expected.items():
                (root / f"{fixture_id}.json").write_text(
                    json.dumps(self.evidence(fixture_id, metrics)), encoding="utf-8",
                )
            with patch(
                "python.spike_core.sparselizard_validation.detect_sparselizard_runtime",
                return_value={
                    "available": True, "signature_verified": False,
                    "manifest": {"backend": {"mumps_registered": True}},
                },
            ):
                report = evaluate_sparselizard_validation(root)
        self.assertEqual(report["summary"]["passed"], 5)
        self.assertEqual(report["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
