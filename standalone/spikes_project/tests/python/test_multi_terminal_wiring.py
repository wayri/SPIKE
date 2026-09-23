from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))
from spikes_studio.document import Document
from spikes_studio.editor_geometry import route, terminal
from spikes_studio.part_properties import form, rewrite_nodes
from spikes_studio.pin_geometry import pins, pin_id

DECK = '''Multi-terminal
V1 drive 0 3
R1 d 0 1k
M1 d gate s bulk mod W=2u L=1u
.model mod NMOS(LEVEL=1 VTO=1 KP=1m)
.op
.end
'''


class MultiTerminalWiring(unittest.TestCase):
    def test_gate_and_bulk_survive_roundtrip_undo(self):
        doc = Document.from_netlist(DECK)
        source, resistor, mos = doc.data['components']
        original = deepcopy(doc.data)
        self.assertEqual([p.label for p in pins(mos)], ['D', 'S', 'G', 'B'])
        self.assertEqual(form(DECK, 'M1')['nodes'], ['d', 's', 'gate', 'bulk'])
        doc.connect((source['id'], 0), (mos['id'], 2))
        self.assertIn('M1 d drive s bulk mod W=2u L=1u', doc.data['source'])
        doc.connect((source['id'], 1), (mos['id'], 3))
        self.assertIn('M1 d drive s 0 mod W=2u L=1u', doc.data['source'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'roundtrip.spksch'
            doc.save(path)
            self.assertEqual(Document.load(path).data, doc.data)
        doc.undo();doc.undo()
        self.assertEqual(doc.data, original)

    def test_every_terminal_rotates_mirrors_routes(self):
        doc = Document.from_netlist(DECK)
        first, _, mos = doc.data['components']
        for rotation in (0, 90, 180, 270):
            for mirror in (False, True):
                device = dict(mos, rotation=rotation, mirror_x=mirror)
                identities = [pin_id(device, i) for i in range(4)]
                self.assertEqual(len(set(identities)), 4)
                for i in range(4):
                    wire = {'a': [first['id'], 0], 'b': [mos['id'], i]}
                    points = route({first['id']: first, mos['id']: device}, wire)
                    self.assertEqual(points[-1], terminal(device, i))
                    self.assertTrue(all(a[0] == b[0] or a[1] == b[1] for a,b in zip(points,points[1:])))

    def test_preserve_suffix_and_reject_bad_edit(self):
        candidate = rewrite_nodes(DECK, 'M1', ['drain', 'source', 'gate', 'bulk'])
        self.assertEqual(candidate, DECK.replace('M1 d gate s bulk', 'M1 drain gate source bulk'))
        doc = Document.from_netlist(DECK); original = deepcopy(doc.data)
        with self.assertRaises(ValueError):doc.connect((doc.data['components'][0]['id'],0),(doc.data['components'][-1]['id'],4))
        self.assertEqual(doc.data, original)
        for bad in (['d','g'], ['d','s','g\n.end','b']):
            with self.assertRaises(ValueError):rewrite_nodes(DECK,'M1',bad)

    def test_bjt_terminal_order(self):
        source = 'BJT\nR1 e 0 1\nQ1 c b e mod\n.model mod NPN(IS=1f BF=100)\n.op\n.end\n'
        self.assertEqual(form(source,'Q1')['nodes'], ['c','e','b'])
        changed = rewrite_nodes(source,'Q1',['c','e','drive'])
        self.assertIn('Q1 c drive e mod',changed)
