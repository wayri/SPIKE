# SPDX-License-Identifier: Apache-2.0
"""Compare review drafts to retained native STEP corners and failure controls."""
import base64
import copy
import json
from pathlib import Path
import unittest

import numpy as np

from python.spike_core.component_placement_review import draft_kicad_component_placement, REFERENCE_STEP_SHA256
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.spider_v2_schema import content_digest
from python.spike_core.mcad_export_design import assembly_from_context
from scripts.parity_native_step_placement_gate import points

ROOT = Path(__file__).resolve().parents[2]


def draft(design, ordinal=1, **overrides):
    args = {'native_version': '10.0.6', 'expected_design_digest': content_digest(design),
            'step_sha256': REFERENCE_STEP_SHA256}
    args.update(overrides)
    component = design['components'][0]
    return draft_kicad_component_placement(design, component['id'], component['model_ids'][ordinal], **args)


class PlacementReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs = {name: SpiDeRV2.from_v1(import_kicad_design(str(ROOT /
                       'benchmarks/parity-import/native-step-reference' / (name + '.kicad_pcb')))).to_dict()
                       for name in ('front-37', 'front-90', 'back-37', 'back-90')}
        cls.reference = json.loads((ROOT / 'docs/validation/parity/WF01-S04C3-native-step.json').read_text())

    def test_eight_drafts_match_actual_native_corners_and_do_not_mutate(self):
        import itertools
        corners = np.array([list(p) + [1.] for p in itertools.product([0., 2.], [0., 3.], [0., 4.])])
        for case in self.reference['cases']:
            if case['model_index'] == 0:
                continue
            design = copy.deepcopy(self.designs[case['name']])
            before = copy.deepcopy(design)
            result = draft(design, case['model_index'])
            transformed = (np.array(result['model_to_board_mm']).reshape(4, 4) @ corners.T).T[:, :3].tolist()
            points(transformed, case['spike_vertices_mm'])
            self.assertEqual(design, before)
            self.assertEqual(result['status'], 'review_required')
            for key in ('source_projection_enabled', 'material_qualified', 'solver_ready'):
                self.assertFalse(result[key])
            self.assertEqual(result['mounting_clearance_mm'], .05)

    def test_native_origin_is_used_instead_of_pad_centroid(self):
        design = self.designs['front-90']
        self.assertNotEqual(design['components'][0]['position_mm'], [20., 10.])
        result = draft(design, 2)
        matrix = result['model_to_board_mm']
        for actual, expected in zip([matrix[3], matrix[7], matrix[11]], [20., 10., -.05]):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_explicit_handoff_can_use_reviewed_draft_and_remains_partial(self):
        design = self.designs['front-90']
        result = draft(design)
        context = {'design': design, 'parameters': {'allow_partial': True}}
        plan = assembly_from_context(context)
        occurrence = plan['properties']['component_occurrences'][0]
        context['parameters']['component_models'] = [{
            'occurrence_id': occurrence['id'], 'model_id': result['model_id'],
            'design_digest': result['design_digest'], 'model_to_board_mm': result['model_to_board_mm'],
            'placement_reference': 'Original native fixture reviewed in test; exporter clearance retained.',
            'geometry': {'type': 'step', 'sha256': REFERENCE_STEP_SHA256,
                         'data_base64': base64.b64encode((ROOT / 'benchmarks/parity-import/component-solid.step').read_bytes()).decode()}}]
        bound = assembly_from_context(context)
        body = next(o for o in bound['objects'] if o['kind'] == 'component')
        self.assertEqual(body['transform'], result['model_to_board_mm'])
        self.assertFalse(body['properties']['solver_ready'])
        self.assertIn('COMPONENT_GEOMETRY_REQUIRED', [d['code'] for d in bound['diagnostics']])

    def test_scope_stale_and_scaled_controls_reject(self):
        design = self.designs['front-90']
        for kwargs in ({'native_version': '10.0.7'}, {'expected_design_digest': '0' * 64},
                       {'step_sha256': '0' * 64}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                draft(design, **kwargs)
        with self.assertRaisesRegex(ValueError, 'PLACEMENT_SCALE'):
            draft(design, 0)

    def test_missing_conflicting_and_nonfinite_source_facts_reject(self):
        for mutation in ('origin', 'angle', 'layer', 'owner', 'stack', 'boolean', 'nan', 'applied'):
            design = copy.deepcopy(self.designs['front-90'])
            component = design['components'][0]
            model = design['models'][1]
            if mutation == 'origin':
                component['extensions']['spike.v1'].pop('native_footprint_at_mm')
            elif mutation == 'angle':
                component['rotation_deg'] = 12.
            elif mutation == 'layer':
                component['extensions']['spike.v1']['layer'] = 'B.Cu'
            elif mutation == 'owner':
                model['extensions']['spike.v1']['component'] = 'foreign'
            elif mutation == 'stack':
                design['layers'][1]['thickness_mm'] = 2.
            elif mutation in ('boolean', 'nan'):
                model['extensions']['spike.v1']['source_placement']['declared_vectors']['offset'][1] = (
                    False if mutation == 'boolean' else float('nan'))
            else:
                model['transform'] = [1.] * 16
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                draft(design)

    def test_contradictory_declarations_and_unknown_physical_layers_reject(self):
        for mutation in ('model_only', 'both_normalized', 'unknown_layer', 'named_copper', 'units', 'handedness', 'frame', 'contract'):
            design = copy.deepcopy(self.designs['front-90'])
            if mutation in ('model_only', 'both_normalized'):
                declaration = design['models'][1]['extensions']['spike.v1']['source_placement']
                declaration['declared_vectors']['offset'] = [0., 0., 0.]
                declaration['declared_vectors']['rotate'] = [0., 0., 0.]
                if mutation == 'both_normalized':
                    design['components'][0]['extensions']['spike.v1']['model_sources'][1] = copy.deepcopy(declaration)
            elif mutation == 'unknown_layer':
                design['layers'].append({'id': 'unknown', 'layer_type': 'copper', 'thickness_mm': None})
            elif mutation == 'named_copper':
                design['layers'].append({'id': 'unknown', 'name': 'In1.Cu', 'layer_type': 'signal', 'thickness_mm': None})
            elif mutation == 'units':
                design['frame']['units'] = 'inch'
            elif mutation == 'handedness':
                design['frame']['handedness'] = 'left'
            elif mutation == 'frame':
                design['frame']['transform'] = list(design['frame']['transform'])
                design['frame']['transform'][3] = 3.
            else:
                design['contract'] = 'unknown'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                draft(design)
