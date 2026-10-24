# SPDX-License-Identifier: Apache-2.0
import copy
import math
import unittest
import numpy as np
from python.spike_core.propulsion_pod_energy_table import PeriodicLinearMagneticPort, CONTRACT
from python.spike_core.propulsion_pod_energy_step import symmetric_coordinate_gradient


def table(intervals=96):
    angles=np.linspace(0,2*math.pi,intervals+1)
    matrices=[np.diag([.002+.0002*np.cos(t),.003+.0001*np.sin(t),.0025]) for t in angles]
    flux=[.01*np.cos(t-np.arange(3)*2*math.pi/3) for t in angles]
    return dict(contract=CONTRACT,angles_rad=angles.tolist(),inductance_h=np.asarray(matrices).tolist(),
                pm_flux_wb_turn=np.asarray(flux).tolist(),zero_current_coenergy_j=(-1000+.002*np.cos(12*angles)).tolist(),
                maximum_phase_current_a=100.)


class PeriodicEnergyTableTests(unittest.TestCase):
    def test_inverse_full_flux_and_gradient(self):
        port=PeriodicLinearMagneticPort(table(),[.0001]*3);theta=.234
        q=port.flux_coordinates([1.,-.2,-.8],theta);s=port.energy_gradient(q,theta)
        np.testing.assert_allclose(s['current_coordinates_a'],[1.,-.2],atol=2e-15)
        np.testing.assert_allclose(np.array([[1,0,-1],[0,1,-1]])@s['flux_linkage_wb_turn'],q,atol=1e-16)
        eps=1e-6
        derivative=port.energy_difference([*q,theta-eps],[*q,theta+eps])/(2*eps)
        self.assertAlmostEqual(derivative,-s['torque_n_m'],places=9)
        self.assertGreater(port.diagnostics['minimum_bernstein_balanced_inductance_h'],0.)

    def test_stable_baseline_difference_and_periodic_work(self):
        port=PeriodicLinearMagneticPort(table());a=np.array([.001,-.002,2*math.pi-1e-10]);b=a+[1e-14,-1e-14,2e-10]
        dg,diag=symmetric_coordinate_gradient(port,a,b)
        self.assertLess(abs(dg@(b-a)-port.energy_difference(a,b)),1e-17)
        self.assertLess(abs(port.energy_difference([.001,-.002,0],[.001,-.002,2*math.pi])),1e-15)
        shifted=copy.deepcopy(table());shifted['zero_current_coenergy_j']=[x+10 for x in shifted['zero_current_coenergy_j']]
        other=PeriodicLinearMagneticPort(shifted)
        self.assertAlmostEqual(port.energy_difference(a,b),other.energy_difference(a,b),places=19)

    def test_envelope_reciprocity_period_and_spd_rejected(self):
        for change in ('reciprocity','period','indefinite','nan'):
            bad=table()
            if change=='reciprocity':bad['inductance_h'][3][0][1]=.1
            if change=='period':bad['pm_flux_wb_turn'][-1][0]+=.1
            if change=='indefinite':bad['inductance_h'][4][0][0]=-.1
            if change=='nan':bad['zero_current_coenergy_j'][2]=float('nan')
            with self.subTest(change=change),self.assertRaises(ValueError):PeriodicLinearMagneticPort(bad)
        port=PeriodicLinearMagneticPort(table())
        with self.assertRaisesRegex(ValueError,'envelope'):port.flux_coordinates([101.,-101.,0.],0.)
        with self.assertRaisesRegex(ValueError,'envelope'):port.energy_difference([0.,0.,0.],[100.,0.,.1])


if __name__=='__main__':unittest.main()
