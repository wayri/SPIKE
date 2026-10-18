# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""The offline RT0 audit must fail closed on incomplete or drifting evidence."""

import unittest
from pathlib import Path
import tempfile

from scripts.audit_peec_rt0_refinement import evaluate_rows, _sexpr_block, verify_marble_source_topology


def row(resistance: float) -> dict:
    return {"status": "completed", "resistance_ohm": resistance,
        "routed_connected": True, "c383_connected": True,
        "relative_residual": 1e-12, "maximum_cell_kcl_error_a": 1e-12,
        "maximum_face_kcl_error_a": 1e-12, "relative_energy_error": 1e-12}


class RefinementAuditTests(unittest.TestCase):
    def test_requires_three_completed_refinements(self):
        self.assertEqual(evaluate_rows([row(1), row(.99)]), (False, []))
        blocked = row(.98) | {"status": "blocked"}
        self.assertEqual(evaluate_rows([row(1), row(.99), blocked]), (False, []))

    def test_requires_both_small_and_nonworsening_changes(self):
        passed, changes = evaluate_rows([row(1), row(.985), row(.978)])
        self.assertTrue(passed)
        self.assertLess(changes[1], changes[0])
        self.assertFalse(evaluate_rows([row(1), row(.96), row(.94)])[0])
        self.assertFalse(evaluate_rows([row(1), row(.99), row(.975)])[0])

    def test_rejects_connectivity_and_algebraic_failures(self):
        good = [row(1), row(.985), row(.978)]
        for field, value in (("routed_connected", False),
                             ("c383_connected", False),
                             ("relative_residual", 1e-6),
                             ("maximum_cell_kcl_error_a", 1e-7),
                             ("maximum_face_kcl_error_a", 1e-7),
                             ("relative_energy_error", 1e-6)):
            with self.subTest(field=field):
                rows = [dict(item) for item in good]
                rows[1][field] = value
                self.assertFalse(evaluate_rows(rows)[0])

    def test_old_isolation_evidence_cannot_pass_new_topology_contract(self):
        rows = [row(1), row(.985), row(.978)]
        for item in rows:
            del item["c383_connected"]
            item["disconnected_rejected"] = True
        self.assertFalse(evaluate_rows(rows)[0])

    def test_native_expression_ignores_parentheses_in_strings(self):
        self.assertEqual(_sexpr_block('(x "unmatched (" (y)) trailing', 0),
                         '(x "unmatched (" (y))')
        with self.assertRaises(ValueError):
            _sexpr_block('(x (y)', 0)

    def test_native_topology_oracle_rejects_unpinned_source(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "wrong.kicad_pcb"
            board.write_text("(kicad_pcb)")
            with self.assertRaisesRegex(ValueError, "pinned Marble"):
                verify_marble_source_topology(board)

    def test_pinned_marble_native_pad_one_is_connected(self):
        board = Path(__file__).resolve().parents[2] / "build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb"
        if not board.is_file():
            self.skipTest("Optional local pinned Marble source is not installed")
        evidence = verify_marble_source_topology(board)
        self.assertTrue(evidence["c383_fully_covered"])
        self.assertTrue(evidence["u37_center_in_same_filled_polygon"])
        self.assertAlmostEqual(evidence["c383_copper_overlap_mm2"], .62 ** 2, places=10)
        self.assertAlmostEqual(evidence["c383_center_mm"][0], 234.4784)


if __name__ == "__main__":
    unittest.main()
