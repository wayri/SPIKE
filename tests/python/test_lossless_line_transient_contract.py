# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schemas and an independently specified round-trip series."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator

from python.spike_core.service import handle
from examples.lossless_line_transient.run_line import request

ROOT = Path(__file__).resolve().parents[2]


class LosslessLineContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'lossless-line-transient-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_against_independent_geometric_reflection_series(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        response = handle({'method': 'run_lossless_line_transient', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        result = response['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before)
        self.assertEqual(result['source_request'], raw)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        self.assertFalse(result['production_qualified'])
        self.assertAlmostEqual(result['characteristic_impedance_ohm'], 50., delta=1e-12)
        self.assertAlmostEqual(result['one_way_delay_s'], 25e-9, delta=1e-22)
        self.assertAlmostEqual(result['propagation_speed_m_per_s'], 2e8, delta=1e-6)
        self.assertAlmostEqual(result['reflection_coefficient_by_boundary']['left'], -1/3, delta=1e-14)
        self.assertAlmostEqual(result['reflection_coefficient_by_boundary']['right'], 1/3, delta=1e-14)

        def source(t):
            return max(0., min(1., t/10e-9))

        def forward(t):
            # Independently derived left-launched geometric round trips:
            # launch=2/3, one round trip multiplier=(-1/3)*(+1/3).
            return (2/3)*sum((-1/9)**m*source(t-2*m*25e-9) for m in range(16))

        for row in result['points']:
            expected_probes = []
            self.assertEqual([p['id'] for p in row['probe_values']], ['left', 'midpoint', 'right'])
            for actual, probe in zip(row['probe_values'], raw['probes']):
                t, q = row['time_s'], probe['fractional_position']
                a, b = forward(t-q*25e-9), forward(t-(2-q)*25e-9)/3
                v, i = a+b, (a-b)/50.
                for key, expected in [('forward_voltage_v', a), ('backward_voltage_v', b), ('voltage_v', v), ('current_left_to_right_a', i)]:
                    self.assertAlmostEqual(actual[key], expected, delta=2e-10+1e-9*abs(expected))
                self.assertAlmostEqual(actual['transported_power_w'], v*i, delta=2e-12+1e-9*abs(v*i))
                energy = .5*100e-12*v*v+.5*250e-9*i*i
                self.assertAlmostEqual(actual['energy_density_j_per_m'], energy, delta=1e-20+1e-9*energy)
                expected_probes.append((v, i))
            for side, (v, i), sign, resistance in [('left', expected_probes[0], 1, 25.), ('right', expected_probes[-1], -1, 100.)]:
                terminal = row['boundary_values'][side]
                self.assertAlmostEqual(terminal['voltage_v'], v, delta=2e-10)
                self.assertAlmostEqual(terminal['current_into_line_a'], sign*i, delta=2e-10)
                self.assertAlmostEqual(terminal['resistor_power_w'], resistance*i*i, delta=2e-12)
                self.assertAlmostEqual(terminal['source_voltage_v']-v-resistance*sign*i, 0., delta=2e-10)
                self.assertAlmostEqual(terminal['kvl_residual_v'], 0., delta=2e-10)

    def test_worker_and_schema_reject_invalid_physics_contracts(self):
        for mutation in ('extra', 'missing', 'length', 'bool_l', 'negative_c', 'negative_r', 'history', 'position', 'duplicate', 'outside'):
            raw = request()
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            elif mutation == 'missing': raw.pop('left_boundary')
            elif mutation == 'length': raw['length_m'] = 0.
            elif mutation == 'bool_l': raw['inductance_h_per_m'] = True
            elif mutation == 'negative_c': raw['capacitance_f_per_m'] = -1.
            elif mutation == 'negative_r': raw['right_boundary']['resistance_ohm'] = -1.
            elif mutation == 'history': raw['left_boundary']['voltage_points'][0]['voltage_v'] = 1.
            elif mutation == 'position': raw['probes'][0]['fractional_position'] = 1.1
            elif mutation == 'duplicate': raw['probes'][1]['id'] = raw['probes'][0]['id']
            else: raw['output_times_s'][-1] = 1.
            with self.subTest(mutation=mutation):
                response = handle({'method': 'run_lossless_line_transient', 'params': {'request': raw}})
                self.assertFalse(response['ok'], response)
                self.assertNotIn('result', response)
                if mutation not in ('duplicate', 'outside'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_executes_and_contracts_are_registered(self):
        process = subprocess.run([sys.executable, str(ROOT/'examples/lossless_line_transient/run_line.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.validators[1].validate(json.loads(process.stdout))
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/lossless-line-transient-{kind}/v1'], f'lossless-line-transient-{kind}-v1.schema.json')
