# SPDX-License-Identifier: Apache-2.0
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

    def test_short_real_face_is_symmetric_and_not_a_point_or_gap(self):
        size=5e-5
        tiny=[(0,0),(size,0),(size,size),(0,size)]
        neighbor=[(-1,0),(0,0),(0,1),(-1,1)]
        self.assertAlmostEqual(_shared_polygon_face_length(tiny,neighbor,.0001),size)
        self.assertAlmostEqual(_shared_polygon_face_length(neighbor,tiny,.0001),size)
        point_neighbor=[(size,size),(2*size,size),(2*size,2*size),(size,2*size)]
        self.assertEqual(_shared_polygon_face_length(tiny,point_neighbor,.0001),0)
        gap_neighbor=[(size+5e-8,0),(2*size,0),(2*size,size),(size+5e-8,size)]
        self.assertEqual(_shared_polygon_face_length(tiny,gap_neighbor,.0001),0)

    def test_audit_short_face_oracle(self):
        from scripts.audit_hybrid_zone_topology import shared_face_length
        triangle=[(0,0),(2e-5,0),(0,8e-5)]
        lower=[(-1,-1),(1,-1),(1,0),(-1,0)]
        for left,right in ((triangle,lower),(lower,triangle)):
            self.assertAlmostEqual(shared_face_length(left,right,.0001),2e-5,places=13)
        point=[(2e-5,0),(4e-5,0),(4e-5,8e-5),(2e-5,8e-5)]
        self.assertEqual(shared_face_length(triangle,point,.0001),0)
        separated=[(x,y-5e-8) for x,y in lower]
        self.assertEqual(shared_face_length(triangle,separated,.0001),0)

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
