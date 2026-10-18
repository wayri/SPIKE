# SPDX-License-Identifier: Apache-2.0
"""Pinned manufacturer revision boundary without redistributing vendor files."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('vendor_logic_qualification',
    Path(__file__).resolve().parents[4]/'scripts/qualify_spikes_logic_vendor.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VendorLogicQualificationTests(unittest.TestCase):
    def test_unknown_or_changed_revision_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, 'reviewed testbench'):
            module.check_archive('SN74HC20', 'absent', 'absent')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'changed.zip'
            path.write_bytes(b'changed revision')
            with self.assertRaisesRegex(ValueError, 'revision differs'):
                module.check_archive('SN74HC11', path, 'absent')

    def test_public_sources_are_not_installed_models(self):
        self.assertEqual(set(module.MODELS), {'SN74HC10', 'SN74HC11'})
        for member, digest, url, _ in module.MODELS.values():
            self.assertEqual(len(digest), 64)
            self.assertTrue(url.startswith('https://www.ti.com/lit/zip/'))
            self.assertNotIn('/', member)
