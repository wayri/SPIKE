# SPDX-License-Identifier: Apache-2.0
import math
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_annular_gap import AnnularGap, MU0


class AnnularGapTests(unittest.TestCase):
    def test_constant_trace_logarithmic_solution_and_gauge(self):
        g=AnnularGap(1.,2.,.01,3);a=np.zeros(g.size);b=a.copy();a[0]=math.sqrt(2*math.pi)
        out=g.energy_torque(a,b,.4)
        self.assertAlmostEqual(out['vacuum_energy_j'],math.pi*.01/(MU0*math.log(2)),places=10)
        f=g.field(a,b,.4,np.array([1.,math.sqrt(2),2.]),0.)
        np.testing.assert_allclose(f['potential_a_wb_per_m'],[1.,.5,0.],atol=2e-16)
        self.assertEqual(out['rotor_torque_n_m'],0.)
        K,_=g.matrices(.4);v=np.zeros(2*g.size);v[0]=v[g.size]=1.
        np.testing.assert_allclose(K@v,0.,atol=1e-10)
        common=np.zeros(g.size);common[0]=1e8
        self.assertEqual(g.energy_torque(common,common,.4)['vacuum_energy_j'],0.)
        with self.assertRaises(ValueError):g.field(a,b,float('nan'),1.5,0.)
        huge=np.ones(g.size)*1e308
        with self.assertRaises(ValueError):g.energy_torque(huge,huge,.4)

    def test_single_mode_torque_matches_contour_and_energy_derivative(self):
        g=AnnularGap(.04,.045,.025,5);a=np.zeros(g.size);b=a.copy();n=3
        a[2*n-1]=.002*math.sqrt(math.pi);b[2*n-1]=.003*math.sqrt(math.pi);theta=.23
        out=g.energy_torque(a,b,theta);eps=1e-6
        derivative=(g.energy_torque(a,b,theta+eps)['vacuum_energy_j']-g.energy_torque(a,b,theta-eps)['vacuum_energy_j'])/(2*eps)
        self.assertAlmostEqual(out['rotor_torque_n_m'],-derivative,places=7)
        phi=np.arange(2048)*2*math.pi/2048
        for r in (.041,.0425,.044):
            f=g.field(a,b,theta,r,phi)
            stress=g.depth*r*r/MU0*2*math.pi*np.mean(f['radial_b_t']*f['azimuthal_b_t'])
            self.assertAlmostEqual(stress,out['rotor_torque_n_m'],places=10)
        K,_=g.matrices(theta);self.assertGreater(np.linalg.eigvalsh(K)[1],0.)
        np.testing.assert_allclose(g.matrices(theta+2*math.pi)[0],K,atol=1e-8)


if __name__=='__main__':unittest.main()
