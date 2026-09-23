# SPDX-License-Identifier: MIT
"""Independent geometric oracles for clipped copper face conductance widths."""
import math
import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import _shared_polygon_face_length, build_hybrid_mesh


class HybridZoneFaceWidthTests(unittest.TestCase):
    def test_full_and_clipped_faces(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertAlmostEqual(_shared_polygon_face_length(square, [(1, 0), (2, 0), (2, 1), (1, 1)]), 1.0)
        sliver = [(1, .4), (2, .4), (2, .401), (1, .401)]
        self.assertAlmostEqual(_shared_polygon_face_length(square, sliver), .001)
        self.assertAlmostEqual(_shared_polygon_face_length(sliver, square), .001)

    def test_point_contact_and_separate_islands_have_no_conductance_face(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertEqual(_shared_polygon_face_length(square, [(1, 1), (2, 1), (2, 2), (1, 2)]), 0)
        self.assertEqual(_shared_polygon_face_length(square, [(1.001, 0), (2, 0), (2, 1), (1.001, 1)]), 0)

    def test_diagonal_triangle_face(self):
        self.assertAlmostEqual(_shared_polygon_face_length([(0, 0), (1, 0), (0, 1)], [(1, 0), (1, 1), (0, 1)]), math.sqrt(2))

    def test_existing_containment_tolerance_recognizes_numerical_seams(self):
        left = [(0, 0), (1, 0), (1, 1), (0, 1)]
        right = [(1.000005, 0), (2, 0), (2, 1), (1.000005, 1)]
        self.assertEqual(_shared_polygon_face_length(left, right), 0)
        self.assertAlmostEqual(_shared_polygon_face_length(left, right, tolerance=.0001), 1)

    def test_final_partial_grid_row_uses_actual_face_width(self):
        mesh = build_hybrid_mesh(
            DesignIR(layers=[{"name": "F.Cu"}], zones=[{
                "id": "rectangle", "net_name": "VCC", "layer": "F.Cu",
                "points": [(0, 0), (2, 0), (2, 1.25), (0, 1.25)],
            }]),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 1, "zone_cell_mm": 1}),
        )
        horizontal = [b for b in mesh.branches if b.kind == "zone" and abs(b.start_mm[1] - b.end_mm[1]) < 1e-8]
        self.assertEqual(len(horizontal), 2)
        self.assertEqual(sorted(round(b.width_mm, 8) for b in horizontal), [.25, 1.0])
        for branch in horizontal:
            expected = branch.length_mm * 1e-3 / (5.8e7 * branch.width_mm * .035e-6)
            self.assertAlmostEqual(branch.resistance_ohm, expected)

    def test_submicrometre_face_is_not_widened_by_generic_branch_floor(self):
        mesh = build_hybrid_mesh(
            DesignIR(layers=[{"name": "F.Cu"}], zones=[{
                "id": "sliver", "net_name": "VCC", "layer": "F.Cu",
                "points": [(0, 0), (2, 0), (2, 1.0005), (0, 1.0005)],
            }]),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"zone_cell_mm": 1}),
        )
        widths = sorted(b.width_mm for b in mesh.branches if b.kind == "zone")
        self.assertAlmostEqual(widths[0], .0005)


if __name__ == "__main__":
    unittest.main()
