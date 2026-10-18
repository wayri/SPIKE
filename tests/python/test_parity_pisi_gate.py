# SPDX-License-Identifier: Apache-2.0
"""Failed, stale or incomplete numerical stage evidence must not mark Done."""
import copy
import json
import unittest
from scripts.parity_pisi_gate import ROOT, validate_receipt


class PiSiGateTests(unittest.TestCase):
    def test_retained_capacitive_network_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI07-S04.json').read_text())
        validate_receipt(receipt, stage='SI07-S04')
    def test_retained_inductive_network_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI07-S03.json').read_text())
        validate_receipt(receipt, stage='SI07-S03')
    def test_retained_terminated_network_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI07-S02.json').read_text())
        validate_receipt(receipt, stage='SI07-S02')
    def test_retained_network_transient_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI07-S01.json').read_text())
        validate_receipt(receipt, stage='SI07-S01')
    def test_retained_rational_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI08-S04.json').read_text())
        validate_receipt(receipt, stage='SI08-S04')
    def test_retained_resampling_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI08-S03.json').read_text())
        validate_receipt(receipt, stage='SI08-S03')
    def test_retained_deembedding_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI08-S02.json').read_text())
        validate_receipt(receipt, stage='SI08-S02')
    def test_retained_decap_selection_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI03-S02.json').read_text())
        validate_receipt(receipt, stage='PI03-S02')
    def test_retained_decap_corner_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI03-S01.json').read_text())
        validate_receipt(receipt, stage='PI03-S01')
    def test_retained_feedback_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI02-S04.json').read_text())
        validate_receipt(receipt, stage='PI02-S04')
    def test_retained_thermal_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI02-S03.json').read_text())
        validate_receipt(receipt, stage='PI02-S03')
    def test_retained_reduction_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI02-S02.json').read_text())
        validate_receipt(receipt, stage='PI02-S02')
    def test_retained_dielectric_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI02-S01.json').read_text())
        validate_receipt(receipt, stage='PI02-S01')
    def test_retained_multiload_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI04-S02.json').read_text())
        validate_receipt(receipt, stage='PI04-S02')
    def test_retained_pi_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/PI04-S01.json').read_text())
        validate_receipt(receipt, stage='PI04-S01')

    def test_retained_si_execution(self):
        receipt=json.loads((ROOT/'docs/validation/parity/SI08-S01.json').read_text())
        validate_receipt(receipt, stage='SI08-S01')

    def test_corrupted_evidence_rejected(self):
        baseline=json.loads((ROOT/'docs/validation/parity/SI08-S01.json').read_text())
        for mutation in ('status','qualification','stage','source','log','skip','count','names'):
            receipt=copy.deepcopy(baseline)
            if mutation=='status': receipt['status']='failed'
            elif mutation=='qualification': receipt['production_qualified']=True
            elif mutation=='stage': receipt['stage_id']='PI04-S01'
            elif mutation=='source': receipt['sources']['python/spike_core/sparameter_modes.py']='0'*64
            elif mutation=='log': receipt['log']='../outside.log'
            elif mutation=='skip': receipt['tests']['skipped']=[receipt['tests']['names'][0]]
            elif mutation=='count': receipt['tests']['run']-=1
            else: receipt['tests']['names'].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt, stage='SI08-S01')


if __name__=='__main__': unittest.main()
