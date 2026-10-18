# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.wire_visuals import crossings,endpoint_junctions
from spikes_studio.document import Document
from spikes_studio.editor_geometry import route,wire_preview
from spikes_studio.junction_edit import split_at


def row(ident,node,points):return dict(id=ident,node=node,points=points)


class WireVisualTests(unittest.TestCase):
    def test_hops_never_join_different_nets_and_last_wire_bridges(self):
        rows=[row('a','A',[(0,50),(100,50)]),row('b','B',[(50,0),(50,100)])]
        found=crossings(rows);self.assertEqual(len(found),1);self.assertEqual(found[0]['kind'],'hop')
        self.assertEqual(found[0]['node'],'b');self.assertFalse(found[0]['horizontal'])
        rows[0]['draw_order']=10;rows[1]['draw_order']=2
        self.assertTrue(crossings(rows)[0]['horizontal'])
        rows[1]['node']='a';self.assertEqual(crossings(rows)[0]['kind'],'junction')
    def test_tees_endpoint_dots_and_nonconnected_endpoint_contact(self):
        rows=[row('a','n',[(0,50),(100,50)]),row('b','N',[(50,0),(50,50)])]
        self.assertEqual(crossings(rows)[0]['kind'],'junction')
        rows[1]['node']='other';self.assertEqual(crossings(rows),[])
        endpoints=[row('a','n',[(0,0),(50,0)]),row('b','n',[(50,0),(100,0)]),row('c','n',[(50,0),(50,100)])]
        self.assertEqual(len(endpoint_junctions(endpoints)),1)
    def test_explicit_junctions_can_start_finish_and_preview_wires(self):
        doc=Document.from_netlist('Junction test\nV1 n 0 1\nR1 n 0 1k\nR2 n 0 2k\nR3 n 0 3k\n.op\n.end\n')
        parts={p['ref']:p for p in doc.data['components']};doc.connect([parts['R1']['id'],0],[parts['R2']['id'],0])
        byid={p['id']:p for p in doc.data['components']};wire=doc.data['wires'][0];points=route(byid,wire)
        a,b=max(zip(points,points[1:]),key=lambda pair:abs(pair[0][0]-pair[1][0])+abs(pair[0][1]-pair[1][1]))
        at=((a[0]+b[0])/2,(a[1]+b[1])/2);ident=split_at(doc,wire['id'],at,0)
        self.assertEqual(doc.data['wires'][0]['draw_order'],doc.data['wires'][1]['draw_order'])
        doc.connect_endpoints([ident],[parts['R3']['id'],0]);self.assertEqual(len(doc.data['wires']),3)
        junctions={j['id']:j for j in doc.data['junctions']}
        preview=wire_preview(byid,[ident],[],(at[0]+40,at[1]+20),junctions=junctions)
        self.assertEqual(preview[0],at);doc.validate()
        doc.undo();self.assertEqual(len(doc.data['wires']),2);doc.undo();self.assertEqual(doc.data['junctions'],[])
    def test_marker_budget_and_diagonal_rejection(self):
        with self.assertRaises(ValueError):crossings([row('a','n',[(0,0),(20,20)])])
        with self.assertRaises(ValueError):crossings([row('a','n',[(0,5),(10,5)]),row('b','x',[(5,0),(5,10)])],limit=0)
    def test_wiring_merge_preserves_source_bound_label(self):
        from spikes_studio.net_labels import attach
        doc=Document.from_netlist('Label merge\nV1 a 0 1\nR1 a 0 1k\nR2 b 0 2k\n.op\n.end\n')
        parts={p['ref']:p for p in doc.data['components']}
        attach(doc,'local','signal',[parts['R2']['id'],0])
        doc.connect([parts['R1']['id'],0],[parts['R2']['id'],0]);doc.validate()
        self.assertEqual(doc.data['labels'][0]['net'],'a');self.assertEqual(doc.data['labels'][0]['name'],'a')
