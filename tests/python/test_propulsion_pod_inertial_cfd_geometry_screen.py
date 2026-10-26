# SPDX-License-Identifier: Apache-2.0
import itertools,unittest
import numpy as np
from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_intersections import _filtered_determinants, _separated
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_geometry_screen import face_separation_certificates


class BatchedFaceCertificates(unittest.TestCase):
    def test_scalar_fastpath_equivalence_and_no_false_separation(self):
        rng=np.random.default_rng(6410);vertices=rng.normal(size=(2400,3));cells=np.arange(2400).reshape(-1,4)
        for start in (0,200,400):
            a=np.arange(start,start+100);b=a+100;result=face_separation_certificates(vertices,cells,a,b);expected=[]
            for i,j in zip(a,b):
                lp,rp=vertices[cells[i]],vertices[cells[j]];differences=rp[None,:,:]-lp[:,None,:];axes=[]
                for points in (lp,rp):
                    for x,y,z in itertools.combinations(range(4),3):axes.append((points[y]-points[x],points[z]-points[x]))
                signs=_filtered_determinants(np.array([e[0] for e in axes])[:,None,None,:],np.array([e[1] for e in axes])[:,None,None,:],differences[None,...])
                expected.append(np.any(np.all(signs>0,axis=(1,2))|np.all(signs<0,axis=(1,2))))
                if result[i-start]:
                    diagnostics={'axis_tests':0,'exact_predicates':0}
                    self.assertTrue(_separated(vertices,cells[i],cells[j],{},{},diagnostics))
            np.testing.assert_array_equal(result,expected)

    def test_tangent_and_overlapping_cells_defer(self):
        base=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        vertices=np.concatenate([base,base+.1,base+np.array([1.,0.,0.])]);cells=np.arange(12).reshape(3,4)
        np.testing.assert_array_equal(face_separation_certificates(vertices,cells,[0,0],[1,2]),[False,False])
        with self.assertRaises(ValueError):face_separation_certificates(vertices,cells,np.zeros(257),np.zeros(257))
        with self.assertRaises(ValueError):face_separation_certificates(vertices,cells,[.1],[1])
        with self.assertRaises(ValueError):face_separation_certificates(vertices,cells,[-1],[1])

    def test_inexact_underflow_never_certifies(self):
        base=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])*1e-110
        vertices=np.concatenate([base,base+2e-110]);cells=np.arange(8).reshape(2,4)
        np.testing.assert_array_equal(face_separation_certificates(vertices,cells,[0],[1]),[False])

if __name__=='__main__':unittest.main()
