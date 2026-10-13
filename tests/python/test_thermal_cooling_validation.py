# SPDX-License-Identifier: Apache-2.0
"""Contract and real-runtime checks for the cooling validation orchestrator."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from python.spike_core.calculix_runtime import probe_calculix_runtime
from scripts.validate_thermal_cooling_environments import (
    CFD_FINAL_MASS_RELATIVE_TOLERANCE,
    CFD_MASS_RELATIVE_TOLERANCE,
    REPORT_CONTRACT,
    evaluate_openfoam_mass_balance,
    run_established_solver_comparisons,
    run_openfoam_cht,
    run_validation,
)


ROOT = Path(__file__).resolve().parents[2]


def _history(root: Path, name: str, values: list[tuple[float, float]]) -> None:
    path = root / "postProcessing" / "air" / name / "0" / "surfaceFieldValue.dat"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Time sum(phi)\n" + "".join(f"{time:.3f} {value:.16g}\n" for time, value in values),
        encoding="ascii",
    )


class ThermalCoolingValidationTests(unittest.TestCase):
    def test_mass_balance_uses_complete_aligned_histories_and_fixed_gates(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _history(root, "spikeMassFlux_air_fan_in", [(0.001, -1.2e-5), (0.002, -1.2e-5), (0.003, -1.2e-5)])
            _history(root, "spikeMassFlux_air_exhaust", [(0.001, 1.1999998e-5), (0.002, 1.2e-5), (0.003, 1.2e-5)])
            result = evaluate_openfoam_mass_balance(root, expected_mass_flow_kg_s=1.2e-5)
            self.assertTrue(result["passed"])
            self.assertEqual(result["relative_tolerance"], CFD_MASS_RELATIVE_TOLERANCE)
            self.assertEqual(result["final_relative_tolerance"], CFD_FINAL_MASS_RELATIVE_TOLERANCE)
            self.assertEqual(len(result["history_sha256"]), 2)

            _history(root, "spikeMassFlux_air_exhaust", [(0.001, 1.19e-5), (0.002, 1.2e-5), (0.003, 1.2e-5)])
            self.assertFalse(evaluate_openfoam_mass_balance(root, expected_mass_flow_kg_s=1.2e-5)["passed"])

    def test_misaligned_mass_history_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _history(root, "spikeMassFlux_air_fan_in", [(0.001, -1.2e-5), (0.002, -1.2e-5)])
            _history(root, "spikeMassFlux_air_exhaust", [(0.001, 1.2e-5), (0.003, 1.2e-5)])
            with self.assertRaisesRegex(ValueError, "not aligned"):
                evaluate_openfoam_mass_balance(root, expected_mass_flow_kg_s=1.2e-5)

    def test_missing_openfoam_is_blocked_without_saved_result_substitution(self):
        unavailable = {"available": False, "transport": "none", "version": "", "distribution": ""}
        with patch("scripts.validate_thermal_cooling_environments.detect_openfoam_runtime", return_value=unavailable):
            result = run_openfoam_cht("unused")
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["passed"])
        self.assertIn("not substituted", result["reason"])

    def test_orchestrator_never_promotes_authored_evidence(self):
        comparison = {"status": "passed", "passed": True}
        cfd = {"status": "passed", "passed": True, "conjugate_interface_heat_flow": {"status": "not_evaluated"}}
        with patch("scripts.validate_thermal_cooling_environments._source_identity", return_value={"source.py": "a" * 64}), \
             patch("scripts.validate_thermal_cooling_environments.run_established_solver_comparisons", return_value=comparison), \
             patch("scripts.validate_thermal_cooling_environments.run_openfoam_cht", return_value=cfd):
            report = run_validation("unused")
        self.assertEqual(report["contract"], REPORT_CONTRACT)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["production_qualified"])
        self.assertFalse(report["qualification"]["production_qualified"])
        self.assertTrue(report["sources_unchanged_during_run"])

    @unittest.skipUnless(probe_calculix_runtime()["available"], "Separately installed CalculiX executable unavailable")
    def test_real_calculix_cooling_and_interface_comparisons(self):
        result = run_established_solver_comparisons()
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["cooling_environment"]["passed"])
        self.assertTrue(result["solid_interface"]["passed"])
        self.assertFalse(result["cooling_environment"]["calculix_execution"].get("production_qualified", False))


if __name__ == "__main__":
    unittest.main()
