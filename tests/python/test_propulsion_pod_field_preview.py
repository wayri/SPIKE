# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
import numpy as np
from python.spike_core.propulsion_pod_field_preview import magnetic_preview


class FieldPreviewTests(unittest.TestCase):
    def test_actual_piecewise_constant_field_owners_and_source_immutability(self):
        f={'nodes_m':[[0.,0.],[1.,0.],[1.,1.],[0.,1.]],'triangles':[[0,1,2],[0,3,2]],
           'region_ids':['a','b'],'element_b_t':[[1.,2.],[-3.,4.]]}
        before=copy.deepcopy(f);p=magnetic_preview(f,9)
        self.assertTrue(p['presentation_only']);self.assertEqual(f,before)
        self.assertEqual(len(p['triangles']),128)
        for owner,B,region in zip(p['source_element_ids'],p['element_b_t'],p['region_ids']):
            self.assertEqual(B,f['element_b_t'][owner]);self.assertEqual(region,f['region_ids'][owner])

    def test_quadratic_potential_linear_field_sampled_at_actual_centroids(self):
        nodes=np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.]])
        tri=np.array([[0,1,2],[0,3,2]])
        field_at=lambda xy: np.stack([xy[...,0]+2*xy[...,1],3*xy[...,0]-xy[...,1]],axis=-1)
        f={'nodes_m':nodes.tolist(),'triangles':tri.tolist(),'region_ids':['a','b'],
           'element_b_t':field_at(nodes[tri].mean(axis=1)).tolist(),
           'p2_barycentric_b_t':field_at(nodes[tri]).tolist()}
        p=magnetic_preview(f,9)
        centres=np.asarray(p['nodes_m'])[p['triangles']].mean(axis=1)
        np.testing.assert_allclose(p['element_b_t'],field_at(centres),atol=1e-15)
        self.assertEqual(p['source_field_order'],2)


if __name__=='__main__':unittest.main()
