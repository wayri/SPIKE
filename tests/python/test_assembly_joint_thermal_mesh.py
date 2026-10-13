# SPDX-License-Identifier: Apache-2.0
"""Actual Gmsh board/STEP conformity followed by independently known slab heat."""
import ctypes.util
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from python.spike_core.assembly_thermal_components import promote_thermal_components
from python.spike_core.assembly_thermal_meshing import prepare_assembly_thermal_mesh, run_assembly_thermal_mesh
from python.spike_core.assembly_thermal_autolink import discover_assembly_thermal_links, autolink_assembly_thermal_contacts
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
from tests.python.test_assembly_thermal_meshing import fixture, has_runtime, runtime
from tests.python.test_thermal_component_promotion import pure_fixture


class JointMeshAdmissionTests(unittest.TestCase):
    def test_original_finite_face_not_only_infinite_plane_is_required(self):
        from python.spike_core.assembly_thermal_joint_geometry import verify_joint_source_interfaces
        center, normal = np.array([.5, .5, 0.]), np.array([0., 0., 1.])
        edges = [(np.array(start), np.array(inward)) for start, inward in (
            ([0., 0., 0.], [1., 0., 0.]), ([1., 0., 0.], [-1., 0., 0.]),
            ([0., 0., 0.], [0., 1., 0.]), ([0., 1., 0.], [0., -1., 0.]))]
        geometry = ({sid: [(center, normal, edges)] for sid in ('a', 'b')}, {'a': 'board', 'b': 'part'})
        interface = [{'source_object_ids': ['a', 'b'], 'vertices': [0, 1, 2]}]
        valid = [[.1, .1, 0.], [.9, .1, 0.], [.1, .9, 0.]]
        self.assertEqual(verify_joint_source_interfaces(geometry, interface, valid)['checked_interface_triangles'], 1)
        # Same plane and normal, but outside the retained finite square.
        with self.assertRaisesRegex(ValueError, 'SOURCE_SEPARATION'):
            verify_joint_source_interfaces(geometry, interface, [[2., 2., 0.], [3., 2., 0.], [2., 3., 0.]])

    def test_joint_solid_budget_blocks_before_output_creation(self):
        p, a, o, reader = fixture()
        p['assembly_ir']['boards'] = [dict(p['assembly_ir']['boards'][0], id='b'+str(i),
                                         frame={'frame_id': 'f'+str(i)}) for i in range(30)]
        original = p['design_ir']['layers'][0]
        p['design_ir']['layers'] = [dict(original, id='layer'+str(i), order=i, z_mm=i) for i in range(3)]
        a['boards']['board-design']['layer_materials'] = {'layer'+str(i): 'reviewed' for i in range(3)}
        plan = prepare_assembly_thermal_mesh(p, a, o, artifact_reader=reader)
        self.assertEqual(plan['status'], 'blocked')
        self.assertIn('ASSEMBLY_JOINT_BUDGET', [item['code'] for item in plan['blockers']])


