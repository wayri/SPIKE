import os
from pathlib import Path
import unittest
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project

@unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native B engine required')
class GenericPowerModels(unittest.TestCase):
    def run_device(self,model,gate,supply):
        definitions=(Path(__file__).resolve().parents[4]/'examples/spikes/compact_charge/generic_power_devices.lib').read_text()
        deck=f'.title generic\n{definitions}\nVs a 0 {supply}\nVg g 0 {gate}\nX1 a g 0 {model}\n.tran 20n 25u\n.end'
        result=run_native_project(parse_netlist(deck,native_extensions=True),os.environ['SPIKES_TEST_NATIVE_LIBRARY'],integration_method='backward_euler').to_dict()
        self.assertEqual(result['status'],'completed',result)
        d=result['data'];return d['time_s'],[-x for x in d['element_current_a']['VS']]

    def test_igbt_tail(self):
        t,i=self.run_device('SPK_IGBT','PULSE(0 8 1u 20n 20n 4u 30u)','5')
        at=lambda time:i[min(range(len(t)),key=lambda k:abs(t[k]-time))]
        self.assertLess(at(.5e-6),1e-5)
        self.assertGreater(at(4e-6),30)
        self.assertGreater(at(6e-6),5)
        self.assertLess(at(14e-6),.01)

    def test_scr_latch_and_commutate(self):
        t,i=self.run_device('SPK_SCR','PULSE(0 2 1u 20n 20n 3u 30u)','PWL(0 5 8u 5 8.02u 0 20u 0 20.02u 5 25u 5)')
        at=lambda time:i[min(range(len(t)),key=lambda k:abs(t[k]-time))]
        self.assertLess(at(.5e-6),1e-5)
        self.assertGreater(at(7e-6),40)
        self.assertLess(abs(at(14e-6)),1e-6)
        self.assertLess(abs(at(24e-6)),1e-4)
