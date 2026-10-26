# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
import unittest

from scripts.verify_si08_interoperability import ROOT, validate_receipt


class InteroperabilityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT/'docs/validation/parity/SI08-I01-interoperability-r3-20261025.json').read_text(encoding='utf-8'))

    def test_current_source_bound_receipt(self):
        validate_receipt(self.receipt)

    def test_rejects_scope_coverage_omission_staleness_and_skips(self):
        def stale(p):
            key = next(iter(p['sources_before']))
            p['sources_before'][key] = p['sources_after'][key] = '0'*64
        changes = [lambda p: p.update(family_complete=True),
                   lambda p: p['sources_before'].pop(next(iter(p['sources_before']))),
                   lambda p: p['tests'].update(skipped=['omitted']),
                   lambda p: p['tests']['names'].pop(), stale,
                   lambda p: p['log'].update(path='../outside.log')]
        for change in changes:
            value = deepcopy(self.receipt); change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_receipt(value)
