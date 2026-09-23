import copy
import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.cli import main
from python.spike_core.external_pi_result_validation import validate_external_pi_multiport


def external_fixture():
    matrix = [[0.20, 0.05], [0.05, 0.30]]
    return {
        "contract": "spike/pi-multiport-result/v1",
        "engine_id": "external.sparselizard",
        "status": "completed",
        "model_status": "experimental",
        "analysis_id": "sl-analytic-two-port",
        "net": "VCC",
        "ports": [
            {
                "id": "load",
                "role": "observation",
                "endpoint_reviewed": True,
                "positive_terminal": {"object_id": "U1.1", "object_type": "pad", "net": "VCC"},
                "negative_terminal": {"object_id": "U1.2", "object_type": "pad", "net": "GND"},
            },
            {
                "id": "C1",
                "role": "candidate",
                "endpoint_reviewed": True,
                "positive_terminal": {"object_id": "C1.1", "object_type": "pad", "net": "VCC"},
                "negative_terminal": {"object_id": "C1.2", "object_type": "pad", "net": "GND"},
                "location": {"component_ref": "C1"},
            },
        ],
        "z_parameters": [
            {"frequency_hz": frequency, "resistance_ohm": matrix, "reactance_ohm": [[0, 0], [0, 0]]}
            for frequency in (1e3, 1e4)
        ],
        "quality": {"passivity_tolerance_ohm": 1e-9, "reciprocity_tolerance": 1e-9},
        "convergence": {"passed": True, "levels": [{"cells": 100}, {"cells": 400}]},
        "provenance": {
            "solver_version": "fixture",
            "adapter_version": "1.0.0",
            "geometry_digest": "0123456789abcdef",
            "request_digest": "fedcba9876543210",
        },
    }


class ExternalPiResultValidationTests(unittest.TestCase):
    def test_valid_result_normalizes_for_pdn_optimizer_without_promoting_status(self):
        normalized = validate_external_pi_multiport(
            external_fixture(),
            expected_engine_id="external.sparselizard",
            expected_frequencies_hz=[1e3, 1e4],
        )

        self.assertEqual(normalized["contract"], "spike/pdn-multiport/v1")
        self.assertEqual(normalized["model_status"], "experimental")
        self.assertEqual(normalized["engine_id"], "external.sparselizard")
        self.assertEqual(normalized["candidates"][0]["id"], "C1")
        self.assertAlmostEqual(normalized["candidates"][0]["transfer_impedance"][0]["resistance_ohm"], 0.05)

    def test_mismatched_frequency_grid_and_nonpassive_matrix_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "frequency grid"):
            validate_external_pi_multiport(external_fixture(), expected_frequencies_hz=[1e3, 2e4])

        fixture = external_fixture()
        fixture["z_parameters"][0]["resistance_ohm"] = [[-1.0, 0], [0, 0.3]]
        with self.assertRaisesRegex(ValueError, "passivity"):
            validate_external_pi_multiport(fixture)

    def test_validated_status_requires_evidence_and_explicit_reviewed_terminals(self):
        fixture = external_fixture()
        fixture["model_status"] = "validated"
        with self.assertRaisesRegex(ValueError, "validation_evidence"):
            validate_external_pi_multiport(fixture)

        fixture = copy.deepcopy(external_fixture())
        fixture["ports"][1]["endpoint_reviewed"] = False
        with self.assertRaisesRegex(ValueError, "reviewed"):
            validate_external_pi_multiport(fixture)

    def test_cli_imports_the_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sparselizard-result.json"
            output = Path(directory) / "normalized.json"
            source.write_text(json.dumps(external_fixture()), encoding="utf-8")
            code = main([
                "--quiet", "--output", str(output),
                "external-pi-import", str(source),
                "--engine-id", "external.sparselizard",
            ])
            normalized = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(normalized["contract"], "spike/pdn-multiport/v1")
        self.assertEqual(normalized["engine_id"], "external.sparselizard")


if __name__ == "__main__":
    unittest.main()
