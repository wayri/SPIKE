# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original normalized PCB fixtures; no external board or CAD data."""
import copy
import importlib.util
import math
import unittest
from unittest.mock import patch

from python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_compiler import compile_pcb_volume_model, PcbVolumeError


def rectangle(x0, y0, x1, y1):
    return [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]


def model():
    return {'contract': 'spike/pcb-volume-model/v1', 'copper_material_id': 'copper',
            'drill_material_id': 'air',
            'board': {'id': 'board', 'outer_mm': rectangle(0,0,10,8),
                      'holes_mm': [rectangle(7,5,8,6)]},
            'layers': [{'id': name, 'z_min_mm': low, 'z_max_mm': high,
                        'background_material_id': 'fr4'}
                       for name, low, high in [('top',0,.035), ('core1',.035,.5),
                                                ('inner',.5,.535), ('core2',.535,1),
                                                ('bottom',1,1.035)]],
            'copper': [
                {'id': 'pad_a_top', 'net': 'A', 'layer_id': 'top',
                 'outer_mm': rectangle(1.5,1.5,2.5,2.5), 'holes_mm': []},
                {'id': 'pad_a_bottom', 'net': 'A', 'layer_id': 'bottom',
                 'outer_mm': rectangle(1.5,1.5,2.5,2.5), 'holes_mm': []},
                {'id': 'pad_b_top', 'net': 'B', 'layer_id': 'top',
                 'outer_mm': rectangle(4.5,1.5,5.5,2.5), 'holes_mm': []},
                {'id': 'pad_b_inner', 'net': 'B', 'layer_id': 'inner',
                 'outer_mm': rectangle(4.5,1.5,5.5,2.5), 'holes_mm': []},
                {'id': 'pad_c_inner', 'net': 'C', 'layer_id': 'inner',
                 'outer_mm': rectangle(5.8,2.8,6.2,3.2), 'holes_mm': []}],
            'vias': [{'id': name, 'net': net, 'z_min_mm': low, 'z_max_mm': high,
                      'center_mm': center, 'outer_radius_mm': .15, 'inner_radius_mm': .1}
                     for name, net, low, high, center in [
                         ('through_a','A',0,1.035,[2,2]), ('blind_b','B',0,.535,[5,2]),
                         ('buried_c','C',.035,1,[6,3])]]}


class PcbVolumeDependencyTests(unittest.TestCase):
    def test_dependency_failure_is_explicit(self):
        with patch.dict('sys.modules', {'shapely': None, 'shapely.geometry': None}):
            with self.assertRaisesRegex(PcbVolumeError, 'PCB_VOLUME_DEPENDENCY'):
                compile_pcb_volume_model(model())


