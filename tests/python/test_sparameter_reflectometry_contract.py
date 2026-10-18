# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema and independent analytic loaded-RLC reference."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator

from python.spike_core.service import handle
from examples.network_reflectometry.run_reflectometry import request

ROOT = Path(__file__).resolve().parents[2]


class ReflectometryContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'network-reflectometry-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_against_analytic_reflection_impedance_and_network_power(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        response = handle({'method': 'run_network_reflectometry', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        result = response['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        self.assertEqual(result['transient_result']['initial_state'], raw['transient_request']['initial_state'])
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['diagnostics']['solution_count'], 1)
        alpha = (20.+1/(75.*.004))/2
        omega = math.sqrt((1+20./75.)/.004-alpha*alpha)
        steady = 2./(1+20./75.)
        distinguished_current = False
        for row, original in zip(result['points'], result['transient_result']['points']):
            t = row['time_s']; decay = math.exp(-alpha*t)
            voltage = steady*(1-decay*(math.cos(omega*t)+alpha/omega*math.sin(omega*t)))
            derivative = steady*decay*(omega+alpha*alpha/omega)*math.sin(omega*t)
            network_current = voltage/75.
            source_current = network_current+.004*derivative
            self.assertAlmostEqual(row['network_voltage_v'], voltage, delta=2e-10+1e-9*abs(voltage))
            self.assertAlmostEqual(row['network_current_a'], network_current, delta=2e-10+1e-9*abs(network_current))
            self.assertAlmostEqual(row['incident_voltage_v'], .5*(voltage+50*network_current), delta=2e-10)
            self.assertAlmostEqual(row['reflected_voltage_v'], .5*(voltage-50*network_current), delta=2e-10)
            self.assertAlmostEqual(row['instantaneous_network_power_w'], voltage*voltage/75., delta=2e-10)
            self.assertAlmostEqual(original['source_current_a_by_port']['receiver'], source_current, delta=2e-10)
            distinguished_current |= abs(source_current-network_current) > .001
            if t == 0:
                self.assertEqual(row['reflection_status'], 'incident_below_floor')
                self.assertEqual(row['impedance_status'], 'incident_below_floor')
                self.assertIsNone(row['reflection_coefficient'])
                self.assertIsNone(row['apparent_impedance_ohm'])
            else:
                self.assertEqual(row['reflection_status'], 'resolved')
                self.assertEqual(row['impedance_status'], 'resolved')
                self.assertAlmostEqual(row['reflection_coefficient'], .2, delta=2e-10)
                self.assertAlmostEqual(row['apparent_impedance_ohm'], 75., delta=2e-8)
        self.assertTrue(distinguished_current)
        for status, value in [('reflection_status', 'reflection_coefficient'), ('impedance_status', 'apparent_impedance_ohm')]:
            corrupted = deepcopy(result); corrupted['points'][0][value] = 0.
            self.assertTrue(list(self.validators[1].iter_errors(corrupted)), status)
            corrupted = deepcopy(result); corrupted['points'][1][value] = None
            self.assertTrue(list(self.validators[1].iter_errors(corrupted)), status)

        corrupted = deepcopy(result)
        corrupted['points'][0].update(impedance_status='resolved', apparent_impedance_ohm=75.)
        self.assertTrue(list(self.validators[1].iter_errors(corrupted)))
        corrupted = deepcopy(result)
        corrupted['points'][1].update(impedance_status='incident_below_floor', apparent_impedance_ohm=None)
        self.assertTrue(list(self.validators[1].iter_errors(corrupted)))

    def test_worker_and_schema_fail_closed_on_invalid_requests(self):
        for mutation in ('extra', 'missing', 'probe', 'bool_floor', 'zero_floor', 'negative_current', 'infinite', 'state'):
            raw = request()
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            elif mutation == 'missing': raw.pop('probe_port')
            elif mutation == 'probe': raw['probe_port'] = 'absent'
            elif mutation == 'bool_floor': raw['minimum_incident_voltage_v'] = True
            elif mutation == 'zero_floor': raw['minimum_incident_voltage_v'] = 0.
            elif mutation == 'negative_current': raw['minimum_current_a'] = -1.
            elif mutation == 'infinite': raw['minimum_current_a'] = float('inf')
            else: raw['transient_request']['initial_state']['fit_request_digest'] = '0'*64
            with self.subTest(mutation=mutation):
                response = handle({'method': 'run_network_reflectometry', 'params': {'request': raw}})
                self.assertFalse(response['ok'], response)
                self.assertNotIn('result', response)
                if mutation not in ('probe', 'infinite', 'state'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_executes_and_contracts_are_registered(self):
        process = subprocess.run([sys.executable, str(ROOT/'examples/network_reflectometry/run_reflectometry.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.validators[1].validate(json.loads(process.stdout))
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/network-reflectometry-{kind}/v1'], f'network-reflectometry-{kind}-v1.schema.json')
