# SPDX-License-Identifier: Apache-2.0
"""Independent full-PDE virtual-work and terminal reciprocity checks."""
import math
import unittest
import numpy as np

from python.spike_core.magnetic_fem import MU0, solve_magnetostatic
from python.spike_core.propulsion_pod_field import FieldMotor
from python.spike_core.propulsion_pod_field import validate_field_spec, DEFAULT_SPEC
from unittest.mock import patch


class FieldMotorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = FieldMotor()

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

    def test_actual_pde_basis_solution_and_linkage_quadrature(self):
        m=self.motor;i=[5.,-2.];theta=.4
        reduced=m.evaluate(i,theta,include_field=True)
        direct,linkage,energy,_=self.direct(i,theta)
        np.testing.assert_allclose(reduced['field']['potential_a_wb_per_m'],direct['potential_a_wb_per_m'],rtol=2e-11,atol=1e-13)
        np.testing.assert_allclose(reduced['field']['element_b_t'],direct['element_b_t'],rtol=2e-10,atol=1e-11)
        np.testing.assert_allclose(reduced['flux_linkage_wb_turn'],linkage,rtol=2e-11,atol=1e-14)
        self.assertAlmostEqual(reduced['magnetic_energy_j'],energy,places=11)
        self.assertTrue(direct['convergence']['converged'])

    def test_direct_full_field_virtual_work_torque(self):
        i=[5.,-2.];theta=.4;delta=1e-4
        _,_,_,upper=self.direct(i,theta+delta)
        _,_,_,lower=self.direct(i,theta-delta)
        virtual_torque=-(upper-lower)/(2*delta)
        torque=self.motor.evaluate(i,theta)['torque_n_m']
        self.assertLess(abs(virtual_torque-torque),2e-9)

    def test_gauge_invariant_balanced_signed_turns(self):
        m=self.motor;state=m.evaluate([3.,1.],.7,include_field=True)
        f=state['field'];a=np.asarray(f['potential_a_wb_per_m']);area=np.asarray(f['element_area_m2'])
        chi=np.asarray(f['winding_chi_per_m2']);depth=m.spec['stack_depth_m']
        for column in range(2):
            self.assertAlmostEqual(float(area[chi[:,column]>0]@chi[chi[:,column]>0,column]),m.spec['turns'],places=11)
            self.assertAlmostEqual(float(area[chi[:,column]<0]@chi[chi[:,column]<0,column]),-m.spec['turns'],places=11)
        shifted=depth*np.sum(area[:,None]*chi*(a[m.triangles]+7).mean(axis=1)[:,None],axis=0)
        np.testing.assert_allclose(shifted,state['flux_linkage_wb_turn'],rtol=0,atol=2e-14)

    def test_inductance_is_reciprocal_positive_and_current_derivative(self):
        m=self.motor;L=m.inductance_h
        np.testing.assert_allclose(L,L.T,rtol=0,atol=1e-14)
        self.assertTrue(np.all(np.linalg.eigvalsh(L)>0))
        for column in range(2):
            i=np.array([4.,-7.]);d=np.zeros(2);d[column]=.001
            plus=m.evaluate(i+d,.3);minus=m.evaluate(i-d,.3)
            derivative=(np.asarray(plus['flux_linkage_wb_turn'])-minus['flux_linkage_wb_turn'])/.002
            np.testing.assert_allclose(derivative,L[:,column],rtol=1e-9,atol=1e-13)

    def test_angle_derivatives_and_torque_current_reciprocity(self):
        m=self.motor;i=np.array([5.,-2.]);theta=.4;delta=1e-5
        state=m.evaluate(i,theta);upper=m.evaluate(i,theta+delta);lower=m.evaluate(i,theta-delta)
        fd=(np.array(upper['flux_linkage_wb_turn'])-lower['flux_linkage_wb_turn'])/(2*delta)
        expected=state['angular_derivatives']['dflux_dangle_wb_turn_per_rad']
        np.testing.assert_allclose(fd,expected,rtol=1e-8,atol=1e-12)
        for column in range(2):
            d=np.zeros(2);d[column]=delta
            derivative=(m.evaluate(i+d,theta)['torque_n_m']-m.evaluate(i-d,theta)['torque_n_m'])/(2*delta)
            self.assertAlmostEqual(derivative,expected[column],places=10)
        dtorque=(upper['torque_n_m']-lower['torque_n_m'])/(2*delta)
        self.assertAlmostEqual(dtorque,state['angular_derivatives']['dtorque_dangle_nm_per_rad'],places=9)

    def test_terminal_energy_shaft_power_chain_rule(self):
        m=self.motor;i=np.array([5.,-2.]);idot=np.array([-3.,1.]);omega=37.;theta=.4;dt=1e-6
        state=m.evaluate(i,theta)
        voltage=m.inductance_h@idot+np.array(state['angular_derivatives']['dflux_dangle_wb_turn_per_rad'])*omega
        up=m.evaluate(i+dt*idot,theta+dt*omega)['magnetic_energy_j']
        down=m.evaluate(i-dt*idot,theta-dt*omega)['magnetic_energy_j']
        storage_rate=(up-down)/(2*dt)
        self.assertLess(abs(i@voltage-storage_rate-state['torque_n_m']*omega),1e-8)

    def test_exact_finite_step_port_energy_and_harmonic_secants(self):
        m=self.motor;i0=np.array([2.,-3.]);i1=np.array([4.,1.]);t0=.2;t1=.51
        a=m.evaluate(i0,t0);b=m.evaluate(i1,t1);mid=(t0+t1)/2;delta=t1-t0
        terms=m.coupling_terms(mid)
        delta_psi=np.asarray(b['pm_flux_linkage_wb_turn'])-a['pm_flux_linkage_wb_turn']
        delta_c=b['pm_source_potential_j']-a['pm_source_potential_j']
        psi_secant=np.asarray(terms['dpsi_dangle_wb_turn_per_rad'])*math.sin(delta/2)/(delta/2)
        c_secant=terms['dpm_source_potential_dangle_j_per_rad']*math.sin(delta)/delta
        np.testing.assert_allclose(delta_psi/delta,psi_secant,atol=1e-15)
        self.assertLess(abs(delta_c/delta-c_secant),1e-14)
        ibar=(i0+i1)/2
        discrete_torque=float(ibar@psi_secant+c_secant)
        port_work=float(ibar@(np.asarray(b['flux_linkage_wb_turn'])-a['flux_linkage_wb_turn']))
        stored=b['magnetic_energy_j']-a['magnetic_energy_j']
        self.assertLess(abs(port_work-stored-discrete_torque*delta),1e-14)

    def test_periodicity_pm_zero_current_and_current_reversal(self):
        m=self.motor
        zero=m.evaluate([0.,0.],.31)
        # Fixed fourfold circular geometry has no material-position saliency.
        self.assertLess(abs(zero['torque_n_m']),1e-11)
        self.assertGreater(np.linalg.norm(zero['flux_linkage_wb_turn']),0.)
        a=m.evaluate([5.,-2.],.31);b=m.evaluate([-5.,2.],.31)
        np.testing.assert_allclose(np.asarray(a['flux_linkage_wb_turn'])+b['flux_linkage_wb_turn'],2*np.asarray(zero['flux_linkage_wb_turn']),rtol=1e-12,atol=1e-14)
        periodic=m.evaluate([5.,-2.],.31+2*math.pi)
        np.testing.assert_allclose(a['flux_linkage_wb_turn'],periodic['flux_linkage_wb_turn'],atol=1e-14)
        self.assertAlmostEqual(a['torque_n_m'],periodic['torque_n_m'],places=13)

    def test_zero_remanence_and_mutation_isolation(self):
        m=FieldMotor({'remanence_t':0.})
        state=m.evaluate([3.,-2.],.5)
        self.assertEqual(state['torque_n_m'],0.)
        np.testing.assert_allclose(state['flux_linkage_wb_turn'],m.inductance_h@[3.,-2.],rtol=1e-12)
        spec=m.spec;spec['remanence_t']=1.
        self.assertEqual(m.spec['remanence_t'],0.)
        with self.assertRaises(ValueError):m.inductance_h[0,0]=0.

    def test_strict_input_and_geometry_budgets(self):
        for spec in ({'extra':1},{'turns':True},{'remanence_t':float('nan')},
                     {'rotor_radius_m':.03},{'mesh_edge_m':.0005,'outer_radius_m':.2}):
            with self.subTest(spec=spec),self.assertRaises(ValueError):FieldMotor(spec)
        for current,angle in (([1.],0.),([1.,True],0.),([1.,float('inf')],0.),([201.,0.],0.),([0.,0.],float('nan'))):
            with self.subTest(current=current,angle=angle),self.assertRaises(ValueError):self.motor.evaluate(current,angle)

    def test_pure_shared_spec_validation_boundaries(self):
        raw={'turns':1,'remanence_t':0,'max_current_a':.001}
        with patch('python.spike_core.propulsion_pod_field.solve_magnetostatic') as solver:
            clean=validate_field_spec(raw)
            self.assertEqual(clean['turns'],1)
            self.assertIs(type(clean['remanence_t']),float)
            self.assertEqual(validate_field_spec(None),DEFAULT_SPEC)
            solver.assert_not_called()
        self.assertEqual(raw,{'turns':1,'remanence_t':0,'max_current_a':.001})
        clean['turns']=7
        self.assertEqual(raw['turns'],1)
        for spec in ({'unknown':1},{'turns':True},{'mesh_edge_m':False},
                     {'remanence_t':float('nan')},{'max_current_a':float('inf')},
                     {'rotor_radius_m':.03},{'mesh_edge_m':.0005,'outer_radius_m':.2}):
            with self.subTest(spec=spec),self.assertRaises(ValueError):validate_field_spec(spec)


if __name__=='__main__':unittest.main()
