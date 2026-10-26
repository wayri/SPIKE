# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from scipy.sparse import bmat,csc_matrix,diags
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_pressure_pin import pressure_pin_reduction, restore_pressure_gauge


class PressureGaugePin(unittest.TestCase):
    def test_nonsymmetric_upper_block_non_null_aligned_gauge(self):
        z=np.array([1.,2.,3.]);z/=np.linalg.norm(z);projection=np.eye(3)-np.outer(z,z)
        C=projection;G=np.diag([2.,3.,4.])@projection;g=np.array([4.,1.,2.])
        matrix=bmat([[diags([3.,4.,5.]),csc_matrix(G),csc_matrix((3,1))],[csc_matrix(C),csc_matrix((3,3)),csc_matrix(g[:,None])],[csc_matrix((1,3)),csc_matrix(g[None,:]),csc_matrix((1,1))]],format='csc')
        rng=np.random.default_rng(702)
        for _ in range(5):
            rhs=rng.normal(size=7);reduced,b,context,evidence=pressure_pin_reduction(matrix,rhs,3,z)
            result=restore_pressure_gauge(np.linalg.solve(reduced.toarray(),b),context)
            np.testing.assert_allclose(matrix@result,rhs,rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(result,np.linalg.solve(matrix.toarray(),rhs),rtol=1e-12,atol=1e-12)
        with self.assertRaises(ValueError):pressure_pin_reduction(matrix,np.ones(7),3,np.ones(3))

if __name__=='__main__':unittest.main()
