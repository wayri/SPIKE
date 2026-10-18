# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema/example checks against an independent loaded RLC formula."""
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
from examples.rlc_network_transient.run_loaded_rlc import request

ROOT = Path(__file__).resolve().parents[2]


class RlcContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlc-network-transient-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_loaded_rlc_state_power_and_original_provenance(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        out = handle({'method': 'run_rlc_network_transient', 'params': {'request': raw}})
        self.assertTrue(out['ok'], out); result = out['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before); self.assertFalse(result['production_qualified'])
        self.assertEqual(result['fit_result']['source']['network'], raw['fit_request']['source'])
        self.assertEqual(result['terminations'], raw['terminations'])
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, allow_nan=False, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        # LC V''+(RC+L/Rload)V'+(1+R/Rload)V=Vs; V(0)=V'(0)=0.
        alpha = (20.+1/(75.*.004))/2
        omega2 = (1+20./75.)/.004; omega = math.sqrt(omega2-alpha*alpha)
        steady = 2/(1+20./75.)
        for row in result['points']:
            t = row['time_s']; decay = math.exp(-alpha*t)
            voltage = steady*(1-decay*(math.cos(omega*t)+alpha/omega*math.sin(omega*t)))
            derivative = steady*omega2/omega*decay*math.sin(omega*t)
            network_i = voltage/75.; source_i = network_i+.004*derivative
            current_derivative = 2-20*source_i-voltage
            self.assertAlmostEqual(row['port_voltage_v_by_port']['receiver'], voltage, delta=2e-10)
            self.assertAlmostEqual(row['port_current_a_by_port']['receiver'], network_i, delta=2e-10)
            self.assertAlmostEqual(row['source_current_a_by_port']['receiver'], source_i, delta=2e-10)
            self.assertAlmostEqual(row['inductor_current_a_by_port']['receiver'], source_i, delta=2e-10)
            self.assertAlmostEqual(row['capacitor_voltage_v_by_port']['receiver'], voltage, delta=2e-10)
            self.assertAlmostEqual(row['capacitor_voltage_derivative_v_per_s_by_port']['receiver'], derivative, delta=2e-8)
            self.assertAlmostEqual(row['inductor_current_derivative_a_per_s_by_port']['receiver'], current_derivative, delta=2e-8)
            self.assertAlmostEqual(row['boundary_residual_v_by_port']['receiver'], 0., delta=2e-10)
            self.assertAlmostEqual(row['boundary_residual_a_by_port']['receiver'], 0., delta=2e-10)
            power = row['termination_resistor_power_w_by_port']['receiver']
            self.assertAlmostEqual(power, 20*source_i**2, delta=2e-11)
            self.assertAlmostEqual(row['inductor_energy_j_by_port']['receiver'], .5*source_i**2, delta=2e-11)
            self.assertAlmostEqual(row['capacitor_energy_j_by_port']['receiver'], .002*voltage**2, delta=2e-11)
            self.assertAlmostEqual(2*source_i-voltage*network_i-power-source_i*current_derivative-.004*voltage*derivative, 0., delta=2e-10)

    def test_worker_and_schema_fail_closed_on_unsupported_boundaries(self):
        for mutation in ('negative', 'boolean', 'infinite', 'no_c', 'no_l', 'ideal_c', 'missing', 'unknown', 'port'):
            raw = request(); term = raw['terminations'][0]
            if mutation == 'negative': term['capacitance_f'] = -1.
            if mutation == 'boolean': term['inductance_h'] = True
            if mutation == 'infinite': term['inductance_h'] = float('inf')
            if mutation == 'no_c': term['capacitance_f'] = 0.
            if mutation == 'no_l': term['inductance_h'] = 0.
            if mutation == 'ideal_c': term.update(inductance_h=0., resistance_ohm=0.)
            if mutation == 'missing': term.pop('inductance_h')
            if mutation == 'unknown': term['temperature_k'] = 300.
            if mutation == 'port': term['port_name'] = 'other'
            out = handle({'method': 'run_rlc_network_transient', 'params': {'request': raw}})
            with self.subTest(mutation=mutation):
                self.assertFalse(out['ok'], out); self.assertNotIn('result', out)
                if mutation not in ('infinite', 'port'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))
        self.assertTrue(list(self.validators[0].iter_errors(request() | {'extra': 1})))

    def test_example_runs_and_public_contracts_are_registered(self):
        out = subprocess.run([sys.executable, str(ROOT/'examples/rlc_network_transient/run_loaded_rlc.py')],
                             cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)['contract'], 'spike/rlc-network-transient-result/v1')
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/rlc-network-transient-{kind}/v1'], f'rlc-network-transient-{kind}-v1.schema.json')
