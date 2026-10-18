# SPDX-License-Identifier: Apache-2.0
"""Real worker/schema checks for an original supplied capacitor corner study."""
import copy
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT = Path(__file__).resolve().parents[2]


def request():
    provenance = {'kind': 'supplied', 'source_id': 'original-corner-fixture'}
    return {
        'contract': 'spike/pdn-decap-corners-request/v1',
        'base_request': {
            'contract': 'spike/pdn-network-request/v1', 'reference': 'GND',
            'nodes': ['rail'], 'elements': [
                {'id': 'source', 'type': 'resistor', 'positive': 'rail', 'negative': 'GND',
                 'resistance_ohm': 1., 'provenance': provenance}],
            'ports': [{'id': 'load', 'mode': 'single', 'positive': 'rail', 'negative': 'GND'}],
            'frequencies_hz': [1000., 10000., 100000.], 'load_transient': None},
        'corners': [{'id': 'nominal', 'bias_voltage_v': 1., 'temperature_k': 298.15},
                    {'id': 'hot-biased', 'bias_voltage_v': 3.3, 'temperature_k': 358.15}],
        'capacitors': [{'id': 'C1', 'positive': 'rail', 'negative': 'GND',
                        'provenance': provenance, 'corners': [
                            {'corner_id': 'nominal', 'capacitance_f': 10e-6, 'esr_ohm': .02, 'esl_h': 1e-9},
                            {'corner_id': 'hot-biased', 'capacitance_f': 4e-6, 'esr_ohm': .04, 'esl_h': 1.2e-9}]}],
        'target_impedance_ohm_by_port': {'load': .5}}


class DecapCornerContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT / 'schemas' / filename).read_text()))
                           for filename in ('pdn-decap-corners-request-v1.schema.json',
                                            'pdn-decap-corners-result-v1.schema.json')]

    def test_actual_worker_schema_and_failed_target_retention(self):
        req = request()
        before = copy.deepcopy(req)
        self.validators[0].validate(req)
        response = handle({'method': 'run_pdn_decap_corners', 'params': {'request': req}})
        self.assertTrue(response['ok'], response)
        result = response['result']
        self.validators[1].validate(result)
        self.assertEqual(req, before)
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['meets_target'])
        self.assertEqual(result['worst_case']['corner_id'], 'hot-biased')
        self.assertEqual(len(result['corners']), 2)
        self.assertGreater(result['worst_case']['target_ratio'], 1.)
        self.assertEqual(result['corners'][0]['element_mapping'][0]['provenance'],
                         req['capacitors'][0]['provenance'])

    def test_actual_worker_rejects_incomplete_corner_and_unknown_fields(self):
        for mutation in ('missing', 'unknown', 'boolean', 'targets'):
            req = request()
            if mutation == 'missing': req['capacitors'][0]['corners'].pop()
            elif mutation == 'unknown': req['extra'] = True
            elif mutation == 'boolean': req['corners'][0]['temperature_k'] = True
            else: req['target_impedance_ohm_by_port'] = {'elsewhere': .5}
            response = handle({'method': 'run_pdn_decap_corners', 'params': {'request': req}})
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'], response)
                self.assertNotIn('result', response)
        self.assertTrue(list(self.validators[0].iter_errors(req | {'extra': 1})))

    def test_documented_example_matches_independent_parallel_impedance(self):
        from examples.pdn_decap_corners.run_corners import make_request
        req = make_request()
        self.validators[0].validate(req)
        response = handle({'method': 'run_pdn_decap_corners', 'params': {'request': req}})
        self.assertTrue(response['ok'], response)
        self.validators[1].validate(response['result'])
        for index, corner in enumerate(response['result']['corners']):
            supplied = req['capacitors'][0]['corners'][index]
            for sample in corner['samples']:
                w = 2 * math.pi * sample['frequency_hz']
                source_z = .1 + 1j * w * 10e-9
                capacitor_z = supplied['esr_ohm'] + 1j * (
                    w * supplied['esl_h'] - 1 / (w * supplied['capacitance_f']))
                expected = abs(source_z * capacitor_z / (source_z + capacitor_z))
                self.assertAlmostEqual(sample['impedance_magnitude_ohm_by_port']['load'],
                                       expected, delta=2e-12)


if __name__ == '__main__':
    unittest.main()
