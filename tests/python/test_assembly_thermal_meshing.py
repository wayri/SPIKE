# SPDX-License-Identifier: Apache-2.0
"""Original closed-volume bridge tests; not general solver qualification."""
import copy
import ctypes.util
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.assembly_thermal_meshing import prepare_assembly_thermal_mesh, run_assembly_thermal_mesh
from python.spike_core import gmsh_occ_runtime as runtime


def fixture():
    data = b'Original minimal retained source fixture'
    sha = hashlib.sha256(data).hexdigest()
    design = {'design_id': 'board-design', 'source': {'artifact_path': 'package:sources/board.kicad_pcb', 'source_digest': sha},
              'metadata': {'board_outline_drawings': [{'type': 'rect', 'layer': 'Edge.Cuts', 'start': [0,0], 'end': [2,2]}]},
              'layers': [{'id': 'dielectric', 'layer_type': 'dielectric', 'order': 0, 'z_mm': 0, 'thickness_mm': 1}]}
    assembly = {'contract': 'spike/assembly-ir/v1', 'assembly_id': 'test-assembly', 'name': 'Original test',
                'boards': [{'id': 'board-a', 'design_id': 'board-design', 'frame': {'frame_id': 'frame-a'}},
                           {'id': 'board-b', 'design_id': 'board-design', 'frame': {'frame_id': 'frame-b',
                            'transform': [1,0,0,4,0,1,0,0,0,0,1,0,0,0,0,1]}}]}
    assignments = {'materials': [{'id': 'reviewed', 'thermal_conductivity_w_mk': 2, 'provenance': 'Original effective-layer test value'}],
                   'boards': {'board-design': {'representation': 'layer_homogenized', 'layer_materials': {'dielectric': 'reviewed'}}},
                   'parts': {}}
    options = {'min_size_mm': 1, 'max_size_mm': 1, 'max_cells': 10000, 'max_vertices': 10000}
    return {'assembly_ir': assembly, 'design_ir': design}, assignments, options, lambda uri: data


class PreparationTests(unittest.TestCase):
    def test_duplicate_occurrences_retain_stack_and_local_geometry(self):
        payload, assignments, options, reader = fixture()
        original = copy.deepcopy(payload)
        plan = prepare_assembly_thermal_mesh(payload, assignments, options, artifact_reader=reader)
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(len(plan['jobs']), 2)
        self.assertEqual(plan['jobs'][0]['job'], plan['jobs'][1]['job'])
        self.assertEqual(plan['jobs'][0]['object_metadata'], {'layer:dielectric': {'kind': 'board_layer', 'layer': 'dielectric'}})
        self.assertEqual(plan['jobs'][0]['stack_binding'], plan['jobs'][1]['stack_binding'])
        self.assertEqual(payload, original)
        self.assertTrue(plan['jobs'][0]['approximations'])

    def test_missing_source_material_outline_and_flex_block(self):
        mutations = [lambda p,a: a['boards'].clear(),
                     lambda p,a: p['design_ir']['metadata'].clear(),
                     lambda p,a: p['design_ir'].update(bends=[{'id': 'bend'}]),
                     lambda p,a: p['design_ir']['source'].update(source_digest='0'*64),
                     lambda p,a: p['design_ir']['layers'][0].update(thickness_mm=None)]
        for mutation in mutations:
            p, a, options, reader = fixture()
            mutation(p,a)
            result = prepare_assembly_thermal_mesh(p,a,options,artifact_reader=reader)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(len(result['blockers']), 2)

    def test_curved_outline_not_tessellated_and_render_mesh_not_solid(self):
        p,a,o,r = fixture()
        p['design_ir']['metadata']['board_outline_drawings'][0]['type'] = 'circle'
        p['assembly_ir']['parts'] = [{'id': 'case', 'model_id': 'display', 'frame': {'frame_id': 'case'}}]
        p['models'] = {'models': [{'id': 'display', 'model_type': 'glb'}]}
        plan = prepare_assembly_thermal_mesh(p,a,o,artifact_reader=r)
        self.assertEqual(plan['status'], 'blocked')
        self.assertIn('PART_SOLID', {item['code'] for item in plan['blockers']})

    def test_dependency_failure_has_recovery_without_allocating_output(self):
        p,a,o,r = fixture()
        with tempfile.TemporaryDirectory() as d, patch.object(runtime, 'verify_installation', side_effect=ValueError('missing pin')):
            result = run_assembly_thermal_mesh(p,a,o,Path(d)/'output',artifact_reader=r)
            self.assertEqual(result['status'], 'blocked')
            self.assertFalse((Path(d)/'output').exists())

    def test_invalid_resource_budget_rejected_before_any_artifact_read(self):
        p,a,o,r = fixture()
        o['max_cells'] = True
        with self.assertRaises(ValueError):
            prepare_assembly_thermal_mesh(p,a,o,artifact_reader=lambda uri: self.fail('must not read'))


