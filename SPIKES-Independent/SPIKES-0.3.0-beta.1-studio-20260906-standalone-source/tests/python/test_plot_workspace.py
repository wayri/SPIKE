from pathlib import Path
import os
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.signal_math import SignalMath,Quantity,VOLT,AMP
from spikes_studio.plot_workspace import sample,cursor_math,OperatingPointMath,format_value,instrument_data
from spikes_studio.run_control import native_batch

STEP_DECK=RC_DECK.replace('R1 in out 1k','R1 in out {res}').replace('V1 in','.param res=1k\n.step param res list 1k 2k 4k\nV1 in')

class WorkspaceTests(unittest.TestCase):
    def test_cross_run_cursors_keep_independent_grids(self):
        engines=[SignalMath([0,1,2],{'v(out)':Quantity([0,1,2],VOLT)}),SignalMath([0,.5,2],{'v(out)':Quantity([0,1,4],VOLT),'i(r)':Quantity([0,1,4],AMP)})]
        a={'run':0,'expression':'V(out)','time':.5};b={'run':1,'expression':'V(out)','time':1.5}
        self.assertEqual(cursor_math(engines,a,b).values,2.5)
        self.assertEqual(cursor_math(engines,a,b,'b/a').values,6)
        self.assertEqual(cursor_math(engines,a,b,'(b-a)/dt').values,2.5)
        with self.assertRaises(ValueError):cursor_math(engines,a,dict(b,expression='I(r)'))
        with self.assertRaises(ValueError):sample(engines[0],'V(out)',3)
        with self.assertRaises(ValueError):cursor_math(engines,a,dict(a),'(b-a)/dt')

    def test_op_is_scalar_not_a_synthetic_waveform(self):
        result={'data':{'node_voltage_v':{'out':2},'element_current_a':{'R1':.1},'element_power_w':{'R1':.2}}}
        engine=OperatingPointMath(result)
        self.assertAlmostEqual(engine.evaluate('V(out)*I(R1)').values,.2)
        self.assertEqual(str(engine.evaluate('P(R1)').unit),'W')
        with self.assertRaises(ValueError):engine.evaluate('t')
        with self.assertRaises(ValueError):engine.evaluate('rms(V(out))')
        self.assertIn('∠',format_value(Quantity(1+1j,VOLT),'Polar / degrees'))

    def test_instruments_transaction_and_validation(self):
        doc=Document.from_netlist(RC_DECK)
        item={'id':'one','anchor':doc.data['components'][1]['id'],'kind':'Readout','expression':'V(out)','source':'Selected run','format':'Engineering','frequency_hz':1000,'x':100,'y':300}
        doc.commit(lambda d:d['instruments'].append(item));self.assertEqual(len(doc.data['instruments']),1)
        doc.undo();self.assertEqual(doc.data['instruments'],[]);doc.redo();self.assertEqual(len(doc.data['instruments']),1)
        with self.assertRaises(ValueError):doc.commit(lambda d:d['instruments'][0].update(x=float('nan')))
        self.assertEqual(doc.data['instruments'][0]['x'],100)

    def test_step_budget_rejected_before_native_execution(self):
        source=STEP_DECK.replace('10u 5m','50n 5m')
        with self.assertRaisesRegex(ValueError,'retained scalar'):native_batch(source,'does-not-exist.dll')

    def test_nested_list_and_linear_elaboration(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.contracts import CircuitProject
        source=STEP_DECK.replace('.param res=1k','.param res=1k supply=1\n.step param supply 1 2 1').replace('V1 in 0 1','V1 in 0 {supply}')
        project=parse_netlist(source,native_extensions=True)
        self.assertEqual(len(project.step_variants),6)
        self.assertEqual(dict(project.step_variants[-1].parameters),{'supply':2,'res':4000})
        self.assertEqual(CircuitProject.from_dict(project.to_dict()).step_variants,project.step_variants)

    def test_scalar_readout_and_missing_channel(self):
        from types import SimpleNamespace
        doc=Document.from_netlist(RC_DECK)
        owner=SimpleNamespace(result={'data':{'node_voltage_v':{'out':3}}},math=None,result_source=None,selected_run=0,doc=doc)
        item={'source':'Selected run','expression':'V(out)','kind':'Readout','format':'Engineering'}
        label,value,curve=instrument_data(owner,item)
        self.assertIn('DC OP',label);self.assertIn('3.0000 V',value);self.assertIsNone(curve)
        with self.assertRaises(ValueError):instrument_data(owner,dict(item,expression='V(missing)'))
        with self.assertRaises(ValueError):instrument_data(owner,dict(item,kind='Mini plot'))

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Native library not configured')
    def test_actual_cpp_parameter_sweep(self):
        result=native_batch(STEP_DECK,os.environ['SPIKES_TEST_LIBRARY'])
        self.assertEqual(result['status'],'completed');self.assertEqual(len(result['runs']),3)
        final=[]
        for index,run in enumerate(result['runs']):
            self.assertEqual(run['provenance']['step_parameters']['res'],1000*2**index)
            engine=SignalMath.from_result(run);value=float(engine.evaluate('V(out)').values[-1]);final.append(value)
            self.assertAlmostEqual(value,1-np.exp(-.005/(1000*2**index*1e-6)),delta=.004)
        self.assertGreater(final[0],final[1]);self.assertGreater(final[1],final[2])

if __name__=='__main__':unittest.main()
