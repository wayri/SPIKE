# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from python.spike_core.openfoam_mesh_geometry_audit import audit_mesh_geometry, audit_polymesh_geometry


def cube():
    return {'contract':'spike/solver-mesh/v1','units':'m','coordinate_system':'right_handed_xyz',
            'vertices':[[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],
            'cells':[{'kind':'hexahedron','vertices':list(range(8))}]}


class GeometryAuditTests(unittest.TestCase):
    def test_orthogonal_cube(self):
        result = audit_mesh_geometry(cube())
        self.assertAlmostEqual(result['volume_m3'],1)
        self.assertTrue(result['orthogonal_centroid_geometry'])

    def test_sheared_noncuboidal_cell(self):
        mesh = cube()
        for p in mesh['vertices']:
            p[0] += .5*p[2]
        result = audit_mesh_geometry(mesh)
        self.assertAlmostEqual(result['volume_m3'],1)
        self.assertAlmostEqual(result['maximum_face_nonorthogonality_deg'],26.565051177,places=8)
        self.assertFalse(result['orthogonal_centroid_geometry'])

    def test_tetrahedral_pair(self):
        mesh = cube()
        mesh['vertices'] = [[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1]]
        mesh['cells'] = [{'kind':'tetrahedron','vertices':[0,1,2,3]}, {'kind':'tetrahedron','vertices':[0,2,1,4]}]
        result = audit_mesh_geometry(mesh)
        self.assertEqual(result['interior_faces'],1)
        self.assertAlmostEqual(result['volume_m3'],1/3)
        self.assertFalse(result['production_qualified'])

    def test_warped_face_rejected(self):
        mesh = cube()
        mesh['vertices'][6][2] = 1.1
        with self.assertRaisesRegex(ValueError,'Nonplanar'):
            audit_mesh_geometry(mesh)

    def test_duplicate_and_invalid(self):
        mesh = cube()
        mesh['cells'].append(copy.deepcopy(mesh['cells'][0]))
        with self.assertRaises(ValueError): audit_mesh_geometry(mesh)

    def test_actual_polymesh_renderer_disables_skew_flux(self):
        from python.spike_core import openfoam_fan_fixture as fixture
        original = fixture.write_polymesh
        def skew(neutral, output):
            for point in neutral['mesh']['vertices']:
                point[0] += .5*point[2]
            neutral['mesh_evidence']['sha256'] = fixture._digest(neutral['mesh'])
            return original(neutral,output)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'case'
            with patch.object(fixture,'write_polymesh',side_effect=skew):
                fixture.build_fan_heated_fixture(root,divisions=2,end_time_s=.01,write_interval_steps=10)
            audit = audit_polymesh_geometry(root/'case/constant/air/polyMesh')
            self.assertFalse(audit['orthogonal_centroid_geometry'])
            metadata = json.loads((root/'case/constant/geometryDiagnostic.json').read_text())
            self.assertFalse(metadata['orthogonal_constant_k_diagnostic_enabled'])
        mesh = cube()
        mesh['vertices'][0][0] = True
        with self.assertRaises(ValueError): audit_mesh_geometry(mesh)


if __name__ == '__main__': unittest.main()
