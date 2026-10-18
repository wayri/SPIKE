# SPDX-License-Identifier: Apache-2.0
"""Original retained component identity, placement and exact STEP mesh checks."""
import copy
import ctypes.util
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.assembly_field.run_examples import setup
from python.spike_core.assembly_frames import IDENTITY, resolve_world
from python.spike_core.assembly_thermal_components import (
    promote_thermal_components, thermal_component_inventory, PROVENANCE_KEY)
from python.spike_core.assembly_thermal_meshing import prepare_assembly_thermal_mesh, run_assembly_thermal_mesh
from python.spike_core.project_package import ProjectPackageError, read_project, write_spike_package
from python.spike_core.service_project_thermal_mesh import (
    promote_thermal_components_in_project, read_assembly_thermal_mesh_setup)
from python.spike_core.spider_v2 import AssemblyIRV1
from tests.python.test_assembly_thermal_meshing import fixture, has_runtime, runtime
from tests.python.test_project_assembly_field import MODEL_ARTIFACT, _payload


def add_component(payload, model, board_id):
    payload['models'] = {'contract': 'spike/model-index/v1', 'models': [copy.deepcopy(model)]}
    payload['design_ir']['components'] = [{'id': 'component-1', 'reference': 'U1', 'position_mm': [1, 1],
                                          'side': 'top', 'rotation_deg': 90, 'model_ids': [model['id']]}]
    placement = list(IDENTITY)
    placement[3], placement[7], placement[11] = .5, .5, 2.
    selection = {'board_occurrence_id': board_id, 'component_id': 'component-1', 'model_id': model['id'],
                 'component_to_board_transform_mm': placement, 'material_id': 'reviewed', 'placement_reviewed': True}
    return selection


def pure_fixture():
    p, a, o, reader = fixture()
    model = {'id': 'component-step', 'model_type': 'step', 'uri': 'package:models/artifacts/component.step',
             'digest': hashlib.sha256(MODEL_ARTIFACT).hexdigest(), 'transform': list(IDENTITY)}
    selection = add_component(p, model, 'board-a')
    return p, a, o, selection, lambda uri: MODEL_ARTIFACT if uri.startswith('package:models/') else reader(uri)


