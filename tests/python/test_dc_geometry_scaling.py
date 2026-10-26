# SPDX-License-Identifier: Apache-2.0
"""Independent equivalence checks for batched tetrahedron geometry admission."""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import patch

import numpy as np

import python.spike_core.solvers.thermal_fluid.heat.assembly_tetra_thermal_validation as validation
from python.spike_core.solvers.thermal_fluid.heat.assembly_tetra_thermal_validation import AssemblyTetraThermalError, _hanging_node_audit, _overlap_audit
from python.spike_core.solvers.geometry_meshing.preparation.tetra_aabb_candidates import overlapping_pairs
from tests.python.test_assembly_tetra_thermal import cube


def scalar_overlap(xyz, cells):
    """Frozen pre-vectorization SAT calculation used only as an oracle."""
    points = [xyz[cell["vertices"]] for cell in cells]
    lows = np.array([point.min(0) for point in points])
    highs = np.array([point.max(0) for point in points])
    edges = [[point[j]-point[i] for i, j in itertools.combinations(range(4), 2)]
             for point in points]
    normals = [[np.cross(point[j]-point[i], point[k]-point[i])
                for i, j, k in itertools.combinations(range(4), 3)] for point in points]
    comparisons = 0
    for i, j in overlapping_pairs(lows, highs, validation.MAX_HIERARCHY_VISITS, validation.require):
        comparisons += 1
        validation.require(comparisons <= validation.MAX_COMPARISONS,
                           "Geometry comparison budget exceeded.")
        axes = np.concatenate((normals[i], normals[j],
            np.cross(np.array(edges[i])[:, None], np.array(edges[j])).reshape(-1, 3)))
        lengths = np.linalg.norm(axes, axis=1)
        axes = axes[lengths > 0]/lengths[lengths > 0, None]
        a = (points[i]-points[i][0])@axes.T
        b = (points[j]-points[i][0])@axes.T
        overlap = np.minimum(a.max(0), b.max(0))-np.maximum(a.min(0), b.min(0))
        tolerance = 1e-11*max(np.max(highs[i]-lows[i]), np.max(highs[j]-lows[j]))
        validation.require(np.any(overlap <= tolerance), "Overlapping tetrahedral solid interiors.")
    return comparisons


def audit(function, xyz, cells):
    try:
        return ("accepted", function(xyz, cells))
    except AssemblyTetraThermalError as error:
        return ("rejected", str(error))


class DCGeometryScalingTests(unittest.TestCase):
    def test_seeded_translated_rotated_pairs_match_scalar_all_axes(self):
        random = np.random.default_rng(1402)
        base = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        for index in range(96):
            matrix, _ = np.linalg.qr(random.normal(size=(3, 3)))
            scale = np.diag(random.uniform(.2, 1.8, 3))
            shift = random.uniform(-1.2, 1.2, 3)
            translated = (base@(matrix@scale).T)+shift
            origin = np.array([1e7, -2e7, 3e7]) if index % 3 == 0 else 0.
            xyz = np.vstack((base+origin, translated+origin))
            cells = [{"vertices": [0, 1, 2, 3]}, {"vertices": [4, 5, 6, 7]}]
            self.assertEqual(audit(scalar_overlap, xyz, cells), audit(_overlap_audit, xyz, cells))

    def test_conforming_grid_candidate_counter_matches_scalar(self):
        mesh = cube(2)
        xyz = np.asarray(mesh["vertices"], dtype=float)
        self.assertEqual(_overlap_audit(xyz, mesh["cells"]), scalar_overlap(xyz, mesh["cells"]))

    def test_overlap_and_comparison_budget_rejections_are_retained(self):
        first = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        xyz = np.vstack((first, first+np.array([.05, .05, .05])))
        cells = [{"vertices": [0, 1, 2, 3]}, {"vertices": [4, 5, 6, 7]}]
        self.assertEqual(audit(scalar_overlap, xyz, cells), audit(_overlap_audit, xyz, cells))
        self.assertEqual(audit(_overlap_audit, xyz, cells),
                         ("rejected", "Overlapping tetrahedral solid interiors."))
        with patch.object(validation, "MAX_COMPARISONS", 0):
            self.assertEqual(audit(scalar_overlap, xyz, cells), audit(_overlap_audit, xyz, cells))
            self.assertEqual(audit(_overlap_audit, xyz, cells),
                             ("rejected", "Geometry comparison budget exceeded."))

    def test_hanging_node_audit_remains_active(self):
        xyz = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
                        [.2, .2, .2]])
        gradients = np.vstack((-np.ones(3), np.eye(3)))
        with self.assertRaisesRegex(AssemblyTetraThermalError, "hanging vertex"):
            _hanging_node_audit(xyz, [{"vertices": [0, 1, 2, 3]}],
                                [(1/6, gradients)], [{"body"}],
                                [{"body"} for _ in xyz])


if __name__ == "__main__":
    unittest.main()
