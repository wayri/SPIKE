# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema and independent attenuated round-trip series."""
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
from examples.distortionless_line_transient.run_line import request

ROOT = Path(__file__).resolve().parents[2]


class DistortionlessLineContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'distortionless-line-transient-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_against_independent_attenuated_echo_and_loss_reference(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        response = handle({'method': 'run_distortionless_line_transient', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        result = response['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before); self.assertEqual(result['source_request'], raw)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        self.assertFalse(result['production_qualified'])
        self.assertAlmostEqual(result['characteristic_impedance_ohm'], 50., delta=1e-12)
        self.assertAlmostEqual(result['resistance_ohm_per_m'], 2.5, delta=1e-13)
        self.assertAlmostEqual(result['conductance_s_per_m'], .001, delta=1e-15)
        self.assertAlmostEqual(result['attenuation_neper_per_m'], .05, delta=1e-14)
        self.assertAlmostEqual(result['one_way_voltage_attenuation'], math.exp(-.25), delta=1e-14)

        def source(t): return max(0., min(1., t/10e-9))

        def launch(t):
            # A round trip has boundary factor -1/9 and flight factor exp(-.5).
            return (2/3)*sum((-math.exp(-.5)/9)**m*source(t-2*m*25e-9) for m in range(16))

        for row in result['points']:
            expected_probes = []
            self.assertEqual([p['id'] for p in row['probe_values']], ['left', 'midpoint', 'right'])
            for actual, probe in zip(row['probe_values'], raw['line_request']['probes']):
                t, q = row['time_s'], probe['fractional_position']
                f = math.exp(-.25*q)*launch(t-q*25e-9)
                b = math.exp(-.25*(2-q))*launch(t-(2-q)*25e-9)/3
                v, i = f+b, (f-b)/50.
                for field, expected in [('forward_voltage_v', f), ('backward_voltage_v', b), ('voltage_v', v), ('current_left_to_right_a', i)]:
                    self.assertAlmostEqual(actual[field], expected, delta=2e-10+1e-9*abs(expected))
                self.assertAlmostEqual(actual['transported_power_w'], v*i, delta=2e-12+1e-9*abs(v*i))
                energy = .5*100e-12*v*v+.5*250e-9*i*i
                conductor, dielectric = 2.5*i*i, .001*v*v
                self.assertAlmostEqual(actual['energy_density_j_per_m'], energy, delta=1e-20+1e-9*energy)
                for field, expected in [('conductor_loss_w_per_m', conductor), ('dielectric_loss_w_per_m', dielectric), ('total_loss_w_per_m', conductor+dielectric)]:
                    self.assertAlmostEqual(actual[field], expected, delta=2e-12+1e-9*expected)
                self.assertAlmostEqual(actual['total_loss_w_per_m'], 2e7*energy, delta=2e-12+1e-9*(2e7*energy))
                expected_probes.append((v, i))
            for side, (v, i), sign, resistance in [('left', expected_probes[0], 1, 25.), ('right', expected_probes[-1], -1, 100.)]:
                terminal = row['boundary_values'][side]
                self.assertAlmostEqual(terminal['voltage_v'], v, delta=2e-10)
                self.assertAlmostEqual(terminal['current_into_line_a'], sign*i, delta=2e-10)
                self.assertAlmostEqual(terminal['resistor_power_w'], resistance*i*i, delta=2e-12)
                self.assertAlmostEqual(terminal['source_voltage_v']-v-resistance*sign*i, 0., delta=2e-10)

    def test_worker_and_schema_reject_invalid_loss_contracts(self):
        for mutation in ('extra', 'missing', 'negative', 'boolean', 'infinite', 'independent_r', 'nonzero_start'):
            raw = request()
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            elif mutation == 'missing': raw.pop('attenuation_rate_per_s')
            elif mutation == 'negative': raw['attenuation_rate_per_s'] = -1.
            elif mutation == 'boolean': raw['attenuation_rate_per_s'] = True
            elif mutation == 'infinite': raw['attenuation_rate_per_s'] = float('inf')
            elif mutation == 'independent_r': raw['resistance_ohm_per_m'] = 3.
            else: raw['line_request']['left_boundary']['voltage_points'][0]['voltage_v'] = 1.
            with self.subTest(mutation=mutation):
                response = handle({'method': 'run_distortionless_line_transient', 'params': {'request': raw}})
                self.assertFalse(response['ok'], response); self.assertNotIn('result', response)
                if mutation != 'infinite': self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_executes_and_contracts_are_registered(self):
        process = subprocess.run([sys.executable, str(ROOT/'examples/distortionless_line_transient/run_line.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.validators[1].validate(json.loads(process.stdout))
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/distortionless-line-transient-{kind}/v1'], f'distortionless-line-transient-{kind}-v1.schema.json')
