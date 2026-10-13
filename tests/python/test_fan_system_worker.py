# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fan operating-point example, schema, and exact JSON worker transport."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import jsonschema

from examples.assembly_field.run_fan_system import run_examples, setup_fan_system
from python.spike_core.fan_system_operating_point import solve_fan_system_operating_point

ROOT = Path(__file__).resolve().parents[2]
METHOD = 'solve_fan_system_operating_point'


class FanSystemWorkerTests(unittest.TestCase):
    def run_worker(self, requests):
        process = subprocess.run([sys.executable, '-m', 'python.spike_core.service'],
                                 cwd=ROOT, input='\n'.join(json.dumps(r, allow_nan=False) for r in requests) + '\n',
                                 text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        self.assertEqual(len(responses), len(requests), process.stdout)
        return responses

    def test_example_roots_heat_topology_and_fan_loss(self):
        normal, single, failed = run_examples()
        self.assertEqual(normal['model_status'], 'approximate')
        self.assertTrue(normal['not_resolved_CFD'])
        self.assertFalse(normal['board_convection_inferred'])
        self.assertGreater(normal['operating_point']['total_flow_m3_s'], single['operating_point']['total_flow_m3_s'])
        self.assertEqual(failed['operating_point']['total_flow_m3_s'], 0)
        self.assertEqual(normal['air_summary']['total_heat_w'], 20)
        self.assertTrue(normal['limits']['passed'])
        self.assertFalse(single['limits']['passed'])
        self.assertFalse(failed['limits']['passed'])
        for case in (normal, single):
            passages = case['passages']
            self.assertEqual(len(passages), 4)
            self.assertAlmostEqual(passages[0]['flow_m3_s'] / passages[1]['flow_m3_s'], 2)
            for passage in passages:
                self.assertEqual([s['site_id'] for s in passage['stages']], ['Q129', 'Q10'])
                self.assertEqual(passage['stages'][0]['inlet_temperature_k'], 300)
                expected_rise = 5 / (1.2 * passage['flow_m3_s'] * 1000)
                self.assertAlmostEqual(passage['outlet_temperature_k'], 300 + expected_rise, places=10)
                self.assertAlmostEqual(passage['energy_residual_w'], 0, places=8)

    def test_schema_accepts_examples_and_rejects_inferred_extra_data(self):
        schema = json.loads((ROOT / 'schemas/fan-system-operating-point-request-v1.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        for active in (2, 1, 0):
            validator.validate(setup_fan_system(active))
        bad = setup_fan_system()
        bad['system']['passages'][0]['flow_fraction'] = .25
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad)
        bad = setup_fan_system()
        bad['system']['passages'][0]['heat_loads'][0]['heat_w'] = None
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad)

    def test_worker_exact_round_trip_all_fan_states(self):
        requests = [{'id': f'fan-{active}', 'method': METHOD,
                     'params': {'request': setup_fan_system(active)}} for active in (2, 1, 0)]
        responses = self.run_worker(requests)
        for request, response in zip(requests, responses):
            self.assertTrue(response['ok'], response)
            self.assertEqual(response['id'], request['id'])
            self.assertEqual(response['meta']['method'], METHOD)
            self.assertGreaterEqual(response['meta']['duration_ms'], 0)
            self.assertEqual(response['result'], solve_fan_system_operating_point(request['params']['request']))

    def test_worker_rejects_overrides_digest_tampering_unknown_heat_and_recovers(self):
        overrides = {'request': setup_fan_system(), 'solver_executable': 'ignored-must-not-execute'}
        tampered = setup_fan_system()
        tampered['fan']['curve'][0]['pressure_pa'] = 101
        unknown = setup_fan_system()
        unknown['system']['passages'][0]['heat_loads'][0]['heat_w'] = None
        cases = [('overrides', overrides), ('digest', {'request': tampered}), ('unknown', {'request': unknown})]
        requests = [{'id': case, 'method': METHOD, 'params': params} for case, params in cases]
        requests.append({'id': 'recovered', 'method': METHOD, 'params': {'request': setup_fan_system()}})
        responses = self.run_worker(requests)
        for request, response in zip(requests[:-1], responses[:-1]):
            self.assertFalse(response['ok'])
            self.assertEqual(response['id'], request['id'])
            self.assertEqual(response['error_code'], 'SPIKE-BE-IPC-E-0001')
        self.assertTrue(responses[-1]['ok'], responses[-1])

    def test_example_runs_standalone_without_writing_artifacts(self):
        process = subprocess.run([sys.executable, str(ROOT / 'examples/assembly_field/run_fan_system.py')],
                                 cwd=ROOT, text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), run_examples())


if __name__ == '__main__':
    unittest.main()
