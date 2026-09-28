# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Manufactured resistance/KCL check for the geometry-only sparse audit."""

import unittest

from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch, MeshNode
from scripts.audit_peec_refinement import _solve_sparse_dc


class SparseAuditTests(unittest.TestCase):
    def test_two_series_face_resistors(self):
        mesh = HybridMesh(nodes=[MeshNode(i, float(i), 0, 0, "F.Cu", "N") for i in range(3)])
        for i, width in enumerate((0.2, 0.1)):
            mesh.branches.append(MeshBranch(str(i), "zone", i, i + 1,
                (float(i), 0, 0), (float(i + 1), 0, 0), width, .035,
                5.8e7, "F.Cu", "N", "square"))
        voltage, currents, quality = _solve_sparse_dc(mesh, [0, 1, 2], [0, 1], 0, 2)
        expected = sum(branch.resistance_ohm for branch in mesh.branches)
        self.assertAlmostEqual(voltage, expected, places=12)
        self.assertAlmostEqual(float(currents[0]), 1, places=12)
        self.assertAlmostEqual(float(currents[1]), 1, places=12)
        self.assertLess(quality["relative_residual"], 1e-12)
        self.assertLess(quality["maximum_current_balance_a"], 1e-12)


if __name__ == "__main__":
    unittest.main()
