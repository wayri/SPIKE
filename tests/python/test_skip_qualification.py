# SPDX-License-Identifier: Apache-2.0
"""The evidence runner must reject skip/xfail/drift, not manufacture closure."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.qualify_skipped_tests import (
    GIT_EXECUTABLE, admitted, baseline_selectors, digest, read_baseline, runtime_snapshot, source_snapshot, test_ids,
)


class SkipQualificationTests(unittest.TestCase):
    def test_baseline_records_include_class_skips(self):
        records = baseline_selectors(
            "test_x (test_one.C.test_x) ... skipped 'runtime'\n"
            "setUpClass (test_two.D) ... skipped 'fixture'\n")
        self.assertEqual(records, ['tests.python.test_one.C.test_x', 'tests.python.test_two.D'])
        for text in ('OK', "test_x (test_one.C.test_x) ... skipped 'x'\n" * 2):
            with self.assertRaises(ValueError):
                baseline_selectors(text)

    def test_empty_duplicate_and_source_drift_rejected(self):
        result = unittest.TestResult()
        self.assertFalse(admitted(result, [], {}, {}))
        result.testsRun = 2
        self.assertFalse(admitted(result, ['a', 'a'], {}, {}))
        result.testsRun = 1
        self.assertTrue(admitted(result, ['a'], {'hash': 'a'}, {'hash': 'a'}))
        self.assertFalse(admitted(result, ['a'], {'hash': 'a'}, {'hash': 'b'}))

    def test_non_python_project_fixture_and_script_drift_are_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('examples/device.json', 'scripts/probe.py', 'build_kernel.ps1', 'build/cache.bin'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('initial')
            with patch('scripts.qualify_skipped_tests.subprocess.run') as listed:
                listed.return_value.stdout = b'examples/device.json\0scripts/probe.py\0build_kernel.ps1\0build/cache.bin\0'
                before = source_snapshot(root)
                self.assertEqual(listed.call_args.args[0][0], GIT_EXECUTABLE)
                (root / 'examples/device.json').write_text('changed')
                self.assertNotEqual(before, source_snapshot(root))
                self.assertEqual(set(before), {'examples/device.json', 'scripts/probe.py', 'build_kernel.ps1'})
                current = source_snapshot(root)
                (root / 'build_kernel.ps1').write_text('changed root script')
                self.assertNotEqual(current, source_snapshot(root))

    def test_parsed_baseline_hash_is_from_same_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.log'
            path.write_text("test_x (test_one.C.test_x) ... skipped 'runtime'\n")
            resolved, selectors, source_hash = read_baseline(path)
            self.assertEqual(selectors, ['tests.python.test_one.C.test_x'])
            self.assertEqual(source_hash, digest(resolved))
            path.write_text("test_y (test_other.D.test_y) ... skipped 'changed'\n")
            self.assertNotEqual(source_hash, digest(resolved))

    def test_runtime_control_and_executable_drift_are_bound(self):
        before = runtime_snapshot()
        with patch.dict(os.environ, {'SPIKES_TEST_LIBRARY': 'changed-runtime.dll'}):
            self.assertNotEqual(before, runtime_snapshot())
        with patch('scripts.qualify_skipped_tests.digest', return_value='changed-executable'):
            self.assertNotEqual(before, runtime_snapshot())

    def test_all_nonpassing_outcomes_rejected(self):
        for outcome in ('skip', 'xfail', 'xpass', 'fail', 'error'):
            class Case(unittest.TestCase):
                def runTest(self):
                    if outcome == 'skip':
                        self.skipTest('real runtime absent')
                    if outcome in ('xfail', 'fail'):
                        self.fail('failure')
                    if outcome == 'error':
                        raise ValueError('error')
            if outcome in ('xfail', 'xpass'):
                Case.runTest = unittest.expectedFailure(Case.runTest)
            suite = unittest.TestSuite([Case()])
            expected = list(test_ids(suite))
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            with self.subTest(outcome=outcome):
                self.assertFalse(admitted(result, expected, {}, {}))


if __name__ == '__main__':
    unittest.main()
