# SPDX-License-Identifier: Apache-2.0
"""Withhold Done for stale, failed or overclaimed placement review evidence."""
import copy
import json
import unittest

from scripts.parity_component_review_gate import ROOT, validate_receipt


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT / 'docs/validation/parity/WF01-S04C4.json').read_text())

    def test_current_receipt(self):
        validate_receipt(self.receipt)

    def test_failed_skipped_and_false_projection_reject(self):
        for mutation in ('failed', 'skipped', 'missing', 'projection'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'failed':
                receipt['status'] = 'failed'
            elif mutation == 'skipped':
                receipt['tests']['skipped'] = ['placement']
            elif mutation == 'missing':
                receipt['tests']['names'].pop()
            else:
                receipt['source_projection_enabled'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)

    def test_changed_implementation_native_receipt_or_log_reject(self):
        for mutation in ('source', 'native', 'log'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'source':
                receipt['sources']['python/spike_core/component_placement_review.py'] = '0' * 64
            elif mutation == 'native':
                receipt['native_receipt_sha256'] = '0' * 64
            else:
                receipt['log_sha256'] = '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)
