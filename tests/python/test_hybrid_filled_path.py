# SPDX-License-Identifier: Apache-2.0
"""A retained source cutout must survive meshing and graph construction."""
import unittest
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.filled_copper_path import FilledCopperPath
from python.spike_core.hybrid_mesh import (
    _normalize_filled_zone_polygon, _point_in_polygon, _polygon_area,
    _polygon_is_contained_in, _segment_inside_polygon, _segments,
    build_hybrid_mesh,
)


def source_path():
    # The retraced connector traverses the void. It is source encoding, not
    # physical copper; its midpoint must not acquire tolerance-only occupancy.
    return [(0., 0.), (8., 0.), (8., 6.), (0., 6.), (0., 0.),
            (6., 4.), (6., 2.), (2., 2.), (2., 4.), (6., 4.)]


class HybridFilledPathTests(unittest.TestCase):
    def test_original_coordinates_and_physical_cutout_are_retained(self):
        source = source_path()
        domain = _normalize_filled_zone_polygon(source)
        self.assertIsInstance(domain, FilledCopperPath)
        self.assertEqual(list(domain), source)
        self.assertFalse(_point_in_polygon((4.5, 3.), domain, 1e-6))
        self.assertTrue(_point_in_polygon((1., 1.), domain, 1e-6))
        self.assertNotIn(((0., 0.), (6., 4.)), list(_segments(domain)))
        self.assertNotIn(((6., 4.), (0., 0.)), list(_segments(domain)))

    def test_cells_conserve_area_and_graph_never_crosses_cutout(self):
        source = source_path()
        domain = _normalize_filled_zone_polygon(source)
        design = SpiDeR(layers=[{'name': 'F.Cu'}], zones=[{
            'id': 'source-with-hole', 'layer': 'F.Cu', 'net_name': 'VCC',
            'points': source,
        }])
        mesh = build_hybrid_mesh(design, AnalysisSpec(mode='dc', net_names=['VCC'],
            mesh={'zone_cell_mm': 1., 'node_tolerance_mm': 10., 'max_zone_cells': 1000}))
        cells = [cell for cell in mesh.cells if cell['source_id'] == 'source-with-hole']
        self.assertEqual(mesh.geometry_counts['zone'], 1)
        self.assertFalse(mesh.truncated)
        self.assertFalse(any(issue.severity == 'error' for issue in mesh.issues))
        self.assertAlmostEqual(sum(_polygon_area([(p[0], p[1]) for p in cell['vertices_mm']])
                                   for cell in cells), 40., places=8)
        owners = [cell['node_id'] for cell in cells]
        self.assertEqual(len(owners), len(set(owners)))
        for cell in cells:
            self.assertTrue(_polygon_is_contained_in(
                [(p[0], p[1]) for p in cell['vertices_mm']], domain, 1e-6))
        adjacent = {index: set() for index in range(len(mesh.nodes))}
        for branch in mesh.branches:
            a, b = mesh.nodes[branch.node_p], mesh.nodes[branch.node_n]
            self.assertTrue(_segment_inside_polygon((a.x_mm, a.y_mm), (b.x_mm, b.y_mm), domain, 1e-6))
            adjacent[a.id].add(b.id)
            adjacent[b.id].add(a.id)
        reached, stack = set(), [owners[0]]
        while stack:
            index = stack.pop()
            if index not in reached:
                reached.add(index)
                stack.extend(adjacent[index]-reached)
        self.assertTrue(set(owners) <= reached)

    def test_narrow_hole_is_not_bridged_by_node_or_face_tolerance(self):
        source = [(0., 0.), (8., 0.), (8., 6.), (0., 6.), (0., 0.),
                  (4.00001, 4.), (4.00001, 2.), (4., 2.), (4., 4.), (4.00001, 4.)]
        domain = _normalize_filled_zone_polygon(source)
        mesh = build_hybrid_mesh(SpiDeR(layers=[{'name': 'F.Cu'}], zones=[{
            'id': 'narrow-hole', 'layer': 'F.Cu', 'net_name': 'VCC', 'points': source,
        }]), AnalysisSpec(mode='dc', net_names=['VCC'],
            mesh={'zone_cell_mm': 1., 'node_tolerance_mm': 10.}))
        self.assertEqual(mesh.geometry_counts['zone'], 1)
        self.assertFalse(any(issue.severity == 'error' for issue in mesh.issues))
        for branch in mesh.branches:
            a, b = mesh.nodes[branch.node_p], mesh.nodes[branch.node_n]
            self.assertTrue(_segment_inside_polygon(
                (a.x_mm, a.y_mm), (b.x_mm, b.y_mm), domain, 1e-10))

    def test_fragment_budget_failure_cannot_return_a_conductive_partial_graph(self):
        design = SpiDeR(layers=[{'name': 'F.Cu'}], zones=[{
            'id': 'source-with-hole', 'layer': 'F.Cu', 'net_name': 'VCC',
            'points': source_path(),
        }])
        with patch('python.spike_core.filled_copper_path.MAX_CELL_FRAGMENT_WORK', 0):
            mesh = build_hybrid_mesh(design, AnalysisSpec(mode='dc', net_names=['VCC'],
                mesh={'zone_cell_mm': 1.}))
        self.assertEqual(mesh.branches, [])
        self.assertTrue(any(issue.severity == 'error' and issue.status == 'failed'
                            for issue in mesh.issues))


if __name__ == '__main__':
    unittest.main()
