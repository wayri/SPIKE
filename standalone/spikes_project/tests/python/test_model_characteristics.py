from pathlib import Path
import sys,unittest,os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.part_properties import parse
from spikes_studio.model_characteristics import characteristic


class Characteristics(unittest.TestCase):
    def test_sources(self):
        source='.title source\nV1 a 0 PULSE(0 5 1u 2u 2u 3u 10u)\nR1 a 0 1k\n.tran 1u 30u\n.end'
        c=characteristic(parse(source).elements[0]);self.assertEqual(max(c['y']),5)
        self.assertEqual(c['x'],sorted(c['x']));self.assertEqual(len(c['x']),len(c['y']))

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native library required')
    def test_diode_curve_native(self):
        from spikes_studio.run_control import native_batch
        source='.title diode\nV1 a 0 0\nD1 a 0 dm\n.model dm D(IS=1p N=1.3)\n.op\n.end'
        el=next(e for e in parse(source).elements if e.kind=='diode');c=characteristic(el)
        for index in (0,40,120,200):
            v=c['x'][index];expected=c['y'][index]
            result=native_batch(source.replace('V1 a 0 0',f'V1 a 0 {v:.17g}'),os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
            self.assertAlmostEqual(result['data']['element_current_a']['D1'],expected,delta=max(1e-14,abs(expected)*1e-6))

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native library required')
    def test_switch_curve_native(self):
        from spikes_studio.run_control import native_batch
        source='.title switch\nV1 a 0 1\nV2 control 0 0\nS1 a 0 control 0 2 1000 .5 .1\n.op\n.end'
        el=next(e for e in parse(source).elements if e.kind=='voltage_controlled_switch');c=characteristic(el)
        for index in (0,100,200):
            result=native_batch(source.replace('V2 control 0 0',f'V2 control 0 {c["x"][index]:.17g}'),os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
            self.assertAlmostEqual(result['data']['element_current_a']['S1'],1/c['y'][index],delta=1e-8)
