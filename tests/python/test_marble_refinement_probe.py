# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "marble_refinement_matrix_probe.py"
SPEC = importlib.util.spec_from_file_location("marble_refinement_matrix_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MarbleRefinementProbeTests(unittest.TestCase):
    def test_symmetric_pair_count_matches_refined_marble_mesh(self):
        self.assertEqual(MODULE.matrix_pair_count(120), 7260)

    def test_pair_count_rejects_invalid_branch_count(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            MODULE.matrix_pair_count(-1)

    def test_probe_default_matches_production_per_pair_budget(self):
        self.assertEqual(MODULE.probe.__defaults__, (2_000_000,))


if __name__ == "__main__":
    unittest.main()
