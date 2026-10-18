# SPDX-License-Identifier: Apache-2.0
"""Registered worker/CLI and strict wire contracts for the RLGC star."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from jsonschema import Draft202012Validator

from examples.rlgc_line_junction.run_line import request
from python.spike_core.service import handle
from tests.python.test_rlgc_line_junction import matrix, physical_oracle, value

ROOT = Path(__file__).resolve().parents[2]


class JunctionContractTests(unittest.TestCase):
    def validators(self):
        return [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlgc-line-junction-{kind}-v1.schema.json').read_text())) for kind in ('request', 'result')]

    def test_actual_worker_physical_nodal_oracle_and_provenance(self):
        raw = request(); before = deepcopy(raw); incoming, outgoing = self.validators(); incoming.validate(raw)
        response = handle({'method': 'run_rlgc_line_junction', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response); out = response['result']; outgoing.validate(out)
        self.assertEqual(raw, before); self.assertEqual(out['source_request'], raw)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(out['input_digest'], digest); self.assertFalse(out['production_qualified'])
        self.assertEqual(out['network']['port_names'], [leg['id'] for leg in raw['legs']])
        for original, child in zip(raw['legs'], out['legs']):
            self.assertEqual(child['id'], original['id'])
            source = child['result']['source_request']
            self.assertEqual(source['line_request'], original['line_request']); self.assertEqual(source['probes'], original['probes'])
            expected = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            self.assertEqual(child['result']['input_digest'], expected)
        for k, point in enumerate(out['points']):
            expected, states, _ = physical_oracle(raw, k)
            np.testing.assert_allclose(matrix(out['network']['s_parameters'][k]), expected, atol=2e-12, rtol=1e-10)
            drive = np.array([value(z) for z in raw['excitations'][k]['incident_waves']]); physical = states@drive
            for j, child in enumerate(out['legs']):
                left = child['result']['points'][k]['boundary_values']['left']
                np.testing.assert_allclose([value(left['voltage_v']), value(left['current_into_line_a'])], physical[2*j:2*j+2], atol=2e-12, rtol=1e-10)
            self.assertAlmostEqual(point['power_balance']['net_input_w'], float(np.vdot(drive, drive).real-np.vdot(expected@drive, expected@drive).real), delta=2e-12)

    def test_example_cli_and_manifest(self):
        _, validator = self.validators()
        catalog = json.loads((ROOT/'schemas/manifest.json').read_text())
        for kind in ('request', 'result'):
            self.assertEqual(catalog['schemas'][f'spike/rlgc-line-junction-{kind}/v1'], f'rlgc-line-junction-{kind}-v1.schema.json')
        example = subprocess.run([sys.executable, str(ROOT/'examples/rlgc_line_junction/run_line.py')], cwd=ROOT, capture_output=True, text=True, check=True, timeout=60)
        validator.validate(json.loads(example.stdout))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            output = Path(folder)/'result.json'
            run = subprocess.run([sys.executable, '-m', 'python.spike_core.cli', '--quiet', '--output', str(output), 'rlgc-junction', str(ROOT/'examples/rlgc_line_junction/three-legs.request.json')], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr); validator.validate(json.loads(output.read_text()))

    def test_strict_schemas_and_worker_failure(self):
        incoming, outgoing = self.validators()
        for mutation in ('one_leg', 'boolean', 'unknown', 'wave_shape'):
            raw = request()
            if mutation == 'one_leg': raw['legs'] = raw['legs'][:1]
            elif mutation == 'boolean': raw['legs'][0]['line_request']['length_m'] = True
            elif mutation == 'unknown': raw['legs'][0]['unknown'] = 0
            else: raw['excitations'][0]['incident_waves'][0]['extra'] = 1
            self.assertFalse(incoming.is_valid(raw)); self.assertFalse(handle({'method': 'run_rlgc_line_junction', 'params': {'request': raw}})['ok'])
        response = handle({'method': 'run_rlgc_line_junction', 'params': {'request': request()}})['result']
        for mutation in ('qualification', 'extra', 'junction'):
            changed = deepcopy(response)
            if mutation == 'qualification': changed['production_qualified'] = True
            elif mutation == 'extra': changed['network']['extra'] = 0
            else: changed['points'][0]['junction']['current_residual_a'] = {'real': 0}
            self.assertFalse(outgoing.is_valid(changed))


if __name__ == '__main__':
    unittest.main()
