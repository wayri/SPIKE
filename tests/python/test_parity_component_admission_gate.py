# SPDX-License-Identifier: Apache-2.0
"""Reject failed, incomplete or stale bounded native admission receipts."""
import copy
import json
import unittest

from scripts.parity_component_admission_gate import ROOT, validate_receipt


class ComponentAdmissionGateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT / 'docs/validation/parity/WF01-S04C2.json').read_text())

    def test_current_native_receipt(self):
        validate_receipt(self.receipt)

    def test_failures_skips_missing_native_case_and_wrong_runtime_rejected(self):
        for mutation in ('failed', 'skipped', 'missing', 'runtime', 'qualified', 'errors', 'expected_failures'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'failed':
                receipt['status'] = 'failed'
            elif mutation == 'skipped':
                receipt['tests']['skipped'] = ['native']
            elif mutation == 'errors':
                receipt['tests']['errors'] = ['native']
            elif mutation == 'expected_failures':
                receipt['tests']['expected_failures'] = ['native']
            elif mutation == 'missing':
                receipt['tests']['names'].pop()
            elif mutation == 'runtime':
                receipt['runtime']['python'] = '3.12.9'
            else:
                receipt['material_qualified'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)

    def test_stale_runner_or_log_and_foreign_path_rejected(self):
        for mutation in ('source', 'log', 'path'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'source':
                receipt['sources']['scripts/parity_component_admission_gate.py'] = '0' * 64
            elif mutation == 'log':
                receipt['log_sha256'] = '0' * 64
            else:
                receipt['log'] = '../foreign.log'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt)
