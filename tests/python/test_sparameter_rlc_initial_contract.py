# SPDX-License-Identifier: Apache-2.0
"""Worker/public state schemas and analytic charged/energized decay reference."""
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
from examples.rlc_network_initial.run_free_decay import request

ROOT = Path(__file__).resolve().parents[2]


class RlcInitialContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlc-network-transient-{kind}-v2.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]
        self.state = Draft202012Validator(json.loads((ROOT/'schemas/rlc-initial-state-v1.schema.json').read_text(encoding='utf-8')))

    def test_worker_free_decay_initial_energy_and_provenance(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        out = handle({'method': 'run_initialized_rlc_network_transient', 'params': {'request': raw}})
        self.assertTrue(out['ok'], out); result = out['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before); self.assertEqual(result['initial_state'], raw['initial_state'])
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['fit_result']['source']['network'], raw['fit_request']['source'])
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, allow_nan=False, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        self.state.validate(result['restart_state'])
        self.assertEqual(result['restart_state']['fit_request_digest'], raw['initial_state']['fit_request_digest'])
        alpha = (20.+1/(75.*.004))/2
        omega = math.sqrt((1+20./75.)/.004-alpha*alpha)
        a = 1.25; b = ((-.02-a/75.)/.004+alpha*a)/omega
        for row in result['points']:
            t = row['time_s']; c = math.cos(omega*t); s = math.sin(omega*t); decay = math.exp(-alpha*t)
            voltage = decay*(a*c+b*s)
            derivative = decay*((b*omega-alpha*a)*c-(a*omega+alpha*b)*s)
            source_i = .004*derivative+voltage/75.
            self.assertAlmostEqual(row['port_voltage_v_by_port']['receiver'], voltage, delta=2e-10)
            self.assertAlmostEqual(row['source_current_a_by_port']['receiver'], source_i, delta=2e-10)
            self.assertAlmostEqual(row['port_current_a_by_port']['receiver'], voltage/75., delta=2e-10)
            self.assertAlmostEqual(row['capacitor_voltage_derivative_v_per_s_by_port']['receiver'], derivative, delta=2e-8)
            self.assertAlmostEqual(row['inductor_current_derivative_a_per_s_by_port']['receiver'], -20*source_i-voltage, delta=2e-8)
        first = result['points'][0]
        self.assertAlmostEqual(first['capacitor_energy_j_by_port']['receiver']+first['inductor_energy_j_by_port']['receiver'], .003325, delta=1e-12)
        self.assertEqual(result['restart_state']['fit_state_sqrt_w'], result['final_state_sqrt_w'])
        self.assertEqual(result['restart_state']['inductor_current_a_by_port'], result['final_inductor_current_a_by_port'])
        self.assertEqual(result['restart_state']['capacitor_voltage_v_by_port'], result['final_capacitor_voltage_v_by_port'])

    def test_worker_and_schema_reject_invalid_initial_state_without_success(self):
        for mutation in ('digest', 'missing', 'unknown', 'shape', 'ports', 'boolean', 'nonfinite', 'contract'):
            raw = request(); state = raw['initial_state']
            if mutation == 'digest': state['fit_request_digest'] = '0'*64
            if mutation == 'missing': state.pop('fit_state_sqrt_w')
            if mutation == 'unknown': state['time_s'] = 0.
            if mutation == 'shape': state['fit_state_sqrt_w'] = []
            if mutation == 'ports': state['capacitor_voltage_v_by_port'] = {'wrong': 1.}
            if mutation == 'boolean': state['inductor_current_a_by_port']['receiver'] = True
            if mutation == 'nonfinite': state['capacitor_voltage_v_by_port']['receiver'] = float('inf')
            if mutation == 'contract': state['contract'] = 'spike/rlc-initial-state/v9'
            out = handle({'method': 'run_initialized_rlc_network_transient', 'params': {'request': raw}})
            with self.subTest(mutation=mutation):
                self.assertFalse(out['ok'], out); self.assertNotIn('result', out)
                if mutation not in ('digest', 'ports', 'nonfinite'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))
        self.assertTrue(list(self.validators[0].iter_errors(request() | {'extra': 1})))

    def test_example_executes_and_all_contracts_registered(self):
        out = subprocess.run([sys.executable, str(ROOT/'examples/rlc_network_initial/run_free_decay.py')],
                             cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)['contract'], 'spike/rlc-network-transient-result/v2')
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/rlc-network-transient-{kind}/v2'], f'rlc-network-transient-{kind}-v2.schema.json')
        self.assertEqual(catalog['spike/rlc-initial-state/v1'], 'rlc-initial-state-v1.schema.json')
