# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd import _line_search_steps, RotatingNavierStokes
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_forcing import armijo_trial
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_case import run_case


class ExplicitLineSearchBudget(unittest.TestCase):
    def test_analytic_curvature_witness_requires_more_than_seven_trials(self):
        # F(x)=1-x+200*x^2 at x=0. Exact Newton q=1, norm-merit slope=-1.
        # Same production Armijo inequality; seven steps all fail, 1/256 passes.
        residual=np.array([1.]);slope=-1.
        def accepted(budget):
            for alpha in _line_search_steps(budget):
                trial=np.array([1-alpha+200*alpha*alpha])
                if armijo_trial(residual,trial,alpha,slope):return alpha
            return None
        self.assertEqual(_line_search_steps(),(1.,.5,.25,.125,.0625,.03125,.015625))
        self.assertIsNone(accepted(7))
        self.assertEqual(accepted(14),1/256)
        self.assertFalse(armijo_trial(residual,np.array([1-1/128+200/128**2]),1/128,slope))
        # Extending the search budget is not permission to accept a bad trial.
        self.assertFalse(armijo_trial(residual,np.array([2.]),1/8192,slope))

    def test_invalid_budget_rejected_before_solver_update_and_case_artifacts(self):
        for budget in (True,False,0,-1,15,7.,'14',None,np.int64(14)):
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(ValueError,'exact integer'):_line_search_steps(budget)
                with self.assertRaisesRegex(ValueError,'exact integer'):
                    RotatingNavierStokes.solve(None,None,maximum_line_search_trials=budget)
                with self.assertRaisesRegex(ValueError,'exact integer'):
                    run_case('absent-mesh','absent-geometry','absent-output',maximum_line_search_trials=budget)
        self.assertEqual(_line_search_steps(1),(1.,))
        self.assertEqual(len(_line_search_steps(14)),14)
        self.assertEqual(_line_search_steps(14)[-1],1/8192)
