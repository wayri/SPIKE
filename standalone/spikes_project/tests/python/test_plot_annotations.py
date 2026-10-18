# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.plot_annotations import create,commit,validate,sweep_cursor_rows
from spikes_studio.signal_math import SignalMath,Quantity,VOLT


class PlotAnnotationTests(unittest.TestCase):
    def test_save_undo_and_invalid_annotation(self):
        owner=SimpleNamespace(doc=Document.from_netlist(RC_DECK),update_title=lambda:None)
        notes=[create(0,(.001,1),'Threshold'),create(0,(.002,.8),'Rise',kind='arrow',head=(.001,.6))]
        commit(owner,notes)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plot.spksch';owner.doc.save(path)
            self.assertEqual(Document.load(path).data['metadata']['plot_annotations'],notes)
        owner.doc.undo();self.assertNotIn('plot_annotations',owner.doc.data['metadata'])
        for note in ({**notes[0],'point':[float('nan'),0]},{**notes[0],'kind':'execute'},{**notes[0],'text':''}):
            with self.assertRaises(ValueError):validate([note])

    def test_all_step_values_use_each_runs_original_data(self):
        a=SignalMath([0,1,2],{'v(out)':Quantity([0,2,4],VOLT)})
        b=SignalMath([0,1,2],{'v(out)':Quantity([0,4,8],VOLT)})
        owner=SimpleNamespace(cursors=[.5],run_engines=[a,b],traces=[('v(out)',None,'V')],run_results=[{'provenance':{'step_parameters':{'r':1000}}},{'provenance':{'step_parameters':{'r':2000}}}])
        owner.cursor_descriptor=lambda i:dict(time=owner.cursors[i],run=0,expression='v(out)')
        rows=sweep_cursor_rows(owner)
        self.assertEqual(len(rows),2);self.assertIn('r=2000',rows[1][2]);self.assertIn('1.0000 V',rows[0][-1]);self.assertIn('2.0000 V',rows[1][-1])
        owner.cursors=[3.]
        self.assertTrue(all(row[-1].startswith('Unavailable:') for row in sweep_cursor_rows(owner)))
