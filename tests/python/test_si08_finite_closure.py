# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.check_si08_closure import ROOT,validate_checklist


class FiniteClosureTests(unittest.TestCase):
    def setUp(self):
        self.payload=json.loads((ROOT/'docs/si08-closure-checklist-v1.json').read_text(encoding='utf-8'))

    def test_current_progress_and_external_release_separation(self):
        result=validate_checklist(self.payload)
        self.assertIn('I04',result['verified']);self.assertIn('I03',result['ready_implementation'])
        self.assertIn('I01',result['verified']);self.assertIn('I02',result['verified'])
        self.assertEqual(result['pending_external'],['E01','E02']);self.assertEqual(result['pending_release'],['R01','R02'])
        self.assertFalse(result['implementation_complete']);self.assertFalse(result['full_family_complete']);self.assertFalse(result['release_ready'])

    def test_frozen_inventory_scope_and_external_dependency_cannot_drift(self):
        changes=[lambda p:p['implementation'].pop(),lambda p:p.update(scope_version=2),
                 lambda p:p['implementation'][0]['steps'].pop(),
                 lambda p:p['implementation'][0]['depends_on'].append('E01'),
                 lambda p:p['original_targets'].pop()]
        for change in changes:
            p=deepcopy(self.payload);change(p)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_checklist(p)

    def test_unverified_and_stale_evidence_cannot_be_promoted(self):
        for group in ('implementation','external_validation','release'):
            p=deepcopy(self.payload)
            row=next(r for r in p[group] if r['status']!='verified')
            row['status']='verified'
            with self.subTest(group=group),self.assertRaises(ValueError):validate_checklist(p)
        p=deepcopy(self.payload);r=next(r for r in p['implementation'] if r['id']=='I04');original=json.loads((ROOT/r['evidence']).read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            path=Path(directory)/'receipt.json';original['tests']['skipped']=['omitted']
            path.write_text(json.dumps(original),encoding='utf-8');r['evidence']=path.relative_to(ROOT).as_posix()
            with self.assertRaises(ValueError):validate_checklist(p)


if __name__=='__main__':unittest.main()
