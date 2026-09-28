# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""The offline RT0 audit must fail closed on incomplete or drifting evidence."""

import unittest

from scripts.audit_peec_rt0_refinement import evaluate_rows


def row(resistance: float) -> dict:
    return {"status": "completed", "resistance_ohm": resistance,
        "routed_connected": True, "disconnected_rejected": True,
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
                             ("disconnected_rejected", False),
                             ("relative_residual", 1e-6),
                             ("maximum_cell_kcl_error_a", 1e-7),
                             ("maximum_face_kcl_error_a", 1e-7),
                             ("relative_energy_error", 1e-6)):
            with self.subTest(field=field):
                rows = [dict(item) for item in good]
                rows[1][field] = value
                self.assertFalse(evaluate_rows(rows)[0])


if __name__ == "__main__":
    unittest.main()