def has_runtime():
    try:
        runtime.verify_installation()
        return importlib.util.find_spec('shapely') is not None
    except ValueError:
        return False


@unittest.skipUnless(has_runtime(), 'Requires admitted local Windows CPython 3.11 OCC runtime')
class RealOccBridgeTests(unittest.TestCase):
    def test_real_conforming_board_volume_and_duplicate_occurrences(self):
        p,a,o,r = fixture()
        with tempfile.TemporaryDirectory() as d:
            result = run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=r)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(list((Path(d)/'run').glob('case-*'))), 1)
            self.assertEqual(len(result['request']['bodies']), 2)
            for evidence in result['evidence']:
                self.assertAlmostEqual(evidence['metrics']['cad_volume_mm3'], 4)
                self.assertAlmostEqual(evidence['metrics']['tetrahedron_volume_mm3'], 4, places=9)
            mesh = result['handoff']['mesh']
            self.assertEqual(result['meshing_mode'], 'joint_conformal')
            self.assertEqual(len(mesh['cells']), sum(len(body['mesh']['cells']) for body in result['request']['bodies']))
            self.assertEqual(len({c['id'] for c in mesh['cells']}), len(mesh['cells']))
            self.assertFalse(result['contacts_inferred'])

    def test_real_step_solid_with_model_and_occurrence_placement(self):
        # Create an original analytic 2x3x4 mm solid with the admitted API.
        with tempfile.TemporaryDirectory() as d, os.add_dll_directory(str(runtime.DLL.parent)):
            original = ctypes.util.find_library
            with patch.object(ctypes.util, 'find_library', side_effect=lambda n: str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
                spec = importlib.util.spec_from_file_location('gmsh', runtime.API)
                gmsh = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gmsh)
            path = Path(d)/'original.step'
            gmsh.initialize(['gmsh','-nopopup'], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                gmsh.model.add('original')
                gmsh.model.occ.addBox(0,0,0,2,3,4)
                gmsh.model.occ.synchronize()
                gmsh.write(str(path))
            finally:
                gmsh.finalize()
            data = path.read_bytes()
            p,a,o,_ = fixture()
            p['assembly_ir']['boards'] = []
            placement = list(IDENTITY)
            placement[3] = 10
            p['assembly_ir']['parts'] = [{'id':'case','model_id':'exact', 'frame': {'frame_id':'case','transform':placement}}]
            model_placement = list(IDENTITY)
            model_placement[7] = 5
            p['models'] = {'models':[{'id':'exact','model_type':'step','uri':'package:models/artifacts/original.step',
                                     'digest':hashlib.sha256(data).hexdigest(),'transform':model_placement}]}
            a['boards'] = {}
            a['parts'] = {'case':'reviewed'}
            result = run_assembly_thermal_mesh(p,a,o,Path(d)/'run',artifact_reader=lambda uri:data)
            self.assertEqual(result['status'], 'completed')
            self.assertAlmostEqual(result['evidence'][0]['metrics']['cad_volume_mm3'], 24, places=8)
            self.assertAlmostEqual(result['evidence'][0]['metrics']['tetrahedron_volume_mm3'], 24, places=8)
            points = result['handoff']['mesh']['vertices']
            self.assertAlmostEqual(min(p[0] for p in points), .010)
            self.assertAlmostEqual(min(p[1] for p in points), .005)
            self.assertTrue(result['request']['bodies'][0]['boundary_faces'])
            # A STEP compound with separate solids has no reviewed per-solid
            # material/ownership assignment and must fail rather than vanish.
            gmsh.initialize(['gmsh','-nopopup'], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                gmsh.model.add('compound')
                gmsh.model.occ.addBox(0,0,0,1,1,1)
                gmsh.model.occ.addBox(3,0,0,1,1,1)
                gmsh.model.occ.synchronize()
                gmsh.write(str(path))
            finally:
                gmsh.finalize()
            data = path.read_bytes()
            p['models']['models'][0]['digest'] = hashlib.sha256(data).hexdigest()
            blocked = run_assembly_thermal_mesh(p,a,o,Path(d)/'compound-run',artifact_reader=lambda uri:data)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertIn('STEP_SOURCE_VOLUME', blocked['blockers'][0]['message'])


if __name__ == '__main__':
    unittest.main()

