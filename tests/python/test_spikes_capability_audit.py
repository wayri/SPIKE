import unittest
from python.spikes.capability_audit import run_capability_audit,CASES

class CapabilityAuditTests(unittest.TestCase):
    def test_local_source_probes_use_real_top_level_files(self):
        rows={row['id']:row for row in run_capability_audit()['features']}
        for ident in ('language.include','language.library_section'):
            with self.subTest(feature=ident):
                self.assertEqual(rows[ident]['parser'],'accepted')
                self.assertEqual(rows[ident]['elements'],2)
                self.assertEqual(rows[ident]['numerical_verification'],'not_tested')

    def test_evidence_does_not_promote_parser_to_parity(self):
        result=run_capability_audit();rows={r['id']:r for r in result['features']}
        self.assertFalse(result['full_spice_parity'])
        self.assertEqual(result['summary']['positive_probes'],len(CASES))
        self.assertTrue(result['summary']['strict_rejection_sentinels_passed'])
        self.assertEqual(rows['language.scoped_models']['parser'],'accepted')
        self.assertEqual(rows['source.sin']['parser'],'accepted')
        self.assertEqual(rows['source.exp']['parser'],'accepted')
        self.assertEqual(rows['source.sffm']['parser'],'accepted')
        self.assertTrue(all(r['numerical_verification']=='not_tested' for r in rows.values()))
        self.assertTrue(all(len(r['deck_sha256'])==64 for r in rows.values()))

if __name__=='__main__':unittest.main()
