import sys
from pathlib import Path
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.model_placement import prepare,insert,is_model_card

class ModelPlacement(unittest.TestCase):
    def test_clipboard_classification(self):
        self.assertTrue(is_model_card('* note\n.model demo D(IS=1n\n+ N=2)'))
        self.assertFalse(is_model_card('.model demo D(IS=1n)\nD1 a 0 demo\n.end'))
    def test_transaction_and_layout(self):
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data);parts=list(doc.data['components'])
        plan=prepare(doc,'.model TEST D(IS=1n N=2)');identity=insert(doc,plan,(420,310))
        self.assertEqual(doc.data['components'][:-1],parts)
        self.assertEqual(doc.data['components'][-1]['id'],identity)
        self.assertEqual(doc.data['components'][-1]['x'],420)
        self.assertEqual(len(doc.undo_stack),1)
        doc.undo();self.assertEqual(doc.data,before)

    def test_collision_and_unsupported(self):
        doc=Document.from_netlist(RC_DECK)
        insert(doc,prepare(doc,'.model TEST D(IS=1n)'),(0,0))
        plan=prepare(doc,'.model TEST D(IS=2n)')
        self.assertIn('TEST_paste1',plan['model'])
        self.assertEqual(plan['part']['ref'],'D2')
        for text in ('.model bad NMOS(LEVEL=54)','.model bad IGBT(VTO=3)'):
            with self.assertRaises(ValueError):prepare(doc,text)
