# SPDX-License-Identifier: Apache-2.0
"""Actual worker transport and strict catalog against independent wave oracles."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np
from jsonschema import Draft202012Validator
from python.spike_core.contract_catalog import schema_operation
from python.spike_core.service import handle
from tests.python.test_sparameter_multiport_deembedding import fixture_case, matrix, request

ROOT = Path(__file__).resolve().parents[2]


class MultiportDeembeddingContractTests(unittest.TestCase):
    def setUp(self):
        self.validators = {}
        for kind in ('request', 'result'):
            name = f'multiport-deembedding-{kind}-v1.schema.json'
            schema = schema_operation('read', {'name': name})['schema']
            Draft202012Validator.check_schema(schema)
            self.validators[kind] = Draft202012Validator(schema)

    def call(self, req, **extra):
        return handle({'method': 'deembed_multiport', 'params': {'request': req, **extra}})

    def test_handle_independent_three_and_four_port_oracles_and_source_preservation(self):
        for n in (3, 4):
            fixture, dut = fixture_case(n)
            req = request(fixture, dut)
            before = deepcopy(req)
            self.validators['request'].validate(req)
            response = self.call(req)
            self.assertTrue(response['ok'], response)
            result = response['result']
            self.validators['result'].validate(result)
            np.testing.assert_allclose(matrix(result['derived_network']['s_parameters'][0]), dut,
                                       atol=2e-12, rtol=2e-12)
            self.assertEqual(req, before)
            self.assertEqual(result['source_request'], before)
            self.assertEqual(result['derived_network']['port_names'], before['dut_ports'])
            self.assertFalse(result['production_qualified'])
            self.assertEqual(result['model_status'], 'experimental')
            req['measured']['id'] = 'changed-after-return'
            self.assertEqual(result['source_request'], before)

    def test_jsonl_subprocess_success_and_late_failure_return_no_partial_sweep(self):
        fixture, dut = fixture_case(3)
        good = request(fixture, dut)
        bad = deepcopy(good)
        for key in ('measured', 'fixture'):
            bad[key]['frequencies_hz'] = [7.3e7, 9e7]
            bad[key]['s_parameters'] *= 2
        # A valid first sample followed by singular fixture transmissions.
        bad['fixture']['s_parameters'][1] = [[{'real': 0., 'imag': 0.} for _ in range(6)] for _ in range(6)]
        messages = [{'id': ident, 'method': 'deembed_multiport', 'params': {'request': req}}
                    for ident, req in (('success', good), ('failure', bad))]
        process = subprocess.run([sys.executable, str(ROOT/'scripts/spike_worker_entry.py')],
                                 cwd=ROOT, input=''.join(json.dumps(m)+'\n' for m in messages),
                                 text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        success, failure = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertTrue(success['ok'], success)
        self.validators['result'].validate(success['result'])
        np.testing.assert_allclose(matrix(success['result']['derived_network']['s_parameters'][0]),
                                   dut, atol=2e-12, rtol=2e-12)
        self.assertFalse(failure['ok'], failure)
        self.assertNotIn('result', failure)
        self.assertIn('MULTIPORT_DEEMBEDDING_ILL_CONDITIONED', json.dumps(failure))

    def test_handle_rejects_bad_fields_maps_grids_reference_and_conditioning(self):
        fixture, dut = fixture_case(3)
        original = request(fixture, dut)
        mutations = [lambda r: r.update(extra=1),
                     lambda r: r['measured'].update(extra=1),
                     lambda r: r['measured']['s_parameters'][0][0][0].update(real=True),
                     lambda r: r['dut_ports'].__setitem__(0, r['dut_ports'][1]),
                     lambda r: r['fixture'].update(reference_impedance_ohm=75.),
                     lambda r: r['fixture'].update(frequencies_hz=[8e7]),
                     lambda r: r['fixture'].update(s_parameters=[[[{'real': 0., 'imag': 0.} for _ in range(6)] for _ in range(6)]])]
        for change in mutations:
            req = deepcopy(original)
            change(req)
            before = deepcopy(req)
            response = self.call(req)
            self.assertFalse(response['ok'], response)
            self.assertNotIn('result', response)
            self.assertEqual(req, before)
        self.assertFalse(self.call(original, extra=True)['ok'])

    def test_catalog_rejects_false_qualification_and_malformed_nested_results(self):
        fixture, dut = fixture_case(4)
        result = self.call(request(fixture, dut))['result']
        discovery = schema_operation('read', {})
        catalog = discovery['schemas']
        ids = [entry['id'] for entry in discovery['descriptors']]
        self.assertEqual(len(ids), len(set(ids)))
        manifest = json.loads((ROOT/'schemas/manifest.json').read_text())['schemas']
        for kind in ('request', 'result'):
            name = f'multiport-deembedding-{kind}-v1.schema.json'
            self.assertIn(name, catalog)
            descriptor = next(entry for entry in discovery['descriptors'] if entry['name'] == name)
            self.assertEqual(descriptor['id'], f'https://spike.local/schemas/{name}')
            self.assertEqual(descriptor['title'], f'Supplied multiport fixture removal {kind}')
            self.assertEqual(manifest[f'spike/multiport-deembedding-{kind}/v1'], name)
        changes = [lambda r: r.update(production_qualified=True),
                   lambda r: r.update(model_status='validated'),
                   lambda r: r['source_request']['fixture'].update(extra=1),
                   lambda r: r['derived_network']['s_parameters'][0][0][0].update(extra=1),
                   lambda r: r['diagnostics'][0].pop('feedback_condition'),
                   lambda r: r['diagnostics'][0].update(recovery_condition=1e9),
                   lambda r: r['diagnostics'][0].update(extra=1),
                   lambda r: r['source_request']['measured'].update(port_names=[]),
                   lambda r: r['derived_network']['s_parameters'][0][0].pop(),
                   lambda r: r['source_request']['fixture']['s_parameters'][0].pop(),
                   lambda r: r.update(input_digest='not-a-digest')]
        for change in changes:
            bad = deepcopy(result)
            change(bad)
            self.assertTrue(list(self.validators['result'].iter_errors(bad)))
            checked = schema_operation('validate', {'name': 'multiport-deembedding-result-v1.schema.json',
                                                     'document': bad})
            self.assertFalse(checked['valid'])


if __name__ == '__main__':
    unittest.main()
