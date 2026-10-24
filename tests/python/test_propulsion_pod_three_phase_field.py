# SPDX-License-Identifier: Apache-2.0
"""Independent three-phase field, neutral and reciprocal energy checks."""
import math
import unittest
import numpy as np
from python.spike_core.magnetic_fem import MU0, solve_magnetostatic
from python.spike_core.propulsion_pod_three_phase_field import ThreePhaseFieldMotor, validate_field_spec

class ThreePhaseFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.motor=ThreePhaseFieldMotor()

    def direct(self, currents, theta):
        """Re-solve actual nonlinear-kernel interface, not cached port matrices."""
        m = self.motor
        materials = {key: dict(v) for key, v in m.materials.items()}
        materials['rotor']['remanence_t'] = [m.spec['remanence_t']*math.cos(theta),
                                            m.spec['remanence_t']*math.sin(theta)]
        j = m.winding_chi_per_m2@currents
        result = solve_magnetostatic(nodes_m=m.nodes_m.tolist(), triangles=m.triangles.tolist(),
            region_ids=m.region_ids, materials=materials, stack_depth_m=m.spec['stack_depth_m'],
            dirichlet_a_wb_per_m={int(k):0. for k in m.boundary}, current_density_a_per_m2=j.tolist(),
            absolute_tolerance_a=1e-10, relative_tolerance=1e-10)
        a = np.asarray(result['potential_a_wb_per_m'])
        area = np.asarray(result['element_area_m2'])
        linkage = m.spec['stack_depth_m']*np.sum(area[:,None]*m.winding_chi_per_m2*a[m.triangles].mean(axis=1)[:,None],axis=0)
        rotor_area = float(area[np.asarray(m.region_ids)=='rotor'].sum())
        pm_constant = (m.spec['stack_depth_m']*rotor_area*m.spec['remanence_t']**2
                       /(2*MU0*m.spec['rotor_relative_permeability']))
        # Existing kernel's w(B=0)=0 plus the stated recoil reference constant.
        energy = result['magnetic_energy_j']+pm_constant
        return result, linkage, energy, energy-np.asarray(currents)@linkage

    def test_full_pde_linkage_and_virtual_work(self):
        m=self.motor;i=[5.,-2.,-3.];t=.4
        state=m.evaluate(i,t,True);direct,flux,energy,_=self.direct(i,t)
        np.testing.assert_allclose(state['field']['potential_a_wb_per_m'],direct['potential_a_wb_per_m'],rtol=3e-10,atol=1e-13)
        np.testing.assert_allclose(state['flux_linkage_wb_turn'],flux,atol=1e-13)
        self.assertAlmostEqual(state['magnetic_energy_j'],energy,places=11)
        h=1e-4
        torque=-(self.direct(i,t+h)[3]-self.direct(i,t-h)[3])/(2*h)
        self.assertLess(abs(torque-state['torque_n_m']),2e-9)

    def test_six_disjoint_signed_regions_and_gauge(self):
        m=self.motor;chi=m.winding_chi_per_m2;area=m._op.areas
        self.assertEqual(chi.shape[1],3)
        self.assertTrue(np.all(np.count_nonzero(chi,axis=1)<=1))
        for k in range(3):
            self.assertAlmostEqual(float(area[chi[:,k]>0]@chi[chi[:,k]>0,k]),40.,places=11)
            self.assertAlmostEqual(float(area[chi[:,k]<0]@chi[chi[:,k]<0,k]),-40.,places=11)
        state=m.evaluate([3.,1.,-4.],.7,True);a=np.asarray(state['field']['potential_a_wb_per_m'])
        shifted=m.spec['stack_depth_m']*np.sum(area[:,None]*chi*(a[m.triangles]+7).mean(axis=1)[:,None],axis=0)
        np.testing.assert_allclose(shifted,state['flux_linkage_wb_turn'],atol=3e-14)

    def test_neutral_constraint_and_spec_admission(self):
        for i in ([1,2,3],[0,0],[1,True,-2],[float('nan'),0,0],[201,-100,-101]):
            with self.assertRaises(ValueError): self.motor.evaluate(i,0.)
        for s in ({'extra':1},{'turns':True},{'remanence_t':float('inf')}):
            with self.assertRaises(ValueError):validate_field_spec(s)
        self.assertEqual(self.motor.evaluate([1,-1,0],0.)['neutral_current_a'],0.)

    def test_phase_permutation_and_inductance(self):
        m=self.motor;L=m.inductance_h
        np.testing.assert_allclose(L,L.T,atol=1e-14)
        self.assertGreater(np.linalg.eigvalsh(L).min(),0.)
        np.testing.assert_allclose(L,np.roll(np.roll(L,1,axis=0),1,axis=1),atol=1e-13)
        i=np.array([5.,-2.,-3.]);theta=.4
        a=m.evaluate(i,theta);b=m.evaluate(np.roll(i,1),theta+2*math.pi/3)
        np.testing.assert_allclose(b['flux_linkage_wb_turn'],np.roll(a['flux_linkage_wb_turn'],1),atol=2e-13)
        self.assertAlmostEqual(a['torque_n_m'],b['torque_n_m'],places=11)

    def test_constrained_reciprocity_and_energy_chain(self):
        m=self.motor;i=np.array([5.,-2.,-3.]);di=np.array([2.,-3.,1.]);t=.4;h=1e-5
        state=m.evaluate(i,t);dpsi=np.array(state['angular_derivatives']['dflux_dangle_wb_turn_per_rad'])
        fd=(m.evaluate(i+h*di,t)['torque_n_m']-m.evaluate(i-h*di,t)['torque_n_m'])/(2*h)
        self.assertAlmostEqual(fd,float(di@dpsi),places=10)
        omega=37.;dt=1e-6;v=m.inductance_h@di+dpsi*omega
        du=(m.evaluate(i+dt*di,t+dt*omega)['magnetic_energy_j']-m.evaluate(i-dt*di,t-dt*omega)['magnetic_energy_j'])/(2*dt)
        self.assertLess(abs(i@v-du-state['torque_n_m']*omega),1e-8)
        # Any neutral/common voltage contributes zero terminal power.
        self.assertAlmostEqual(float(i@(v+123.)),float(i@v),places=11)

    def test_discrete_energy_and_harmonic_secants(self):
        m=self.motor;i0=np.array([2.,-3.,1.]);i1=np.array([4.,1.,-5.]);t0=.2;t1=.51
        a=m.evaluate(i0,t0);b=m.evaluate(i1,t1);d=t1-t0;terms=m.coupling_terms((t0+t1)/2)
        ps=np.array(terms['dpsi_dangle_wb_turn_per_rad'])*math.sin(d/2)/(d/2)
        cs=terms['dpm_source_potential_dangle_j_per_rad']*math.sin(d)/d
        np.testing.assert_allclose((np.array(b['pm_flux_linkage_wb_turn'])-a['pm_flux_linkage_wb_turn'])/d,ps,atol=1e-14)
        ib=(i0+i1)/2;work=ib@(np.array(b['flux_linkage_wb_turn'])-a['flux_linkage_wb_turn'])
        self.assertLess(abs(work-(b['magnetic_energy_j']-a['magnetic_energy_j'])-(ib@ps+cs)*d),1e-14)

    def test_zero_pm_periodicity_and_bounds(self):
        m=ThreePhaseFieldMotor({'remanence_t':0.});i=[2.,-1.,-1.]
        self.assertEqual(m.evaluate(i,.4)['torque_n_m'],0.)
        np.testing.assert_allclose(m.evaluate(i,.4)['flux_linkage_wb_turn'],m.inductance_h@i,atol=1e-14)
        a=self.motor.evaluate(i,.4);b=self.motor.evaluate(i,.4+2*math.pi)
        np.testing.assert_allclose(a['flux_linkage_wb_turn'],b['flux_linkage_wb_turn'],atol=1e-14)
        self.assertEqual(self.motor.diagnostics['basis_field_solves'],5)

if __name__=='__main__': unittest.main()
