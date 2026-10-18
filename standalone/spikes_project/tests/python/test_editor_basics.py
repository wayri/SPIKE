from pathlib import Path
import sys
import unittest
from copy import deepcopy
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,Keymap
from spikes_studio.preferred_values import recommend
from spikes_studio.editor_geometry import terminal,route,transform

DECK='Wire test\nV1 in 0 1\nR1 in a 1k\nR2 b 0 1k\n.op\n.end\n'

class EditorTests(unittest.TestCase):
    def test_rotation_is_undoable_and_retained(self):
        d=Document.from_netlist(DECK);p=d.data['components'][1];before=deepcopy(d.data)
        d.rotate([p['id']]);self.assertEqual(terminal(d.data['components'][1],0),(p['x'],p['y']-55))
        d.apply_source(DECK.replace('1k','2k'));self.assertEqual(d.data['components'][1]['rotation'],90)
        d.undo();d.undo();self.assertEqual(d.data,before)
    def test_wire_merges_real_net_and_undo(self):
        d=Document.from_netlist(DECK);before=deepcopy(d.data);a,b=d.data['components'][1:]
        d.connect((a['id'],1),(b['id'],0));self.assertEqual(d.data['components'][2]['nodes'][0],'a')
        self.assertIn('R2 a 0',d.data['source']);self.assertEqual(len(d.data['wires']),1);self.assertEqual(d.data['revision'],1)
        points=route({p['id']:p for p in d.data['components']},d.data['wires'][0]);self.assertEqual(points[0],terminal(a,1))
        d.undo();self.assertEqual(d.data,before);d.redo();self.assertEqual(len(Document(d.data).data['wires']),1)
    def test_invalid_wire_is_atomic(self):
        d=Document.from_netlist(DECK);before=deepcopy(d.data)
        with self.assertRaises(ValueError):d.connect(('missing',0),(d.data['components'][0]['id'],0))
        self.assertEqual(d.data,before)
        with self.assertRaises(ValueError):d.rotate(['missing'])
    def test_connectivity_is_source_authoritative_read_only_and_persistent(self):
        d=Document.from_netlist('Connectivity\nRz NetB 0 1k\nR2 shared n2 1k\nR1 SHARED n1 1k\nR4 shared n4 1k\nR3 shared n3 1k\n.op\n.end\n')
        parts={p['ref']:p for p in d.data['components']}
        # Loaded documents may retain spelling aliases even though net identity
        # is case-insensitive.  Preserve each terminal's source spelling.
        parts['R1']['nodes'][0]='SHARED'
        junction='junction-a'
        d.data['junctions']=[{'id':junction,'x':300,'y':200,
                              'source_terminal':[parts['R1']['id'],0],'source_node':'SHARED'}]
        d.data['wires']=[
            {'id':'wire-c','a':[parts['R1']['id'],0],'b':[junction],'waypoints':[],'bend':'horizontal','manual':True},
            {'id':'wire-a','a':[junction],'b':[parts['R2']['id'],0],'waypoints':[],'bend':'horizontal','manual':True},
            {'id':'wire-b','a':[parts['R3']['id'],0],'b':[parts['R4']['id'],0],'waypoints':[],'bend':'horizontal','manual':True},
        ]
        d.validate();before=deepcopy(d.data);revision=d.data['revision'];dirty=d.dirty
        first=d.connectivity();self.assertEqual(first,d.connectivity())
        self.assertEqual(d.data,before);self.assertEqual(d.data['revision'],revision);self.assertEqual(d.dirty,dirty)
        shared=next(net for net in first if net['normalized_name']=='shared')
        self.assertEqual(shared['name'],'SHARED')
        self.assertEqual([pin['node'] for pin in shared['pins']],['SHARED','shared','shared','shared'])
        self.assertEqual(shared['terminal_count'],4)
        self.assertEqual([pin['ref'] for pin in shared['pins']],['R1','R2','R3','R4'])
        self.assertEqual(shared['wire_ids'],['wire-a','wire-b','wire-c'])
        self.assertEqual(shared['drawing_groups'],2)
        # A disconnected drawing group does not split the single source-named net.
        self.assertEqual(sum(net['normalized_name']=='shared' for net in first),1)
        self.assertEqual([net['normalized_name'] for net in first],sorted(net['normalized_name'] for net in first))
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path=Path(folder)/'connectivity.spikes.json';d.save(path);reopened=Document.load(path)
            self.assertEqual(reopened.connectivity(),first)
            self.assertFalse(reopened.dirty)
    def test_preferred_values(self):
        self.assertEqual(recommend(4750)['nearest'],4700)
        self.assertEqual(recommend(9900)['nearest'],10000)
        self.assertEqual(recommend(22e-9,'E12')['nearest'],22e-9)
        self.assertEqual(recommend(26,'E6')['lower'],22)
        for value in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):recommend(value)
    def test_keys_do_not_conflict(self):
        Keymap();Keymap.preset('LTspice-inspired')
    def test_routes_avoid_endpoint_bodies_at_all_rotations(self):
        for offset in ((250,0),(0,250),(250,250),(-250,0),(0,-250),(-250,-250),(111,0),(0,111)):
            for ra in (0,90,180,270):
                for rb in (0,90,180,270):
                    for ia in (0,1):
                        for ib in (0,1):
                            with self.subTest(offset=offset,rotations=(ra,rb),pins=(ia,ib)):
                                a={'x':100,'y':100,'rotation':ra}
                                b={'x':100+offset[0],'y':100+offset[1],'rotation':rb}
                                wires=[{'a':['a',ia],'b':['b',ib]},
                                       {'a':['a',ia],'b':['b',ib],'manual':True,'bend':'horizontal'},
                                       {'a':['a',ia],'b':['b',ib],'manual':True,'bend':'vertical'}]
                                for wire in wires:
                                    points=route({'a':a,'b':b},wire)
                                    self.assertEqual(points[0],terminal(a,ia));self.assertEqual(points[-1],terminal(b,ib))
                                    for p,q in zip(points,points[1:]):
                                        self.assertTrue(p[0]==q[0] or p[1]==q[1])
                                        for part in (a,b):
                                            corners=[transform(part,x,y) for x in (-55,55) for y in (-30,30)]
                                            left,right=min(v[0] for v in corners),max(v[0] for v in corners)
                                            top,bottom=min(v[1] for v in corners),max(v[1] for v in corners)
                                            horizontal=p[1]==q[1] and top<p[1]<bottom and max(min(p[0],q[0]),left)<min(max(p[0],q[0]),right)
                                            vertical=p[0]==q[0] and left<p[0]<right and max(min(p[1],q[1]),top)<min(max(p[1],q[1]),bottom)
                                            self.assertFalse(horizontal or vertical,(wire,p,q,part,points))

if __name__=='__main__':unittest.main()
