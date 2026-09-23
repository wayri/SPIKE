# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import itertools
import unittest

from python.spike_core.tetra_mesh_optimization import optimize_tetra_mesh
from python.spike_core.tetra_mesh_refinement import TetraRefinementError, _det


def interior_mesh():
    points = [[0,0,0],[2,0,0],[.3,1,0],[.2,.2,1],[.12,.06,.03]]
    cells=[]
    boundary=[]
    for index,face in enumerate(itertools.combinations(range(4),3)):
        vertices=list(face)+[4]
        if _det(points,vertices)<0:
            vertices[0],vertices[1]=vertices[1],vertices[0]
        cells.append({'id':str(index),'kind':'tetrahedron','material_id':'solid','vertices':vertices,'source_object_ids':['board']})
        boundary.append({'label':'wall','vertices':list(face)})
    return {'contract':'spike/solver-mesh/v1','units':'m','coordinate_system':'right_handed_xyz',
            'vertices':points,'cells':cells,'counts':{'vertices':5,'cells':4},'object_map':{'board':{'kind':'board'}}},boundary


class TetraOptimizationTests(unittest.TestCase):
    def test_quality_volume_and_fixed_boundary(self):
        mesh,boundary=interior_mesh()
        snapshot=copy.deepcopy(mesh)
        result=optimize_tetra_mesh(mesh,boundary)
        self.assertEqual(mesh,snapshot)
        self.assertEqual(result['mesh']['vertices'][:4],mesh['vertices'][:4])
        self.assertEqual(result['mesh']['cells'],mesh['cells'])
        self.assertEqual(result['boundary_triangles'],boundary)
        self.assertGreater(result['quality']['after']['minimum_mean_ratio'],
                           2*result['quality']['before']['minimum_mean_ratio'])
        self.assertAlmostEqual(result['quality']['after']['volume'],result['quality']['before']['volume'])
        self.assertTrue(result['moves'])

    def test_protected(self):
        mesh,boundary=interior_mesh()
        result=optimize_tetra_mesh(mesh,boundary,protected_vertices=[4])
        self.assertEqual(result['mesh'],mesh)
        self.assertEqual(result['moves'],[])

    def test_interface_fixed(self):
        mesh,boundary=interior_mesh()
        mesh['cells'][0]['material_id']='copper'
        result=optimize_tetra_mesh(mesh,boundary)
        self.assertIn(4,result['fixed_vertices'])
        self.assertEqual(result['mesh'],mesh)

    def test_invalid(self):
        mesh,boundary=interior_mesh()
        for kwargs in ({'iterations':11},{'iterations':True},{'protected_vertices':[True]},
                       {'protected_vertices':[5]},{'protected_vertices':[4,4]}):
            with self.assertRaises(TetraRefinementError):
                optimize_tetra_mesh(mesh,boundary,**kwargs)
        mesh['cells'][0]['vertices'].reverse()  # Reverse four entries is even; swap instead.
        mesh['cells'][0]['vertices'][0],mesh['cells'][0]['vertices'][1]=mesh['cells'][0]['vertices'][1],mesh['cells'][0]['vertices'][0]
        with self.assertRaises(TetraRefinementError):
            optimize_tetra_mesh(mesh,boundary)


if __name__=='__main__':
    unittest.main()
