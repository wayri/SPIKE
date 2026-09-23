import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.cli import main
from python.spike_core.pdn import optimize_pdn, review_pdn


class PdnReviewTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "networks": {
                "parasitics": [{
                    "net": "VCC",
                    "impedance": [
                        {"frequency_hz": 1e3, "resistance_ohm": 0.10, "reactance_ohm": 0.0, "magnitude_ohm": 0.10, "phase_deg": 0},
                        {"frequency_hz": 1e4, "resistance_ohm": 0.30, "reactance_ohm": 0.0, "magnitude_ohm": 0.30, "phase_deg": 0},
                        {"frequency_hz": 1e5, "resistance_ohm": 0.08, "reactance_ohm": 0.0, "magnitude_ohm": 0.08, "phase_deg": 0},
                    ],
                }],
            },
        }

    def test_target_violations_resonance_and_candidates_are_reported(self):
        report = review_pdn(self.result, 0.2, "VCC", [{
            "id": "bulk-10mF",
            "capacitance_f": 0.01,
            "esr_ohm": 0.005,
            "esl_h": 1e-9,
        }])
        self.assertEqual(report["contract"], "spike/pdn-review/v1")
        self.assertEqual(report["status"], "violated")
        self.assertEqual(report["violation_count"], 1)
        self.assertEqual(len(report["resonances"]), 1)
        self.assertGreater(report["candidate_screening"][0]["worst_impedance_improvement_percent"], 0)
        self.assertEqual(report["model_status"], "approximate")

    def test_cli_pdn_review_uses_the_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ac-result.json"
            output = Path(directory) / "pdn.json"
            source.write_text(json.dumps(self.result), encoding="utf-8")
            code = main([
                "--output", str(output),
                "--quiet",
                "pdn-review", str(source),
                "--target-ohm", "0.2",
                "--net", "VCC",
                "--candidate", "bulk,0.01,0.005,1e-9,2",
            ])
            self.assertEqual(code, 2)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["contract"], "spike/pdn-review/v1")
            self.assertEqual(report["candidate_screening"][0]["count"], 2)

    def test_explicit_mounting_path_changes_candidate_ranking(self):
        result = {
            "model_status": "approximate",
            "networks": {"parasitics": [{
                "net": "VCC",
                "impedance": [
                    {"frequency_hz": 1e5, "resistance_ohm": 0.30, "reactance_ohm": 0.0},
                    {"frequency_hz": 1e6, "resistance_ohm": 0.30, "reactance_ohm": 0.0},
                    {"frequency_hz": 1e7, "resistance_ohm": 0.30, "reactance_ohm": 0.0},
                ],
            }]},
        }
        common = {
            "capacitance_f": 10e-6,
            "esr_ohm": 0.005,
            "esl_h": 0.5e-9,
            "count": 1,
        }
        report = review_pdn(result, 0.2, "VCC", [
            {**common, "id": "remote", "mounting_inductance_h": 20e-9, "location": {"pad_id": "C20.1"}},
            {**common, "id": "near", "mounting_inductance_h": 0.2e-9, "location": {"pad_id": "C1.1"}},
        ])

        self.assertEqual(report["candidate_screening"][0]["id"], "near")
        self.assertEqual(report["candidate_screening"][0]["placement_method"], "series_connection_path")
        self.assertGreater(
            report["candidate_screening"][1]["worst_target_ratio"],
            report["candidate_screening"][0]["worst_target_ratio"],
        )
        self.assertEqual(report["candidate_method_counts"]["series_connection_path"], 2)

    def test_two_port_loading_matches_analytic_reduction(self):
        frequencies = [1e3, 1e4]
        result = {
            "model_status": "validated",
            "networks": {"parasitics": [{
                "net": "VCC",
                "model_status": "validated",
                "impedance": [
                    {"frequency_hz": frequency, "resistance_ohm": 0.1, "reactance_ohm": 0.0}
                    for frequency in frequencies
                ],
            }]},
        }
        candidate = {
            "id": "C1-pad",
            "capacitance_f": 1.0,
            "esr_ohm": 0.0,
            "esl_h": 0.0,
            "count": 1,
            "location": {"component_ref": "C1", "pad_id": "C1.1"},
            "source_result_id": "validated-two-port-fixture",
            "endpoint_reviewed": True,
            "reciprocal": True,
            "model_status": "validated",
            "local_impedance": [
                {"frequency_hz": frequency, "resistance_ohm": 0.2, "reactance_ohm": 0.0}
                for frequency in frequencies
            ],
            "transfer_impedance": [
                {"frequency_hz": frequency, "resistance_ohm": 0.05, "reactance_ohm": 0.0}
                for frequency in frequencies
            ],
        }
        report = review_pdn(result, 0.2, "VCC", [candidate])
        screened = report["candidate_screening"][0]
        load = complex(0, -1 / (2 * 3.141592653589793 * frequencies[0]))
        expected = complex(0.1, 0) - complex(0.05, 0) ** 2 / (complex(0.2, 0) + load)

        self.assertEqual(screened["placement_method"], "multiport_impedance_loading")
        self.assertAlmostEqual(screened["response"][0]["resistance_ohm"], expected.real, places=12)
        self.assertAlmostEqual(screened["response"][0]["reactance_ohm"], expected.imag, places=12)
        self.assertEqual(screened["model_status"], "validated")
        self.assertEqual(report["model_status"], "validated")

    def test_unreviewed_geometry_candidate_is_rejected(self):
        candidate = {
            "id": "unreviewed",
            "capacitance_f": 1e-3,
            "source_result_id": "two-port-run",
            "local_impedance": self.result["networks"]["parasitics"][0]["impedance"],
            "transfer_impedance": self.result["networks"]["parasitics"][0]["impedance"],
        }
        report = review_pdn(self.result, 0.2, "VCC", [candidate])

        self.assertEqual(report["candidate_screening"][0]["status"], "rejected")
        self.assertEqual(report["candidate_screening"][0]["issues"][0]["code"], "SPIKE-BE-PI-E-0100")
        self.assertEqual(report["model_status"], "unsupported")

    def test_cli_accepts_versioned_geometry_candidate_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ac-result.json"
            candidates = root / "candidates.json"
            output = root / "pdn.json"
            source.write_text(json.dumps(self.result), encoding="utf-8")
            candidates.write_text(json.dumps({
                "contract": "spike/pdn-candidate-set/v1",
                "candidates": [{
                    "id": "mounted-bank",
                    "capacitance_f": 0.01,
                    "esr_ohm": 0.005,
                    "esl_h": 1e-9,
                    "mounting_inductance_h": 0.5e-9,
                }],
            }), encoding="utf-8")
            code = main([
                "--output", str(output), "--quiet", "pdn-review", str(source),
                "--target-ohm", "0.2", "--net", "VCC", "--candidate-file", str(candidates),
            ])
            report = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(code, 2)
            self.assertEqual(report["candidate_screening"][0]["placement_method"], "series_connection_path")

    def test_cli_accepts_candidate_array_and_rejects_wrong_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ac-result.json"
            candidates = root / "candidates.json"
            output = root / "pdn.json"
            source.write_text(json.dumps(self.result), encoding="utf-8")
            candidates.write_text(json.dumps([{
                "id": "array-candidate",
                "capacitance_f": 0.01,
                "esr_ohm": 0.005,
                "esl_h": 1e-9,
            }]), encoding="utf-8")

            code = main([
                "--output", str(output), "--quiet", "pdn-review", str(source),
                "--target-ohm", "0.2", "--net", "VCC", "--candidate-file", str(candidates),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["candidate_screening"][0]["id"], "array-candidate")

            candidates.write_text(json.dumps({
                "contract": "spike/pdn-candidate-set/v99",
                "candidates": [],
            }), encoding="utf-8")
            code = main([
                "--output", str(output), "--quiet", "pdn-review", str(source),
                "--target-ohm", "0.2", "--net", "VCC", "--candidate-file", str(candidates),
            ])
            self.assertEqual(code, 1)
            self.assertIn("unsupported contract", json.loads(output.read_text(encoding="utf-8"))["error"])

    def test_candidate_schema_is_versioned_and_strict(self):
        schema_path = Path(__file__).resolve().parents[2] / "schemas" / "pdn-candidate-set-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["contract"]["const"], "spike/pdn-candidate-set/v1")
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["candidate"]["additionalProperties"])

    def test_multiport_bank_optimizer_ranks_explicit_ports_by_analytic_loading(self):
        frequencies = [1e3, 1e4]
        matrix = [
            [0.20, 0.10, 0.02],
            [0.10, 0.30, 0.01],
            [0.02, 0.01, 0.25],
        ]
        result = {
            "model_status": "validated",
            "networks": {"pdn_multiports": [{
                "contract": "spike/pdn-multiport/v1",
                "model_status": "validated",
                "net": "VCC",
                "source_result_id": "analytic-three-port",
                "ports": [
                    {"id": "load", "role": "observation", "endpoint_reviewed": True},
                    {"id": "C_NEAR", "role": "candidate", "endpoint_reviewed": True},
                    {"id": "C_FAR", "role": "candidate", "endpoint_reviewed": True},
                ],
                "candidates": [
                    {"id": "C_NEAR", "endpoint_reviewed": True, "location": {"pad_id": "C1.1"}},
                    {"id": "C_FAR", "endpoint_reviewed": True, "location": {"pad_id": "C2.1"}},
                ],
                "z_parameters": [{
                    "frequency_hz": frequency,
                    "resistance_ohm": matrix,
                    "reactance_ohm": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                } for frequency in frequencies],
            }]},
        }
        library = [{
            "id": "C100u",
            "capacitance_f": 100e-6,
            "esr_ohm": 0.005,
            "esl_h": 0.5e-9,
            "min_count": 1,
            "max_count": 1,
            "unit_cost": 0.25,
            "voltage_rating_v": 25,
            "ripple_current_rating_a": 2,
            "model_status": "validated",
        }]

        optimized = optimize_pdn(result, 0.19, "VCC", library, {
            "max_total_count": 1,
            "operating_voltage_v": 12,
            "voltage_derating": 0.8,
            "required_ripple_current_a": 1,
        })

        self.assertEqual(optimized["contract"], "spike/pdn-optimization/v1")
        self.assertEqual(optimized["search_status"], "exhaustive")
        self.assertEqual(optimized["model_status"], "validated")
        self.assertEqual(optimized["recommendations"][0]["assignments"][0]["port_id"], "C_NEAR")
        load = complex(0.005, 2 * 3.141592653589793 * frequencies[0] * 0.5e-9 - 1 / (2 * 3.141592653589793 * frequencies[0] * 100e-6))
        expected = 0.20 - 0.10 * 0.10 / (0.30 + load)
        self.assertAlmostEqual(
            optimized["recommendations"][0]["response"][0]["resistance_ohm"],
            expected.real,
            places=12,
        )

    def test_optimizer_rejects_unrated_parts_and_never_claims_optimum_when_bounded(self):
        result = {
            "model_status": "approximate",
            "networks": {"pdn_multiports": [{
                "contract": "spike/pdn-multiport/v1",
                "model_status": "approximate",
                "net": "VCC",
                "source_result_id": "bounded",
                "ports": [
                    {"id": "load", "role": "observation", "endpoint_reviewed": True},
                    {"id": "C1", "role": "candidate", "endpoint_reviewed": True},
                    {"id": "C2", "role": "candidate", "endpoint_reviewed": True},
                ],
                "candidates": [
                    {"id": "C1", "endpoint_reviewed": True},
                    {"id": "C2", "endpoint_reviewed": True},
                ],
                "z_parameters": [{
                    "frequency_hz": frequency,
                    "resistance_ohm": [[0.2, 0.05, 0.04], [0.05, 0.3, 0.01], [0.04, 0.01, 0.3]],
                    "reactance_ohm": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                } for frequency in (1e3, 1e4)],
            }]},
        }
        library = [
            {"id": "unrated", "capacitance_f": 1e-3},
            {"id": "rated", "capacitance_f": 1e-3, "voltage_rating_v": 50, "ripple_current_rating_a": 5},
        ]
        optimized = optimize_pdn(result, 0.2, "VCC", library, {
            "operating_voltage_v": 24,
            "required_ripple_current_a": 1,
            "max_evaluations": 1,
        })

        self.assertEqual(optimized["search_status"], "bounded")
        self.assertEqual(optimized["optimality"], "recommendation_only")
        self.assertEqual(optimized["search"]["rejected_library"][0]["id"], "unrated")
        self.assertTrue(optimized["search"]["truncated"])


if __name__ == "__main__":
    unittest.main()
