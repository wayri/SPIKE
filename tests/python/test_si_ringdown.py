# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from python.spike_core.si_ringdown import qualify_ringdown, qualify_ringdown_convergence


class RingdownTests(unittest.TestCase):
    def trace(self, f=1e9, q=50):
        t=np.arange(4096)*1e-11
        return t, np.exp(-np.pi*f*t/q)*np.cos(2*np.pi*f*t+.3)

    def test_analytic(self):
        for q in (10,50,300):
            t,y=self.trace(q=q)
            r=qualify_ringdown(t,y,source_off_time_s=0)
            self.assertEqual(r['status'],'qualified_observed_single_mode')
            self.assertAlmostEqual(r['mode']['q_factor']/q,1,places=7)
            self.assertFalse(r['physical_eigenmode_qualified'])

    def test_multimode_rejected(self):
        t,y=self.trace()
        y+=.3*np.exp(-np.pi*1.3e9*t/60)*np.cos(2*np.pi*1.3e9*t)
        self.assertEqual(qualify_ringdown(t,y,source_off_time_s=0)['status'],'not_qualified')

    def test_no_decay_and_driven(self):
        t,y=self.trace(q=1e9)
        self.assertEqual(qualify_ringdown(t,y,source_off_time_s=0)['status'],'not_qualified')
        with self.assertRaises(ValueError):
            qualify_ringdown(t,y,source_off_time_s=t[10])

    def test_refinement_and_duplicate(self):
        reports=[]
        for error in (.004,.001,.00025):
            t,y=self.trace(f=1e9*(1+error),q=50*(1+error))
            reports.append(qualify_ringdown(t,y,source_off_time_s=0))
        self.assertEqual(qualify_ringdown_convergence(reports,[.004,.002,.001])['status'],'numerically_stable_observed_mode')
        self.assertEqual(qualify_ringdown_convergence([reports[0]]*3,[.004,.002,.001])['status'],'not_qualified')

    def test_zero_and_invalid(self):
        t,y=self.trace()
        self.assertEqual(qualify_ringdown(t,y*0,source_off_time_s=0)['reasons'],['zero_probe'])
        t[30]+=1e-12
        with self.assertRaises(ValueError):
            qualify_ringdown(t,y,source_off_time_s=0)


if __name__ == '__main__':
    unittest.main()
