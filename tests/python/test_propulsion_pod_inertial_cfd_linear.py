# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch
import numpy as np
from scipy.sparse import csc_matrix
from python.spike_core.propulsion_pod_inertial_cfd_linear import refined_gmres,RefinedLinearSolveError


class ResidualRefinement(unittest.TestCase):
    def test_ill_conditioned_small_direct_oracle(self):
        rng=np.random.default_rng(930);q,_=np.linalg.qr(rng.normal(size=(18,18)))
        matrix=q@np.diag(np.geomspace(1.,1e8,18))@q.T;rhs=rng.normal(size=18)
        result,history=refined_gmres(csc_matrix(matrix),rhs,None)
        direct=np.linalg.solve(matrix,rhs)
        self.assertLess(np.linalg.norm(matrix@result-rhs)/np.linalg.norm(rhs),1e-8)
        self.assertEqual(history[-1]['GMRES_info'],0)
        # Conditioning-aware forward comparison; a small backward residual
        # alone is deliberately not asserted to establish small forward error.
        self.assertLess(np.linalg.norm(result-direct)/np.linalg.norm(direct),2e-7)

    def test_exhausted_status_is_only_initial_iterate(self):
        matrix=csc_matrix([[2.,0.],[0.,3.]]);rhs=np.array([1.,2.]);direct=np.array([.5,2/3]);seen=[]
        def mocked(A,b,**kwargs):
            seen.append(b.copy())
            return (direct*.9,40) if len(seen)==1 else (np.linalg.solve(A.toarray(),b),0)
        with patch('python.spike_core.propulsion_pod_inertial_cfd_linear.gmres',side_effect=mocked):
            result,history=refined_gmres(matrix,rhs,None)
        np.testing.assert_allclose(seen[1],.1*rhs,atol=1e-15)
        np.testing.assert_allclose(result,direct,atol=1e-15)
        self.assertEqual([r['GMRES_info'] for r in history],[40,0])

    def test_failed_status_and_finite_residual_never_promoted(self):
        with patch('python.spike_core.propulsion_pod_inertial_cfd_linear.gmres',return_value=(np.zeros(2),40)):
            with self.assertRaises(RefinedLinearSolveError):refined_gmres(csc_matrix(np.eye(2)),np.ones(2),None,max_refinements=1)
        with self.assertRaises(ValueError):refined_gmres(csc_matrix(np.eye(2)),np.array([float('nan'),1.]),None)

    def test_robust_norm_extremes_nonzero_not_false_zero(self):
        for magnitude in (1e-300,1e308):
            rhs=np.array([magnitude,magnitude])
            result,history=refined_gmres(csc_matrix(2*np.eye(2)),rhs,None)
            np.testing.assert_allclose(result/magnitude,[.5,.5],rtol=1e-12)
            self.assertEqual(history[-1]['GMRES_info'],0)
            self.assertLess(history[-1]['true_full_relative_residual'],1e-8)

    def test_already_converged_original_system_needs_no_correction(self):
        matrix=csc_matrix([[2.,0.],[0.,3.]]);rhs=np.array([1.,2.]);solution=np.array([.5,2/3])
        with patch('python.spike_core.propulsion_pod_inertial_cfd_linear.gmres',side_effect=AssertionError('Unnecessary tiny correction solve')):
            result,history=refined_gmres(matrix,rhs,None,initial_iterate=solution)
        np.testing.assert_array_equal(result,solution)
        self.assertTrue(history[-1]['no_correction_required'])

    def test_positive_inner_budget_status_retained_outer_residual_independent(self):
        rhs=np.array([1.,2.])
        with patch('python.spike_core.propulsion_pod_inertial_cfd_linear.gmres',return_value=(rhs.copy(),40)):
            result,history=refined_gmres(csc_matrix(np.eye(2)),rhs,None)
        np.testing.assert_array_equal(result,rhs)
        self.assertEqual(history[-1]['GMRES_info'],40)
        self.assertEqual(history[-1]['overall_refinement_status'],'converged_original_system')

if __name__=='__main__':unittest.main()
