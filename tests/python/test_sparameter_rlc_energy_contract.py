# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema/example and independent scalar heat/work quadrature."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
from scipy.integrate import quad

from python.spike_core.service import handle
from examples.rlc_energy_ledger.run_energy import request

ROOT = Path(__file__).resolve().parents[2]


class RlcEnergyContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlc-energy-ledger-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                           for kind in ('request', 'result')]

    def test_worker_integrated_energy_against_analytic_scalar_reference(self):
        raw = request(); before = deepcopy(raw); self.validators[0].validate(raw)
        out = handle({'method': 'run_rlc_energy_ledger', 'params': {'request': raw}})
        self.assertTrue(out['ok'], out); result = out['result']; self.validators[1].validate(result)
        self.assertEqual(raw, before); self.assertFalse(result['production_qualified'])
        self.assertEqual(result['relative_tolerance'], raw['relative_tolerance'])
        self.assertEqual(result['absolute_tolerance_j'], raw['absolute_tolerance_j'])
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, allow_nan=False, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'], digest)
        self.assertEqual(result['transient_result']['initial_state'], raw['transient_request']['initial_state'])
        alpha = (20.+1/(75.*.004))/2
        omega = math.sqrt((1+20./75.)/.004-alpha*alpha)
        a = 1.25; b = ((-.02-a/75.)/.004+alpha*a)/omega

        def physical(t):
            c = math.cos(omega*t); s = math.sin(omega*t); decay = math.exp(-alpha*t)
            voltage = decay*(a*c+b*s)
            derivative = decay*((b*omega-alpha*a)*c-(a*omega+alpha*b)*s)
            return voltage, .004*derivative+voltage/75.

        for row in result['intervals']:
            left, right = row['start_time_s'], row['end_time_s']
            heat = quad(lambda t: 20*physical(t)[1]**2, left, right, epsabs=1e-13)[0]
            network = quad(lambda t: physical(t)[0]**2/75., left, right, epsabs=1e-13)[0]
            self.assertAlmostEqual(row['resistor_heat_j_by_port']['receiver'], heat, delta=1e-10)
            self.assertAlmostEqual(row['network_work_j_by_port']['receiver'], network, delta=1e-10)
            self.assertAlmostEqual(row['source_work_j_by_port']['receiver'], 0., delta=1e-12)
            self.assertAlmostEqual(row['balance_residual_j_by_port']['receiver'], 0., delta=1e-10)
        totals = result['totals']
        self.assertAlmostEqual(totals['initial_boundary_storage_j_by_port']['receiver'], .003325, delta=1e-12)
        heat = quad(lambda t: 20*physical(t)[1]**2, 0., 2., epsabs=1e-13)[0]
        network = quad(lambda t: physical(t)[0]**2/75., 0., 2., epsabs=1e-13)[0]
        self.assertAlmostEqual(totals['resistor_heat_j_by_port']['receiver'], heat, delta=1e-10)
        self.assertAlmostEqual(totals['network_work_j_by_port']['receiver'], network, delta=1e-10)
        self.assertGreater(result['diagnostics']['maximum_doubling_count'], 0)

    def test_worker_and_schema_fail_closed_on_invalid_energy_requests(self):
        for mutation in ('zero_relative', 'loose_relative', 'bool_relative', 'negative_absolute', 'nonfinite', 'missing', 'extra', 'state'):
            raw = request()
            if mutation == 'zero_relative': raw['relative_tolerance'] = 0.
            if mutation == 'loose_relative': raw['relative_tolerance'] = 1e-3
            if mutation == 'bool_relative': raw['relative_tolerance'] = True
            if mutation == 'negative_absolute': raw['absolute_tolerance_j'] = -1.
            if mutation == 'nonfinite': raw['absolute_tolerance_j'] = float('inf')
            if mutation == 'missing': raw.pop('transient_request')
            if mutation == 'extra': raw['thermal_mesh'] = 'implicit'
            if mutation == 'state': raw['transient_request']['initial_state']['fit_request_digest'] = '0'*64
            out = handle({'method': 'run_rlc_energy_ledger', 'params': {'request': raw}})
            with self.subTest(mutation=mutation):
                self.assertFalse(out['ok'], out); self.assertNotIn('result', out)
                if mutation not in ('nonfinite', 'state'):
                    self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_executes_and_contracts_are_registered(self):
        out = subprocess.run([sys.executable, str(ROOT/'examples/rlc_energy_ledger/run_energy.py')],
                             cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)['contract'], 'spike/rlc-energy-ledger-result/v1')
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request', 'result'):
            self.assertEqual(catalog[f'spike/rlc-energy-ledger-{kind}/v1'], f'rlc-energy-ledger-{kind}-v1.schema.json')
