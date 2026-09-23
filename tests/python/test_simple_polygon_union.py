import unittest

from python.core.simple_polygon_union import union_two_simple_polygons


class SimplePolygonUnionTests(unittest.TestCase):
    def test_overlapping_anchor_and_primitive_form_one_ccw_boundary(self):
        resolved = union_two_simple_polygons(
            [[0, -2], [2, -2], [2, 2], [0, 2]],
            [[-1, -1], [1, -1], [1, 1], [-1, 1]],
        )
        self.assertEqual(
            resolved,
            [[-1.0, -1.0], [0.0, -1.0], [0.0, -2.0], [2.0, -2.0],
             [2.0, 2.0], [0.0, 2.0], [0.0, 1.0], [-1.0, 1.0]],
        )

    def test_shared_edge_is_removed_from_the_union_interior(self):
        resolved = union_two_simple_polygons(
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            [[1, 0], [2, 0], [2, 1], [1, 1]],
        )
        self.assertEqual(resolved[0], [0.0, 0.0])
        self.assertNotIn([[1.0, 0.0], [1.0, 1.0]], [
            [resolved[index], resolved[(index + 1) % len(resolved)]]
            for index in range(len(resolved))
        ])

    def test_contained_anchor_preserves_the_outer_primitive(self):
        outer = [[-2, -2], [2, -2], [2, 2], [-2, 2]]
        self.assertEqual(
            union_two_simple_polygons(outer, [[-1, -1], [1, -1], [1, 1], [-1, 1]]),
            [[float(x), float(y)] for x, y in outer],
        )

    def test_disjoint_or_point_touching_inputs_fail_closed(self):
        left = [[0, 0], [1, 0], [1, 1], [0, 1]]
        self.assertEqual(union_two_simple_polygons(left, [[2, 0], [3, 0], [3, 1], [2, 1]]), [])
        self.assertEqual(union_two_simple_polygons(left, [[1, 1], [2, 1], [2, 2], [1, 2]]), [])


if __name__ == "__main__":
    unittest.main()
