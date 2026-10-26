# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import math
import unittest
from unittest.mock import patch

from python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing import PcbFocusSizingError, assess_focus_mesh, plan_focus_regions, target_size_at


def prism(identifier, outer, z0=0, z1=.1):
    return {'id': identifier, 'material_id': 'copper', 'priority': 1,
            'shape': {'kind': 'polygon_prism', 'outer_mm': outer, 'holes_mm': [],
                      'z_min_mm': z0, 'z_max_mm': z1}}


def tube(identifier, x, y):
    return {'id': identifier, 'material_id': 'copper', 'priority': 2,
            'shape': {'kind': 'tube', 'center_mm': [x, y], 'outer_radius_mm': .3,
                      'inner_radius_mm': .1, 'z_min_mm': 0, 'z_max_mm': 1}}


def solid_fixture():
    solids = [
        prism('trace-a', [[0, 0], [2, 2], [2.2, 1.8], [.2, -.2]]),
        prism('trace-b', [[10, 0], [12, 0], [12, .2], [10, .2]]),
        prism('plane', [[-5, -5], [20, -5], [20, 5], [-5, 5]]),
        tube('via-1', 5, 1),
        prism('board', [[-6, -6], [21, -6], [21, 6], [-6, 6]], -.5, 1.5),
    ]
    metadata = {
        'trace-a': {'kind': 'track', 'net': 'PWR', 'layer': 'F.Cu'},
        'trace-b': {'kind': 'track', 'net': 'PWR', 'layer': 'F.Cu'},
        'plane': {'kind': 'zone', 'net': 'GND', 'layer': 'In1.Cu'},
        'via-1': {'kind': 'via', 'net': 'SIG', 'layer': '*.Cu'},
        'board': {'kind': 'substrate', 'layer': 'dielectric'},
    }
    return solids, metadata


def policy(**updates):
    value = {'contract': 'spike/pcb-focus-sizing/v1', 'net_names': ['PWR'],
             'source_ids': [], 'fine_size_mm': .1, 'coarse_size_mm': 2.0,
             'halo_mm': .5, 'growth_rate': .5, 'regions': []}
    value.update(updates)
    return value


def two_cell_mesh(units='mm', shift=0):
    scale = .001 if units == 'm' else 1.0
    points_mm = [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2],
                 [20, 20, 20], [22, 20, 20], [20, 22, 20], [20, 20, 22]]
    points = [[(coordinate + shift) * scale for coordinate in point] for point in points_mm]
    cells = [{'id': 'near', 'kind': 'tetrahedron', 'vertices': [0, 1, 2, 3],
              'material_id': 'copper', 'source_object_ids': ['part']},
             {'id': 'far', 'kind': 'tetrahedron', 'vertices': [4, 5, 6, 7],
              'material_id': 'copper', 'source_object_ids': ['part']}]
    return {'contract': 'spike/solver-mesh/v1', 'units': units,
            'coordinate_system': 'right_handed_xyz', 'vertices': points, 'cells': cells,
            'counts': {'vertices': len(points), 'cells': len(cells)},
            'object_map': {'part': {'kind': 'solid'}}}


def region(bounds=None):
    return {'id': 'r', 'bounds_mm': bounds or [[0, 0, 0], [1, 1, 1]],
            'target_size_mm': 1.0, 'halo_mm': 2.0, 'growth_rate': .5}