@unittest.skipUnless(has_runtime(), 'Requires admitted local Windows CPython 3.11 OCC runtime')
class RealJointMeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        with os.add_dll_directory(str(runtime.DLL.parent)):
            original = ctypes.util.find_library
            with patch.object(ctypes.util, 'find_library', side_effect=lambda n: str(runtime.DLL) if n in ('gmsh', 'gmsh-4.15') else original(n)):
                spec = importlib.util.spec_from_file_location('gmsh', runtime.API)
                gmsh = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gmsh)
            path = Path(cls.directory.name)/'original-package.step'
            gmsh.initialize(['gmsh', '-nopopup'], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                gmsh.model.add('original_2x2x1_mm_package')
                gmsh.model.occ.addBox(0, 0, 0, 2, 2, 1)
                gmsh.model.occ.synchronize()
                gmsh.write(str(path))
            finally:
                gmsh.finalize()
        cls.step = path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def mesh(self, label, z=1.):
        p, a, o, selected, reader = pure_fixture()
        p['assembly_ir']['boards'] = p['assembly_ir']['boards'][:1]
        p['models']['models'][0]['digest'] = hashlib.sha256(self.step).hexdigest()
        transform = selected['component_to_board_transform_mm']
        transform[3], transform[7], transform[11] = 0., 0., z
        artifacts = lambda uri: self.step if uri.startswith('package:models/') else reader(uri)
        promoted = promote_thermal_components(p, [selected], a['materials'], artifact_reader=artifacts)
        part = promoted['promoted_parts'][0]['id']
        promoted['payload']['assembly_ir']['thermal_contacts'] = [
            {'id': 'package-contact', 'endpoint_a': 'board-a', 'endpoint_b': part,
             'contact_area_mm2': 4., 'thermal_resistance_k_per_w': 50.}]
        a['parts'].update(promoted['part_material_assignments'])
        result = run_assembly_thermal_mesh(promoted['payload'], a, o, Path(self.directory.name)/label,
                                          artifact_reader=artifacts)
        return result, part

    def test_actual_joint_mesh_autolink_internal_and_calculix_preserve_reviewed_resistance(self):
        result, part = self.mesh('touching')
        self.assertEqual(result['status'], 'completed', result.get('blockers'))
        self.assertEqual(result['meshing_mode'], 'joint_conformal')
        self.assertGreater(result['joint_interface_admission']['checked_interface_triangles'], 0)
        self.assertLessEqual(result['joint_interface_admission']['maximum_roundoff_allowance_mm'], 1e-10)
        geometry = result['request']
        problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'heat_sources': [], 'boundaries': [], 'contacts': []}
        for body in geometry['bodies']:
            plane, temperature = (0., 300.) if body['occurrence_id'] == 'board-a' else (1., 400.)
            for face in body['boundary_faces']:
                if all(math.isclose(body['mesh']['vertices'][v][2], plane, abs_tol=1e-9) for v in face['vertices']):
                    problem['boundaries'].append({'face': {'occurrence_id': body['occurrence_id'], 'face_id': face['id']},
                                                  'type': 'temperature', 'temperature_k': temperature})
        preview = discover_assembly_thermal_links(geometry, problem)
        self.assertEqual(len(preview['proposals']), 1)
        self.assertEqual(preview['proposals'][0]['status'], 'ready')
        self.assertAlmostEqual(preview['proposals'][0]['contact_area_mm2'], 4., places=9)
        self.assertGreater(preview['proposals'][0]['face_pair_count'], 2)
        linked = autolink_assembly_thermal_contacts(geometry, problem, ['package-contact'])['problem']
        self.assertAlmostEqual(linked['contacts'][0]['thermal_contact_conductance_w_m2k'], 5000., places=6)
        # Two L=1 mm, A=4 mm^2, k=2 W/m/K slabs: each R=L/kA=125 K/W.
        # Explicit contact R=50 K/W. Total R=300 K/W, Q=100/300 W.
        internal = run_assembly_field_thermal(geometry, linked)
        self.assertAlmostEqual(internal['occurrence_temperatures']['board-a']['maximum_k'], 300+100*125/300, places=6)
        self.assertAlmostEqual(internal['occurrence_temperatures'][part]['minimum_k'], 400-100*125/300, places=6)
        self.assertAlmostEqual(sum(c['left_to_right_heat_w'] for c in internal['field_result']['contacts']), -1/3, places=8)
        self.assertLess(abs(internal['field_result']['heat_balance']['imbalance_w']), 1e-8)
        from python.spike_core.calculix_runtime import probe_calculix_runtime
        from python.spike_core.calculix_thermal import run_calculix_thermal
        if not probe_calculix_runtime()['available']:
            self.skipTest('Internal real Gmsh/contact oracle passed; separately installed CalculiX unavailable')
        external = run_calculix_thermal(geometry, linked, {'threads': 1, 'timeout_seconds': 60})
        self.assertAlmostEqual(external['occurrence_temperatures']['board-a']['maximum_k'], 300+100*125/300, delta=.002)
        self.assertAlmostEqual(external['occurrence_temperatures'][part]['minimum_k'], 400-100*125/300, delta=.002)
        # Shared CAD interface nodes became separately indexed physical unknowns.
        ranges = [trace['vertex_range'] for trace in result['handoff']['source_traceability']]
        self.assertLessEqual(ranges[0][1], ranges[1][0])
        self.assertFalse(result['contacts_inferred'])

    def test_cross_occurrence_overlap_is_rejected_by_boolean_ancestry(self):
        result, _ = self.mesh('overlap', z=.5)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('ASSEMBLY_JOINT_OVERLAP', result['blockers'][0]['message'])

    def test_real_gap_is_not_welded_or_turned_into_contact(self):
        result, _ = self.mesh('gap', z=1.01)
        self.assertEqual(result['status'], 'completed', result.get('blockers'))
        problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'heat_sources': [], 'boundaries': [], 'contacts': []}
        preview = discover_assembly_thermal_links(result['request'], problem)
        self.assertEqual(preview['proposals'], [])
        self.assertEqual(preview['unmatched_contact_ids'], ['package-contact'])

    def test_cad_tolerance_must_not_close_positive_source_gaps(self):
        for index, gap in enumerate((1e-8, 1e-10, 1e-12)):
            with self.subTest(gap_mm=gap):
                result, _ = self.mesh('near-gap-'+str(index), z=1+gap)
                self.assertEqual(result['status'], 'blocked')
                self.assertIn('ASSEMBLY_JOINT_SOURCE_SEPARATION', result['blockers'][0]['message'])

    def test_original_two_board_gap_and_rotated_exact_contact(self):
        for index, gap in enumerate((0., 1e-8)):
            with self.subTest(gap_mm=gap):
                p, a, o, reader = fixture()
                # Shared rigid placement rotates the original finite source faces.
                p['assembly_ir']['boards'][0]['frame']['transform'] = [0,-1,0,0,1,0,0,0,0,0,1,0,0,0,0,1]
                p['assembly_ir']['boards'][1]['frame']['transform'] = [0,-1,0,0,1,0,0,0,0,0,1,1+gap,0,0,0,1]
                p['assembly_ir']['thermal_contacts'] = [{'id': 'boards', 'endpoint_a': 'board-a', 'endpoint_b': 'board-b',
                                                         'contact_area_mm2': 4., 'thermal_resistance_k_per_w': 50.}]
                result = run_assembly_thermal_mesh(p, a, o, Path(self.directory.name)/('board-gap-'+str(index)),
                                                  artifact_reader=reader)
                if gap:
                    self.assertEqual(result['status'], 'blocked')
                    self.assertIn('SOURCE_SEPARATION', result['blockers'][0]['message'])
                else:
                    self.assertEqual(result['status'], 'completed', result.get('blockers'))
                    problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'heat_sources': [], 'boundaries': [], 'contacts': []}
                    preview = discover_assembly_thermal_links(result['request'], problem)
                    self.assertEqual(preview['proposals'][0]['status'], 'ready')
                    self.assertAlmostEqual(preview['proposals'][0]['contact_area_mm2'], 4.)


if __name__ == '__main__':
    unittest.main()
