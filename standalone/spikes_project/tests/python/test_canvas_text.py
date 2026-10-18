# SPDX-License-Identifier: Apache-2.0
"""Canvas text blocks must commit atomically and never execute plain notes."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.canvas_text import classify,place
from spikes_studio.document import Document,RC_DECK,Keymap


class CanvasTextTests(unittest.TestCase):
    def test_note_does_not_modify_circuit_and_t_is_registered(self):
        doc=Document.from_netlist(RC_DECK);source=doc.data['source']
        ids=place(doc,'Power stage\nobserve ripple',(200,300))
        self.assertEqual(doc.data['source'],source)
        self.assertEqual(doc.data['annotations'][0]['id'],ids[0])
        self.assertEqual(Keymap().bindings['edit.canvas_text'],'T')

    def test_block_undo_and_disabled_source_are_atomic(self):
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        ids=place(doc,'.param gain=2\n.temp 40',(100,400))
        self.assertEqual(len(ids),2)
        self.assertIn('.temp 40',doc.data['source'])
        doc.undo();self.assertEqual(doc.data,before)
        ids=place(doc,'* .param gain=2\n* .temp 40',(100,400))
        self.assertTrue(all(not d['enabled'] for d in doc.data['directives'] if d['id'] in ids))
        self.assertIn('* @spikes-off .temp 40',doc.data['source'])
        doc.enable_directives(ids,True)
        self.assertTrue(all(d['enabled'] for d in doc.data['directives'] if d['id'] in ids))

    def test_invalid_second_card_has_no_partial_effect(self):
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        with self.assertRaises(ValueError):place(doc,'.param gain=2\n.tran nonsense',(100,400))
        self.assertEqual(doc.data,before)
        self.assertEqual(doc.undo_stack,[])
        with self.assertRaisesRegex(ValueError,'structural'):classify('.subckt bad a b\n.ends')
        with self.assertRaises(ValueError):classify('.param x=2\nR1 a b 1k')

    def test_continuation_and_explicit_disabled_draft(self):
        self.assertEqual(classify('.param gain=2\n+ offset=1')['cards'],['.param gain=2\n+ offset=1'])
        doc=Document.from_netlist(RC_DECK)
        ids=place(doc,'.notyet implemented',(10,10),enabled=False)
        self.assertFalse(next(v for v in doc.data['directives'] if v['id']==ids[0])['enabled'])
