# SPDX-License-Identifier: Apache-2.0
"""Independent derivative and Legendre oracles on small supplied-law fields."""
import unittest
from unittest.mock import patch
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_nonlinear_port import DirectNonlinearMagneticPort
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_three_phase import STAR
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_energy_step import symmetric_coordinate_gradient
from tests.python.test_propulsion_pod_nonlinear_motor import prepare


class DirectNonlinearPortTests(unittest.TestCase):
    def test_source_binding_includes_all_reviewed_physics_dependencies(self):
        import hashlib
        model,_=prepare(False);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
        expected={'propulsion_pod_nonlinear_port.py','propulsion_pod_nonlinear_motor.py',
            'propulsion_pod_nonlinear_p2.py','propulsion_pod_modal_gap.py','magnetic_fem.py',
            'propulsion_pod_annular_gap.py','propulsion_pod_magnetic_p2.py',
            'propulsion_pod_separated_motor.py','propulsion_pod_three_phase.py'}
        bound=p._identity['implementation_sha256']
        self.assertEqual(set(bound),expected)
        for path in p._source_paths:self.assertEqual(bound[path.name],hashlib.sha256(path.read_bytes()).hexdigest())
        changed=dict(bound);changed['propulsion_pod_annular_gap.py']='changed'
        with patch.object(p,'_source_hashes',return_value=changed):
            with self.assertRaisesRegex(ValueError,'dependencies'):p.flux_coordinates([0,0,0],.2)

    def test_run_expiry_precedes_validation_and_applies_to_cached_hits(self):
        model,_=prepare(False);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
        p.flux_coordinates([1,-1,0],.2)
        with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_nonlinear_port.time.monotonic',return_value=100.) as clock:
            with p.bounded_run(110.):
                p._begin();self.assertEqual(p._deadline,110.)
                clock.return_value=110.
                with patch.object(model,'validate_dependencies',side_effect=AssertionError('costly validation reached')):
                    with self.assertRaisesRegex(ValueError,'run deadline'):p.flux_coordinates([1,-1,0],.2)
                with patch.object(model,'evaluate',side_effect=AssertionError('field solve reached')):
                    with self.assertRaisesRegex(ValueError,'wall budget'):p._state([1,-1],.2)
            for invalid in (100.,99.,float('inf'),float('nan'),True,None):
                with self.assertRaises(ValueError):
                    with p.bounded_run(invalid):pass

    def test_nested_run_minimum_and_restoration_after_failure(self):
        model,_=prepare(False);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
        identity=p.source_sha256
        with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_nonlinear_port.time.monotonic',return_value=100.):
            p._begin();self.assertEqual(p._deadline,160.)
            with p.bounded_run(150.):
                p._begin();self.assertEqual(p._deadline,150.)
                with p.bounded_run(170.):
                    p._begin();self.assertEqual(p._deadline,150.)
                    self.assertEqual(p._run_deadline,150.)
                with self.assertRaisesRegex(RuntimeError,'deliberate'):
                    with p.bounded_run(125.):
                        p._begin();self.assertEqual(p._deadline,125.)
                        raise RuntimeError('deliberate')
                self.assertEqual(p._run_deadline,150.);self.assertEqual(p._deadline,150.)
            self.assertEqual(p._deadline,160.);self.assertEqual(p._run_deadline,float('inf'))
            with p.bounded_run(1000.):
                p._begin();self.assertEqual(p._deadline,160.)
        self.assertEqual(p.source_sha256,identity)

    def test_current_and_angle_sensitivity_against_independent_solves(self):
        model, _ = prepare(True)
        i=np.array([9000.,-2000.,-7000.]);theta=.173
        result=model.evaluate(i,theta,include_sensitivities=True)
        M=result['balanced_differential_inductance_h']
        for j in range(2):
            delta=STAR[:,j]*.01
            plus=model.evaluate(i+delta,theta);minus=model.evaluate(i-delta,theta)
            fd=STAR.T@(np.array(plus['flux_linkage_wb_turn'])-minus['flux_linkage_wb_turn'])/.02
            np.testing.assert_allclose(M[:,j],fd,rtol=2e-6,atol=1e-13)
        h=1e-5
        plus=model.evaluate(i,theta+h);minus=model.evaluate(i,theta-h)
        fd=(np.array(plus['flux_linkage_wb_turn'])-minus['flux_linkage_wb_turn'])/(2*h)
        np.testing.assert_allclose(result['phase_flux_angle_derivative_wb_turn_per_rad'],fd,rtol=2e-6,atol=1e-10)

    def test_nonlinear_inverse_and_scalar_derivatives(self):
        model,_=prepare(True);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10000.)
        i=[9000.,-2000.,-7000.];theta=.173;q=p.flux_coordinates(i,theta)
        result=p.energy_gradient(q,theta)
        np.testing.assert_allclose(result['current_coordinates_a'],i[:2],rtol=1e-7,atol=1e-5)
        a=np.r_[q,theta];direction=np.array([1e-8,-2e-8,1e-4])
        expected=np.r_[i[:2],-result['torque_n_m']]@direction
        errors=[]
        for h in (1.,.5,.25):
            fd=p.energy_difference(a-h*direction,a+h*direction)/(2*h)
            errors.append(abs(fd-expected))
        self.assertLess(errors[-1],1e-9)
        self.assertLess(errors[-1],errors[0])

    def test_stable_joint_difference_and_discrete_chain(self):
        model,_=prepare(True);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10000.)
        a=np.r_[p.flux_coordinates([4000.,-1000.,-3000.],.2),.2]
        b=a+np.array([1e-9,-2e-9,1e-5])
        dg,diagnostics=symmetric_coordinate_gradient(p,a,b)
        reverse,_=symmetric_coordinate_gradient(p,b,a)
        np.testing.assert_allclose(dg,reverse,rtol=1e-7,atol=1e-7)
        self.assertLess(abs(diagnostics['chain_error_j']),1e-11)
        tiny=a+np.array([1e-16,-1e-16,1e-12])
        value=p.energy_difference(a,tiny)
        state=p.energy_gradient(a[:2],float(a[2]))
        expected=np.r_[state['current_coordinates_a'],-state['torque_n_m']]@(tiny-a)
        self.assertAlmostEqual(value,expected,delta=2e-14)

    def test_linear_limit_and_rejections(self):
        model,_=prepare(False);p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.,end_turn_inductance_h=[1e-5,2e-5,3e-5])
        i=np.array([3.,-1.,-2.]);theta=.31;linear=model.motor.linear_ports(theta)
        flux=np.array(linear['pm_flux_linkage_wb_turn'])+(np.array(linear['inductance_h'])+p.end)@i
        q=p.flux_coordinates(i,theta);np.testing.assert_allclose(q,STAR.T@flux,atol=1e-12)
        np.testing.assert_allclose(p.energy_gradient(q,theta)['current_coordinates_a'],i[:2],atol=1e-7)
        with self.assertRaisesRegex(ValueError,'balanced'):p.flux_coordinates([1,1,1],theta)
        with self.assertRaisesRegex(ValueError,'envelope'):p.flux_coordinates([11,-11,0],theta)
        with self.assertRaises(ValueError):p.energy_gradient([1.,1.],theta)
        p.max_current_a=11.
        with self.assertRaisesRegex(ValueError,'dependencies'):p.energy_gradient(q,theta)

    def test_explicit_resource_and_input_bounds(self):
        model,_=prepare(False)
        for args in ({'maximum_seconds':float('nan')},{'maximum_field_solves':True},
                     {'maximum_cache_bytes':0},{'end_turn_inductance_h':[-1,0,0]}):
            with self.assertRaises(ValueError):DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.,**args)
        p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.,maximum_cache_bytes=1)
        with self.assertRaisesRegex(ValueError,'cache byte'):p.flux_coordinates([1,-1,0],.2)
        p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10000.,maximum_field_solves=1)
        with self.assertRaisesRegex(ValueError,'field solve budget'):p.energy_gradient([.01,.01],.2)

    def test_energy_baseline_and_deficient_winding_rank(self):
        model,_=prepare(False)
        p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
        a=np.r_[p.flux_coordinates([3.,-1.,-2.],.2),.2];b=a+[1e-12,-2e-12,1e-10]
        expected=p.energy_difference(a,b)
        original=model.evaluate
        def shifted(*args,**kwargs):
            result=original(*args,**kwargs);result['magnetic_energy_j']+=1e12;return result
        with patch.object(model,'evaluate',side_effect=shifted):
            changed=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
            self.assertEqual(changed.energy_difference(a,b),expected)
        from tests.python.test_propulsion_pod_separated_motor import fixture,SeparatedMotor
        from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_nonlinear_p2 import NonlinearP2MagneticOperator
        from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_nonlinear_motor import NonlinearSeparatedMotor
        data=fixture()
        for name in ('rotor','stator'):
            data[name]['winding_chi_per_m2']=np.zeros((len(data[name]['triangles']),3)).tolist()
        motor=SeparatedMotor(data,maximum_mode=2)
        model=NonlinearSeparatedMotor(motor,NonlinearP2MagneticOperator(motor.rotor.op,{}),
            NonlinearP2MagneticOperator(motor.stator.op,{}),{n:data[n]['winding_chi_per_m2'] for n in ('rotor','stator')})
        p=DirectNonlinearMagneticPort(model,maximum_phase_current_a=10.)
        with self.assertRaisesRegex(ValueError,'not positive'):p.flux_coordinates([0,0,0],.2)

if __name__=='__main__':unittest.main()
