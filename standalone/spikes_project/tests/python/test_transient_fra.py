import unittest,os,math
import numpy as np
from python.spikes.transient_fra import analyze,fit_fundamental


class TransientFraTests(unittest.TestCase):
    def test_phase_reference(self):
        t=np.linspace(.0037,.0437,1001)
        z,residual=fit_fundamental(t,2*np.sin(2*np.pi*100*t+.4)+3,100)
        self.assertAlmostEqual(z.real,2*math.cos(.4),places=8)
        self.assertAlmostEqual(z.imag,2*math.sin(.4),places=8)
        self.assertLess(residual,1e-10)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native library required')
    def test_switched_transfer(self):
        source='.title switching FRA\nV1 in 0 2\nVgate gate 0 PULSE(0 5 0 100n 100n 24.9u 50u)\nS1 in out gate 0 .1 1G 2.5 .01\nR1 out 0 1\n.tran 1u 12m\n.end'
        result=analyze(source,os.environ['SPIKES_TEST_NATIVE_LIBRARY'],'V1','V(out)',[1000],amplitude=.1,max_step_s=1e-6)
        row=result['rows'][0]
        self.assertAlmostEqual(row['real'],.5/1.1,delta=.04)
        self.assertGreater(row['nonfundamental_residual_rms_v'],.1)
