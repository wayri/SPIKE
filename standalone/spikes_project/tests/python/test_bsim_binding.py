import os
import unittest
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project

@unittest.skipUnless(os.name=='nt' and os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Windows native library required')
class BsimBinding(unittest.TestCase):
    def run_deck(self,source):
        result=run_native_project(parse_netlist(source,native_extensions=True),os.environ['SPIKES_TEST_NATIVE_LIBRARY'],integration_method='backward_euler').to_dict()
        self.assertEqual(result['status'],'completed',result)
        return result['data']

    def test_dc_and_charge_transient(self):
        for family in ('BSIMBULK','BSIMCMG'):
            with self.subTest(family=family):
                deck=f'.title Berkeley\nVd d 0 1\nVg g 0 {{gate}}\nM1 d g 0 0 model\n.model model {family}()\n{{analysis}}\n.end'
                off=self.run_deck(deck.replace('{gate}','0').replace('{analysis}','.op'))
                on=self.run_deck(deck.replace('{gate}','1').replace('{analysis}','.op'))
                self.assertGreater(-on['element_current_a']['VD'],-off['element_current_a']['VD']+1e-10)
                self.assertAlmostEqual(on['element_current_a']['M1']+on['element_current_a']['VD'],0,delta=1e-9)
                transient=self.run_deck(deck.replace('{gate}','PULSE(0 1 1n 1n 1n 10n 20n)').replace('{analysis}','.tran 100p 4n'))
                self.assertGreater(max(abs(v) for v in transient['element_current_a']['VG']),1e-10)
                for drain,source in zip(transient['element_current_a']['M1'],transient['element_current_a']['VD']):self.assertAlmostEqual(drain+source,0,delta=1e-9)
                power=transient['element_power_w']
                for m,d,g in zip(power['M1'],power['VD'],power['VG']):self.assertAlmostEqual(m+d+g,0,delta=1e-8)

    def test_unknown_parameter_rejected(self):
        project=parse_netlist('.title bad\nV1 d 0 1\nM1 d d 0 0 mm\n.model mm BSIMBULK(NOTREAL=1)\n.op\n.end',native_extensions=True)
        with self.assertRaisesRegex(Exception,'Unknown OSDI parameter'):
            run_native_project(project,os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
