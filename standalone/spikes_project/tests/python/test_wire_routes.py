from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document
from spikes_studio.editor_geometry import route,terminal


class WireRoutes(unittest.TestCase):
    def test_corner_route_move_undo_preserves_electrical_source(self):
        d=Document.from_netlist('Route\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.connect((a['id'],0),(b['id'],0),[[50,50],[300,50]])
        wire=d.data['wires'][0];parts={p['id']:p for p in d.data['components']};points=route(parts,wire)
        self.assertEqual(points[0],terminal(parts[a['id']],0));self.assertEqual(points[-1],terminal(parts[b['id']],0))
        self.assertTrue(all(p[0]==q[0] or p[1]==q[1] for p,q in zip(points,points[1:])))
        source=d.data['source'];d.move_wire_route(wire['id'],20,30)
        self.assertEqual(d.data['source'],source);self.assertNotEqual(route(parts,d.data['wires'][0]),points)
        d.undo();self.assertEqual(route(parts,d.data['wires'][0]),points)
        self.assertEqual(Document(d.data).data['wires'],d.data['wires'])

    def test_invalid_corners_are_atomic(self):
        d=Document.from_netlist('Route\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];source=d.data['source']
        with self.assertRaises(ValueError):d.connect((a['id'],0),(b['id'],0),[[float('nan'),2]])
        self.assertEqual(d.data['source'],source);self.assertFalse(d.data['wires'])
