# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_thermal import ThermalNetwork, validate_thermal_spec

class ThermalTests(unittest.TestCase):
    def isolated(self,**extra):
        return ThermalNetwork(dict(links_w_per_k=np.zeros((11,11)).tolist(),ambient_conductance_w_per_k=[0.]*11,**extra))

    def test_analytic_rc_midpoint_and_refinement(self):
        n=ThermalNetwork({'links_w_per_k':np.zeros((11,11)).tolist(),'ambient_conductance_w_per_k':[.5]*11})
        t=np.full(11,310.);h=.1
        out=n.midpoint_step(t,[0,0,0],[.5]*3,h)
        C=np.array(n.spec['capacities_j_per_k']);expected=298.15+(t-298.15)*(C-h*.25)/(C+h*.25)
        np.testing.assert_allclose(out['temperature_k'],expected,atol=2e-13)
        errs=[]
        for steps in (10,20,40):
            x=t.copy()
            for _ in range(steps):x=np.array(n.midpoint_step(x,[0]*3,[.5]*3,1/steps)['temperature_k'])
            errs.append(np.linalg.norm(x-(298.15+(t-298.15)*np.exp(-.5/C))))
        self.assertLess(errs[1],errs[0]/3.8);self.assertLess(errs[2],errs[1]/3.8)

    def test_linear_temperature_feedback_closed_form(self):
        n=self.isolated();t=np.full(11,298.15);h=.2;out=n.midpoint_step(t,[10,0,0],[1,0,0],h)
        r=.08;a=.00393;C=8.;p=100*r
        expected=(2*C/h*t[0]+p*(1-a*298.15))/(2*C/h-p*a)
        self.assertAlmostEqual(out['midpoint_temperature_k'][0],expected,places=11)
        self.assertGreater(out['resistances']['winding_resistance_ohm'][0],r)

    def test_loss_channels_and_no_double_count(self):
        n=self.isolated(copper_alpha_per_k=0.,mosfet_alpha_per_k=0.)
        out=n.midpoint_step([298.15]*11,[2,3,4],[1,0,.25],.1,5.)
        expected=np.array([.32,.72,1.28,.008,0,0,.018,.008,.024,5,0])
        np.testing.assert_allclose(out['heat_distribution_w'],expected,atol=1e-14)
        self.assertAlmostEqual(out['electrical_loss_j'],float(expected[:9].sum())*.1,places=13)
        self.assertAlmostEqual(out['storage_j'],out['electrical_loss_j']+.5,places=10)
        self.assertLess(abs(out['energy_residual_j']),1e-10)

    def test_passive_links_conserve_energy_and_ambient_balance(self):
        n=ThermalNetwork();t=np.linspace(300,320,11);out=n.midpoint_step(t,[5,-2,-3],[.2,.5,.8],.01,2.)
        self.assertLess(abs(out['energy_residual_j']),1e-10)
        self.assertLess(np.max(np.abs(out['thermal_residual_w'])),1e-9)
        isolated=ThermalNetwork({'ambient_conductance_w_per_k':[0]*11})
        o=isolated.midpoint_step(t,[0]*3,[.5]*3,.01)
        self.assertLess(abs(o['storage_j']),1e-10)

    def test_resistance_phase_major_mapping(self):
        n=ThermalNetwork({'mosfet_resistance_ref_ohm':[.001,.002,.003,.004,.005,.006]})
        r=n.resistances([298.15]*11,[0,1,.5])
        np.testing.assert_allclose(r['leg_resistance_ohm'],[.002,.003,.0055],atol=1e-16)
        hot=n.resistances([308.15]*11,[0,1,.5])
        np.testing.assert_allclose(np.array(hot['leg_resistance_ohm'])/r['leg_resistance_ohm'],1.04)

    def test_adversarial_validation_and_runaway(self):
        for s in ({'extra':1},{'copper_alpha_per_k':True},{'mosfet_alpha_per_k':float('nan')},
                  {'capacities_j_per_k':[0]*11},{'links_w_per_k':np.ones((11,11)).tolist()},
                  {'minimum_temperature_k':1.,'copper_alpha_per_k':.1}):
            with self.subTest(s=s),self.assertRaises(ValueError):validate_thermal_spec(s)
        n=self.isolated()
        for i,d,h,b in (([1]*2,[.5]*3,.1,0),([0]*3,[1.1]*3,.1,0),([True]*3,[.5]*3,.1,0),([0]*3,[.5]*3,0,0),([0]*3,[.5]*3,.1,-1),([10000]*3,[.5]*3,1,0)):
            with self.assertRaises(ValueError):n.midpoint_step([298.15]*11,i,d,h,b)
        with self.assertRaises(ValueError):n.midpoint_step([449]*11,[100]*3,[.5]*3,.1)

    def test_spec_copy_isolation(self):
        n=ThermalNetwork();s=n.spec;s['capacities_j_per_k'][0]=0
        self.assertEqual(n.spec['capacities_j_per_k'][0],8.)

    def test_large_passive_step_rejected_before_rc_overshoot(self):
        n=ThermalNetwork({'links_w_per_k':np.zeros((11,11)).tolist(),'ambient_conductance_w_per_k':[.5]*11})
        with self.assertRaisesRegex(ValueError,'monotonicity'):
            n.midpoint_step([310.]*11,[0]*3,[.5]*3,10.)

if __name__=='__main__':unittest.main()
