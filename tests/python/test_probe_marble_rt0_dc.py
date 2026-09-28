# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Safety and output-contract checks for the Marble-only diagnostic."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.probe_marble_rt0_dc import _partition_summary, probe


class MarbleRT0ProbeTests(unittest.TestCase):
    def test_partition_summary_omits_unbounded_contact_records(self):
        summary = _partition_summary({
            "method": "interior_rectangles_shared_face_flux",
            "groups": [{"layer": "B.Cu", "omitted_area_fraction": 0.01}],
            "visited_box_count": 42,
            "terminal_contacts": [{"source_id": str(index)} for index in range(1000)],
        })
        self.assertEqual(summary["visited_box_count"], 42)
        self.assertEqual(len(summary["groups"]), 1)
        self.assertNotIn("terminal_contacts", summary)

    def test_unattainable_refinement_and_bad_budgets_fail_before_import(self):
        with TemporaryDirectory() as directory:
            board = Path(directory) / "dummy.kicad_pcb"
            board.write_text("not a board", encoding="utf-8")
            for kwargs in (
                {"size_mm": 0.049},
                {"size_mm": float("nan")},
                {"size_mm": 0.1, "area_limit": float("nan")},
                {"size_mm": 0.1, "boundary_depth": -1},
                {"size_mm": 0.1, "max_unknowns": 0},
                {"size_mm": 0.1, "solver": "unbounded"},
                {"size_mm": 0.1, "max_iterations": 0},
                {"size_mm": 0.1, "timeout_s": float("inf")},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    probe(board, **kwargs)

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                probe(board, 0.1)


if __name__ == "__main__":
    unittest.main()
