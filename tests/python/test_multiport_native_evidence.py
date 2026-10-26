# SPDX-License-Identifier: Apache-2.0
"""Synthetic unittest artifacts exercise validators; these are NOT native evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from examples.multiport_deembedding.run_fixture import demonstration
from python.spike_core.solvers.signal_integrity.networks.sparameter_multiport_deembedding import deembed_multiport
from scripts import parity_multiport_native_gate as gate


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Source stand-ins are explicitly synthetic; real source coverage is
        # independently checked by the production integration validator.
        for name in (*gate.SOURCES, *gate.VALIDATOR_SOURCES):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic unittest source: '+name)
        self.request = demonstration()
        self.request['external_ports'] = gate.EXTERNAL[:]
        self.request['dut_ports'] = gate.DUT[:]
        self.request['measured']['port_names'] = gate.EXTERNAL[:]
        self.request['fixture']['port_names'] = gate.EXTERNAL+gate.DUT
        self.capture = {'source': deepcopy(self.request), 'result': deembed_multiport(self.request)}
        for name, value in (('request', self.request), ('capture', self.capture)):
            (self.root/(name+'.json')).write_text(json.dumps(value))
        retained = ('Experimental result retained 3 DUT ports; 2 complete diagnostic samples '
                    + ' '.join(gate.EXTERNAL+gate.DUT))
        for label, width in (('wide', 1200), ('narrow', 950)):
            Image.new('RGB', (width, 600), 'white').save(self.root/(label+'.jpg'), 'JPEG')
            (self.root/(label+'.txt')).write_text(retained)
        for key, text in {'invalidation': 'button (disabled) Export source and result',
                          'failure': 'alert MULTIPORT_DEEMBEDDING_ILL_CONDITIONED button (disabled) Export source and result',
                          'recovery': retained}.items():
            (self.root/(key+'.txt')).write_text(text)
        paths = {'request': 'request.json', 'capture': 'capture.json',
                 'wide_image': 'wide.jpg', 'wide_uia': 'wide.txt',
                 'narrow_image': 'narrow.jpg', 'narrow_uia': 'narrow.txt',
                 'invalidation_uia': 'invalidation.txt', 'failure_uia': 'failure.txt',
                 'recovery_uia': 'recovery.txt'}
        hashes = {name: gate.digest(self.root/name) for name in gate.SOURCES}
        self.manifest = {'contract': 'spike/multiport-native-observation/v1', 'stage_id': 'SI08-S05',
                         'family_complete': False, 'production_qualified': False,
                         'observation': {'kind': 'trusted_agent_native_ui', 'observer': 'SYNTHETIC UNITTEST FIXTURE',
                                         'observed_at_utc': '2026-10-24T00:00:00Z',
                                         'statement': 'SYNTHETIC TEST ONLY: no real native observation claimed.'},
                         'sources_before': hashes, 'sources_after': deepcopy(hashes),
                         'artifacts': {key: gate.binding(self.root/path, self.root) for key, path in paths.items()}}

    def reject(self, mutate):
        value = deepcopy(self.manifest)
        mutate(value)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            gate.validate_native(value, self.root)

    def test_synthetic_validator_fixture_accepts_complete_artifact_set(self):
        gate.validate_native(self.manifest, self.root)

    def test_native_uia_split_inline_numbers_preserve_observed_labels(self):
        path = self.root/'inline.txt'
        path.write_text('1 heading Experimental result retained\n2 text 3\n3 text DUT ports;\n4 text 2\n5 text complete diagnostic samples')
        self.assertTrue(gate.retained_result(gate.normalized(path)))

    def test_browser_integral_number_transport_keeps_exact_worker_digest(self):
        def browser_numbers(value):
            if isinstance(value, dict):
                return {key: browser_numbers(item) for key, item in value.items()}
            if isinstance(value, list):
                return [browser_numbers(item) for item in value]
            return int(value) if type(value) is float and value.is_integer() else value
        transported = browser_numbers(self.request)
        capture = {'source': transported, 'result': deembed_multiport(transported)}
        self.assertNotEqual(gate._digest(self.request), gate._digest(transported))
        gate.validate_capture(self.request, capture)
        capture['result']['input_digest'] = gate._digest(self.request)
        with self.assertRaises(ValueError):
            gate.validate_capture(self.request, capture)

    def test_source_scope_observation_and_artifact_failures(self):
        for mutate in (lambda m: m.update(production_qualified=True),
                       lambda m: m.update(family_complete=True),
                       lambda m: m['observation'].update(kind='unverified'),
                       lambda m: m['sources_before'].pop(gate.SOURCES[0]),
                       lambda m: m['sources_after'].update({gate.SOURCES[0]: '0'*64}),
                       lambda m: m['artifacts'].pop('recovery_uia'),
                       lambda m: m['artifacts']['capture'].update(sha256='0'*64),
                       lambda m: m['artifacts']['request'].update(path='../outside.json')):
            with self.subTest(mutation=mutate):
                self.reject(mutate)
        (self.root/gate.SOURCES[0]).write_text('changed source')
        self.reject(lambda m: None)

    def test_export_identity_digest_numeric_and_qualification_failures(self):
        mutations = [lambda c: c['source'].update(extra=True),
                     lambda c: c['result']['source_request']['measured'].update(id='different'),
                     lambda c: c['result'].update(input_digest='0'*64),
                     lambda c: c['result'].update(production_qualified=True),
                     lambda c: c['result']['derived_network']['s_parameters'][1][2][2].update(real=.2),
                     lambda c: c['result']['derived_network']['s_parameters'][0][0][0].update(real=float('nan')),
                     lambda c: c['result']['derived_network'].update(port_names=list(reversed(gate.DUT))),
                     lambda c: c['result']['diagnostics'][1].update(reconstruction_residual=1.),
                     lambda c: c['result']['diagnostics'].pop()]
        for mutate in mutations:
            value = deepcopy(self.capture)
            mutate(value)
            with self.assertRaises(ValueError):
                gate.validate_capture(self.request, value)

    def test_uia_failure_recovery_invalidation_and_dimensions_required(self):
        for key, text in [('invalidation_uia', 'Export source and result'),
                          ('failure_uia', 'button (disabled) Export source and result alert'),
                          ('recovery_uia', '3 DUT ports; no retained result'),
                          ('wide_uia', 'Experimental result retained 3 DUT ports; 2 complete diagnostic samples')]:
            original = deepcopy(self.manifest)
            path = self.root/self.manifest['artifacts'][key]['path']
            before = path.read_bytes()
            path.write_text(text)
            self.manifest['artifacts'][key] = gate.binding(path, self.root)
            self.reject(lambda m: None)
            path.write_bytes(before)
            self.manifest = original
        path = self.root/'narrow.jpg'
        Image.new('RGB', (800, 600)).save(path, 'JPEG')
        self.manifest['artifacts']['narrow_image'] = gate.binding(path, self.root)
        self.reject(lambda m: None)

    def test_stage_wrapper_binds_manifest_and_integration_and_rejects_promotion(self):
        manifest_path = self.root/'manifest.json'
        manifest_path.write_text(json.dumps(self.manifest))
        integration_path = self.root/'integration.json'
        integration_path.write_text('{"synthetic_unittest_integration": true}')
        receipt = {'contract': 'spike/multiport-native-stage-evidence/v1', 'stage_id': 'SI08-S05',
                   'status': 'passed', 'stage_complete': True, 'family_complete': False,
                   'production_qualified': False, 'native_visual_verified': True,
                   'worker_schema_verified': True, 'headless_desktop_verified': True,
                   'integration': gate.binding(integration_path, self.root),
                   'manifest': gate.binding(manifest_path, self.root),
                   'validator_sources': {name: gate.digest(self.root/name) for name in gate.VALIDATOR_SOURCES},
                   'sources_before': self.manifest['sources_before'], 'sources_after': self.manifest['sources_after']}
        # Only the upstream integration validator is mocked. Its own retained
        # real-command tests are separate from these synthetic native fixtures.
        with patch.object(gate, 'integration_validate') as check:
            gate.validate_evidence(receipt, self.root)
            check.assert_called_once()
            for key in ('family_complete', 'production_qualified'):
                bad = deepcopy(receipt); bad[key] = True
                with self.assertRaises(ValueError): gate.validate_evidence(bad, self.root)
            bad = deepcopy(receipt); bad['manifest']['sha256'] = '0'*64
            with self.assertRaises(ValueError): gate.validate_evidence(bad, self.root)
            bad = deepcopy(receipt); bad['validator_sources'][gate.VALIDATOR_SOURCES[0]] = '0'*64
            with self.assertRaises(ValueError): gate.validate_evidence(bad, self.root)
        with patch.object(gate, 'integration_validate', side_effect=ValueError('failed integration')):
            with self.assertRaises(ValueError): gate.validate_evidence(receipt, self.root)


if __name__ == '__main__':
    unittest.main()
