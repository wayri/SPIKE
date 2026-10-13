# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Strict contract admission for local grids and prescribed surface boundaries."""
import copy
import json
import unittest
import csv
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator
from python.spike_core.board_thermal import run_board_thermal
from tests.python.test_layered_thermal_surface_boundaries import design, request

ROOT = Path(__file__).resolve().parents[2]


class ThermalGridContractTests(unittest.TestCase):
    def setUp(self):
        self.request_validator = Draft202012Validator(json.loads((ROOT / 'schemas/board-thermal-request-v1.schema.json').read_text()))
        self.result_validator = Draft202012Validator(json.loads((ROOT / 'schemas/board-thermal-result-v1.schema.json').read_text()))
        self.input = request()
        self.input['board'].update(include_tracks=True, include_pads=True, include_zones=True, fuzzy_sigma_mm=0)

    def test_roundtrip_with_prescribed_air(self):
        self.input['board'].update(ambient_bottom_grid_c=[25, 30], convection_bottom_grid_w_m2k=[10, 20])
        self.request_validator.validate(self.input)
        result = run_board_thermal(design(), self.input)
        self.assertEqual(result['status'], 'completed', result)
        self.result_validator.validate(result)
        self.assertEqual(result, json.loads(json.dumps(result, allow_nan=False)))

    def test_uniform_compatibility(self):
        for key in ('x_edges_mm', 'y_edges_mm'):
            self.input['board'].pop(key)
        self.request_validator.validate(self.input)
        self.result_validator.validate(run_board_thermal(design(), self.input))

    def test_reject_incomplete_or_inapplicable_features(self):
        for update, remove in [({}, 'y_edges_mm'), ({'model': 'plate', 'conductivity_w_mk': 1}, None),
                               ({'include_copper': True}, None), ({'ambient_top_grid_c': [-274, 25]}, None),
                               ({'convection_top_grid_w_m2k': [-1, 10]}, None), ({'unexpected_grid': []}, None)]:
            candidate = copy.deepcopy(self.input)
            candidate['board'].update(update)
            if remove:
                candidate['board'].pop(remove)
            self.assertTrue(list(self.request_validator.iter_errors(candidate)), (update, remove))

    def test_length_and_order_are_semantic_checks(self):
        for update in ({'ambient_top_grid_c': [25]}, {'x_edges_mm': [0, 5, 3, 10]}):
            candidate = copy.deepcopy(self.input)
            candidate['board'].update(update)
            self.request_validator.validate(candidate)
            self.assertEqual(run_board_thermal(design(), candidate)['status'], 'blocked')

    def test_direct_heat_reports_no_package_temperature(self):
        self.input['components'] = []
        self.input['board_heat_sources'] = [{'id': 'board-U1', 'component_ref': 'U1', 'power_w': .1,
            'contact_mode': 'square', 'contact_size_mm': 10}]
        self.request_validator.validate(self.input)
        result = run_board_thermal(design(), self.input)
        self.assertEqual(result['status'], 'completed', result)
        self.result_validator.validate(result)
        self.assertIsNone(result['summary']['maximum_junction_temperature_c'])
        self.assertIsNone(result['board_heat_sources'][0]['junction_temperature_c'])
        invalid = copy.deepcopy(self.input)
        invalid['board_heat_sources'][0]['r_junction_case_k_w'] = 1
        self.assertTrue(list(self.request_validator.iter_errors(invalid)))
        from examples.sas_qualification.run_board_reference import export_fields
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            export_fields(result, output, 'direct')
            with (output / 'direct-components.csv').open(newline='') as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(exported[0]['junction_temperature_c'], '')
            self.assertEqual(exported[0]['temperature_status'], 'board_only_junction_unsolved')
            with (output / 'direct-fields.csv').open(newline='') as stream:
                fields = list(csv.DictReader(stream))
            self.assertEqual([float(row['x_mm']) for row in fields[:2]], [1.5, 6.5])


if __name__ == '__main__':
    unittest.main()
