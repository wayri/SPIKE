# SPDX-License-Identifier: Apache-2.0
"""Worker/schema provenance and independent physical finite-family enumeration."""
from copy import deepcopy
import hashlib
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
import numpy as np
from scipy.linalg import expm

from python.spike_core.service import handle
from examples.multi_aggressor_crosstalk.run_crosstalk import request

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def physical_trace(source):
    """KCL C*V'=I-G*V; KVL L*I'=Vs-R*I-V, no wave/fitted solver."""
    conductance = np.array([[.020, -.004, -.003], [-.004, .030, -.002], [-.003, -.002, .025]])
    ports = source['fit_request']['source']['port_names']
    terms = {term['port_name']: term for term in source['terminations']}
    n = len(ports)
    inv_c = np.diag([1/terms[p]['capacitance_f'] for p in ports])
    inv_l = np.diag([1/terms[p]['inductance_h'] for p in ports])
    r = np.diag([terms[p]['resistance_ohm'] for p in ports])
    generator = np.zeros((4*n, 4*n))
    generator[:n, :n] = -inv_c@conductance
    generator[:n, n:2*n] = inv_c
    generator[n:2*n, :n] = -inv_l
    generator[n:2*n, n:2*n] = -inv_l@r
    generator[n:2*n, 2*n:3*n] = inv_l
    generator[2*n:3*n, 3*n:] = np.eye(n)
    state = np.zeros(4*n)
    initial = source['initial_state']
    state[:n] = [initial['capacitor_voltage_v_by_port'][p] for p in ports]
    state[n:2*n] = [initial['inductor_current_a_by_port'][p] for p in ports]
    waves = [terms[p]['voltage_points'] for p in ports]
    times = sorted({0., *source['output_times_s'], *(pt['time_s'] for wave in waves for pt in wave)})
    values = {0.: float(state[0])}
    for left, right in zip(times, times[1:]):
        for j, wave in enumerate(waves):
            segment = min(sum(pt['time_s'] <= left for pt in wave)-1, len(wave)-2)
            a, b = wave[segment:segment+2]
            slope = (b['voltage_v']-a['voltage_v'])/(b['time_s']-a['time_s'])
            state[2*n+j] = a['voltage_v']+slope*(left-a['time_s'])
            state[3*n+j] = slope
        state = expm(generator*(right-left))@state
        values[right] = float(state[0])
    return [values[t] for t in source['output_times_s']]


class MultiAggressorContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'multi-aggressor-crosstalk-{kind}-v1.schema.json').read_text()))
                           for kind in ('request', 'result')]

    def test_worker_schema_identity_and_independent_physical_enumeration(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        response = handle({'method': 'run_multi_aggressor_crosstalk', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        result = response['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before)
        self.assertEqual(result['input_digest'], digest(raw))
        self.assertEqual(result['source_request'], raw['transient_request'])
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['aggressor_port_names'], ['clock', 'data'])
        self.assertEqual(result['diagnostics']['solution_count'], 5)
        bias = result['reference_voltage_v_by_port']
        traces = []
        for signs in product((-1, 1), repeat=2):
            source = deepcopy(raw['transient_request'])
            for term in source['terminations']:
                p = term['port_name']
                if p in bias:
                    sign = dict(zip(['clock', 'data'], signs))[p]
                    for pt in term['voltage_points']:
                        pt['voltage_v'] = bias[p]+sign*(pt['voltage_v']-bias[p])
            traces.append(physical_trace(source))
        for i, row in enumerate(result['envelope']):
            low, high = min(t[i] for t in traces), max(t[i] for t in traces)
            self.assertAlmostEqual(row['minimum_voltage_v'], low, delta=2e-10+1e-9*abs(low))
            self.assertAlmostEqual(row['maximum_voltage_v'], high, delta=2e-10+1e-9*abs(high))
            self.assertAlmostEqual(row['lower_margin_v'], low-raw['lower_limit_v'], delta=2e-10)
            self.assertAlmostEqual(row['upper_margin_v'], raw['upper_limit_v']-high, delta=2e-10)
        for key in ('worst_upper_pattern', 'worst_lower_pattern'):
            witness = result[key]; source = deepcopy(raw['transient_request'])
            for term in source['terminations']:
                p = term['port_name']
                if p in bias and witness['polarity_by_port'][p] == -1:
                    for pt in term['voltage_points']:
                        pt['voltage_v'] = bias[p]+bias[p]-pt['voltage_v']
            self.assertEqual(witness['verified_input_digest'], digest(source))
            np.testing.assert_allclose(witness['verified_victim_voltage_v'], physical_trace(source), atol=2e-10, rtol=1e-9)

    def test_worker_and_schema_reject_invalid_requests_without_partial_result(self):
        for mutation in ('extra', 'missing', 'victim', 'duplicate', 'unknown', 'bool_bias', 'limits', 'state'):
            raw = request()
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            elif mutation == 'missing': raw.pop('aggressors')
            elif mutation == 'victim': raw['aggressors'][0]['port_name'] = 'victim'
            elif mutation == 'duplicate': raw['aggressors'][1] = deepcopy(raw['aggressors'][0])
            elif mutation == 'unknown': raw['aggressors'][0]['port_name'] = 'absent'
            elif mutation == 'bool_bias': raw['aggressors'][0]['reference_voltage_v'] = True
            elif mutation == 'limits': raw['upper_limit_v'] = raw['lower_limit_v']
            else: raw['transient_request']['initial_state']['fit_request_digest'] = '0'*64
            with self.subTest(mutation=mutation):
                response = handle({'method': 'run_multi_aggressor_crosstalk', 'params': {'request': raw}})
                self.assertFalse(response['ok'], response)
                self.assertNotIn('result', response)
                if mutation in ('extra', 'missing', 'bool_bias'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_and_registered_contracts(self):
        process = subprocess.run([sys.executable, str(ROOT/'examples/multi_aggressor_crosstalk/run_crosstalk.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.validators[1].validate(json.loads(process.stdout))
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text())['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/multi-aggressor-crosstalk-{kind}/v1'], f'multi-aggressor-crosstalk-{kind}-v1.schema.json')
