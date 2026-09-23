from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.recovery import Recovery,restore
from spikes_studio.subsheet import add_subsheet


class RecoveryAndHierarchy(unittest.TestCase):
    def test_autosave_keeps_invalid_draft_separate_and_recovers_unsaved(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Document.from_netlist(RC_DECK);recovery=Recovery(directory)
            self.assertIsNone(recovery.save(d,RC_DECK))
            path=recovery.save(d,'incomplete draft','original.spksch')
            self.assertIsNone(recovery.save(d,'incomplete draft','original.spksch'))
            restored,draft=restore(path)
            self.assertEqual(restored.data['source'],RC_DECK);self.assertEqual(draft,'incomplete draft');self.assertTrue(restored.dirty)
            self.assertEqual(path.parent,Path(directory))

    def test_subsheet_maps_ports_to_parent_nodes_and_is_undoable(self):
        source='Hierarchy\nV1 in 0 1\n.op\n.end\n'
        candidate=add_subsheet(source,'DIVIDER','XDIV',['IN','OUT','REF'],['in','out','0'],'R1 IN OUT 1k\nR2 OUT REF 1k')
        d=Document.from_netlist(source);d.apply_source(candidate)
        self.assertEqual({p['ref'] for p in d.data['components']},{'V1','XDIV:R1','XDIV:R2'})
        self.assertEqual(next(p for p in d.data['components'] if p['ref']=='XDIV:R1')['nodes'],['in','out'])
        d.undo();self.assertEqual(d.data['source'],source)
        with self.assertRaises(ValueError):add_subsheet(source,'BAD','XBAD',['A','A'],['in','0'],'R1 A 0 1k')
        with self.assertRaises(ValueError):add_subsheet(source,'BAD','XBAD',['A'],['in'],'.end')
