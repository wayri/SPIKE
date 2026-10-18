# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document, RC_DECK
from spikes_studio.power_symbols import attach, remove


class PowerSymbolTests(unittest.TestCase):
    def test_ground_merge_undo_and_persistence(self):
        doc=Document.from_netlist(RC_DECK.replace('C1 out 0','C1 out return'))
        capacitor=next(p for p in doc.data['components'] if p['ref']=='C1')
        before=deepcopy(doc.data)
        attach(doc,'reference_ground',(capacitor['id'],1))
        self.assertEqual(next(p for p in doc.data['components'] if p['ref']=='C1')['nodes'][1],'0')
        self.assertEqual(len(doc.data['wires']),len(before['wires']))
        with tempfile.TemporaryDirectory() as tmp:
            doc.save(Path(tmp)/'power.spksch')
            self.assertEqual(Document.load(Path(tmp)/'power.spksch').data['power_symbols'],doc.data['power_symbols'])
        doc.undo();self.assertEqual(doc.data,before)

    def test_earth_and_flags_do_not_ground_or_create_source(self):
        doc=Document.from_netlist(RC_DECK);part=doc.data['components'][0];source=doc.data['source']
        for kind in ('power_flag','earth_ground','chassis_ground','signal_ground'):
            marker=attach(doc,kind,(part['id'],0))
            self.assertEqual(doc.data['source'],source)
            with self.assertRaises(ValueError):attach(doc,kind,(part['id'],0))
            remove(doc,marker['id'])
        self.assertEqual(doc.data['power_symbols'],[])

    def test_invalid_terminal_and_unsafe_rewrite_are_atomic(self):
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        with self.assertRaises(ValueError):attach(doc,'power_flag',('absent',0))
        self.assertEqual(doc.data,before)
        doc=Document.from_netlist(RC_DECK.replace('.end','.subckt EXTRA p n\nR9 p n 1k\n.ends EXTRA\n.end'))
        before=deepcopy(doc.data)
        with self.assertRaises(ValueError):attach(doc,'reference_ground',(doc.data['components'][0]['id'],0))
        self.assertEqual(doc.data,before)
