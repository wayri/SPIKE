import unittest
from python.spikes.netlist import parse_netlist


class BehavioralLoweringSafety(unittest.TestCase):
    def test_sample_collision_is_not_linearized(self):
        # This polynomial equals 2*x at the former four classification samples.
        deck='.title B safety\nV1 a 0 0\nB1 b 0 V={2*V(a)+(V(a)+1)*V(a)*(V(a)-1)*(V(a)-2)}\nR1 b 0 1k\n.op\n.end'
        element=parse_netlist(deck,native_extensions=True).elements[1]
        self.assertEqual(element.kind,'behavioral_voltage_source')

    def test_simple_affine_still_lowers(self):
        deck='.title B linear\nV1 a 0 0\nB1 b 0 V={2*V(a)}\nR1 b 0 1k\n.op\n.end'
        self.assertEqual(parse_netlist(deck,native_extensions=True).elements[1].kind,'vcvs')
