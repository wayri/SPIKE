# SPDX-License-Identifier: Apache-2.0
"""Process round-trip and rejection coverage for external analysis results."""

import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.extensions import ExtensionManifest, ProcessExtension
from python.spike_core.extension_analysis_results import admit_analysis_result, design_binding


SCRIPT = r'''
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--result", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
binding = request["context"]["design_binding"]
variant = request["context"].get("parameters", {}).get("variant", "")
if variant == "wrong_design":
    binding["digest_sha256"] = "0" * 64
sample = float("nan") if variant == "nonfinite" else 1.0
result = {
    "contract": "spike/v1", "analysis_id": "outside-1", "status": "completed",
    "mode": "si", "model_status": "experimental", "summary": {"sample": sample},
    "fields": {"visualization": {"schema": "spike/result-visualization/v1",
        "scalar_fields": {"voltage_v": [{"x_mm": 1, "y_mm": 2, "layer": "F.Cu", "value": 3}]},
        "vector_fields": {}}}, "networks": {}, "probes": [], "issues": [],
    "provenance": {"design_id": binding["design_id"],
        "design_digest_sha256": binding["digest_sha256"], "solver": "fixture/1"},
}
json.dump({"contract": "spike/extension-result/v1", "status": "completed",
           "data": {"analysis_result": result}}, open(args.result, "w", encoding="utf-8"))
'''


class ExtensionAnalysisResultsTest(unittest.TestCase):
    def _extension(self, directory, permissions=None):
        path = Path(directory) / "run.py"
        path.write_text(SCRIPT, encoding="utf-8")
        manifest = ExtensionManifest.from_dict({
            "id": "fixture.solver", "name": "Fixture", "version": "1", "provider": "Tests",
            "description": "Local test", "runtime": "python", "entrypoint": "run.py",
            "permissions": permissions or ["design.read", "results.write"],
            "contributes": {"analyses": [{"id": "solve", "name": "Solve", "output_contract": "spike/v1"}]},
        })
        return ProcessExtension(manifest, Path(directory), trusted=True)

    def test_round_trip_preserves_visual_result_and_binds_design(self):
        with tempfile.TemporaryDirectory() as directory:
            extension = self._extension(directory)
            result = extension.invoke("solve", {"design": {"contract": "spike/v1", "design_id": "board-1",
                "name": "Board", "layers": [], "nets": []}})
        data = result["data"]
        self.assertEqual(data["analysis_result"]["provenance"]["design_digest_sha256"], data["input_design_sha256"])
        self.assertEqual(data["analysis_result"]["provenance"]["extension_id"], "fixture.solver")
        self.assertEqual(data["analysis_result"]["fields"]["visualization"]["scalar_fields"]["voltage_v"][0]["value"], 3)

    def test_mismatched_board_and_nonfinite_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            extension = self._extension(directory)
            design = {"contract": "spike/v1", "design_id": "board-1"}
            with self.assertRaisesRegex(ValueError, "does not match"):
                extension.invoke("solve", {"design": design, "parameters": {"variant": "wrong_design"}})
            with self.assertRaisesRegex(ValueError, "non-finite"):
                extension.invoke("solve", {"design": design, "parameters": {"variant": "nonfinite"}})

    def test_permissions_are_required_by_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "results.write"):
                self._extension(directory, permissions=["design.read"])

    def test_validated_claim_requires_evidence_and_visual_samples_are_bounded(self):
        binding = design_binding({"contract": "spike/v1", "design_id": "board-1"})
        result = {"contract": "spike/v1", "analysis_id": "outside-1", "status": "completed",
            "mode": "si", "model_status": "validated", "summary": {}, "fields": {},
            "networks": {}, "probes": [], "issues": [],
            "provenance": {"design_id": binding["design_id"],
                "design_digest_sha256": binding["digest_sha256"], "solver": "fixture/1"}}
        with self.assertRaisesRegex(ValueError, "validation_evidence"):
            admit_analysis_result(result, binding, extension_id="fixture.solver")
        result["model_status"] = "experimental"
        result["fields"]["visualization"] = {"schema": "spike/result-visualization/v1",
            "scalar_fields": {"voltage_v": [{}] * 250_001}}
        with self.assertRaisesRegex(ValueError, "sample limit"):
            admit_analysis_result(result, binding, extension_id="fixture.solver")

    def test_vector_samples_use_magnitude_without_scalar_value(self):
        binding = design_binding({"contract": "spike/v1", "design_id": "board-1"})
        result = {"contract": "spike/v1", "analysis_id": "vector-1", "status": "completed",
            "mode": "emi", "model_status": "unvalidated", "summary": {},
            "fields": {"visualization": {"schema": "spike/result-visualization/v1",
                "vector_fields": {"magnetic_field": [{"x_mm": 1, "y_mm": 2,
                    "vector": [0, 0, 3], "magnitude": 3}]}}},
            "networks": {}, "probes": [], "issues": [],
            "provenance": {"design_id": binding["design_id"],
                "design_digest_sha256": binding["digest_sha256"], "solver": "fixture/1"}}
        self.assertEqual(admit_analysis_result(result, binding, extension_id="fixture.solver")
                         ["fields"]["visualization"]["vector_fields"]["magnetic_field"][0]["magnitude"], 3)


if __name__ == "__main__":
    unittest.main()
