# SPDX-License-Identifier: Apache-2.0
"""Independent radial/Maxwell oracles; high modes use only small O(N) arrays."""
import math
import unittest
import numpy as np

from python.spike_core.propulsion_pod_annular_gap import AnnularGap
from python.spike_core.propulsion_pod_modal_gap import ModalGap


def independent_mode(gap, n, r, s, angle):
    """Integrate separated harmonic solution, not the endpoint gap quadratic."""
    L=math.log(gap.b/gap.a);co=math.cos(n*angle);si=math.sin(n*angle)
    u=np.array([co*r[0]-si*r[1],si*r[0]+co*r[1]])
    z,w=np.polynomial.legendre.leggauss(64);x=(z+1)*L/2;w=w*L/2
    den=math.sinh(n*L)
    y=(np.sinh(n*(L-x))[:,None]*u+np.sinh(n*x)[:,None]*s)/den
    dy=n*(-np.cosh(n*(L-x))[:,None]*u+np.cosh(n*x)[:,None]*s)/den
    energy=gap.scale/2*np.sum(w*(np.sum(dy*dy,axis=1)+n*n*np.sum(y*y,axis=1)))
    x=.37*L;y=(math.sinh(n*(L-x))*u+math.sinh(n*x)*s)/den
    dy=n*(-math.cosh(n*(L-x))*u+math.cosh(n*x)*s)/den
    phi=np.arange(4*n+9)*2*math.pi/(4*n+9)
    ap=n*(-y[0]*np.sin(n*phi)+y[1]*np.cos(n*phi))/math.sqrt(math.pi)
    ax=(dy[0]*np.cos(n*phi)+dy[1]*np.sin(n*phi))/math.sqrt(math.pi)
    torque=-gap.scale*2*math.pi*np.mean(ap*ax)
    return float(energy),float(torque)


class ModalGapTests(unittest.TestCase):
    def test_stable_difference_mixed_and_tiny_increments(self):
        gap=AnnularGap(.04,.04016,.025,3);theta=.23
        modal=ModalGap(gap,theta);rng=np.random.default_rng(912)
        c=rng.normal(size=2*gap.size)*.001;direction=rng.normal(size=len(c))*1e-8
        delta=1e-8
        difference=modal.energy_difference(c,c+direction,delta)
        # Independently integrate dE along the straight coefficient/angle path.
        nodes,weights=np.polynomial.legendre.leggauss(12);reference=0.
        for node,weight in zip(nodes,weights):
            t=(node+1)/2;other=ModalGap(gap,float(theta+t*delta));v=c+t*direction
            reference+=weight/2*(other.apply(v)@direction-other.energy_torque(v)['rotor_torque_n_m']*delta)
        self.assertAlmostEqual(difference,reference,delta=2e-13)
        self.assertAlmostEqual(difference,-ModalGap(gap,theta+delta).energy_difference(c+direction,c,-delta),delta=2e-13)
    def test_dense_reference_action_angle_and_energy_parity(self):
        rng=np.random.default_rng(817)
        for count in (0,3,31):
            for dimensions in ((.04,.040001),(.04,.07)):
                gap=AnnularGap(*dimensions,.025,count)
                for angle in (0.,.173,-.7):
                    modal=ModalGap(gap,angle);c=rng.normal(size=2*gap.size)*.001
                    K,dK=gap.matrices(angle)
                    np.testing.assert_allclose(modal.apply(c),K@c,rtol=2e-11,atol=2e-9)
                    np.testing.assert_allclose(modal.angle_derivative_action(c),dK@c,rtol=2e-12,atol=2e-9)
                    assembled=modal.add_to_dense(np.zeros_like(K))
                    np.testing.assert_allclose(assembled,K,rtol=3e-15,atol=2e-9)
                    old=gap.energy_torque(c[:gap.size],c[gap.size:],angle);new=modal.energy_torque(c)
                    for key in old:self.assertAlmostEqual(old[key],new[key],delta=2e-12*max(1.,abs(old[key])))
                    q=rng.normal(size=len(c));self.assertAlmostEqual(q@modal.apply(c),c@modal.apply(q),delta=2e-7)

    def test_high_modes_independent_radial_energy_and_maxwell_torque(self):
        for cutoff in (255,1007,1024):
            gap=AnnularGap(.04,.04016,.025,cutoff);angle=.173
            modal=ModalGap(gap,angle);c=np.zeros(2*gap.size);expected=np.zeros(2)
            for n,r,s in ((1,np.array([.001,-.0002]),np.array([-.0003,.0007])),
                          (cutoff,np.array([.0004,.0009]),np.array([.0008,-.0006]))):
                c[2*n-1:2*n+1]=r;c[gap.size+2*n-1:gap.size+2*n+1]=s
                expected+=independent_mode(gap,n,r,s,angle)
            actual=modal.energy_torque(c)
            np.testing.assert_allclose([actual['vacuum_energy_j'],actual['rotor_torque_n_m']],expected,rtol=2e-11,atol=2e-11)
            self.assertGreater(actual['vacuum_energy_j'],0)
            # Energy's coefficient derivative is the action; central quadratic FD.
            q=np.sin(np.arange(len(c))*.3)*.0001;h=1e-4
            derivative=(modal.energy_torque(c+h*q)['vacuum_energy_j']-modal.energy_torque(c-h*q)['vacuum_energy_j'])/(2*h)
            self.assertAlmostEqual(derivative,q@modal.apply(c),delta=2e-9)
            errors=[]
            for h in (1e-6,5e-7,2.5e-7):
                plus=ModalGap(gap,angle+h).energy_torque(c)['vacuum_energy_j']
                minus=ModalGap(gap,angle-h).energy_torque(c)['vacuum_energy_j']
                errors.append(abs(-(plus-minus)/(2*h)-actual['rotor_torque_n_m']))
            self.assertLess(errors[-1],errors[0]/8)
            self.assertLess(errors[-1]/abs(actual['rotor_torque_n_m']),2e-8)

    def test_constant_gauge_and_rejections(self):
        gap=AnnularGap(.04,.041,.025,1024);modal=ModalGap(gap,.2)
        c=np.zeros(2*gap.size);c[0]=c[gap.size]=1e8
        np.testing.assert_array_equal(modal.apply(c),0)
        np.testing.assert_array_equal(modal.angle_derivative_action(c),0)
        self.assertEqual(modal.energy_torque(c),{'vacuum_energy_j':0.,'rotor_torque_n_m':0.})
        for bad in ([0.],np.ones(len(c),complex),np.full(len(c),float('nan'))):
            with self.assertRaises(ValueError):modal.apply(bad)
        for bad in (True,float('inf')):
            with self.assertRaises(ValueError):ModalGap(gap,bad)
        with self.assertRaises(ValueError):modal.add_to_dense(np.zeros((2,2)))
        gap.maximum_mode=1025
        with self.assertRaises(ValueError):ModalGap(gap,.2)


if __name__=='__main__':unittest.main()
