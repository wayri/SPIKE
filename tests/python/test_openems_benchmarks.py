from __future__ import annotations

import unittest

from python.spike_core.openems_benchmarks import (
    _evaluate_patch_result,
    evaluate_mesh_convergence,
    patch_antenna_fixture,
)
from python.spike_core.openems_validation_evidence import (
    load_openems_reference_evidence,
    matching_openems_reference_evidence,
)


class OpenEmsBenchmarkTests(unittest.TestCase):
    def test_recorded_evidence_is_version_bound_and_converged(self):
        evidence = load_openems_reference_evidence()
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(len(evidence["runs"]), 3)
        self.assertIsNotNone(matching_openems_reference_evidence("0.0.36", "1.1.0"))
        self.assertIsNone(matching_openems_reference_evidence("0.0.35", "1.1.0"))

    def test_patch_fixture_uses_distinct_patch_and_ground_planes(self):
        design, spec = patch_antenna_fixture()
        self.assertEqual([zone["net_name"] for zone in design.zones], ["PATCH", "GND"])
        port = spec.options["ports"][0]
        self.assertEqual(port["direction"], "z")
        self.assertNotEqual(port["start"][2], port["stop"][2])
        self.assertEqual(spec.options["far_field"]["contract"], "spike/openems-far-field-request/v1")

    def test_result_evaluation_is_scoped_and_checks_reference_band(self):
        result = {
            "status": "completed",
            "frequency_hz": [2.3e9, 2.45e9, 2.6e9],
            "s_parameters": {
                "s11": {"real": [0.8, 0.1, 0.7], "imag": [0.0, 0.0, 0.0]},
            },
            "far_field": {
                "radiated_power": {"total_w": [0.01]},
                "directivity": {"maximum_linear": [4.5]},
            },
        }
        report = _evaluate_patch_result(result)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["validation_status"], "reference_fixture_passed")
        self.assertEqual(report["scope"], "openems_adapter.simple_patch_antenna")

    def test_convergence_requires_three_passing_runs_and_scopes_validation(self):
        base = {
            "status": "passed",
            "maximum_directivity_linear": [4.5],
        }
        reports = [
            {**base, "mesh_resolution_mm": 5.0, "resonance_hz": 2.30e9},
            {**base, "mesh_resolution_mm": 4.0, "resonance_hz": 2.40e9},
            {**base, "mesh_resolution_mm": 3.0, "resonance_hz": 2.44e9},
        ]
        report = evaluate_mesh_convergence(reports)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["validation_status"], "validated_for_reference_fixture")
        self.assertEqual(report["scope"], "openems_adapter.simple_patch_antenna")


if __name__ == "__main__":
    unittest.main()
