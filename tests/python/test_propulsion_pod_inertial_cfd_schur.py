# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from scipy.sparse import bmat,csc_matrix,diags
from scipy.sparse.linalg import splu,spilu
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_schur import SimpleSchurStokes


class SchurPreconditioner(unittest.TestCase):
    def test_native_storage_counter_is_not_exposed_CSC_nnz(self):
        matrix=diags([-np.ones(9),4*np.ones(10),-np.ones(9)],[-1,0,1],format='csc')
        for factor in (splu(matrix),spilu(matrix)):
            self.assertGreater(factor.nnz,factor.L.nnz+factor.U.nnz)

    def test_full_bordered_action_with_non_null_gauge_and_arbitrary_rhs(self):
        velocity=diags([2.,3.,4.,5.]);C=csc_matrix([[1.,-1.,0.,0.],[0.,1.,-1.,0.],[-1.,0.,1.,0.]])
        gauge=np.array([1.,2.,4.]);g=csc_matrix(gauge[:,None])
        matrix=bmat([[velocity,C.T,csc_matrix((4,1))],[C,csc_matrix((3,3)),g],[csc_matrix((1,4)),g.T,csc_matrix((1,1))]],format='csc')
        owner=SimpleSchurStokes(matrix,4,3,gauge)
        rng=np.random.default_rng(7304)
        for _ in range(4):
            rhs=rng.normal(size=8)
            np.testing.assert_allclose(matrix@(owner.preconditioner@rhs),rhs,rtol=2e-14,atol=2e-14)
            np.testing.assert_allclose(matrix@owner.solve(rhs),rhs,rtol=2e-12,atol=2e-12)
        omitted=SimpleSchurStokes(matrix,4,3,gauge,reference_velocity=False)
        self.assertIsNone(omitted.ilu);self.assertIsNone(omitted.preconditioner)
        with self.assertRaisesRegex(ValueError,'omitted'):omitted.solve(np.ones(8))
        current=omitted.with_velocity(matrix)
        np.testing.assert_allclose(matrix@(current@np.ones(8)),np.ones(8),rtol=2e-14,atol=2e-14)
        # The mean-pressure functional is not the pressure constant null vector.
        self.assertGreater(np.linalg.norm(C.T@gauge),1.)

if __name__=='__main__':unittest.main()
