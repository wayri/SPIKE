# SPDX-License-Identifier: Apache-2.0
"""Reject stale, skipped or falsely promoted native scale stage receipts."""
import copy
import json
import unittest

from scripts.parity_step_scale_gate import ROOT, validate_receipt


class StepScaleGateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT/'docs/validation/parity/WF01-S04C5.json').read_text())

    def test_current_native_scale_receipt(self):
        validate_receipt(self.receipt)

    def test_failed_skipped_incomplete_or_promoted_stage_rejects(self):
        for mutation in ('failed', 'skipped', 'missing', 'qualified'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'failed': receipt['status'] = 'failed'
            elif mutation == 'skipped': receipt['tests']['skipped'] = ['native']
            elif mutation == 'missing': receipt['tests']['names'].pop()
            else: receipt['production_qualified'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)

    def test_stale_worker_native_geometry_or_log_rejects(self):
        for mutation in ('worker', 'geometry', 'log'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'worker': receipt['sources']['python/spike_core/freecad_scale_step.py'] = '0'*64
            elif mutation == 'geometry': receipt['native_evidence_sha256'] = '0'*64
            else: receipt['log_sha256'] = '0'*64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)
