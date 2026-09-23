from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.openfoam_multiregion_execution import RUNNABLE_CASE_CONTRACT, _digest
from python.spike_core.openfoam_multiregion_validation import RECORD_CONTRACT, import_v2606_validation_evidence
from python.spike_core.openfoam_multiregion_execution import MultiRegionExecutionError


def _case(root: Path) -> dict:
    control = root / "system" / "controlDict"; control.parent.mkdir(parents=True); control.write_text("application chtMultiRegionFoam;\n", encoding="utf-8")
    manifest = {
        "contract": RUNNABLE_CASE_CONTRACT, "status": "runnable", "solver": "chtMultiRegionFoam",
        "regions": ["board", "air"], "region_kinds": {"board": "solid", "air": "fluid"},
        "region_conductivity_w_mk": {"board": 0.35, "air": 0.026}, "view_factor_regions": [],
        "input_files": {"system/controlDict": hashlib.sha256(control.read_bytes()).hexdigest()},
        "field_export_path": "postProcessing/spike/fields.json",
    }
    manifest["manifest_digest"] = _digest(manifest)
    (root / "spike_multiregion_runnable_case.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _record(manifest: dict) -> dict:
    return {"contract": RECORD_CONTRACT, "manifest_digest": manifest["manifest_digest"],
            "conservation": {"input_power_w": 10, "boundary_power_w": 9.98, "relative_tolerance": 0.005},
            "mesh_convergence": {"relative_tolerance": 0.002, "levels": [{"cells": 100, "maximum_temperature_k": 330}, {"cells": 400, "maximum_temperature_k": 331}, {"cells": 1600, "maximum_temperature_k": 331.2}]},
            "time_convergence": {"relative_tolerance": 0.002, "levels": [{"delta_t_s": 1, "maximum_temperature_k": 331.8}, {"delta_t_s": .5, "maximum_temperature_k": 331.3}, {"delta_t_s": .25, "maximum_temperature_k": 331.2}]}}


class OpenFoamMultiRegionValidationTests(unittest.TestCase):
    def test_explicit_digest_bound_record_yields_candidate_only(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = _case(Path(temp))
            evidence = import_v2606_validation_evidence(temp, result_record=_record(manifest))
            self.assertTrue(evidence["candidate_passed"])
            self.assertFalse(evidence["qualification"]["production_qualified"])
            self.assertLess(evidence["conservation"]["relative_residual"], .005)

    def test_postprocessing_artifact_is_consumed_without_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root); target = root / "postProcessing" / "spike" / "validation-record.json"; target.parent.mkdir(parents=True)
            record = _record(manifest); del record["time_convergence"]
            target.write_text(json.dumps(record), encoding="utf-8")
            evidence = import_v2606_validation_evidence(root)
            self.assertFalse(evidence["candidate_passed"])
            self.assertEqual(evidence["time_convergence"]["status"], "incomplete")

    def test_wrong_digest_is_rejected_and_never_evaluated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = _case(root); record = _record(manifest); record["manifest_digest"] = "0" * 64
            with self.assertRaisesRegex(MultiRegionExecutionError, "not bound"):
                import_v2606_validation_evidence(root, result_record=record)

    def test_bad_refinement_or_conservation_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = _case(Path(temp)); record = _record(manifest)
            record["conservation"]["boundary_power_w"] = 7
            record["mesh_convergence"]["levels"][2]["cells"] = 200
            evidence = import_v2606_validation_evidence(temp, result_record=record)
            self.assertFalse(evidence["candidate_passed"])
            self.assertFalse(evidence["conservation"]["passed"])
            self.assertEqual(evidence["mesh_convergence"]["status"], "incomplete")

    def test_transient_energy_conservation_includes_storage(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = _case(Path(temp)); record = _record(manifest)
            record["conservation"] = {"input_energy_j": 1.0, "boundary_energy_j": 0.1, "stored_energy_change_j": 0.899, "relative_tolerance": 0.002}
            evidence = import_v2606_validation_evidence(temp, result_record=record)
            self.assertTrue(evidence["conservation"]["passed"])
            self.assertEqual(evidence["conservation"]["mode"], "transient_energy")


if __name__ == "__main__":
    unittest.main()
