# SPDX-License-Identifier: Apache-2.0
"""Release publication must reject partial or altered package sets."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/release_automation.py'
spec = importlib.util.spec_from_file_location('release_automation', SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseAutomationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.folder = self.root / 'dist-release'
        self.folder.mkdir()
        self.names = ['SPIKE_0.3.0_x64-setup.exe',
                      'SPIKE_0.3.0_linux-x86_64_EXPERIMENTAL.flatpak',
                      'SPIKE_0.3.0_macos-arm64_EXPERIMENTAL.dmg',
                      'SPIKE_0.3.0_macos-x86_64_EXPERIMENTAL.dmg']
        for name in self.names:
            payload = ('fixture ' + name).encode()
            (self.folder / name).write_bytes(payload)
            (self.folder / (name + '.sha256')).write_text(hashlib.sha256(payload).hexdigest() + '  ' + name + '\n')

    def tearDown(self):
        self.directory.cleanup()

    def test_complete_set_has_four_packages_and_four_checksums(self):
        self.assertEqual(len(release.packages(self.folder, '0.3.0')), 8)

    def test_missing_architecture_is_rejected(self):
        (self.folder / self.names[-1]).unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete package set'):
            release.packages(self.folder, '0.3.0')

    def test_altered_binary_is_rejected(self):
        (self.folder / self.names[0]).write_bytes(b'changed after verification')
        with self.assertRaisesRegex(ValueError, 'Checksum verification failed'):
            release.packages(self.folder, '0.3.0')

    def test_wrong_checksum_filename_is_rejected(self):
        checksum = self.folder / (self.names[0] + '.sha256')
        checksum.write_text(checksum.read_text().replace(self.names[0], 'another.exe'))
        with self.assertRaisesRegex(ValueError, 'Checksum verification failed'):
            release.packages(self.folder, '0.3.0')

    def test_upload_failure_keeps_release_draft(self):
        calls = []
        def fake_gh(*args, **kwargs):
            calls.append(args)
            if args[0] == 'api':
                return '[[]]'
            if args[:2] == ('release', 'upload'):
                raise RuntimeError('upload failed')
            return ''
        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.0', 'RELEASE_COMMIT': 'a' * 40, 'GITHUB_REPOSITORY': 'example/spike'}), \
             patch.object(release, 'version', return_value='0.3.0'), \
             patch.object(release, 'tag_commit', return_value=None), \
             patch.object(release, 'gh', side_effect=fake_gh):
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                release.publish(self.root)
        self.assertTrue(any(call[:2] == ('release', 'create') and '--draft' in call for call in calls))
        self.assertFalse(any(call[:2] == ('release', 'edit') for call in calls))

    def test_tag_mismatch_rejected_before_github(self):
        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.4.0'}), \
             patch.object(release, 'version', return_value='0.3.0'), \
             patch.object(release, 'gh') as github:
            with self.assertRaisesRegex(ValueError, 'tag must be'):
                release.check(self.root)
            github.assert_not_called()

    def test_versioned_notes_keep_llm_review_disclosure_and_portable_links(self):
        notes = self.root / 'docs' / 'releases' / 'v0.3.0.md'
        notes.parent.mkdir(parents=True)
        notes.write_text('Largely LLM-driven under human review. Early community preview.\n'
                         '[Disclosure](../LLM_DEVELOPMENT.md)\n'
                         '[License](../../LICENSE)\n', encoding='utf-8')
        published_notes = []

        def fake_gh(*args, **kwargs):
            if args[0] == 'api':
                return '[[]]'
            if '--notes-file' in args:
                published_notes.append(Path(args[args.index('--notes-file') + 1]).read_text())
            return ''

        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.0', 'RELEASE_COMMIT': 'a' * 40,
                                     'GITHUB_REPOSITORY': 'example/spike'}), \
                patch.object(release, 'version', return_value='0.3.0'), \
                patch.object(release, 'tag_commit', return_value=None), \
                patch.object(release, 'gh', side_effect=fake_gh):
            release.publish(self.root)
        self.assertEqual(len(published_notes), 2)
        for content in published_notes:
            self.assertIn('LLM-driven under human review', content)
            self.assertIn('https://github.com/example/spike/blob/v0.3.0/docs/LLM_DEVELOPMENT.md', content)
            self.assertIn('https://github.com/example/spike/blob/v0.3.0/LICENSE', content)

    def test_version_drift_is_rejected(self):
        paths = {
            'app/package.json': json.dumps({'version': '0.3.0'}),
            'app/src/appVersion.ts': 'export const APP_VERSION = "0.3.0";\n',
            'app/package-lock.json': json.dumps({'version': '0.3.0', 'packages': {'': {'version': '0.3.0'}}}),
            'app/src-tauri/tauri.conf.json': json.dumps({'version': '0.3.1'}),
            'app/src-tauri/Cargo.toml': '[package]\nversion = "0.3.0"\n',
            'python/spike_core/__init__.py': '__version__ = "0.3.0"\n',
        }
        for name, text in paths.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        with self.assertRaisesRegex(ValueError, 'Tauri version'):
            release.version(self.root)
        (self.root / 'app/src-tauri/tauri.conf.json').write_text(json.dumps({'version': '0.3.0'}))
        (self.root / 'app/src/appVersion.ts').write_text('export const APP_VERSION = "0.2.9";\n')
        with self.assertRaisesRegex(ValueError, 'UI version'):
            release.version(self.root)


if __name__ == '__main__':
    unittest.main()
