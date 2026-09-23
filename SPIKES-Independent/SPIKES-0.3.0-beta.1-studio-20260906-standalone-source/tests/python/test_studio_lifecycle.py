from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.plotting import extrema_indices
from spikes_studio.run_control import BatchRun,InteractiveRun


def wait_for(predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Timed out waiting for native worker state')


class DocumentLifecycleTests(unittest.TestCase):
    def test_source_reconciliation_retains_properties_layout_and_probes(self):
        doc=Document.from_netlist(RC_DECK);part=doc.data['components'][1];ident=part['id']
        doc.update([ident],{'package':'0402','limits':{'power_w':.1}})
        doc.move({ident:(120,320)});doc.add_probe('V(in,out)',ident)
        doc.apply_source(RC_DECK.replace('1k','2k'))
        part=doc.data['components'][1]
        self.assertEqual((part['id'],part['x'],part['package']),(ident,120,'0402'))
        self.assertEqual(part['value'],'2000');self.assertEqual(len(doc.data['probes']),1)
        doc.undo();self.assertIn('1k',doc.data['source']);doc.redo();self.assertIn('2k',doc.data['source'])

    def test_saved_dirty_state_and_failed_source_are_atomic(self):
        doc=Document.from_netlist(RC_DECK);self.assertFalse(doc.dirty)
        doc.apply_source(RC_DECK.replace('1k','2k'));self.assertTrue(doc.dirty)
        with tempfile.TemporaryDirectory() as temp:
            doc.save(Path(temp)/'a.spksch');self.assertFalse(doc.dirty)
            doc.undo();self.assertTrue(doc.dirty);doc.redo();self.assertFalse(doc.dirty)
        with self.assertRaises(ValueError):doc.apply_source('not a valid circuit')
        self.assertFalse(doc.dirty)

    def test_display_decimation_retains_impulses_endpoints_and_bounds(self):
        values=np.zeros(1000000);values[34567]=7;values[890123]=-12
        indices=extrema_indices(values,2000)
        self.assertLessEqual(len(indices),2000)
        self.assertIn(34567,indices);self.assertIn(890123,indices)
        self.assertEqual((indices[0],indices[-1]),(0,len(values)-1))
        self.assertTrue(np.all(np.diff(indices)>0))

    def test_rolling_plan_bypasses_only_full_history_limit(self):
        from python.spikes.netlist import parse_netlist
        source=RC_DECK.replace('10u 5m','1n 1')
        with self.assertRaises(ValueError):parse_netlist(source)
        parsed=parse_netlist(source,transient_capture='rolling')
        self.assertEqual(parsed.analysis.stop_time_s,1)
        self.assertEqual(Document.from_netlist(source).data['source'],source)
        with self.assertRaises(ValueError):parse_netlist(source,transient_capture='invalid')


@unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Set SPIKES_TEST_LIBRARY to exercise the native DLL')
class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):self.library=os.environ['SPIKES_TEST_LIBRARY']

    def test_batch_result_and_real_cancellation(self):
        run=BatchRun(RC_DECK,self.library)
        try:
            def done():run.poll();return run.state!='running'
            wait_for(done,30);self.assertEqual(run.state,'completed',run.error)
            t=np.array(run.result['data']['time_s']);v=np.array(run.result['data']['node_voltage_v']['out'])
            self.assertLess(np.max(abs(v-(1-np.exp(-t/.001)))),.0001)
        finally:run.stop()
        run=BatchRun(RC_DECK.replace('10u 5m','1n 1'),self.library)
        run.stop();self.assertEqual(run.state,'stopped');self.assertFalse(run.process.is_alive())

    def test_pause_freezes_time_resume_keeps_state_controls_and_ring(self):
        run=InteractiveRun(RC_DECK,self.library,capacity=256,speed_ratio=.05)
        try:
            wait_for(lambda:run.total_samples>=200 or run.state=='failed')
            self.assertNotEqual(run.state,'failed',run.error)
            run.pause();wait_for(lambda:run.state=='paused')
            first=run.snapshot();time.sleep(.04);second=run.snapshot()
            self.assertEqual(first['data'],second['data'])
            self.assertLess(abs(first['data']['node_voltage_v']['out'][-1]-(1-np.exp(-first['data']['time_s'][-1]/.001))),.002)
            run.set_source('V1',2);run.resume()
            wait_for(lambda:run.total_samples>700 or run.state=='failed')
            run.pause();wait_for(lambda:run.state=='paused')
            changed=run.snapshot()
            self.assertEqual(changed['data']['node_voltage_v']['in'][-1],2)
            self.assertGreater(changed['data']['node_voltage_v']['out'][-1],1.9)
            self.assertEqual(len(changed['data']['time_s']),256)
            self.assertGreater(changed['provenance']['dropped_samples'],0)
            self.assertTrue(changed['provenance']['control_events'])
            run.stop();wait_for(lambda:run.state=='stopped')
        finally:run.stop();run.thread.join(timeout=5)


if __name__=='__main__':unittest.main()
