# SPDX-License-Identifier: Apache-2.0
"""Explicit source-bound component solids and physical export regressions."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import unittest

from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.mcad_component_models import bind_component_models
from python.spike_core.mcad_export_design import assembly_from_context
from python.spike_core.mcad_export_contract import IDENTITY
from python.spike_core.mcad_export import export_assembly

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    model = (ROOT / 'benchmarks/parity-import/component-solid.step').read_bytes()
    design = SpiDeRV2.from_v1(SpiDeR(design_id='owned-package-board', name='Owned fixture',
        source_format='neutral', components=[{'reference': 'U1', 'at': [2, 3]}],
        stackup=[{'name': 'Core', 'type': 'dielectric', 'thickness_mm': 1.6}],
        metadata={'model_references': [{'source_id': 'owned-body', 'component': 'U1',
            'uri': 'owned-package.step', 'sha256': hashlib.sha256(model).hexdigest()}],
            'board_outline_rings': [{'role': 'outer', 'start_mm': [0, 0], 'segments': [
                {'kind': 'line', 'end_mm': p} for p in ([10, 0], [10, 8], [0, 8], [0, 0])]}]})).to_dict()
    context = {'design': design, 'parameters': {'allow_partial': True}}
    plan = assembly_from_context(context)
    occurrence = plan['properties']['component_occurrences'][0]
    binding = {'occurrence_id': occurrence['id'], 'model_id': occurrence['model_ids'][0],
        'design_digest': plan['properties']['retained_design_digests'][occurrence['design_id']],
        'model_to_board_mm': [0., -1., 0., 10., 1., 0., 0., 20.,
                              0., 0., 1., 2., 0., 0., 0., 1.],
        'placement_reference': 'Owned cuboid, explicit Rz(90) then translation (10,20,2) mm.',
        'geometry': {'type': 'step', 'data_base64': base64.b64encode(model).decode(),
                     'sha256': hashlib.sha256(model).hexdigest()}}
    return context, binding


class ComponentModelTests(unittest.TestCase):
    def test_bound_solid_resolves_only_component_geometry(self):
        context, binding = fixture()
        before = copy.deepcopy(context)
        context['parameters']['component_models'] = [binding]
        assembly = assembly_from_context(context)
        body = next(o for o in assembly['objects'] if o['kind'] == 'component')
        self.assertEqual(body['transform'], binding['model_to_board_mm'])
        self.assertEqual(body['source']['model_id'], binding['model_id'])
        self.assertFalse(body['properties']['solver_ready'])
        self.assertFalse(body['properties']['material_qualified'])
        self.assertNotIn('COMPONENT_GEOMETRY_REQUIRED', [d['code'] for d in assembly['diagnostics']])
        self.assertEqual(context['design'], before['design'])
        self.assertEqual(context['design']['models'][0]['transform'], [])

    def test_invalid_handoffs_reject_without_partial_mutation(self):
        context, binding = fixture()
        for mutation in ('owner', 'model', 'baseline', 'digest', 'scale', 'mirror',
                         'boolean', 'reference', 'geometry', 'unknown', 'duplicate'):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(binding)
                if mutation == 'owner': altered['occurrence_id'] = 'other-board'
                elif mutation == 'model': altered['model_id'] = 'other-model'
                elif mutation == 'baseline': altered['design_digest'] = '0' * 64
                elif mutation == 'digest': altered['geometry']['sha256'] = '0' * 64
                elif mutation == 'scale': altered['model_to_board_mm'][0] = 2
                elif mutation == 'mirror': altered['model_to_board_mm'] = IDENTITY.copy(); altered['model_to_board_mm'][0] = -1
                elif mutation == 'boolean': altered['model_to_board_mm'][3] = True
                elif mutation == 'reference': altered['placement_reference'] = ''
                elif mutation == 'geometry': altered['geometry'] = {'type': 'box', 'size_mm': [1, 1, 1]}
                elif mutation == 'unknown': altered['inferred_material'] = 'copper'
                assembly = assembly_from_context(context)
                original = copy.deepcopy(assembly)
                with self.assertRaises(ValueError):
                    bind_component_models(assembly, [altered, altered] if mutation == 'duplicate' else [altered])
                self.assertEqual(assembly, original)

    def test_missing_solid_stays_diagnostic(self):
        context, _ = fixture()
        context['parameters']['component_models'] = []
        context['parameters']['allow_partial'] = False
        with self.assertRaisesRegex(ValueError, 'COMPONENT_GEOMETRY_REQUIRED'):
            assembly_from_context(context)

    def test_partial_multiple_models_does_not_clear_component_gap(self):
        context, binding = fixture()
        other = copy.deepcopy(context['design']['models'][0])
        import uuid
        other['id'] = str(uuid.uuid4())
        other['source_id'] = 'owned-lid'
        context['design']['models'].append(other)
        context['design']['components'][0]['model_ids'].append(other['id'])
        plan = assembly_from_context(context)
        binding['design_digest'] = next(iter(plan['properties']['retained_design_digests'].values()))
        context['parameters']['component_models'] = [binding]
        projected = assembly_from_context(context)
        self.assertEqual(len([o for o in projected['objects'] if o['kind'] == 'component']), 1)
        self.assertIn('COMPONENT_GEOMETRY_REQUIRED', [d['code'] for d in projected['diagnostics']])

    def test_repeated_board_occurrences_require_separate_bindings(self):
        from python.spike_core.spider_v2 import AssemblyIRV1, BoardInstance
        from python.spike_core.spider_v2_schema import CoordinateFrame
        context, binding = fixture()
        translated = IDENTITY.copy(); translated[3] = 30
        context['project'] = {'assembly_ir': AssemblyIRV1(assembly_id='owned-repeat', name='Owned repeated boards', boards=[
            BoardInstance(id='a', design_id=context['design']['design_id']),
            BoardInstance(id='b', design_id=context['design']['design_id'], frame=CoordinateFrame(
                frame_id='frame-b', parent_frame_id='assembly', transform=tuple(translated))),
        ]).to_dict()}
        plan = assembly_from_context(context)
        occurrences = plan['properties']['component_occurrences']
        bindings = []
        for occurrence in occurrences:
            row = copy.deepcopy(binding)
            row['occurrence_id'] = occurrence['id']
            row['design_digest'] = plan['properties']['retained_design_digests'][occurrence['design_id']]
            bindings.append(row)
        context['parameters']['component_models'] = bindings[:1]
        partial = assembly_from_context(context)
        self.assertEqual([d['source_id'] for d in partial['diagnostics']
                          if d['code'] == 'COMPONENT_GEOMETRY_REQUIRED'], [occurrences[1]['id']])
        context['parameters']['component_models'] = bindings
        result = assembly_from_context(context)
        self.assertEqual({o['parent_id'] for o in result['objects'] if o['kind'] == 'component'}, {'a', 'b'})
        self.assertEqual({o['id'] for o in result['objects'] if o['kind'] == 'component'},
                         {row['occurrence_id'] + '/model:' + row['model_id'] for row in bindings})

    def test_material_assignment_does_not_qualify_physics(self):
        context, binding = fixture()
        binding['material_id'] = 'reviewed-placeholder'
        context['parameters']['materials'] = [{'id': 'reviewed-placeholder', 'name': 'Owned test material',
            'properties': {'density_kg_per_m3': 1000, 'evidence': 'Synthetic fixture only'}}]
        context['parameters']['component_models'] = [binding]
        body = next(o for o in assembly_from_context(context)['objects'] if o['kind'] == 'component')
        self.assertEqual(body['material_id'], 'reviewed-placeholder')
        self.assertFalse(body['properties']['material_qualified'])

    def test_isolated_extension_plan_receives_explicit_handoff(self):
        from python.spike_core.extensions import ExtensionRegistry
        context, binding = fixture()
        context['parameters']['component_models'] = [binding]
        registry = ExtensionRegistry()
        root = ROOT / 'extensions'
        registry.discover([root], trusted_roots=[root])
        result = registry.invoke('spike.mcad', 'mcad-plan', context)
        body = next(o for o in result['data']['objects'] if o['kind'] == 'component')
        self.assertEqual(body['source']['model_id'], binding['model_id'])

    def test_actual_step_export_preserves_placed_bounds_and_volume(self):
        from python.spike_core.dependencies import dependency_status
        if not any(d['id'] == 'freecad' and d['status'] == 'ready'
                   for d in dependency_status()['dependencies']):
            self.skipTest('Optional FreeCAD runtime unavailable')
        context, binding = fixture()
        context['parameters']['component_models'] = [binding]
        result = export_assembly(assembly_from_context(context))
        body = next(o for o in result['manifest']['objects'] if o['kind'] == 'component')
        self.assertEqual(body['solid_count'], 1)
        self.assertEqual(body['step_roundtrip'], 'passed')
        self.assertAlmostEqual(body['volume_mm3'], 24, places=6)
        for actual, expected in zip(body['bounds_mm'], [7, 20, 2, 10, 22, 6]):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_native_cohort_gate_rejects_incomplete_or_invalid_observations(self):
        from scripts.parity_component_model_gate import validate_component_model_gate
        imported = json.loads((ROOT / 'docs/validation/parity/WF01-S04C1-import.json').read_text())
        solid = (ROOT / 'benchmarks/parity-import/component-solid.step').read_bytes()
        native = json.loads((ROOT / 'docs/validation/parity/WF01-S04C1-native-solids.json').read_text())
        validate_component_model_gate(imported, solid, native)
        for mutation in ('missing', 'volume', 'nonfinite', 'bounds', 'placement', 'physics',
                         'asset', 'parent', 'material', 'qualification'):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(native)
                body = next(o for o in altered['objects'] if o['kind'] == 'component')
                if mutation == 'missing': altered['objects'].remove(body)
                elif mutation == 'volume': body['volume_mm3'] = 25
                elif mutation == 'nonfinite': body['volume_mm3'] = float('nan')
                elif mutation == 'bounds': body['bounds_mm'][0] += .01
                elif mutation == 'placement': body['transform'][3] += 1
                elif mutation == 'physics': body['properties']['solver_ready'] = True
                elif mutation == 'parent': body['parent_id'] = 'wrong-parent'
                elif mutation == 'material': body['material_id'] = 'foreign-material'
                elif mutation == 'qualification': altered['solver_qualified'] = True
                changed_solid = solid + b'\n' if mutation == 'asset' else solid
                with self.assertRaises(ValueError): validate_component_model_gate(imported, changed_solid, altered)


if __name__ == '__main__':
    unittest.main()
