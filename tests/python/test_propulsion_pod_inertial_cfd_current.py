# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from scipy.sparse import bmat,csc_matrix,diags
from python.spike_core.propulsion_pod_inertial_cfd_current import RestartCurrentSchur
from python.spike_core.propulsion_pod_inertial_cfd import RotatingNavierStokes
from tests.python.test_cfd_tetra_stokes import box_mesh


class CurrentRestartAdapter(unittest.TestCase):
    def test_no_seed_factor_no_hidden_solve_and_current_direction(self):
        V=diags([2.,3.,4.,5.]);C=csc_matrix([[1.,-1.,0.,0.],[0.,1.,-1.,0.],[-1.,0.,1.,0.]])
        # Nonsymmetric G with the same constant-pressure null mode.
        G=C.T+csc_matrix([[.1,-.1,0.],[0.,.2,-.2],[.1,0.,-.1],[0.,0.,0.]])
        gauge=np.array([1.,2.,4.]);g=csc_matrix(gauge[:,None])
        A=bmat([[V,G,csc_matrix((4,1))],[C,csc_matrix((3,3)),g],[csc_matrix((1,4)),g.T,csc_matrix((1,1))]],format='csc')
        owner=RestartCurrentSchur(A,4,3,gauge)
        self.assertEqual(owner.factor_nonzeros,0)
        self.assertIsNone(owner.last_factor_options)
        with self.assertRaisesRegex(ValueError,'requires explicit field restart'):owner.solve(np.zeros(8))
        M=owner.with_velocity(A);rhs=np.arange(8,dtype=float)
        np.testing.assert_allclose(A@(M@rhs),rhs,atol=2e-14,rtol=2e-14)
        self.assertEqual(owner.last_factor_options['velocity_drop_tol'],1e-6)
        self.assertEqual(owner.last_factor_options['velocity_fill_factor'],20.)
        self.assertLessEqual(owner.last_factor_nonzeros,30_000_000)

    def test_current_adapter_executes_explicit_field_restart_with_final_gates(self):
        def velocity(name,x):return np.array([x[1],0.,0.])
        s=RotatingNavierStokes(box_mesh(2),.3,1.2,linear_method='fixed_relative_forcing_v1',linear_solver_factory=RestartCurrentSchur)
        initial={'u':np.array([velocity('',x) for x in s.base.xyz]),'p':np.full(len(s.base.mesh['vertices']),7.)}
        state=s.solve(velocity,initial=initial,maximum_line_search_trials=14)
        self.assertLess(state['diagnostics']['nonlinear_relative_residual'],1e-9)
        self.assertLess(state['diagnostics']['relative_energy_residual'],1e-7)
        for profile in state['diagnostics']['Newton_component_timings']:
            self.assertEqual(profile['configured_line_search_trials'],14)
            self.assertTrue(1<=profile['attempted_line_search_trials']<=14)
        self.assertEqual(state['diagnostics']['Newton_component_timings'][0]['factor_options']['velocity_fill_factor'],20.)
        with self.assertRaisesRegex(ValueError,'requires explicit field restart'):s.solve(velocity)

    def test_signed_policy_is_explicit_and_bound_to_options(self):
        V=diags([-2.,3.,4.,5.]);C=csc_matrix([[1.,-1.,0.,0.],[0.,1.,-1.,0.],[-1.,0.,1.,0.]])
        G=C.T+csc_matrix([[.1,-.1,0.],[0.,.2,-.2],[.1,0.,-.1],[0.,0.,0.]])
        gauge=np.array([1.,2.,4.]);g=csc_matrix(gauge[:,None])
        A=bmat([[V,G,csc_matrix((4,1))],[C,csc_matrix((3,3)),g],[csc_matrix((1,4)),g.T,csc_matrix((1,1))]],format='csc')
        with self.assertRaises(ValueError):RestartCurrentSchur(A,4,3,gauge).with_velocity(A)
        owner=RestartCurrentSchur(A,4,3,gauge,diagonal_policy='signed_current_nonzero_v1')
        rhs=np.arange(8,dtype=float);M=owner.with_velocity(A)
        np.testing.assert_allclose(A@(M@rhs),rhs,atol=3e-14,rtol=3e-14)
        self.assertEqual(owner.last_factor_options['diagonal_policy'],'signed_current_nonzero_v1')
        self.assertEqual(owner.last_factor_options_sha256,'c417a55e412b3518613a9008ef1af5306c70996839ca0c8302a6007f0adaf00f')
        self.assertEqual(owner.factor_nonzeros,0)

    def test_density_growth_invalid_inputs_fail_before_artifact_or_geometry_work(self):
        from python.spike_core.propulsion_pod_inertial_cfd_case import run_case
        for growth in (True,False,1.,0.,-1.,3.01,float('inf'),float('nan'),'1.5'):
            with self.subTest(growth=growth),self.assertRaisesRegex(ValueError,'density growth'):
                run_case('absent-mesh','absent-geometry','absent-output',density_growth_factor=growth)
