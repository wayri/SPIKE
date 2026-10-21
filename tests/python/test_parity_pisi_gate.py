# SPDX-License-Identifier: Apache-2.0
"""Failed, stale or incomplete numerical stage evidence must not mark Done."""
import copy
import json
import unittest
from scripts.parity_pisi_gate import ROOT, validate_receipt


def current_receipt(stage_id, backlog=None):
    if backlog is None:
        backlog = json.loads((ROOT/'docs/parity-capability-backlog-v1.json').read_text())
    matches = [stage for stage in backlog['stages'] if stage['id'] == stage_id]
    if len(matches) != 1:
        raise ValueError('Expected exactly one current evidence stage')
    path = (ROOT/matches[0]['evidence']).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Current evidence must be inside the repository')
    receipt = json.loads(path.read_text())
    if receipt.get('stage_id') != stage_id:
        raise ValueError('Current evidence stage identity differs')
    return receipt


class PiSiGateTests(unittest.TestCase):
    def test_retained_distortionless_line_execution(self):
        receipt=current_receipt('SI02-S02')
        validate_receipt(receipt, stage='SI02-S02')

    def test_retained_lossless_line_execution(self):
        receipt=current_receipt('SI02-S01')
        validate_receipt(receipt, stage='SI02-S01')

    def test_retained_network_reflectometry_execution(self):
        receipt=current_receipt('SI07-S10')
        validate_receipt(receipt, stage='SI07-S10')

    def test_retained_crosstalk_timing_execution(self):
        receipt=current_receipt('SI07-S09')
        validate_receipt(receipt, stage='SI07-S09')

    def test_retained_multi_aggressor_execution(self):
        receipt=current_receipt('SI07-S08')
        validate_receipt(receipt, stage='SI07-S08')

    def test_retained_rlc_energy_execution(self):
        receipt=current_receipt('SI07-S07')
        validate_receipt(receipt, stage='SI07-S07')

    def test_retained_rlc_initial_execution(self):
        receipt=current_receipt('SI07-S06')
        validate_receipt(receipt, stage='SI07-S06')

    def test_retained_rlc_network_execution(self):
        receipt=current_receipt('SI07-S05')
        validate_receipt(receipt, stage='SI07-S05')

    def test_retained_capacitive_network_execution(self):
        receipt=current_receipt('SI07-S04')
        validate_receipt(receipt, stage='SI07-S04')
    def test_retained_inductive_network_execution(self):
        receipt=current_receipt('SI07-S03')
        validate_receipt(receipt, stage='SI07-S03')
    def test_retained_terminated_network_execution(self):
        receipt=current_receipt('SI07-S02')
        validate_receipt(receipt, stage='SI07-S02')
    def test_retained_network_transient_execution(self):
        receipt=current_receipt('SI07-S01')
        validate_receipt(receipt, stage='SI07-S01')
    def test_retained_rational_execution(self):
        receipt=current_receipt('SI08-S04')
        validate_receipt(receipt, stage='SI08-S04')
    def test_retained_resampling_execution(self):
        receipt=current_receipt('SI08-S03')
        validate_receipt(receipt, stage='SI08-S03')
    def test_retained_deembedding_execution(self):
        receipt=current_receipt('SI08-S02')
        validate_receipt(receipt, stage='SI08-S02')
    def test_retained_decap_selection_execution(self):
        receipt=current_receipt('PI03-S02')
        validate_receipt(receipt, stage='PI03-S02')
    def test_retained_decap_corner_execution(self):
        receipt=current_receipt('PI03-S01')
        validate_receipt(receipt, stage='PI03-S01')
    def test_retained_feedback_execution(self):
        receipt=current_receipt('PI02-S04')
        validate_receipt(receipt, stage='PI02-S04')
    def test_retained_thermal_execution(self):
        receipt=current_receipt('PI02-S03')
        validate_receipt(receipt, stage='PI02-S03')
    def test_retained_reduction_execution(self):
        receipt=current_receipt('PI02-S02')
        validate_receipt(receipt, stage='PI02-S02')
    def test_retained_dielectric_execution(self):
        receipt=current_receipt('PI02-S01')
        validate_receipt(receipt, stage='PI02-S01')
    def test_retained_multiload_execution(self):
        receipt=current_receipt('PI04-S02')
        validate_receipt(receipt, stage='PI04-S02')
    def test_retained_pi_execution(self):
        receipt=current_receipt('PI04-S01')
        validate_receipt(receipt, stage='PI04-S01')

    def test_retained_si_execution(self):
        receipt=current_receipt('SI08-S01')
        validate_receipt(receipt, stage='SI08-S01')

    def test_retained_rlgc_line_execution(self):
        receipt=current_receipt('SI02-S03')
        validate_receipt(receipt, stage='SI02-S03')

    def test_retained_rlgc_fields_execution(self):
        receipt=current_receipt('SI02-S04')
        validate_receipt(receipt, stage='SI02-S04')

    def test_retained_rlgc_cascade_execution(self):
        receipt=current_receipt('SI02-S05')
        validate_receipt(receipt, stage='SI02-S05')

    def test_retained_rlgc_junction_execution(self):
        receipt=current_receipt('SI02-S06')
        validate_receipt(receipt, stage='SI02-S06')

    def test_current_receipt_requires_unique_matching_stage(self):
        backlog = json.loads((ROOT/'docs/parity-capability-backlog-v1.json').read_text())
        stage = next(row for row in backlog['stages'] if row['id'] == 'SI08-S01')
        foreign = next(row for row in backlog['stages'] if row['id'] == 'PI04-S01')
        for rows in ([], [stage, stage], [{**stage, 'evidence': foreign['evidence']}],
                     [{**stage, 'evidence': '../outside.json'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                current_receipt('SI08-S01', {'stages': rows})

    def test_corrupted_evidence_rejected(self):
        baseline=current_receipt('SI08-S01')
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
