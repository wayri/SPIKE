from pathlib import Path
import sys, os, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document
ROOT=Path(__file__).resolve().parents[4]
EXAMPLES=ROOT/'examples/spikes/advanced_systems'


class AdvancedExamples(unittest.TestCase):
    def test_document_and_pins(self):
        d=Document.load(EXAMPLES/'two_wheeler_dashboard.spksch')
        self.assertEqual(len(d.data['dashboard']['widgets']),8)
        self.assertEqual(len(d.data['controller_setup']['pins']),10)
        for path in EXAMPLES.glob('*.cir'):Document.from_netlist(path.read_text())

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native library required')
    def test_native_decks(self):
        from spikes_studio.run_control import native_batch
        for path in EXAMPLES.glob('*.cir'):
            source=path.read_text()
            if path.stem=='ev_motor_plant':source=source.replace('motor_in 0 0','motor_in 0 12').replace('.tran 1m 10','.tran 1m 1')
            result=native_batch(source,os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
            self.assertEqual(result['status'],'completed',path.name)
            data=result['data']['node_voltage_v']
            if path.stem=='ev_motor_plant':self.assertGreater(data['sense'][-1],0)
            if path.stem=='redundant_sensor_fault':self.assertLess(data['filtered_a'][-1]-data['filtered_b'][-1],-1)
