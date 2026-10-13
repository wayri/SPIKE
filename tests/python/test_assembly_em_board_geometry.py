# SPDX-License-Identifier: Apache-2.0
"""Original small polygon studies with independent area and ownership checks."""
import copy
import unittest
from shapely.geometry import Polygon

from python.spike_core.assembly_em_board_geometry import prepare_routed_board_volume


def fixture():
    def rectangle(x0,y0,x1,y1):
        return {'outer_mm':[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],'holes_mm':[]}
    snapshot={'contract':'spike/routed-board-polygons/v1','units':'mm',
        'source_sha256':'a'*64,'chord_error_mm':.001,'board':[rectangle(0,0,10,6)],
        'layers':['top','bottom'],'copper':[
            {'id':'trace','net':'signal','layer':'top','kind':'track','polygons':[rectangle(1,1,5,2)]},
            {'id':'land','net':'signal','layer':'bottom','kind':'pad','polygons':[rectangle(4,1,5,2)]},
            {'id':'return','net':'ground','layer':'top','kind':'filled_zone','polygons':[rectangle(1,3,9,5)]}],
        'drills':[{'id':'via','kind':'via','center_mm':[4.5,1.5],'diameter_mm':.3,
                   'plated':True,'net':'signal','start_layer':'top','end_layer':'bottom'}]}
    stack={'layers':[{'id':'core','z_min_mm':0.,'z_max_mm':1.6,'material_id':'fr4'}],
        'copper_layer_spans':{'top':[0.,.035],'bottom':[1.565,1.6]},'copper_material_id':'copper',
        'air_material_id':'air','plated_hole_wall_mm':.025,'provenance':'Original study assumptions'}
    return snapshot,stack


class RoutedBoardGeometryTests(unittest.TestCase):
    def test_complete_geometry_and_hole_volume(self):
        snapshot,stack=fixture(); before=copy.deepcopy((snapshot,stack))
        result=prepare_routed_board_volume(snapshot,stack)
        self.assertEqual((snapshot,stack),before)
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['evidence']['roi_cropping'])
        self.assertEqual(result['evidence']['source_copper_objects'],3)
        job=result['job']; self.assertEqual(len(job['solids']),6)
        totals={}
        for solid in job['solids']:
            shape=solid['shape']; area=Polygon(shape['outer_mm'],shape['holes_mm']).area
            totals[solid['id']]=area*(shape['z_max_mm']-shape['z_min_mm'])
        self.assertAlmostEqual(totals['layer:core:0'],96.)
        self.assertAlmostEqual(totals['copper:2:0'],16*.035)
        self.assertGreater(totals['barrel:via:0'],0)
        self.assertAlmostEqual(totals['drill:via:0'],3.141592653589793*.15**2*1.6,delta=.002)

    def test_explicit_plating_never_pad_diameter(self):
        snapshot,stack=fixture()
        first=prepare_routed_board_volume(snapshot,stack)
        stack['plated_hole_wall_mm']=.05
        second=prepare_routed_board_volume(snapshot,stack)
        def area(result):
            row=next(s['shape'] for s in result['job']['solids'] if s['id'].startswith('barrel:'))
            return Polygon(row['outer_mm'],row['holes_mm']).area
        self.assertGreater(area(second),area(first))
        self.assertNotEqual(first['stack_binding'],second['stack_binding'])

    def test_reject_missing_stack_and_unfilled_geometry(self):
        for change in (lambda s,t:t.pop('provenance'),lambda s,t:t['copper_layer_spans'].pop('bottom'),
                       lambda s,t:t.update(plated_hole_wall_mm=None),
                       lambda s,t:s['copper'][2].update(polygons=[]),
                       lambda s,t:s['copper'][0].update(kind='unfilled_zone')):
            snapshot,stack=fixture(); change(snapshot,stack)
            with self.assertRaises(ValueError): prepare_routed_board_volume(snapshot,stack)

    def test_reject_cross_net_contact_and_outline_clipping(self):
        snapshot,stack=fixture()
        snapshot['copper'][2]['polygons']=copy.deepcopy(snapshot['copper'][0]['polygons'])
        with self.assertRaisesRegex(ValueError,'cross-net'):
            prepare_routed_board_volume(snapshot,stack)
        snapshot,stack=fixture()
        snapshot['copper'][0]['polygons'][0]['outer_mm'][0]=[-1,1]
        with self.assertRaisesRegex(ValueError,'outside actual board'):
            prepare_routed_board_volume(snapshot,stack)

    def test_unassigned_touch_retains_physical_copper_without_net_inference(self):
        snapshot,stack=fixture()
        extra=copy.deepcopy(snapshot['copper'][0]); extra.update(id='artwork',net='')
        snapshot['copper'].append(extra)
        result=prepare_routed_board_volume(snapshot,stack)
        self.assertGreater(result['evidence']['unassigned_copper_contacts'],0)
        self.assertFalse(result['evidence']['connectivity_inferred'])
        self.assertEqual(result['evidence']['source_copper_objects'],4)
        self.assertTrue(any(g['net'].startswith('__unassigned__:') for g in result['copper_source_groups']))

    def test_partition_many_holes_preserves_exact_area(self):
        snapshot,stack=fixture(); snapshot['drills']=[]; snapshot['copper']=[]
        holes=[]
        for y in range(13):
            for x in range(10):
                a,b=.4+x*.8,.4+y*.35
                holes.append([[a,b],[a+.1,b],[a+.1,b+.1],[a,b+.1]])
        snapshot['copper']=[{'id':'plane','net':'ground','layer':'top','kind':'filled_zone',
                            'polygons':[{'outer_mm':[[.1,.1],[9.9,.1],[9.9,5.9],[.1,5.9]],'holes_mm':holes}]}]
        result=prepare_routed_board_volume(snapshot,stack)
        polygons=[Polygon(s['shape']['outer_mm'],s['shape']['holes_mm'])
                  for s in result['job']['solids'] if s['material_id']=='copper']
        self.assertGreater(len(polygons),1)
        self.assertAlmostEqual(sum(p.area for p in polygons),9.8*5.8-130*.01,places=10)
        self.assertTrue(all(len(p.interiors)<=128 for p in polygons))


class HeaderContactTests(unittest.TestCase):
    def test_terminal_contact_subtracts_drill_and_rejects_other_net(self):
        from scripts.run_arduino_routed_em import contact_area
        square={'kind':'polygon_prism','outer_mm':[[-1,-1],[1,-1],[1,1],[-1,1]],
                'holes_mm':[],'z_min_mm':0.,'z_max_mm':.035}
        hole={**square,'outer_mm':[[-.2,-.2],[.2,-.2],[.2,.2],[-.2,.2]]}
        job={'solids':[{'id':'pad','material_id':'copper','priority':10,'shape':square},
                       {'id':'drill','material_id':'air','priority':20,'shape':hole}],
             'object_metadata':{'pad':{'net':'GND'},'drill':{'kind':'drill'}}}
        pad={'center_mm':[0.,0.],'net':'GND'}
        self.assertAlmostEqual(contact_area(job,pad,0.,1.2),1.44-.16)
        with self.assertRaisesRegex(ValueError,'contact check'):contact_area(job,pad,.1,1.2)
        job['object_metadata']['pad']['net']='OTHER'
        with self.assertRaisesRegex(ValueError,'contact check'):contact_area(job,pad,0.,1.2)


if __name__=='__main__': unittest.main()
