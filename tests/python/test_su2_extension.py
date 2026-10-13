# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from extensions.su2_suite.extension import execute
from python.spike_core.extensions import ExtensionManifest

ROOT = Path(__file__).resolve().parents[2]


def request(contribution, parameters=None):
    return {'contract': 'spike/extension/v1', 'contribution_id': contribution,
            'context': {'parameters': parameters or {}}}


class Su2ExtensionTests(unittest.TestCase):
    def test_manifest_is_valid_and_board_independent(self):
        data = json.loads((ROOT / 'extensions/su2_suite/spike-extension.json').read_text())
        ExtensionManifest.from_dict(data)
        routes = [r for app in data['contributes']['applications'] for r in app.get('workspace_routes', [])]
        self.assertEqual({r['id'] for r in routes}, {'su2-cfd', 'su2-cht'})
        self.assertTrue(all(r['requires_board'] is False for r in routes))
        self.assertNotIn('design.read', data['permissions'])

    def test_preview_contains_physics_without_launching_engine(self):
        with patch('extensions.su2_suite.extension.run_su2_airflow', side_effect=AssertionError('unexpected launch')):
            result = execute(request('su2-cfd-preview', {'cells': 16}))
        self.assertFalse(result['data']['solved'])
        self.assertFalse(result['data']['board_geometry_used'])
        self.assertIn('INC_NAVIER_STOKES', result['data']['config'])

    def test_unsupported_parameters_and_contributions_rejected(self):
        for contribution, params in [('su2-cfd', {'executable': 'bad.exe'}),
                                      ('su2-probe', {'path': 'bad'}), ('other', {})]:
            with self.subTest(contribution=contribution), self.assertRaises(ValueError):
                execute(request(contribution, params))

    def test_failed_convergence_remains_failed(self):
        with patch('extensions.su2_suite.extension.run_su2_airflow', return_value={'status': 'failed_to_converge'}):
            result = execute(request('su2-cfd', {'cells': 16}))
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['data']['production_qualified'])

    def test_failed_thermal_validation_remains_failed(self):
        with patch('python.spike_core.su2_cht.run_su2_cht', return_value={
            'status': 'failed_validation', 'validation': {'passed': False},
            'convergence': {'converged': True}}):
            result = execute(request('su2-cht', {'cells': 16}))
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['data']['result']['validation']['passed'])

    def test_cht_preview_shows_both_solids_without_execution(self):
        with patch('python.spike_core.su2_cht.run_su2_cht', side_effect=AssertionError('unexpected launch')):
            result = execute(request('su2-cht-preview', {'cells': 16}))
        self.assertIn('cold_solid_bounds_m', result['data']['geometry'])
        self.assertIn('runtime', result['data'])
        self.assertFalse(result['data']['board_geometry_used'])
