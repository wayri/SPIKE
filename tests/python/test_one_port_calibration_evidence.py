# SPDX-License-Identifier: Apache-2.0
"""Synthetic validator fixtures; not executed numerical-stage receipts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from scripts import verify_one_port_calibration as gate


class CalibrationEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in gate.SOURCES:
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic validator unittest source', encoding='utf-8')
        self.log = self.root/'synthetic.log'
        self.log.write_text('SYNTHETIC VALIDATOR TEST ONLY\nRan 19 tests in 0 seconds\nOK\n', encoding='utf-8')
        self.capture = self.root/'synthetic.json'
        request = gate.demonstration()
        self.capture.write_text(json.dumps({'source': request, 'result': gate.calibrate_one_port(request)}), encoding='utf-8')
        snapshot = {n: gate.digest(self.root/n) for n in gate.SOURCES}
        self.receipt = {'contract': 'spike/one-port-calibration-evidence/v1', 'stage_id': 'SI08-S06',
                        'status': 'passed', 'stage_complete': True, 'workflow': 'offline_reference',
                        'family_complete': False, 'production_qualified': False,
                        'measurement_qualified': False, 'linearization_qualified': False,
                        'sources_before': snapshot, 'sources_after': deepcopy(snapshot),
                        'tests': {'names': gate.names(unittest.defaultTestLoader.loadTestsFromNames(gate.MODULES)),
                                  'run': 19, 'failures': [], 'errors': [], 'skipped': [],
                                  'expected_failures': [], 'unexpected_successes': []},
                        'log': {'path': self.log.name, 'sha256': gate.digest(self.log)},
                        'capture': {'path': self.capture.name, 'sha256': gate.digest(self.capture)}}

    def test_synthetic_validator_fixture_and_scope_execution_rejections(self):
        gate.validate_receipt(self.receipt, self.root)
        changes = [lambda r: r.update(stage_complete=False), lambda r: r.update(stage_id='SI08'),
                   lambda r: r.update(production_qualified=True), lambda r: r.update(family_complete=True),
                   lambda r: r.update(measurement_qualified=True), lambda r: r.update(linearization_qualified=True),
                   lambda r: r['tests'].update(run=18), lambda r: r['tests'].update(skipped=['omitted']),
                   lambda r: r['tests']['names'].pop(), lambda r: r['sources_before'].pop(gate.SOURCES[0]),
                   lambda r: r['sources_after'].update({gate.SOURCES[0]: '0'*64}),
                   lambda r: r['log'].update(sha256='0'*64), lambda r: r['capture'].update(path='../outside.json')]
        for change in changes:
            r = deepcopy(self.receipt); change(r)
            with self.subTest(change=change), self.assertRaises(ValueError): gate.validate_receipt(r, self.root)

    def test_stale_source_and_hash_bound_artifact_cannot_complete(self):
        (self.root/gate.SOURCES[0]).write_text('changed source', encoding='utf-8')
        with self.assertRaises(ValueError): gate.validate_receipt(self.receipt, self.root)

    def test_rebound_capture_still_checks_identity_numeric_and_uncertainty_scope(self):
        original = json.loads(self.capture.read_text(encoding='utf-8'))
        changes = [lambda c: c['source']['dut'].update(id='changed'),
                   lambda c: c['result'].update(input_digest='0'*64),
                   lambda c: c['result'].update(measurement_qualified=True),
                   lambda c: c['result']['derived_network']['s_parameters'][0][0][0].update(real=.4),
                   lambda c: c['result']['derived_network'].update(port_names=['another-plane']),
                   lambda c: c['result']['covariance'][0].__setitem__(0, float('nan')),
                   lambda c: c['result']['covariance'][0].__setitem__(0, .5)]
        for change in changes:
            capture = deepcopy(original); change(capture)
            self.capture.write_text(json.dumps(capture), encoding='utf-8')
            self.receipt['capture']['sha256'] = gate.digest(self.capture)
            with self.subTest(change=change), self.assertRaises(ValueError): gate.validate_receipt(self.receipt, self.root)


if __name__ == '__main__': unittest.main()
