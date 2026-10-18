# SPDX-License-Identifier: Apache-2.0
"""Worker, schemas, provenance and independently enumerated hand-shifted sources."""
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
import numpy as np

from python.spike_core.service import handle
from examples.crosstalk_timing_corners.run_timing import request
from tests.python.test_sparameter_multi_aggressor_contract import digest, physical_trace

ROOT = Path(__file__).resolve().parents[2]


class CrosstalkTimingContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'crosstalk-timing-corners-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_schemas_and_hand_shifted_physical_corner_enumeration(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        response = handle({'method': 'run_crosstalk_timing_corners', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        result = response['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before)
        self.assertEqual(result['input_digest'], digest(raw))
        self.assertEqual(result['source_crosstalk_request'], raw['crosstalk_request'])
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['diagnostics']['solution_count'], 15)
        # These tables are hand-translated from the original source knots,
        # independent of the implementation's shift/interpolation helpers.
        expected_shift = {
            'clock-late': ('clock', [(0., 0.), (.1, 0.), (.2, 2.), (.5, 2.), (.8, 0.), (1., 0.)]),
            'data-early': ('data', [(0., 1.), (.3, 0.), (.6, 1.), (.8, 1.), (1., 1.)])}
        all_traces = []
        for corner in result['corners']:
            actual = corner['result']
            self.assertEqual(actual['input_digest'], digest({**raw['crosstalk_request'], 'transient_request': actual['source_request']}))
            source = deepcopy(raw['crosstalk_request']['transient_request'])
            if corner['id'] in expected_shift:
                port, table = expected_shift[corner['id']]
                for term in source['terminations']:
                    if term['port_name'] == port:
                        term['voltage_points'] = [{'time_s': t, 'voltage_v': v} for t, v in table]
            else:
                self.assertEqual(actual['source_request'], source)
            for term, shifted in zip(source['terminations'], actual['source_request']['terminations']):
                np.testing.assert_allclose([[p['time_s'], p['voltage_v']] for p in shifted['voltage_points']],
                                           [[p['time_s'], p['voltage_v']] for p in term['voltage_points']], atol=2e-15, rtol=2e-15)
            self.assertEqual(actual['source_request']['initial_state'], source['initial_state'])
            self.assertEqual(actual['source_request']['output_times_s'], source['output_times_s'])
            traces = []
            for signs in product((-1, 1), repeat=2):
                pattern = deepcopy(source)
                for term in pattern['terminations']:
                    port = term['port_name']
                    if port in actual['reference_voltage_v_by_port']:
                        bias = actual['reference_voltage_v_by_port'][port]
                        sign = dict(zip(['clock', 'data'], signs))[port]
                        for point in term['voltage_points']:
                            point['voltage_v'] = bias+sign*(point['voltage_v']-bias)
                traces.append(physical_trace(pattern))
            all_traces.extend(traces)
            np.testing.assert_allclose([e['minimum_voltage_v'] for e in actual['envelope']], np.min(traces, axis=0), atol=2e-10, rtol=1e-9)
            np.testing.assert_allclose([e['maximum_voltage_v'] for e in actual['envelope']], np.max(traces, axis=0), atol=2e-10, rtol=1e-9)
        np.testing.assert_allclose([e['minimum_voltage_v'] for e in result['envelope']], np.min(all_traces, axis=0), atol=2e-10, rtol=1e-9)
        np.testing.assert_allclose([e['maximum_voltage_v'] for e in result['envelope']], np.max(all_traces, axis=0), atol=2e-10, rtol=1e-9)
        for key in ('worst_upper_pattern', 'worst_lower_pattern'):
            winner = result[key]
            child = next(c['result'] for c in result['corners'] if c['id'] == winner['corner_id'])
            self.assertEqual({k: v for k, v in winner.items() if k != 'corner_id'}, child[key])

    def test_worker_and_schema_reject_invalid_corner_contracts(self):
        for mutation in ('extra', 'missing', 'empty', 'duplicate', 'absent_port', 'extra_port', 'bool_delay', 'long_id'):
            raw = request()
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            elif mutation == 'missing': raw.pop('timing_corners')
            elif mutation == 'empty': raw['timing_corners'] = []
            elif mutation == 'duplicate': raw['timing_corners'][1]['id'] = 'nominal'
            elif mutation == 'absent_port': raw['timing_corners'][0]['delay_s_by_port'].pop('data')
            elif mutation == 'extra_port': raw['timing_corners'][0]['delay_s_by_port']['victim'] = 0.
            elif mutation == 'bool_delay': raw['timing_corners'][0]['delay_s_by_port']['data'] = True
            else: raw['timing_corners'][0]['id'] = 'x'*129
            with self.subTest(mutation=mutation):
                response = handle({'method': 'run_crosstalk_timing_corners', 'params': {'request': raw}})
                self.assertFalse(response['ok'], response)
                self.assertNotIn('result', response)
                if mutation in ('extra', 'missing', 'empty', 'bool_delay', 'long_id'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_and_registered_contracts(self):
        process = subprocess.run([sys.executable, str(ROOT/'examples/crosstalk_timing_corners/run_timing.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.validators[1].validate(json.loads(process.stdout))
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/crosstalk-timing-corners-{kind}/v1'], f'crosstalk-timing-corners-{kind}-v1.schema.json')
