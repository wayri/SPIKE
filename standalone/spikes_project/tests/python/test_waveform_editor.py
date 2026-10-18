# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.signal_math import SignalMath,Quantity,VOLT,AMP
from spikes_studio.waveform_editor import evaluated_trace,replace_trace


class WaveformEditorTests(unittest.TestCase):
    def owner(self):
        engine=SignalMath([0,1,2],{'v(out)':Quantity([0,1,2],VOLT),'i(R1)':Quantity([2,2,2],AMP)})
        doc=Document.from_netlist(RC_DECK);doc.data['expressions']=['v(out)']
        owner=SimpleNamespace(math=engine,run_engines=[engine],selected_run=0,doc=doc,traces=[evaluated_trace(engine,'v(out)')],cursor_bindings=[dict(run=0,expression='v(out)')],cursors=[1.],hidden_traces={'v(out)'})
        owner.cursor_descriptor=lambda i:dict(owner.cursor_bindings[i],time=owner.cursors[i])
        owner.expression=SimpleNamespace(SetValue=lambda value:setattr(owner,'edited',value))
        owner.draw_plot=lambda:None;owner.update_title=lambda:None
        return owner

    def test_equation_replacement_rebinds_and_preserves_samples(self):
        owner=self.owner();original=owner.math.signals['v(out)'].values.copy()
        replace_trace(owner,'v(out)','v(out)*i(R1)')
        self.assertEqual(owner.traces[0][2],'W');np.testing.assert_allclose(owner.traces[0][1],[0,2,4])
        self.assertEqual(owner.cursor_bindings[0],dict(run=0,expression='v(out)*i(R1)'))
        self.assertEqual(owner.doc.data['expressions'],['v(out)*i(R1)'])
        self.assertEqual(owner.hidden_traces,{'v(out)*i(R1)'})
        np.testing.assert_array_equal(owner.math.signals['v(out)'].values,original)
        owner.doc.undo();self.assertEqual(owner.doc.data['expressions'],['v(out)'])

    def test_invalid_expression_and_cross_run_binding_are_atomic(self):
        for expression in ('v(missing)','sin(v(out))','__import__("os")','j*v(out)'):
            owner=self.owner();before=deepcopy(owner.doc.data)
            with self.assertRaises(ValueError):replace_trace(owner,'v(out)',expression)
            self.assertEqual(owner.doc.data,before);self.assertEqual(owner.traces[0][0],'v(out)')
        owner=self.owner();owner.run_engines.append(SignalMath([0,1,2],{'v(out)':Quantity([0,2,4],VOLT)}));owner.cursor_bindings[0]['run']=1
        before=deepcopy(owner.doc.data)
        with self.assertRaises(ValueError):replace_trace(owner,'v(out)','i(R1)')
        self.assertEqual(owner.doc.data,before)

    def test_trig_and_custom_units_move_to_compatible_pane(self):
        owner=self.owner();np.testing.assert_allclose(evaluated_trace(owner.math,'sin(v(out)/V)')[1],np.sin([0,1,2]))
        owner.traces.append(evaluated_trace(owner.math,'2*v(out)'))
        owner.doc.data['plot_layout']={'mode':'custom','panes':{'v(out)':1,'2*v(out)':1},'heights':{}}
        replace_trace(owner,'v(out)','i(R1)')
        self.assertEqual(owner.doc.data['plot_layout']['panes']['i(R1)'],2)

    def test_duplicate_expression_rejected(self):
        owner=self.owner();owner.traces.append(evaluated_trace(owner.math,'i(R1)'));before=deepcopy(owner.doc.data)
        with self.assertRaises(ValueError):replace_trace(owner,'v(out)','i(r1)')
        self.assertEqual(owner.doc.data,before)
