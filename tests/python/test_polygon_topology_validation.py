# SPDX-License-Identifier: Apache-2.0
"""Topology must distinguish crossings from dimensional tolerance bands."""
import unittest
from unittest.mock import patch

from python.spike_core.hybrid_mesh import _normalize_filled_zone_polygon, _polygon_is_simple


class PolygonTopologyTests(unittest.TestCase):
    def test_long_edge_near_miss_is_not_a_crossing(self):
        polygon = [(0., 0.), (100., 0.), (100.00005, -1.),
                   (100.00005, 1.), (0., 1.)]
        self.assertTrue(_polygon_is_simple(polygon, 1e-6))

    def test_short_perpendicular_edges_really_cross(self):
        polygon = [(-.0005, 0.), (.0005, 0.), (0., .0005),
                   (0., -.0005), (-.001, -.001)]
        self.assertFalse(_polygon_is_simple(polygon, 1e-6))

    def test_nonzero_area_self_crossing_is_rejected(self):
        polygon = [(0., 0.), (4., 0.), (0., 3.),
                   (4., 3.), (5., 4.), (0., 4.)]
        self.assertFalse(_polygon_is_simple(polygon))

    def test_backtracking_and_nonadjacent_touch_are_rejected(self):
        for polygon in (
            [(0., 0.), (2., 0.), (1., 0.), (1., 1.), (0., 1.)],
            [(0., 0.), (2., 0.), (1., 1.), (2., 2.),
             (0., 2.), (1., 1.)],
        ):
            self.assertFalse(_polygon_is_simple(polygon))

    def test_ordinary_duplicate_cleanup_and_admission_are_preserved(self):
        polygon = [(0., 0.), (2., 0.), (2., 0.), (2., 2.), (0., 2.)]
        expected = [(0., 0.), (2., 0.), (2., 2.), (0., 2.)]
        with patch('python.spike_core.filled_copper_path.MAX_SOURCE_VERTICES', 4):
            self.assertEqual(_normalize_filled_zone_polygon(polygon), expected)


if __name__ == '__main__':
    unittest.main()
