# SPDX-License-Identifier: Apache-2.0
"""Bake-then-rigid review proposals compared to independent native solids."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.scaled_component_review import prepare_scaled_component_review
from python.spike_core.spider_v2_schema import content_digest
from tests.python import test_component_placement_review as placement_tests
ROOT = placement_tests.ROOT
from tests.python.test_component_step_scale import has_native_runtime
from scripts.parity_native_step_placement_gate import points


def prepare(design, ordinal=0, **overrides):
    component = design['components'][0]
    args = {'native_version': '10.0.6', 'expected_design_digest': content_digest(design)}
    args.update(overrides)
    return prepare_scaled_component_review(design, component['id'], component['model_ids'][ordinal],
        (ROOT/'benchmarks/parity-import/component-solid.step').read_bytes(), **args)


class ScaledReviewAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        placement_tests.PlacementReviewTests.setUpClass()
        cls.designs = placement_tests.PlacementReviewTests.designs
        cls.asset = json.loads((ROOT/'docs/validation/parity/WF01-S04C5-final-native.json').read_text())['cases'][0]

    def test_oversized_control_is_rejected_before_native(self):
        design = copy.deepcopy(self.designs['front-90'])
        design.setdefault('extensions', {})['oversized'] = 'x'*(8*1024**2)
        with patch('python.spike_core.scaled_component_review.scale_component_step') as bake:
            with self.assertRaisesRegex(ValueError, 'PLACEMENT_BUDGET'):
                prepare(design)
            bake.assert_not_called()

    def test_invalid_source_baseline_and_unit_control_never_start_native(self):
        for mutation in ('stale', 'version', 'unit', 'node'):
            design = copy.deepcopy(self.designs['front-90'])
            args = {}
            ordinal = 0
            if mutation == 'stale': args['expected_design_digest'] = '0'*64
            elif mutation == 'version': args['native_version'] = '10.0.7'
            elif mutation == 'unit': ordinal = 1
            else: design['models'][0]['extensions']['spike.v1']['source_placement']['declared_vectors']['rotate'] = [0.,0.,0.]
            with self.subTest(mutation=mutation), patch('python.spike_core.scaled_component_review.scale_component_step') as bake:
                with self.assertRaises(ValueError):
                    prepare(design, ordinal, **args)
                bake.assert_not_called()

    def test_snapshot_rejects_design_changed_during_job(self):
        design = copy.deepcopy(self.designs['front-90'])
        def changed(*args, **kwargs):
            design['components'][0]['rotation_deg'] = 12.
            return copy.deepcopy(self.asset)
        with patch('python.spike_core.scaled_component_review.scale_component_step', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'PLACEMENT_STALE'):
                prepare(design)

    def test_cancellation_and_failure_propagate_without_proposal(self):
        with patch('python.spike_core.scaled_component_review.scale_component_step', side_effect=RuntimeError('cancelled')) as bake:
            marker = object()
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                prepare(self.designs['front-90'], cancellation_event=marker)
            self.assertIs(bake.call_args.kwargs['cancellation_event'], marker)


@unittest.skipUnless(has_native_runtime(), 'Optional FreeCAD runtime unavailable')
class NativeScaledReviewTests(unittest.TestCase):
    def test_four_actual_baked_placements_match_native_corners(self):
        placement_tests.PlacementReviewTests.setUpClass()
        records = []
        for case in placement_tests.PlacementReviewTests.reference['cases']:
            if case['model_index'] != 0:
                continue
            design = copy.deepcopy(placement_tests.PlacementReviewTests.designs[case['name']])
            before = copy.deepcopy(design)
            result = prepare(design)
            self.assertEqual(before, design)
            rotation = np.array(result['model_to_board_mm']).reshape(4,4)
            self.assertTrue(np.allclose(rotation[:3,:3].T @ rotation[:3,:3], np.eye(3), atol=1e-12, rtol=0))
            self.assertAlmostEqual(np.linalg.det(rotation[:3,:3]), 1., places=12)
            vertices = result['derived_asset']['native_facts']['roundtrip']['vertices_mm']
            positioned = (rotation @ np.array([p+[1.] for p in vertices]).T).T[:,:3].tolist()
            points(positioned, case['spike_vertices_mm'])
            self.assertEqual(result['status'], 'review_required')
            self.assertTrue(result['derived_model_registration_required'])
            for key in ('solver_ready','material_qualified','source_projection_enabled'):
                self.assertFalse(result[key])
            records.append({'name':case['name'],'proposal':result,'positioned_vertices_mm':positioned})
        target = os.environ.get('SPIKE_SCALED_REVIEW_EVIDENCE')
        if target:
            path = Path(target).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError('Review evidence must remain in the repository')
            path.write_text(json.dumps({'cases':records},indent=2)+'\n')
