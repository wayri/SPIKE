# SPDX-License-Identifier: Apache-2.0
"""Protect scaled review completion against stale and incomplete execution."""
import copy
import json
import unittest

from scripts.parity_scaled_review_gate import ROOT, validate_receipt


class ScaledReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT/'docs/validation/parity/WF01-S04C6.json').read_text())

    def test_current_native_proposals(self):
        validate_receipt(self.receipt)

    def test_failed_skipped_or_false_projection_cannot_mark_done(self):
        for mutation in ('failed','skipped','missing','projection'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'failed': receipt['status'] = 'failed'
            elif mutation == 'skipped': receipt['tests']['skipped'] = ['native']
            elif mutation == 'missing': receipt['tests']['names'].pop()
            else: receipt['source_projection_enabled'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)

    def test_stale_geometry_code_or_log_cannot_mark_done(self):
        for mutation in ('geometry','code','log'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'geometry': receipt['native_evidence_sha256'] = '0'*64
            elif mutation == 'code': receipt['sources']['python/spike_core/scaled_component_review.py'] = '0'*64
            else: receipt['log_sha256'] = '0'*64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)