class ThermalComponentPromotionTests(unittest.TestCase):
    def test_explicit_promotion_preserves_source_identity_and_board_frame(self):
        p, a, _, selection, reader = pure_fixture()
        original = copy.deepcopy(p)
        promoted = promote_thermal_components(p, [selection], a['materials'], artifact_reader=reader)
        self.assertEqual(p, original)
        part = promoted['promoted_parts'][0]
        self.assertEqual(part['frame']['parent_frame_id'], 'frame-a')
        self.assertEqual(part['model_id'], selection['model_id'])
        self.assertEqual(part['source_id'], selection['component_id'])
        self.assertEqual(part['extensions'][PROVENANCE_KEY]['source_sha256'], p['models']['models'][0]['digest'])
        assembly = AssemblyIRV1.from_dict(promoted['payload']['assembly_ir'])
        self.assertEqual(list(resolve_world(assembly, assembly.parts[0].frame)), selection['component_to_board_transform_mm'])
        self.assertEqual(thermal_component_inventory(promoted['payload'])[0]['promoted_part_ids'], [part['id']])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            promote_thermal_components(promoted['payload'], [selection], a['materials'], artifact_reader=reader)

    def test_duplicate_board_components_get_distinct_occurrences_and_world_placement(self):
        p, a, _, selected, reader = pure_fixture()
        second = dict(copy.deepcopy(selected), board_occurrence_id='board-b')
        result = promote_thermal_components(p, [selected, second], a['materials'], artifact_reader=reader)
        first, second = result['promoted_parts']
        self.assertNotEqual(first['id'], second['id'])
        assembly = AssemblyIRV1.from_dict(result['payload']['assembly_ir'])
        transforms = [resolve_world(assembly, part.frame) for part in assembly.parts]
        self.assertAlmostEqual(transforms[1][3]-transforms[0][3], 4.)

    def test_rejects_unreviewed_placement_nonrigid_missing_material_and_display_model(self):
        mutations = [lambda p, s: s.update(placement_reviewed=False),
                     lambda p, s: s['component_to_board_transform_mm'].__setitem__(0, 2.),
                     lambda p, s: s.update(material_id='unknown'),
                     lambda p, s: p['models']['models'][0].update(model_type='glb'),
                     lambda p, s: p['design_ir']['components'][0].update(model_ids=[]),
                     lambda p, s: p['models']['models'][0].update(digest='0'*64)]
        for mutation in mutations:
            p, a, _, s, reader = pure_fixture()
            mutation(p, s)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                promote_thermal_components(p, [s], a['materials'], artifact_reader=reader)

    def test_changed_source_component_and_model_block_subsequent_mesh(self):
        for owner, field, value in [('component', 'rotation_deg', 180), ('model', 'digest', '0'*64)]:
            p, a, o, s, reader = pure_fixture()
            promoted = promote_thermal_components(p, [s], a['materials'], artifact_reader=reader)
            p = promoted['payload']
            a['parts'].update(promoted['part_material_assignments'])
            self.assertEqual(prepare_assembly_thermal_mesh(p, a, o, artifact_reader=reader)['status'], 'ready')
            row = p['design_ir']['components'][0] if owner == 'component' else p['models']['models'][0]
            row[field] = value
            blocked = prepare_assembly_thermal_mesh(p, a, o, artifact_reader=reader)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertIn('COMPONENT_STALE', [item['code'] for item in blocked['blockers']])

    def test_package_promotion_preserves_step_and_saved_materials_and_rejects_stale_manifest(self):
        geometry, _ = setup()
        payload = _payload(geometry)
        payload['results'] = {'original-fixture': {'status': 'experimental', 'value': 4}}
        selection = add_component(payload, payload['models']['models'][0], 'board')
        material = {'id': 'reviewed', 'thermal_conductivity_w_mk': 3,
                    'provenance': 'Original reviewed synthetic material'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'components.spike'
            manifest = write_spike_package(path, payload, model_artifacts={'original-case.step': MODEL_ARTIFACT})
            params = {'project_path': str(path), 'expected_manifest_payload_sha256': manifest['manifest_payload_sha256'],
                      'selections': [selection], 'materials': [material]}
            result = promote_thermal_components_in_project(params, application_version='test')
            opened = read_project(path, include_members=True)
            self.assertEqual(opened.members['models/artifacts/original-case.step'], MODEL_ARTIFACT)
            self.assertTrue(result['invalidated_results'])
            self.assertEqual(opened.payload['results'], {})
            history = opened.payload['extensions']['spike.assembly-structure-history']['previous_states']
            self.assertEqual(history[-1]['results']['original-fixture']['value'], 4)
            inventory = read_assembly_thermal_mesh_setup({'project_path': str(path),
                'expected_manifest_payload_sha256': result['manifest']['manifest_payload_sha256']})
            self.assertEqual(inventory['thermal_materials'], [material])
            self.assertEqual(inventory['part_material_assignments'], result['part_material_assignments'])
            self.assertEqual(len(inventory['components'][0]['promoted_part_ids']), 1)
            before = path.read_bytes()
            with self.assertRaises(ProjectPackageError):
                promote_thermal_components_in_project(params)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(opened.payload['audit'][-1]['event'], 'thermal_components_promoted')

    def test_source_conflict_and_parameter_schema(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        p, a, _, s, reader = pure_fixture()
        p['design_ir']['models'] = [copy.deepcopy(p['models']['models'][0])]
        p['design_ir']['models'][0]['transform'][3] = 7
        self.assertEqual(thermal_component_inventory(p)[0]['models'][0]['status'], 'blocked')
        with self.assertRaisesRegex(ValueError, 'CONFLICT'):
            promote_thermal_components(p, [s], a['materials'], artifact_reader=reader)
        root = Path(__file__).resolve().parents[2]/'schemas'
        assignment_schema = json.loads((root/'assembly-thermal-mesh-assignments-v1.schema.json').read_text())
        registry = Registry().with_resource('https://spike.local/schemas/assembly-thermal-mesh-assignments-v1.schema.json',
                                             Resource.from_contents(assignment_schema))
        schema = json.loads((root/'thermal-component-promotion-v1.schema.json').read_text())
        validator = Draft202012Validator(schema, registry=registry)
        Draft202012Validator.check_schema(schema)
        params = {'project_path': 'test.spike', 'expected_manifest_payload_sha256': 'a'*64,
                  'selections': [s], 'materials': a['materials']}
        validator.validate(params)
        params['selections'][0]['placement_reviewed'] = False
        self.assertTrue(list(validator.iter_errors(params)))


@unittest.skipUnless(has_runtime(), 'Requires admitted local Windows CPython 3.11 OCC runtime')
class RealPromotedStepTests(unittest.TestCase):
    def test_real_component_step_meshed_with_retained_component_and_model_transforms(self):
        with tempfile.TemporaryDirectory() as directory, os.add_dll_directory(str(runtime.DLL.parent)):
            original = ctypes.util.find_library
            with patch.object(ctypes.util, 'find_library', side_effect=lambda n: str(runtime.DLL) if n in ('gmsh', 'gmsh-4.15') else original(n)):
                spec = importlib.util.spec_from_file_location('gmsh', runtime.API)
                gmsh = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gmsh)
            step = Path(directory)/'component.step'
            gmsh.initialize(['gmsh', '-nopopup'], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                gmsh.model.add('original_component')
                gmsh.model.occ.addBox(0, 0, 0, 1, 1, 1)
                gmsh.model.occ.synchronize()
                gmsh.write(str(step))
            finally:
                gmsh.finalize()
            data = step.read_bytes()
            p, a, o, selected, reader = pure_fixture()
            p['models']['models'][0]['digest'] = hashlib.sha256(data).hexdigest()
            p['models']['models'][0]['transform'][7] = .25
            second = dict(copy.deepcopy(selected), board_occurrence_id='board-b')
            artifacts = lambda uri: data if uri.startswith('package:models/') else reader(uri)
            promoted = promote_thermal_components(p, [selected, second], a['materials'], artifact_reader=artifacts)
            a['parts'].update(promoted['part_material_assignments'])
            result = run_assembly_thermal_mesh(promoted['payload'], a, o, Path(directory)/'mesh', artifact_reader=artifacts)
            self.assertEqual(result['status'], 'completed', result.get('blockers'))
            self.assertEqual(len(result['request']['bodies']), 4)
            self.assertEqual(result['request']['materials'], a['materials'])
            self.assertEqual(len(result['handoff']['materials']), 4)
            for material in result['handoff']['materials']:
                self.assertEqual(material['provenance'], a['materials'][0]['provenance'])
                self.assertEqual(material['thermal_conductivity_w_mk'],
                                 [[2., 0., 0.], [0., 2., 0.], [0., 0., 2.]])
            points = result['handoff']['mesh']['vertices']
            for index, part in enumerate(promoted['promoted_parts']):
                trace = next(t for t in result['handoff']['source_traceability'] if t['occurrence_id'] == part['id'])
                self.assertAlmostEqual(trace['volume_m3'], 1e-9, places=16)
                samples = points[trace['vertex_range'][0]:trace['vertex_range'][1]]
                self.assertAlmostEqual(min(p[0] for p in samples), (.5+4*index)*.001, places=12)
                self.assertAlmostEqual(min(p[1] for p in samples), .75e-3, places=12)
                self.assertAlmostEqual(min(p[2] for p in samples), 2e-3, places=12)
                self.assertEqual(trace['source_sha256'], hashlib.sha256(data).hexdigest())
            self.assertFalse(result['contacts_inferred'])
            json.dumps(result, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
