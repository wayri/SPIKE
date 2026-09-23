import unittest,math
from python.spikes.fra import analyze


class FraTests(unittest.TestCase):
    def test_rc_corner(self):
        source='.title FRA\nV1 in 0 0\nR1 in out 1000\nC1 out 0 1u\n.op\n.end'
        corner=1/(2*math.pi*.001)
        r=analyze(source,'V1','V(out)',corner/10,corner*10,3)
        transfer=r['data']['transfer']
        self.assertAlmostEqual(transfer['real'][1],.5,places=7)
        self.assertAlmostEqual(transfer['imaginary'][1],-.5,places=7)
