from pathlib import Path
import sys
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document
from spikes_studio.editor_geometry import transform,select_box,select_lasso,terminal,route

DECK='Editor tools\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 10u 1m\n.end\n'

class SelectionAnnotationTests(unittest.TestCase):
    def test_mirror_in_world_coordinates_at_every_rotation(self):
        for angle in (0,90,180,270):
            for axis in ('horizontal','vertical'):
                d=Document.from_netlist(DECK);p=d.data['components'][1]
                p['rotation']=angle;before=deepcopy(d.data);point=transform(p,23,17)
                d.mirror([p['id']],axis);after=transform(p,23,17)
                expected=(2*p['x']-point[0],point[1]) if axis=='horizontal' else (point[0],2*p['y']-point[1])
                self.assertEqual(after,expected)
                d.mirror([p['id']],axis);self.assertEqual(transform(p,23,17),point)
                d.undo();d.undo();self.assertEqual(d.data,before)

    def test_mirror_retained_through_source_and_serialization(self):
        d=Document.from_netlist(DECK);p=d.data['components'][1]
        d.mirror([p['id']]);d.apply_source(DECK.replace('1k','2k'))
        self.assertTrue(Document(d.data).data['components'][1]['mirror_x'])
        before=deepcopy(d.data)
        for ids,axis in ((['missing'],'horizontal'),([p['id']],'bad')):
            with self.assertRaises(ValueError):d.mirror(ids,axis)
            self.assertEqual(d.data,before)

    def test_mirrored_route_preserves_pin_identity(self):
        d=Document.from_netlist(DECK);a,b=d.data['components'][1:]
        d.connect((a['id'],1),(b['id'],0));d.mirror([a['id']])
        a,b=d.data['components'][1:]
        points=route({p['id']:p for p in d.data['components']},d.data['wires'][0])
        self.assertEqual(points[0],terminal(a,1));self.assertEqual(points[-1],terminal(b,0))
        self.assertEqual(a['nodes'][1],b['nodes'][0])

    def test_box_and_lasso_boundary_and_concavity(self):
        parts=[dict(id=str(i),x=x,y=y) for i,(x,y) in enumerate(((0,0),(1,1),(2,2),(1,2),(4,4)))]
        self.assertEqual(select_box(parts,(2,2),(0,0)),['0','1','2','3'])
        self.assertEqual(select_lasso(parts,[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]),['0','1','3'])
        self.assertEqual(select_lasso(parts,[(0,0),(1,1)]),[])

    def test_annotations_undo_and_inert_source(self):
        d=Document.from_netlist(DECK);before=deepcopy(d.data)
        ident=d.edit_annotation(x=1,y=2,text='.include hostile.lib\nDesign note')
        self.assertEqual(d.data['source'],DECK)
        d.edit_annotation(ident,x=3,y=4,kind='ellipse',width=80,height=90)
        self.assertEqual(len(d.data['annotations']),1)
        self.assertEqual(Document(d.data).data['annotations'][0]['kind'],'ellipse')
        d.remove_annotations([ident]);self.assertEqual(d.data['annotations'],[])
        d.undo();d.undo();d.undo();self.assertEqual(d.data,before)

    def test_bad_annotations_are_atomic(self):
        d=Document.from_netlist(DECK);before=deepcopy(d.data)
        for kwargs in ({'kind':'source'},{'width':-1},{'x':float('nan')},{'text':'a'*16385},{'color':'#fff'}):
            with self.assertRaises(ValueError):d.edit_annotation(**dict(dict(x=0,y=0),**kwargs))
            self.assertEqual(d.data,before)

if __name__=='__main__':unittest.main()
