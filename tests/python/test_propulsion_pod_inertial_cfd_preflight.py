# SPDX-License-Identifier: Apache-2.0
import tempfile,unittest,json
from unittest.mock import patch
from pathlib import Path
import numpy as np
from scipy.sparse import bmat,csc_matrix,eye
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_preflight import check_pressure_kernel, PressureKernelError


class PressureKernelPreflight(unittest.TestCase):
    def temp(self):
        root=Path(__file__).resolve().parents[2]/'output/promo-propulsion-pod-20261023/inertial_cfd/test-tmp'
        root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)
    def matrix(self,C,g):
        return bmat([[eye(3),csc_matrix(C.T),csc_matrix((3,1))],[csc_matrix(C),csc_matrix((3,3)),csc_matrix(g[:,None])],[csc_matrix((1,3)),csc_matrix(g[None,:]),csc_matrix((1,1))]],format='csc')
    def test_constant_only_pass_and_extra_mode_fail_closed(self):
        g=np.ones(3)/np.sqrt(3);C=np.eye(3)-np.outer(g,g)
        with self.temp() as out:
            result=check_pressure_kernel(self.matrix(C,g),3,g,out,pressure_scaling=np.ones(3))
            self.assertTrue(result['passed']);self.assertFalse(result['uniform_inf_sup_proven'])
        v=np.array([1.,-1.,0.])/np.sqrt(2);C=np.outer(v,v)
        with self.temp() as out:
            with self.assertRaises(PressureKernelError):check_pressure_kernel(self.matrix(C,g),3,g,out,pressure_scaling=np.ones(3))

    def test_uncertain_spectral_classification_rejects(self):
        g=np.ones(3)/np.sqrt(3);v=np.array([1.,-1.,0.])/np.sqrt(2);w=np.cross(g,v)
        vectors=np.column_stack((g,v,w));C=np.outer(v,v)*np.sqrt(2e-12)+np.outer(w,w)
        actual=np.linalg.eigvalsh(C@C.T);threshold=1e-12*np.max(np.sum(abs(C@C.T),axis=1))
        mocked=np.array([0.,threshold*1.1,1.])
        with self.temp() as out:
            with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_preflight.eigh',return_value=(mocked,vectors)):
                with self.assertRaises(PressureKernelError):check_pressure_kernel(self.matrix(C,g),3,g,out,pressure_scaling=np.ones(3))

    def test_failure_retains_inputs_and_invalid_eigenpairs_reject(self):
        g=np.ones(3)/np.sqrt(3);C=np.eye(3)-np.outer(g,g);A=self.matrix(C,g)
        with self.temp() as out:
            with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_preflight.eigh',side_effect=np.linalg.LinAlgError('deliberate oracle failure')):
                with self.assertRaises(PressureKernelError):check_pressure_kernel(A,3,g,out,pressure_scaling=np.ones(3))
            self.assertTrue((Path(out)/'scaled-continuity-C.npz').is_file());self.assertTrue((Path(out)/'pressure-kernel-input.npz').is_file())
            self.assertEqual(json.loads((Path(out)/'pressure-kernel-evidence.json').read_text())['status'],'eigensolve_failed')
        with self.temp() as out:
            with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_preflight.eigh',return_value=(np.array([0.,1.,1.]),np.eye(3))):
                with self.assertRaises(PressureKernelError):check_pressure_kernel(A,3,g,out,pressure_scaling=np.ones(3))
        with self.temp() as out:
            with self.assertRaises(PressureKernelError):check_pressure_kernel(A,3,-g,out,pressure_scaling=np.ones(3))

if __name__=='__main__':unittest.main()
