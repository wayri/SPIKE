# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import itertools
import hashlib
import json
from pathlib import Path
import unittest

from python.spike_core.tetra_mesh_refinement import refine_tetra_mesh, TetraRefinementError


def mesh_pair():
    mesh = {'contract':'spike/solver-mesh/v1','units':'m','coordinate_system':'right_handed_xyz',
            'vertices':[[0,0,0],[2,0,0],[.3,1,0],[.2,.2,1],[.4,.3,-2]],
            'cells':[{'id':'a','kind':'tetrahedron','vertices':[0,1,2,3],'material_id':'copper','source_object_ids':['board']},
                     {'id':'b','kind':'tetrahedron','vertices':[0,2,1,4],'material_id':'air','source_object_ids':['board']}],
            'object_map':{'board':{'kind':'board'}},
            'counts':{'vertices':5,'cells':2}}
    faces = {}
    for cell in mesh['cells']:
        for face in itertools.combinations(cell['vertices'],3):
            key = tuple(sorted(face))
            faces.setdefault(key,[]).append(cell['material_id'])
    boundary = [{'vertices':list(f),'label':regions[0]} for f,regions in faces.items() if len(regions)==1]
    return mesh,boundary


class TetraRefinementTests(unittest.TestCase):
    def test_underflow_cell_cannot_hide_in_positive_total_volume(self):
        mesh, boundary = mesh_pair()
        mesh['vertices'] = [[x+10 for x in point] for point in mesh['vertices']]
        mesh['vertices'] += [[0,0,0],[1e-107,0,0],[0,1e-107,0],[0,0,1e-109]]
        mesh['cells'].append({'id':'tiny','kind':'tetrahedron','vertices':[5,6,7,8],
                             'material_id':'air','source_object_ids':['board']})
        mesh['counts'] = {'vertices':9,'cells':3}
        boundary += [{'vertices':list(face),'label':'tiny'} for face in itertools.combinations([5,6,7,8],3)]
        with self.assertRaisesRegex(TetraRefinementError, 'cell volume'):
            refine_tetra_mesh(mesh,[],boundary)

    def test_schema_roundtrip_and_source_ownership(self):
        from jsonschema import Draft202012Validator
        mesh,boundary = mesh_pair()
        result = refine_tetra_mesh(mesh,[[0,1]],boundary)
        schema = json.loads((Path(__file__).resolve().parents[2] / 'schemas' /
                             'solver-mesh-v1.schema.json').read_text(encoding='utf-8'))
        restored = json.loads(json.dumps(result['mesh'],sort_keys=True,allow_nan=False))
        Draft202012Validator(schema).validate(restored)
        self.assertEqual(restored['object_map'],mesh['object_map'])
        for cell in restored['cells']:
            self.assertEqual(cell['source_object_ids'],['board'])

    def test_openfoam_converter_handoff(self):
        # Synthetic converter admission fixture only. Production refinement
        # returns production_qualified=False; this flag is not promoted by it.
        from python.spike_core.openfoam_polymesh import compile_polymesh
        mesh,boundary = mesh_pair()
        result = refine_tetra_mesh(mesh,[[0,1]],boundary)
        refined = result['mesh']
        digest = hashlib.sha256(json.dumps(refined,sort_keys=True,separators=(',',':'),
                                           ensure_ascii=True,allow_nan=False).encode()).hexdigest()
        request = {'contract':'spike/openfoam-polymesh-request/v1','region_id':'testRegion',
                   'mesh':refined,'mesh_evidence':{'contract':'spike/solver-mesh/v1',
                                                 'qualified':True,'sha256':digest},
                   'boundary_patches':[{'name':label,'type':'wall','faces':[
                       f['vertices'] for f in result['boundary_triangles'] if f['label']==label]}
                       for label in ('air','copper')],
                   'cell_zones':[{'name':label,'cell_ids':[c['id'] for c in refined['cells']
                                 if c['material_id']==label]} for label in ('air','copper')]}
        compiled = compile_polymesh(request)
        self.assertIn('neighbour',compiled['files'])
        self.assertIn('copper',compiled['files']['cellZones'])

    def test_interface_conformity_and_volume(self):
        mesh,boundary = mesh_pair()
        snapshot = copy.deepcopy(mesh)
        result = refine_tetra_mesh(mesh,[[0,1]],boundary)
        self.assertEqual(mesh,snapshot)
        self.assertEqual(result['mesh']['counts'],{'vertices':6,'cells':4})
        self.assertEqual(result['mesh']['vertices'][5],[1,0,0])
        self.assertAlmostEqual(result['quality']['after']['volume'],1)
        self.assertEqual(len(result['boundary_triangles']),8)
        self.assertEqual(set(result['parent_cell_ids'].values()),{'a','b'})
        cells = result['mesh']['cells']
        interface = {}
        for cell in cells:
            for f in itertools.combinations(cell['vertices'],3):
                interface.setdefault(tuple(sorted(f)),[]).append(cell['material_id'])
        self.assertEqual(sum(len(set(regions))==2 for regions in interface.values()),2)

    def test_manual_local_and_sequential(self):
        mesh,boundary = mesh_pair()
        result = refine_tetra_mesh(mesh,[[0,3],[0,5]],boundary)
        self.assertEqual(result['mesh']['counts'],{'vertices':7,'cells':4})
        self.assertEqual(next(c for c in result['mesh']['cells'] if c['id']=='b'),mesh['cells'][1])
        self.assertEqual({f['label'] for f in result['boundary_triangles']},{'air','copper'})

    def test_noop_quality(self):
        mesh,boundary = mesh_pair()
        result = refine_tetra_mesh(mesh,[],boundary)
        self.assertGreater(result['quality']['after']['minimum_mean_ratio'],0)
        self.assertLessEqual(result['quality']['after']['minimum_mean_ratio'],1)

    def test_inversion_duplicate_and_same_side(self):
        for mode in ('invert','duplicate','same_side'):
            mesh,boundary = mesh_pair()
            if mode=='invert':
                mesh['cells'][0]['vertices']=[1,0,2,3]
            elif mode=='duplicate':
                mesh['cells'][1]['vertices']=[0,1,2,3]
            else:
                mesh['vertices'][4][2]=2
                mesh['cells'][1]['vertices']=[0,1,2,4]
            with self.subTest(mode=mode), self.assertRaises(TetraRefinementError):
                refine_tetra_mesh(mesh,[],boundary)

    def test_boundary_admission(self):
        mesh,boundary = mesh_pair()
        for bad in (boundary[:-1],boundary+[boundary[0]],boundary+[{'vertices':[0,1,2],'label':'bad'}]):
            with self.assertRaises(TetraRefinementError):
                refine_tetra_mesh(mesh,[],bad)

    def test_resource_and_edge_admission(self):
        mesh,boundary = mesh_pair()
        for kwargs in ({'max_cells':2},{'max_vertices':5},{'max_cells':True}):
            with self.assertRaises(TetraRefinementError):
                refine_tetra_mesh(mesh,[[0,1]],boundary,**kwargs)
        for edges in ([[3,4]],[[0,0]],[[True,1]],[[0,1],[0,1]]):
            with self.assertRaises(TetraRefinementError):
                refine_tetra_mesh(mesh,edges,boundary)

    def test_nonfinite_unknown_fields(self):
        for value in (float('nan'),float('inf'),True,10**1000):
            mesh,boundary = mesh_pair()
            mesh['vertices'][0][0]=value
            with self.assertRaises(TetraRefinementError):
                refine_tetra_mesh(mesh,[],boundary)
        mesh,boundary=mesh_pair()
        mesh['unexpected']=1
        with self.assertRaises(TetraRefinementError):
            refine_tetra_mesh(mesh,[],boundary)


if __name__ == '__main__':
    unittest.main()