@unittest.skipUnless(importlib.util.find_spec('shapely'), 'Optional Shapely runtime unavailable')
class PcbVolumeCompilerTests(unittest.TestCase):
    def test_output_shapes_pass_independent_occ_admission_without_allocation(self):
        from python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_mesher import validate_request
        result = compile_pcb_volume_model(model())
        # This small fixture also fits the legacy shape admission budget. The
        # compiler does not require or instantiate the Gmsh native runtime.
        validate_request({'contract': 'spike/gmsh-occ-mesh/v1', 'solids': result['solids'],
                          'mesh': {'min_size_mm': .01, 'max_size_mm': 1.,
                                   'max_cells': 100000, 'max_vertices': 100000}})

    def test_multilayer_full_board_through_blind_buried_and_source_ownership(self):
        original = model()
        snapshot = copy.deepcopy(original)
        result = compile_pcb_volume_model(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(result, compile_pcb_volume_model(original))
        solids = {solid['id']: solid for solid in result['solids']}
        self.assertEqual(len(solids), 16)
        self.assertEqual(set(solids), set(result['object_metadata']))
        self.assertEqual(result['evidence']['net_ids'], ['A','B','C'])
        self.assertTrue(result['evidence']['all_declared_nets_retained'])
        self.assertFalse(result['evidence']['roi_cropping'])
        self.assertFalse(result['evidence']['production_qualified'])
        self.assertEqual(result['evidence']['board_area_mm2'], 79)
        for layer in original['layers']:
            slab = solids['layer:'+layer['id']]
            self.assertEqual(slab['priority'], 0)
            self.assertEqual(slab['shape']['outer_mm'], original['board']['outer_mm'])
            self.assertEqual(slab['shape']['holes_mm'], original['board']['holes_mm'])
        for feature in original['copper']:
            shape = solids[feature['id']]['shape']
            layer = next(layer for layer in original['layers'] if layer['id'] == feature['layer_id'])
            self.assertEqual((shape['z_min_mm'], shape['z_max_mm']), (layer['z_min_mm'], layer['z_max_mm']))
            self.assertEqual(shape['outer_mm'], feature['outer_mm'])
            self.assertEqual(result['object_metadata'][feature['id']],
                             {'kind':'copper', 'net':feature['net'], 'layer':feature['layer_id']})
        for via in original['vias']:
            barrel, drill = solids[via['id']], solids[via['id']+'__drill']
            self.assertEqual(barrel['priority'], 10)
            self.assertEqual(drill['priority'], 20)
            self.assertEqual(drill['material_id'], 'air')
            self.assertEqual(drill['shape']['outer_radius_mm'], via['inner_radius_mm'])
            self.assertEqual(drill['shape']['inner_radius_mm'], 0)
            for key in ('z_min_mm', 'z_max_mm', 'center_mm'):
                self.assertEqual(barrel['shape'][key], via[key])
                self.assertEqual(drill['shape'][key], via[key])
        # Returned geometry is independent both of input and sibling slabs.
        result['solids'][0]['shape']['outer_mm'][0][0] = -99
        self.assertEqual(original, snapshot)
        self.assertEqual(result['solids'][1]['shape']['outer_mm'][0][0], 0)

    def test_concave_outline_and_hole_not_bounding_rectangle(self):
        value = model()
        value['copper'], value['vias'] = [], []
        value['board']['outer_mm'] = [[0,0],[6,0],[6,4],[3,4],[3,2],[0,2]]
        value['board']['holes_mm'] = [rectangle(4,1,5,2)]
        result = compile_pcb_volume_model(value)
        self.assertEqual(result['evidence']['board_area_mm2'], 17)
        for bad in (rectangle(.5,2.5,1,3), rectangle(4.2,1.2,4.8,1.8)):
            value['copper'] = [{'id':'bad', 'net':'N', 'layer_id':'top', 'outer_mm':bad, 'holes_mm':[]}]
            with self.assertRaisesRegex(PcbVolumeError, 'actual board outline'):
                compile_pcb_volume_model(value)
        # A polygon's vertices can all be in the board while an edge traverses
        # the concave notch. Covers must inspect the entire polygon geometry.
        value['copper'][0]['outer_mm'] = [[1,1],[5,1],[5,3],[4,3],[1,1.9]]
        with self.assertRaisesRegex(PcbVolumeError, 'actual board outline'):
            compile_pcb_volume_model(value)

    def test_same_net_union_sources_preserved_cross_net_overlap_and_contact_rejected(self):
        value = model()
        duplicate = copy.deepcopy(value['copper'][0])
        duplicate['id'] = 'trace_a'
        value['copper'].append(duplicate)
        result = compile_pcb_volume_model(value)
        self.assertIn('trace_a', result['object_metadata'])
        self.assertIn('pad_a_top', result['object_metadata'])
        duplicate['net'] = 'OTHER'
        for ring in (rectangle(1.8,1.8,2.8,2.8), rectangle(2.5,1.5,3,2.5)):
            duplicate['outer_mm'] = ring
            with self.assertRaisesRegex(PcbVolumeError, 'Cross-net copper'):
                compile_pcb_volume_model(value)

    def test_foreign_net_different_z_is_valid_but_z_face_contact_is_rejected(self):
        value = model()
        value['vias'] = []
        value['copper'] = value['copper'][:2]
        value['copper'][1]['net'] = 'OTHER'
        compile_pcb_volume_model(value)
        value['copper'][1]['layer_id'] = 'core1'
        with self.assertRaisesRegex(PcbVolumeError, 'Cross-net copper'):
            compile_pcb_volume_model(value)

    def test_drill_and_barrel_require_foreign_net_antipad(self):
        value = model()
        value['copper'] = [{'id':'plane', 'net':'GROUND', 'layer_id':'top',
                            'outer_mm':rectangle(.2,.2,6.8,4.8), 'holes_mm':[]}]
        value['vias'] = value['vias'][:1]
        with self.assertRaisesRegex(PcbVolumeError, 'drill intersects foreign-net'):
            compile_pcb_volume_model(value)
        value['copper'][0]['holes_mm'] = [rectangle(1.5,1.5,2.5,2.5)]
        compile_pcb_volume_model(value)
        # Clears the drill but not the outer barrel, hence remains a short.
        value['copper'][0]['holes_mm'] = [rectangle(1.88,1.88,2.12,2.12)]
        with self.assertRaisesRegex(PcbVolumeError, 'barrel contacts foreign-net'):
            compile_pcb_volume_model(value)

    def test_analytic_via_circle_containment_and_cross_via_contacts(self):
        value = model()
        value['copper'] = []
        value['vias'] = value['vias'][:1]
        via = value['vias'][0]
        for center in ([.1,2], [7.1,5.5], [6.9,5.5], [.15,2]):
            via['center_mm'] = center
            with self.subTest(center=center), self.assertRaisesRegex(PcbVolumeError, 'Via outer circle'):
                compile_pcb_volume_model(value)
        via['center_mm'] = [2,2]
        other = {**copy.deepcopy(via), 'id':'other', 'net':'OTHER', 'center_mm':[2.2,2]}
        value['vias'].append(other)
        with self.assertRaisesRegex(PcbVolumeError, 'Foreign-net via'):
            compile_pcb_volume_model(value)
        other['net'] = 'A'
        compile_pcb_volume_model(value)

    def test_source_ids_all_global_and_generated_collisions_rejected(self):
        changes = [lambda v: v['copper'][0].update(id='board'),
                   lambda v: v['copper'][0].update(id='top'),
                   lambda v: v['copper'][0].update(id='layer:top'),
                   lambda v: v['copper'][0].update(id='through_a__drill'),
                   lambda v: v['layers'][0].update(id='x'*251),
                   lambda v: v['vias'][0].update(id='x'*250)]
        for change in changes:
            value = model()
            change(value)
            with self.subTest(change=change), self.assertRaises(PcbVolumeError):
                compile_pcb_volume_model(value)

    def test_invalid_geometry_contract_materials_and_spans(self):
        changes = [lambda v: v.update(contract='other'), lambda v: v.update(extra=True),
                   lambda v: v.pop('copper_material_id'), lambda v: v.update(drill_material_id='copper'),
                   lambda v: v['layers'][0].update(background_material_id='copper'),
                   lambda v: v['layers'][1].update(z_min_mm=.036),
                   lambda v: v['layers'][1].update(z_min_mm=.034),
                   lambda v: v['layers'].reverse(), lambda v: v['layers'].clear(),
                   lambda v: v['copper'][0].update(layer_id='absent'),
                   lambda v: v['copper'][0].update(net=''),
                   lambda v: v['vias'][0].update(z_min_mm=-1),
                   lambda v: v['vias'][0].update(z_max_mm=2),
                   lambda v: v['vias'][0].update(inner_radius_mm=0),
                   lambda v: v['vias'][0].update(inner_radius_mm=.15),
                   lambda v: v['vias'][0].update(outer_radius_mm=True),
                   lambda v: v['vias'][0].update(center_mm=[math.nan,2]),
                   lambda v: v['board'].update(outer_mm=[[0,0],[2,2],[0,2],[2,0]]),
                   lambda v: v['board']['outer_mm'].append([0,0]),
                   lambda v: v['board'].update(holes_mm=[rectangle(9,7,11,9)]),
                   lambda v: v['board'].update(holes_mm=[rectangle(1,1,2,2), rectangle(2,1,3,2)]),
                   lambda v: v['board'].update(holes_mm=[rectangle(0,1,2,2)]),
                   lambda v: v['board']['outer_mm'][0].__setitem__(0,10**1000)]
        for index, change in enumerate(changes):
            value = model()
            change(value)
            with self.subTest(index=index), self.assertRaises(PcbVolumeError):
                compile_pcb_volume_model(value)

    def test_resource_limits_before_expansion_and_pair_work(self):
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_compiler.MAX_SOLIDS', 15):
            with self.assertRaisesRegex(PcbVolumeError, 'solid budget'):
                compile_pcb_volume_model(model())
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_compiler.MAX_POLYGON_POINTS', 39):
            with self.assertRaisesRegex(PcbVolumeError, 'Expanded output polygon'):
                compile_pcb_volume_model(model())
        with patch('python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_compiler.MAX_PAIR_CHECKS', 0):
            with self.assertRaisesRegex(PcbVolumeError, 'pair-work budget'):
                compile_pcb_volume_model(model())


if __name__ == '__main__':
    unittest.main()
