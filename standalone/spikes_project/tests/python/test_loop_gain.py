import unittest,math
from python.spikes.loop_gain import analyze


class LoopGain(unittest.TestCase):
    def test_analytical_return_ratio(self):
        source='.title loop\nVref ref 0 0\nEerr error 0 ref fb 1\nEamp gain 0 error 0 10\nR1 gain out 1000\nC1 out 0 1u\nVinj fb out 0\n.op\n.end'
        with self.assertRaises(ValueError):analyze(source,'Vinj')
        r=analyze(source,'Vinj',1,1e5,501,assume_unilateral=True)
        for f,re,im in zip(r['frequency_hz'],r['real'],r['imaginary']):
            expected=10/(1+2j*math.pi*f*.001)
            self.assertAlmostEqual(re,expected.real,places=8);self.assertAlmostEqual(im,expected.imag,places=8)
        cross=r['unity_crossings'][0]
        self.assertAlmostEqual(cross['frequency_hz'],math.sqrt(99)/(2*math.pi*.001),delta=1)
        self.assertAlmostEqual(cross['phase_margin_deg'],180-math.degrees(math.atan(math.sqrt(99))),delta=.02)
