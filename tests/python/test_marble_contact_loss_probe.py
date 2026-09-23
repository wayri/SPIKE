# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Keep the Marble DC attachment perturbation reproducible and diagnostic."""

import unittest
from pathlib import Path

from scripts.probe_marble_contact_loss import probe


class MarbleContactLossProbeTests(unittest.TestCase):
    def test_invalid_sensitivity_is_rejected_before_loading_board(self):
        board = Path("does-not-exist.kicad_pcb")
        with self.assertRaisesRegex(ValueError, "mesh size"):
            probe(board, 0.0, "none", 1.0)
        with self.assertRaisesRegex(ValueError, "contact scale"):
            probe(board, 1.0, "none", 0.0)
        with self.assertRaisesRegex(ValueError, "contact_kind"):
            probe(board, 1.0, "not-a-contact", 1.0)

    def test_optional_marble_contact_perturbation_is_not_a_cure(self):
        board = (Path(__file__).resolve().parents[2] / "build" / "marble-qualification"
                 / "sources" / "Marble-v1.4.4" / "design" / "Marble.kicad_pcb")
        if not board.is_file():
            self.skipTest("pinned public Marble board has not been fetched")
        baseline = probe(board, 1.0, "none", 1.0)
        perturbed = probe(board, 1.0, "all", 0.01)
        self.assertEqual(baseline["qualification"], "diagnostic_only")
        self.assertEqual(baseline["physical_branch_count"], 45)
        self.assertAlmostEqual(baseline["dc_port_resistance_ohm"],
                               0.004778865322878308, places=9)
        self.assertLess(perturbed["dc_port_resistance_ohm"],
                        baseline["dc_port_resistance_ohm"])
        self.assertGreater(perturbed["dc_port_resistance_ohm"], 0.0)
        self.assertLess(baseline["relative_mna_residual"], 1e-12)


if __name__ == "__main__":
    unittest.main()
