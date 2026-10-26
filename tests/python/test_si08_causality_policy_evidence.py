# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
import unittest

from scripts.verify_si08_interoperability import ROOT, validate_receipt


class CausalityPolicyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT/'docs/validation/parity/SI08-I02-policy-20261025.json').read_text(encoding='utf-8'))

    def test_current_source_bound_policy_receipt(self):
        validate_receipt(self.receipt, point_id='I02')

    def test_policy_cannot_be_substituted_omitted_or_overclaimed(self):
        changes = [lambda p: p.update(point_id='I01'),
                   lambda p: p.update(production_qualified=True),
                   lambda p: p['tests'].update(skipped=['missing oracle']),
                   lambda p: p['sources_after'].pop(next(iter(p['sources_after']))),
                   lambda p: p['tests']['names'].pop(),
                   lambda p: p['log'].update(sha256='0'*64)]
        for change in changes:
            value = deepcopy(self.receipt); change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_receipt(value, point_id='I02')