class PcbFocusSizingTests(unittest.TestCase):
    def test_small_translated_polygon_uses_recentered_area(self):
        side = 2 ** -10
        origin = 100_000.0
        outer = [[origin, origin], [origin + side, origin],
                 [origin + side, origin + side], [origin, origin + side]]
        solids = [prism('tiny-translated', outer)]
        metadata = {'tiny-translated': {'kind': 'track', 'net': 'PWR', 'layer': 'F.Cu'}}
        result = plan_focus_regions(solids, metadata, policy())
        self.assertEqual(result['regions'][0]['bounds_mm'],
                         [[origin, origin, 0.0],
                          [origin + side, origin + side, .1]])

    def test_polygon_loop_can_exceed_legacy_2048_point_limit(self):
        count = 2_049
        outer = [[10 * math.cos(2 * math.pi * index / count),
                  10 * math.sin(2 * math.pi * index / count)]
                 for index in range(count)]
        solids = [prism('dense-outline', outer)]
        metadata = {'dense-outline': {'kind': 'zone', 'net': 'PWR', 'layer': 'F.Cu'}}
        result = plan_focus_regions(solids, metadata, policy(), include_solids=False)
        self.assertNotIn('solids', result)
        self.assertEqual(result['evidence']['source_box_count'], 1)

    def test_point_size_formula_transition_boundaries_and_far_cap(self):
        regions = [region()]
        self.assertEqual(target_size_at([.5, .5, .5], regions, 5), 1)
        self.assertEqual(target_size_at([3, .5, .5], regions, 5), 1)  # halo edge
        self.assertEqual(target_size_at([5, .5, .5], regions, 5), 2)
        self.assertEqual(target_size_at([11, .5, .5], regions, 5), 5)  # coarse transition
        self.assertEqual(target_size_at([100, .5, .5], regions, 5), 5)
        second = {**region([[4, 0, 0], [4, 1, 1]]), 'id': 'second',
                  'target_size_mm': .25, 'halo_mm': 0, 'growth_rate': 1}
        self.assertEqual(target_size_at([4, .5, .5], regions + [second], 5), .25)

    def test_monotonic_growth_lipschitz_and_translation(self):
        regions = [region()]
        samples = [target_size_at([x, .5, .5], regions, 5) for x in range(1, 15)]
        self.assertEqual(samples, sorted(samples))
        for left, right in zip(samples, samples[1:]):
            self.assertLessEqual(abs(right - left), .5 + 1e-14)
        shifted = [region([[100, -20, 7], [101, -19, 8]])]
        for point in ([.5, .5, .5], [5, -1, 2], [20, 10, 4]):
            moved = [point[0] + 100, point[1] - 20, point[2] + 7]
            self.assertEqual(target_size_at(point, regions, 5),
                             target_size_at(moved, shifted, 5))

    def test_net_source_and_manual_union_retains_all_solids_without_net_merging(self):
        solids, metadata = solid_fixture()
        request = policy(net_names=['PWR', 'GND'], source_ids=['via-1'],
                         regions=[{'id': 'plane-window',
                                   'bounds_mm': [[1, 1, .02], [2, 2, .02]],
                                   'target_size_mm': .05}])
        snapshot = copy.deepcopy((solids, metadata, request))
        result = plan_focus_regions(solids, metadata, request)
        self.assertEqual((solids, metadata, request), snapshot)
        self.assertEqual(result['solids'], solids)
        self.assertEqual(result['evidence']['retained_solid_count'], len(solids))
        self.assertFalse(result['evidence']['geometry_cropped'])
        self.assertEqual(result['evidence']['selected_source_ids'],
                         ['plane', 'trace-a', 'trace-b', 'via-1'])
        source_regions = [item for item in result['regions'] if item['id'].startswith('source:')]
        self.assertEqual(len(source_regions), 4)
        self.assertIn('source:trace-a', {item['id'] for item in source_regions})
        self.assertIn('source:trace-b', {item['id'] for item in source_regions})
        plane = next(item for item in source_regions if item['id'] == 'source:plane')
        self.assertEqual(plane['bounds_mm'], [[-5.0, -5.0, 0.0], [20.0, 5.0, .1]])
        manual = next(item for item in result['regions'] if item['id'] == 'manual:plane-window')
        self.assertEqual(manual['bounds_mm'], [[1.0, 1.0, .02], [2.0, 2.0, .02]])

    def test_diagonal_source_uses_conservative_box_not_exact_shape_distance(self):
        solids, metadata = solid_fixture()
        result = plan_focus_regions(solids, metadata, policy(source_ids=['trace-a'], net_names=[]))
        box = result['regions'][0]
        self.assertEqual(box['bounds_mm'], [[0.0, -.2, 0.0], [2.2, 2.0, .1]])
        # This box corner is not on the narrow diagonal copper shape but is intentionally focused.
        self.assertEqual(target_size_at([0, 2, .05], result['regions'], 2), .1)
        self.assertIn('not_exact_shape_distance', result['evidence']['distance_model'])

    def test_manual_region_alone_is_valid_and_partial_plane_capable(self):
        solids, metadata = solid_fixture()
        request = policy(net_names=[], regions=[{'id': 'partial',
                                                'bounds_mm': [[2, 2, 0], [4, 3, 0]],
                                                'target_size_mm': .2}])
        result = plan_focus_regions(solids, metadata, request)
        self.assertEqual(result['evidence']['selected_source_ids'], [])
        self.assertEqual(result['evidence']['manual_box_count'], 1)
        self.assertEqual(result['solids'], solids)

    def test_mesh_assessment_converts_units_and_retains_near_and_far_cells(self):
        focus = [{**region([[0, 0, 0], [1, 1, 1]]), 'halo_mm': 0, 'growth_rate': 1}]
        mm = assess_focus_mesh(two_cell_mesh('mm'), focus, 2)
        metres = assess_focus_mesh(two_cell_mesh('m'), focus, 2)
        self.assertEqual(mm['cell_assessments'], metres['cell_assessments'])
        self.assertEqual(mm['counts'], {'cells': 2, 'near_focus': 1,
                                        'far_field': 1, 'above_target': 2})
        self.assertEqual(mm['mesh'], two_cell_mesh('mm'))
        self.assertTrue(mm['all_cells_retained'])
        near = mm['cell_assessments'][0]
        self.assertEqual(near['centroid_mm'], [.5, .5, .5])
        self.assertAlmostEqual(near['longest_edge_mm'], math.sqrt(8))
        self.assertAlmostEqual(near['edge_to_target_ratio'], math.sqrt(8))
        self.assertEqual(metres['coordinate_conversion'], 'm_to_mm')

    def test_mesh_and_regions_translate_together_without_changing_assessment(self):
        base_region = [{**region([[0, 0, 0], [1, 1, 1]]), 'halo_mm': 0, 'growth_rate': 1}]
        shift = 100
        shifted_region = [{**base_region[0],
                           'bounds_mm': [[value + shift for value in point]
                                         for point in base_region[0]['bounds_mm']]}]
        base = assess_focus_mesh(two_cell_mesh('mm'), base_region, 2)
        moved = assess_focus_mesh(two_cell_mesh('mm', shift), shifted_region, 2)
        for old, new in zip(base['cell_assessments'], moved['cell_assessments']):
            self.assertEqual(old['target_size_mm'], new['target_size_mm'])
            self.assertAlmostEqual(old['longest_edge_mm'], new['longest_edge_mm'])
            self.assertAlmostEqual(old['edge_to_target_ratio'], new['edge_to_target_ratio'])

    def test_bvh_assessment_matches_direct_exact_minimum(self):
        regions = []
        for index in range(20):
            regions.append({'id': f'r{index}',
                            'bounds_mm': [[index * 3, -index, 0],
                                          [index * 3 + 1, 1 - index, 1]],
                            'target_size_mm': .1 + .01 * index,
                            'halo_mm': .05 * (index % 3),
                            'growth_rate': .2 + .1 * (index % 5)})
        result = assess_focus_mesh(two_cell_mesh(), regions, 5)
        for item in result['cell_assessments']:
            expected = target_size_at(item['centroid_mm'], regions, 5)
            self.assertAlmostEqual(item['target_size_mm'], expected, places=14)
        self.assertEqual(result['evaluation'], 'exact_bvh_with_bounded_region_comparisons')
        self.assertLessEqual(result['region_cell_comparisons'], 40)

    def test_unknown_selectors_metadata_and_empty_policy_reject(self):
        solids, metadata = solid_fixture()
        for request in (policy(net_names=['MISSING']), policy(source_ids=['missing']),
                        policy(net_names=[], source_ids=[], regions=[])):
            with self.subTest(request=request), self.assertRaises(PcbFocusSizingError):
                plan_focus_regions(solids, metadata, request)
        bad_metadata = {**metadata, 'missing': {'kind': 'track', 'net': 'PWR'}}
        with self.assertRaises(PcbFocusSizingError):
            plan_focus_regions(solids, bad_metadata, policy())

    def test_malformed_policy_geometry_numbers_and_exact_fields_reject(self):
        solids, metadata = solid_fixture()
        mutations = [
            lambda p: p.update(extra=True),
            lambda p: p.update(contract='future'),
            lambda p: p.update(net_names=['PWR', 'PWR']),
            lambda p: p.update(fine_size_mm=True),
            lambda p: p.update(fine_size_mm=0),
            lambda p: p.update(coarse_size_mm=.01),
            lambda p: p.update(halo_mm=-1),
            lambda p: p.update(growth_rate=1.1),
            lambda p: p.update(growth_rate=math.nan),
            lambda p: p.update(regions=[{'id': 'x', 'bounds_mm': [[1, 0, 0], [0, 1, 1]],
                                         'target_size_mm': .1}]),
        ]
        for mutation in mutations:
            request = policy()
            mutation(request)
            with self.subTest(request=request), self.assertRaises(PcbFocusSizingError):
                plan_focus_regions(solids, metadata, request)
        broken = copy.deepcopy(solids)
        broken[0]['shape']['outer_mm'][0][0] = float('inf')
        with self.assertRaises(PcbFocusSizingError):
            plan_focus_regions(broken, metadata, policy())
        broken = copy.deepcopy(solids)
        broken[0]['shape']['kind'] = 'step_file'
        with self.assertRaises(PcbFocusSizingError):
            plan_focus_regions(broken, metadata, policy())

    def test_resource_caps_and_malformed_mesh_reject(self):
        solids, metadata = solid_fixture()
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing.MAX_GENERATED_REGIONS', 1):
            with self.assertRaisesRegex(PcbFocusSizingError, 'budget'):
                plan_focus_regions(solids, metadata, policy())
        two_regions = [{'id': str(index), 'bounds_mm': [[0, 0, 0], [1, 1, 1]],
                        'target_size_mm': .1} for index in range(2)]
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing.MAX_MANUAL_REGIONS', 1):
            with self.assertRaisesRegex(PcbFocusSizingError, '4096'):
                plan_focus_regions(solids, metadata, policy(net_names=[], regions=two_regions))
        focus = [{**region(), 'halo_mm': 0, 'growth_rate': 1}]
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing.MAX_MESH_CELLS', 1):
            with self.assertRaisesRegex(PcbFocusSizingError, 'budget'):
                assess_focus_mesh(two_cell_mesh(), focus, 2)
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_focus_sizing.MAX_ASSESSMENT_COMPARISONS', 0):
            with self.assertRaisesRegex(PcbFocusSizingError, 'comparison budget'):
                assess_focus_mesh(two_cell_mesh(), focus, 2)
        for mutation in (lambda m: m.update(units='inch'),
                         lambda m: m['vertices'][0].__setitem__(0, True),
                         lambda m: m['cells'][0].update(vertices=[1, 0, 2, 3]),
                         lambda m: m['counts'].update(cells=3),
                         lambda m: m['object_map']['part'].update(kind='')):
            mesh = two_cell_mesh()
            mutation(mesh)
            with self.subTest(mesh=str(mesh)[:120]), self.assertRaises(PcbFocusSizingError):
                assess_focus_mesh(mesh, focus, 2)


if __name__ == '__main__':
    unittest.main()
