# SPDX-License-Identifier: Apache-2.0
import unittest
from functools import partial
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_schur import SimpleSchurStokes
import numpy as np
from scipy.sparse import csc_matrix
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd import RotatingNavierStokes, _p2_values
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_forcing import applied_direction, armijo_trial, solve_fixed_step
from tests.python.test_cfd_tetra_stokes import box_mesh


class FixedRelativeNewton(unittest.TestCase):
    def test_applied_direction_and_discarded_lambda_counterexample(self):
        A=csc_matrix([[2.,0.,0.],[0.,0.,1.],[0.,1.,0.]])
        rr=np.array([1.,1.,0.]);g=np.ones(1)
        # A delta=-F exactly, but discarding lambda leaves continuity error1.
        delta=np.linalg.solve(A.toarray(),-rr)
        with self.assertRaisesRegex(ValueError,'physical direction'):applied_direction(A,delta,rr,1,g)
        rr=np.array([1.,0.,0.]);delta,h,slope=solve_fixed_step(A,rr,None,1,g)
        self.assertLessEqual(np.linalg.norm(A@delta+rr),.1*np.linalg.norm(rr))
        self.assertLess(slope,0)

    def test_variable_denominator_false_decrease_is_not_armijo(self):
        old=np.array([1.,0.]);trial=np.array([2.,0.])
        self.assertLess(np.linalg.norm(trial)/100,np.linalg.norm(old))
        self.assertFalse(armijo_trial(old,trial,1.,-.9))
        self.assertTrue(armijo_trial(old,np.array([.1,0.]),1.,-.9))
        with self.assertRaises(ValueError):armijo_trial(old,trial,1.,1.)

    def test_actual_pressure_mean_is_part_of_new_method_residual(self):
        captured=[]
        def observe(matrix,rhs,context):captured.append((matrix.copy(),rhs.copy(),dict(context)))
        solver=RotatingNavierStokes(box_mesh(2),.3,1.2,linear_method='fixed_relative_forcing_v1',linear_solver_factory=partial(SimpleSchurStokes,reference_velocity=False),linear_system_observer=observe)
        def velocity(name,x):return np.array([x[1],0.,0.])
        initial={'u':np.array([velocity('',x) for x in solver.base.xyz]),'p':np.full(len(solver.base.mesh['vertices']),7.)}
        result=solver.solve(velocity,initial=initial)
        self.assertLess(result['diagnostics']['nonlinear_relative_residual'],1e-9)
        self.assertLess(abs(result['diagnostics']['actual_scaled_pressure_mean_residual']),1e-9)
        self.assertTrue(captured);self.assertLess(captured[0][1][-1],0.)
        self.assertEqual(captured[0][2]['n_velocity'],len(solver.base.free))

    def test_admitted_linear_step_does_not_admit_unconverged_nonlinear_field(self):
        a=.2;mu=.3;rho=1.2;O=.4;beta=.1
        def velocity(name,x):return np.array([a*x[0]**2,-2*a*x[0]*x[1],0.])
        def force(x):
            X,Y,Z=x
            return np.array([rho*(2*a*a*X**3+4*a*O*X*Y)-2*mu*a+beta,rho*(2*a*a*X*X*Y+a*O*(3*X*X-2*Y*Y)),0.])
        solver=RotatingNavierStokes(box_mesh(2),mu,rho,linear_method='fixed_relative_forcing_v1');b=solver.base
        initial={'u':np.array([velocity('',x) for x in b.xyz]),'p':np.zeros(len(b.mesh['vertices']))}
        initial['u'].ravel()[b.free]+=np.random.default_rng(83).normal(0,.1,len(b.free))
        with self.assertRaisesRegex(ValueError,'nonlinear residual did not converge'):
            solver.solve(velocity,[0,0,O],body_force=force,initial=initial,max_iterations=1)

    def test_nonexact_SUPG_MMS_refinement_preserves_final_gates(self):
        a=.2;mu=.3;rho=1.2;O=.4;beta=.1;gamma=.07;errors=[];pressure_errors=[]
        def velocity(name,x):return np.array([a*x[0]**3,-3*a*x[0]**2*x[1],0.])
        def force(x):
            X,Y,Z=x
            return np.array([rho*(3*a*a*X**5+6*a*O*X*X*Y)-6*mu*a*X+beta,rho*(3*a*a*X**4*Y+4*a*O*X**3-6*a*O*X*Y*Y)+6*mu*a*Y+2*gamma*Y,0.])
        for n in (2,3):
            s=RotatingNavierStokes(box_mesh(n),mu,rho,supg=True,quadrature_order=6,linear_method='fixed_relative_forcing_v1');state=s.solve(velocity,[0,0,O],body_force=force)
            u=np.einsum('qi,cia->cqa',s.N,state['u'][s.base.local]);exact=np.array([[velocity('',x) for x in row] for row in s.points]);errors.append(float(np.sqrt(np.sum(s.weights*np.sum((u-exact)**2,axis=2)))))
            pressure=(s.Q@state['p'][s.base.mesh['cells']].T).T;exact_pressure=beta*(s.points[:,:,0]-.5)+gamma*(s.points[:,:,1]**2-1/3)
            pressure_errors.append(float(np.sqrt(np.sum(s.weights*(pressure-exact_pressure)**2))))
            self.assertLess(state['diagnostics']['nonlinear_relative_residual'],1e-9)
            self.assertLess(state['diagnostics']['relative_energy_residual'],1e-7)
            self.assertEqual(state['diagnostics']['Newton_linear_method'],'fixed_relative_forcing_v1')
        # h changes1/2 ->1/3, not a factor2; compare observed order rather
        # than incorrectly requiring the factor4 used by the2->4 fixture.
        observed_order=float(np.log(errors[0]/errors[1])/np.log(1.5))
        self.assertGreater(observed_order,2.5)
        self.assertGreater(float(np.log(pressure_errors[0]/pressure_errors[1])/np.log(1.5)),1.5)

if __name__=='__main__':unittest.main()
