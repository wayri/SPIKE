import unittest,os,math
from python.spikes.netlist import parse_netlist
from python.spikes.contracts import CircuitElement
from python.spikes.native_runner import run_native_project

Q='.title NPN\nV1 c 0 5\nV2 b 0 .6\nQ1 c b 0 qmod\n.model qmod NPN(IS=1f BF=99 BR=1 NF=1)\n.op\n.end'
M='.title NMOS\nV1 d 0 5\nV2 g 0 3\nM1 d g 0 0 mmod W=2u L=1u\n.model mmod NMOS(LEVEL=1 VTO=1 KP=1m)\n.op\n.end'


class SemiconductorBinding(unittest.TestCase):
    def test_roundtrip_and_rejection(self):
        for source in (Q,M):
            e=parse_netlist(source,native_extensions=True).elements[-1]
            self.assertEqual(CircuitElement.from_dict(e.to_dict()),e)
        for source in (M.replace('LEVEL=1','LEVEL=54'),Q.replace('NF=1','CJE=1p'),M.replace('.op','.temp 50\n.op')):
            with self.assertRaises(ValueError):parse_netlist(source,native_extensions=True)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native library required')
    def test_native_dc(self):
        for source in (Q,M):
            p=parse_netlist(source,native_extensions=True)
            result=run_native_project(p,os.environ['SPIKES_TEST_NATIVE_LIBRARY']).to_dict()
            self.assertEqual(result['status'],'completed')
            if source==M:self.assertAlmostEqual(result['data']['element_current_a']['M1'],.004,delta=1e-8)
            else:
                expected=.99e-15*math.expm1(.6/(8.617333262145e-5*300.15))
                self.assertAlmostEqual(result['data']['element_current_a']['Q1'],expected,delta=expected*1e-6)

    def test_hierarchy(self):
        deck='.title hierarchy\n.model mm NMOS(LEVEL=1 KP=1m)\n.subckt cell d g s\nM1 d g s s mm W=2u L=1u\n.ends\nV1 d 0 5\nV2 g 0 3\nX1 d g 0 cell\n.op\n.end'
        e=parse_netlist(deck,native_extensions=True).elements[-1]
        self.assertEqual(e.name,'X1:M1');self.assertEqual(e.semiconductor_nodes,('d','g','0','0'))
