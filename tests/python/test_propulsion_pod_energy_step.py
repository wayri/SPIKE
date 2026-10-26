# SPDX-License-Identifier: Apache-2.0
"""Independent analytic nonlinear/salient Hamiltonian coupling oracles."""
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_energy_step import symmetric_coordinate_gradient, energy_port_step
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_thermal import ThermalNetwork


class AnalyticMagneticPort:
    """Positive balanced Hessian in the tested envelope; no physical motor claim."""
    def __init__(self, baseline=0.): self.baseline=baseline
    def energy_gradient(self,q,theta):
        x,y=q; c,s=np.cos(theta),np.sin(theta)
        energy=1000*x*x+1500*y*y+100*x*y*c+2.5e8*(x**4+y**4)-.01*(x*c+y*s)+1e-5*np.cos(2*theta)
        return {'energy_j':energy+self.baseline,
                'current_coordinates_a':[2000*x+100*y*c+1e9*x**3-.01*c,
                                         3000*y+100*x*c+1e9*y**3-.01*s],
                'torque_n_m':100*x*y*s-.01*(x*s-y*c)+2e-5*np.sin(2*theta)}
    def energy_difference(self,start,end):
        # Cancel the baseline algebraically. Long-double intermediate products
        # and trig difference identities keep the tiny-angle oracle independent.
        a,b=np.asarray(start,np.longdouble),np.asarray(end,np.longdouble)
        mid=(a[2]+b[2])/2; half=(b[2]-a[2])/2
        dc=-2*np.sin(mid)*np.sin(half); ds=2*np.cos(mid)*np.sin(half)
        def power_difference(j,n):
            return (b[j]-a[j])*sum(b[j]**k*a[j]**(n-1-k) for k in range(n))
        product_difference=(b[0]-a[0])*b[1]+a[0]*(b[1]-a[1])
        cos_product=product_difference*np.cos(b[2])+a[0]*a[1]*dc
        linear_cos=(b[0]-a[0])*np.cos(b[2])+a[0]*dc
        linear_sin=(b[1]-a[1])*np.sin(b[2])+a[1]*ds
        return float(1000*power_difference(0,2)+1500*power_difference(1,2)+100*cos_product+
                     np.longdouble(2.5e8)*(power_difference(0,4)+power_difference(1,4))-
                     np.longdouble(.01)*(linear_cos+linear_sin)-2e-5*np.sin(a[2]+b[2])*np.sin(b[2]-a[2]))


class EnergyStepTests(unittest.TestCase):
    def test_symmetric_chain_and_baseline_invariance(self):
        a=[.0002,-.0001,2*np.pi-1e-7];b=[.000201,-.000101,2*np.pi+1e-7]
        ordinary,diag=symmetric_coordinate_gradient(AnalyticMagneticPort(),a,b)
        shifted,_=symmetric_coordinate_gradient(AnalyticMagneticPort(1e12),a,b)
        reversed_dg,_=symmetric_coordinate_gradient(AnalyticMagneticPort(),b,a)
        np.testing.assert_allclose(ordinary,shifted,rtol=0,atol=0)
        np.testing.assert_allclose(ordinary,reversed_dg,rtol=1e-12,atol=1e-14)
        self.assertLess(abs(diag['chain_error_j']),1e-18)

    def test_zero_and_tiny_mixed_unit_increments(self):
        p=AnalyticMagneticPort(1e14);a=np.array([.0003,-.0001,2*np.pi])
        exact=p.energy_gradient(a[:2],a[2])
        g,_=symmetric_coordinate_gradient(p,a,a)
        np.testing.assert_allclose(g,np.r_[exact['current_coordinates_a'],-exact['torque_n_m']],atol=1e-15)
        b=a+np.array([1e-15,-1e-15,1e-12]);g,d=symmetric_coordinate_gradient(p,a,b)
        self.assertLess(abs(g@(b-a)-p.energy_difference(a,b)),1e-23)
        self.assertLess(abs(d['chain_error_j']),1e-23)

    def run_steps(self,h,duration=.002):
        p=AnalyticMagneticPort();thermal=ThermalNetwork()
        q=[.0002,-.0001];angle=.2;speed=30.;T=[298.15]*11;defect=0.
        for _ in range(round(duration/h)):
            out=energy_port_step(p,lambda w:dict(torque_nm=2e-6*w,power_w=2e-6*w*w),
                                thermal,q,angle,speed,T,[.6,.4,.5],12.,h,1e-4,1e-6,500.)
            q=out['flux_coordinates_wb_turn'];angle=out['angle_rad'];speed=out['speed_rad_s'];T=out['temperature_k']
            defect+=out['energy']['defect_j']
            self.assertLess(max(map(abs,out['projected_kvl_residual_v'])),1e-8)
            self.assertAlmostEqual(sum(out['work_currents_a']),0.,places=13)
        return np.r_[q,angle,speed],defect

    def test_actual_nonlinear_thermal_exchange_and_refinement(self):
        answers=[self.run_steps(h) for h in (1e-4,5e-5,2.5e-5)]
        for _,defect in answers:self.assertLess(abs(defect),2e-9)
        error1=np.linalg.norm(answers[0][0]-answers[1][0]);error2=np.linalg.norm(answers[1][0]-answers[2][0])
        self.assertGreater(error1/error2,3.5)
        self.assertLess(error1/error2,4.5)

    def test_rejection_preserves_passed_states(self):
        q=[.0002,-.0001];T=[298.15]*11
        with self.assertRaisesRegex(ValueError,'shaft-work'):
            energy_port_step(AnalyticMagneticPort(),lambda w:dict(torque_nm=1.,power_w=0.),
                             ThermalNetwork(),q,.2,30.,T,[.6,.4,.5],12.,1e-4,1e-4,0.,500.)
        self.assertEqual(q,[.0002,-.0001]);self.assertEqual(T,[298.15]*11)


if __name__=='__main__':unittest.main()
