# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Source-area oracles for the experimental zone/pad C surrogate.

These fixtures use exact rectangular areas and epsilon*A/d, independently of
the mesh branch count. They make no claim about electrostatic/fringing error.
"""

import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import build_hybrid_mesh
from python.spike_core.quasistatic_capacitance import EPSILON_0_F_M, estimate_branch_capacitance


def _design(polygon, *, pads=(), tracks=()):
    return DesignIR(
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        nets=[{"name": "N"}],
        stackup=[{"name": "F.Cu", "thickness": 0.035},
                 {"name": "core", "thickness": 0.2, "epsilon_r": 4.0},
                 {"name": "B.Cu", "thickness": 0.035}],
        zones=[{"id": "plane", "layer": "F.Cu", "net_name": "N", "points": polygon}],
        pads=list(pads), tracks=list(tracks))


def _estimate(design, h=0.5):
    spec = AnalysisSpec(mode="ac", net_names=["N"],
        mesh={"target_size_mm": h, "zone_cell_mm": h, "max_zone_cells": 1000},
        options={"peec_volume_extraction": "enabled"})
    mesh = build_hybrid_mesh(design, spec)
    values, _, info = estimate_branch_capacitance(design, spec, mesh.branches)
    return float(values.sum()), info


class CopperAreaUnionRegressionTests(unittest.TestCase):
    def assert_area(self, result, area_mm2):
        expected = EPSILON_0_F_M * 4.0 * area_mm2 / 0.2 * 1e-3
        self.assertAlmostEqual(result / expected, 1.0, places=9)

    def test_fixed_square_area_survives_actual_mesh_refinement(self):
        design = _design([(0, 0), (2, 0), (2, 2), (0, 2)])
        for h in (1.0, 0.5, 0.25):
            with self.subTest(h=h):
                value, info = _estimate(design, h)
                self.assertEqual(info["status"], "approximate")
                self.assert_area(value, 4.0)

    def test_pad_crossing_concave_notch_is_not_falsely_contained(self):
        # U area = 3*3 - 1*2 = 7 mm². The pad fills exactly 1 mm² of its notch.
        # Its four corners are all inside the U, so corner-only containment
        # would wrongly remove the pad's contribution to the copper union.
        design = _design([(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)],
            pads=[{"id": "bridge", "layer": "F.Cu", "layers": ["F.Cu"],
                   "net_name": "N", "shape": "rect", "at": [1.5, 1.7], "size": [2.6, 1.0]}])
        value, info = _estimate(design)
        # An explicitly unsupported union is safe; silently claiming the wrong
        # approximate area is not. Full approximation must match the union.
        if info["status"] == "unsupported":
            self.assertEqual(value, 0.0)
        else:
            self.assert_area(value, 8.0)

    def test_track_already_inside_zone_adds_no_second_copper_area(self):
        plain = _design([(0, 0), (2, 0), (2, 2), (0, 2)])
        with_track = _design([(0, 0), (2, 0), (2, 2), (0, 2)],
            tracks=[{"id": "inside", "layer": "F.Cu", "net_name": "N",
                     "start": [0.5, 1.0], "end": [1.5, 1.0], "width": 0.2}])
        baseline, _ = _estimate(plain)
        value, info = _estimate(with_track)
        if info["status"] == "unsupported":
            self.assertEqual(value, 0.0)
        else:
            self.assertAlmostEqual(value / baseline, 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
