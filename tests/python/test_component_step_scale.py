# SPDX-License-Identifier: Apache-2.0
"""Positive geometry scaling, native invariants and fail-closed admission."""
import base64
import copy
import hashlib
import itertools
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from python.spike_core.component_step_scale import scale_component_step, validate_facts, validate_scale
from python.spike_core.mcad_tessellation import _freecad_path
from scripts.parity_native_step_placement_gate import points

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'benchmarks/parity-import/component-solid.step'


def facts():
    row = {'solid_count': 1, 'valid': True, 'closed': True, 'volume_mm3': 24.,
           'bounds_mm': [0., 0., 0., 2., 3., 4.]}
    scaled = dict(row, bounds_mm=[0., 0., 0., 4., 3., 2.])
    return {'contract': 'spike/scaled-step-native/v1', 'units': 'mm', 'solver_qualified': False,
            'source_sha256': 'source', 'output_sha256': 'derived', 'scale_xyz': [2., 1., .5],
            'source': row, 'scaled': copy.deepcopy(scaled), 'roundtrip': copy.deepcopy(scaled)}


class ScaleAdmissionTests(unittest.TestCase):
    def test_failed_process_produces_no_asset(self):
        data = SOURCE.read_bytes()
        with (patch('python.spike_core.component_step_scale._freecad_path', return_value=Path('unused.exe')),
              patch('python.spike_core.component_step_scale.run_adapter_process', return_value={'return_code': 1, 'stderr': 'cancelled'})):
            with self.assertRaisesRegex(RuntimeError, 'no derived asset accepted'):
                scale_component_step(data, [2., 1., .5], expected_sha256=hashlib.sha256(data).hexdigest())
    def test_source_and_bad_factors_reject_before_native_execution(self):
        data = SOURCE.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        for scale in ([0., 1., 1.], [-1., 1., 1.], [True, 1., 1.], [float('nan'), 1., 1.],
                      [float('inf'), 1., 1.], [1e-4, 1., 1.], [1., 1.], '1,1,1'):
            with self.subTest(scale=scale), patch('python.spike_core.component_step_scale._freecad_path') as runtime:
                with self.assertRaises(ValueError):
                    scale_component_step(data, scale, expected_sha256=sha)
                runtime.assert_not_called()
        with patch('python.spike_core.component_step_scale._freecad_path') as runtime:
            with self.assertRaisesRegex(ValueError, 'STALE'):
                scale_component_step(data, [2., 1., .5], expected_sha256='0' * 64)
            runtime.assert_not_called()

    def test_constant_volume_does_not_hide_changed_bounds(self):
        validate_facts(facts(), 'source', 'derived', [2., 1., .5])
        altered = facts()
        altered['scaled']['bounds_mm'] = [0., 0., 0., 2., 3., 4.]
        with self.assertRaises(ValueError):
            validate_facts(altered, 'source', 'derived', [2., 1., .5])

    def test_native_failures_cannot_be_admitted(self):
        for mutation in ('volume', 'roundtrip', 'sheet', 'multiple', 'boolean_count', 'nan', 'units', 'qualified', 'sha'):
            altered = facts()
            if mutation == 'volume': altered['scaled']['volume_mm3'] *= 1.0086
            elif mutation == 'roundtrip': altered['roundtrip']['bounds_mm'][5] += .01
            elif mutation == 'sheet': altered['source']['closed'] = False
            elif mutation == 'multiple': altered['scaled']['solid_count'] = 2
            elif mutation == 'boolean_count': altered['source']['solid_count'] = True
            elif mutation == 'nan': altered['roundtrip']['volume_mm3'] = float('nan')
            elif mutation == 'units': altered['units'] = 'inch'
            elif mutation == 'qualified': altered['solver_qualified'] = True
            else: altered['output_sha256'] = 'changed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_facts(altered, 'source', 'derived', [2., 1., .5])


def has_native_runtime():
    try:
        _freecad_path()
        return True
    except (ValueError, RuntimeError, OSError):
        return False


@unittest.skipUnless(has_native_runtime(), 'Optional FreeCAD runtime unavailable')
class NativeStepScaleTests(unittest.TestCase):
    def test_actual_curved_conversion_fails_closed(self):
        data = (ROOT / 'benchmarks/parity-import/step-scale/cylinder.step').read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'no derived asset accepted'):
            scale_component_step(data, [2., 1., .5], expected_sha256=hashlib.sha256(data).hexdigest())

    def test_actual_native_cube_factors_and_reimported_vertices(self):
        data = SOURCE.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        results = []
        for scale in ([2., 1., .5], [.5, 3., 2.], [1., 1., 1.]):
            result = scale_component_step(data, scale, expected_sha256=sha)
            self.assertEqual(hashlib.sha256(base64.b64decode(result['geometry']['data_base64'])).hexdigest(),
                             result['geometry']['sha256'])
            native = result['native_facts']
            expected = [[p[i]*scale[i] for i in range(3)]
                        for p in itertools.product([0., 2.], [0., 3.], [0., 4.])]
            for key in ('scaled', 'roundtrip'):
                self.assertEqual(native[key]['vertices_status'], 'complete')
                points(native[key]['vertices_mm'], expected)
            for key in ('placement_scaled', 'material_qualified', 'solver_ready'):
                self.assertFalse(result[key])
            results.append(result)
        # Native tests retain structured evidence when explicitly requested by the gate.
        import os
        target = os.environ.get('SPIKE_SCALE_TEST_EVIDENCE')
        if target:
            path = Path(target).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError('Scale evidence must remain inside the repository')
            path.write_text(json.dumps({'cases': results}, indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
