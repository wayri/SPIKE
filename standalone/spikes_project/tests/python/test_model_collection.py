import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio' / 'python'))
from spikes_studio.model_collection import scan_collection, search_entries, read_entry


class CollectionTests(unittest.TestCase):
    def test_index_preserves_hierarchy_and_review_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'vendor').mkdir()
            (root / 'vendor' / 'analog.lib').write_text('.include "../common.lib"\n.subckt AMP IN OUT VCC VEE\nR1 IN OUT 1k\n.ends\n.model SWITCH NMOS(VTO=2)\n')
            (root / 'common.lib').write_text('.model DX D(IS=1p)\n')
            index = scan_collection(root)
            self.assertEqual(index['counts']['declarations'], 3)
            amp = search_entries(index, 'amp vendor')[0]
            self.assertEqual(amp['pins'], ['IN', 'OUT', 'VCC', 'VEE'])
            self.assertEqual(amp['dependencies_not_loaded'], ['"../common.lib"'])
            self.assertEqual(amp['compatibility'], 'not_qualified')
            self.assertNotIn('original_source', json.dumps(index))
            review = read_entry(index, amp['id'])
            self.assertIn('.include', review['original_source'])
            self.assertEqual(review['execution'], 'not_approved')
            self.assertEqual(len(search_entries(index, kind='model')), 2)
            json.dumps(index)

    def test_limits_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(3):
                (root / f'{number}.lib').write_text(f'.model D{number} D\n')
            self.assertTrue(scan_collection(root, maximum_files=1)['truncated'])
            self.assertTrue(scan_collection(root, maximum_bytes=1)['truncated'])
            self.assertTrue(scan_collection(root, maximum_entries=1)['truncated'])
            index = scan_collection(root, maximum_file_bytes=1)
            self.assertEqual(len(index['issues']), 3)
            self.assertFalse(index['entries'])
            with self.assertRaises(ValueError): scan_collection(root, maximum_files=0)

    def test_changed_file_and_forged_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model = root / 'part.lib'
            model.write_text('.model D1 D\n'); index = scan_collection(root)
            model.write_text('.model D2 D\n')
            with self.assertRaisesRegex(ValueError, 'changed'): read_entry(index, index['entries'][0])
            index['entries'][0]['path'] = '../outside.lib'
            with self.assertRaisesRegex(ValueError, 'inside'): read_entry(index, index['entries'][0])

    def test_bad_files_have_issues(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bad.lib').write_bytes(b'\x00encrypted')
            (root / 'readme.lib').write_text('No declarations')
            index = scan_collection(root)
            self.assertEqual(len(index['issues']), 2)
            self.assertTrue(all('parse_issue' in record for record in index['files']))

    def test_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as external:
            root = Path(folder); outside = Path(external)
            (outside / 'part.lib').write_text('.model SECRET D\n')
            try:
                (root / 'escape').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('Host does not permit creating symlinks')
            index = scan_collection(root)
            self.assertFalse(index['entries'])
            self.assertTrue(index['issues'])


if __name__ == '__main__': unittest.main()
