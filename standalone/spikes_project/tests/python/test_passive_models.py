from pathlib import Path
import sys, os, math, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document
from spikes_studio.model_fidelity import preflight
from spikes_studio.passive_models import impedance,validate


class PassiveTests(unittest.TestCase):
    def test_impedance(self):
        self.assertAlmostEqual(abs(impedance(1e-6,1000,{})),1/(2*math.pi*1000*1e-6))
        f=1/(2*math.pi*math.sqrt(1e-6*1e-6))
        self.assertAlmostEqual(abs(impedance(1e-6,f,{'esr_ohm':2,'esl_h':1e-6})),2)
        for bad in (-1,0,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):validate({'esr_ohm':bad})

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native DLL required')
    def test_native_leakage_and_esr(self):
        from spikes_studio.run_control import native_batch
        source='.title package test\nV1 in 0 1\nR1 in out 1000\nC1 out 0 1u\n.op\n.end\n'
        d=Document.from_netlist(source)
        d.data['model_policy']['components']['C1']={'tier':'source','enforce':False,
            'parasitic_values':{'esr_ohm':2,'esl_h':1e-6,'leakage_ohm':1000}}
        report=preflight(d.data)
        self.assertIn('RSPKPAR_C1',d.data['source'])
        result=native_batch(d.data['source'],os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
        self.assertAlmostEqual(result['data']['node_voltage_v']['out'],.5,places=7)
        self.assertEqual(report['effective_source'],d.data['source'])

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native DLL required')
    def test_native_esr_time_constant(self):
        from spikes_studio.run_control import native_batch
        source='.title ESR transient\nV1 in 0 1\nR1 in out 1000\nC1 out 0 1u\n.tran 1u 5m uic\n.end\n'
        d=Document.from_netlist(source)
        d.data['model_policy']['components']['C1']={'tier':'source','enforce':False,'parasitic_values':{'esr_ohm':1000}}
        preflight(d.data)
        result=native_batch(d.data['source'],os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
        data=result['data'];t=data['time_s'][-1]
        self.assertAlmostEqual(data['node_voltage_v']['out'][-1],1-.5*math.exp(-t/.002),delta=.001)
