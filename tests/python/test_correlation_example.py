# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Analytical seed is checkable but must remain explicitly uncorrelated."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "examples" / "correlation" / "uniform_sheet"


class CorrelationExampleTests(unittest.TestCase):
    def test_sheet_value_and_missing_independent_and_measured_evidence(self):
        case = json.loads((CASE / "analytical.json").read_text(encoding="utf-8"))
        geometry = case["geometry"]
        conductivity = case["material"]["conductivity_s_per_m"]
        expected = geometry["length_m"] / (
            conductivity * geometry["width_m"] * geometry["thickness_m"])
        self.assertAlmostEqual(case["resistance_ohm"], expected, places=16)
        run = subprocess.run([sys.executable,
            str(ROOT / "scripts" / "validate_correlation_manifest.py"),
            str(CASE / "manifest.json")], capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 2, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["status"], "evidence_incomplete")
        self.assertFalse(report["numerical_correlation_performed"])
        self.assertFalse(report["solver_signoff"])
        self.assertIn("evidence_missing:independent_solver:uniform-sheet-independent",
            report["issues"])
        self.assertIn("evidence_missing:measured:uniform-sheet-measured", report["issues"])


if __name__ == "__main__":
    unittest.main()
