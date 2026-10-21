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
             patch.object(release, 'require_publication_identity'), \
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
                patch.object(release, 'require_publication_identity'), \
                patch.object(release, 'tag_commit', return_value=None), \
                patch.object(release, 'gh', side_effect=fake_gh):
            release.publish(self.root)
        self.assertEqual(len(published_notes), 2)
        for content in published_notes:
            self.assertIn('LLM-driven under human review', content)
            self.assertIn('https://github.com/example/spike/blob/v0.3.0/docs/LLM_DEVELOPMENT.md', content)
            self.assertIn('https://github.com/example/spike/blob/v0.3.0/LICENSE', content)

    @staticmethod
    def _candidate(*, author_name='wayri', author_email=release.CANONICAL_EMAIL,
                   author_login='wayri', committer_name='wayri',
                   committer_email=release.CANONICAL_EMAIL, committer_login='wayri'):
        return {
            'sha': 'a' * 40,
            'author': {'login': author_login},
            'committer': {'login': committer_login},
            'commit': {
                'author': {'name': author_name, 'email': author_email},
                'committer': {'name': committer_name, 'email': committer_email},
            },
        }

    def test_nonpublishing_check_does_not_require_publisher_identity(self):
        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.0'}, clear=True), \
                patch.object(release, 'version', return_value='0.3.0'), \
                patch.object(release.subprocess, 'check_output', return_value='a' * 40 + '\n'), \
                patch.object(release, 'gh') as github:
            self.assertEqual(release.check(self.root)['commit'], 'a' * 40)
        github.assert_not_called()

    def test_publish_rejects_wrong_authenticated_account_before_mutation(self):
        calls = []

        def fake_gh(*args, **kwargs):
            calls.append(args)
            if args == ('api', 'user'):
                return json.dumps({'login': 'y-w-r'})
            raise AssertionError(f'unexpected GitHub call: {args}')

        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.0', 'RELEASE_COMMIT': 'a' * 40,
                                     'GITHUB_REPOSITORY': release.CANONICAL_REPOSITORY}, clear=True), \
                patch.object(release, 'version', return_value='0.3.0'), \
                patch.object(release, 'gh', side_effect=fake_gh):
            with self.assertRaisesRegex(ValueError, 'publisher must be wayri'):
                release.publish(self.root)
        self.assertEqual(calls, [('api', 'user')])

    def test_publish_rejects_wrong_commit_identity_before_mutation(self):
        candidate = self._candidate(author_name='y-w-r', author_login='y-w-r')
        calls = []

        def fake_gh(*args, **kwargs):
            calls.append(args)
            if args == ('api', 'user'):
                return json.dumps({'login': 'wayri'})
            if args[:2] == ('api', f'repos/{release.CANONICAL_REPOSITORY}/commits/{"a" * 40}'):
                return json.dumps(candidate)
            raise AssertionError(f'unexpected GitHub call: {args}')

        with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.0', 'RELEASE_COMMIT': 'a' * 40,
                                     'GITHUB_REPOSITORY': release.CANONICAL_REPOSITORY}, clear=True), \
                patch.object(release, 'version', return_value='0.3.0'), \
                patch.object(release, 'gh', side_effect=fake_gh):
            with self.assertRaisesRegex(ValueError, 'author must be wayri'):
                release.publish(self.root)
        self.assertFalse(any(call and call[0] == 'release' for call in calls))

    def test_workflow_identity_uses_run_api_and_rejects_wrong_actor(self):
        run = {'actor': {'login': 'y-w-r'}, 'triggering_actor': {'login': 'wayri'},
               'repository': {'full_name': release.CANONICAL_REPOSITORY}, 'head_sha': 'a' * 40}
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_RUN_ID': '123'}, clear=True), \
                patch.object(release, 'gh', return_value=json.dumps(run)) as github:
            with self.assertRaisesRegex(ValueError, 'actor and triggering actor'):
                release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)
        github.assert_called_once_with('api', f'repos/{release.CANONICAL_REPOSITORY}/actions/runs/123')

    def test_canonical_wayri_identity_passes(self):
        candidate = self._candidate()

        def fake_gh(*args, **kwargs):
            if args == ('api', 'user'):
                return json.dumps({'login': 'wayri'})
            return json.dumps(candidate)

        with patch.dict(os.environ, {}, clear=True), patch.object(release, 'gh', side_effect=fake_gh):
            release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)

    def test_wayri_author_with_github_merge_committer_passes(self):
        candidate = self._candidate(committer_name='GitHub', committer_email='noreply@github.com',
                                    committer_login='web-flow')

        def fake_gh(*args, **kwargs):
            if args == ('api', 'user'):
                return json.dumps({'login': 'wayri'})
            return json.dumps(candidate)

        with patch.dict(os.environ, {}, clear=True), patch.object(release, 'gh', side_effect=fake_gh):
            release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)

    def test_verified_github_display_name_normalization(self):
        candidate = self._candidate(author_name='Yawar', committer_name='GitHub',
                                    committer_email='noreply@github.com', committer_login='web-flow')
        candidate['commit']['verification'] = {'verified': True, 'reason': 'valid'}
        with patch.dict(os.environ, {}, clear=True), patch.object(
                release, 'gh', side_effect=[json.dumps({'login': 'wayri'}), json.dumps(candidate)]):
            release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)

    def test_github_display_name_exception_fails_closed_before_publication(self):
        import copy
        base = self._candidate(author_name='Yawar', committer_name='GitHub',
                               committer_email='noreply@github.com', committer_login='web-flow')
        base['commit']['verification'] = {'verified': True, 'reason': 'valid'}
        mutations = [
            ('author', 'login', 'y-w-r'), ('author', 'login', None),
            ('commit.author', 'email', 'wrong@example.com'),
            ('committer', 'login', 'wayri'), ('commit.committer', 'name', 'Other'),
            ('commit.committer', 'email', 'wrong@example.com'),
            ('commit.verification', 'verified', False),
            ('commit.verification', 'verified', 1),
            ('commit.verification', 'verified', 'true'),
            ('commit.verification', 'verified', None),
            ('commit.verification', 'reason', 'invalid'),
        ]
        for path, key, value in mutations:
            candidate = copy.deepcopy(base)
            target = candidate
            for segment in path.split('.'):
                target = target[segment]
            target[key] = value
            with self.subTest(path=path, key=key, value=value), \
                    patch.dict(os.environ, {}, clear=True), patch.object(
                        release, 'gh', side_effect=[json.dumps({'login': 'wayri'}), json.dumps(candidate)]) as github:
                with self.assertRaises(ValueError):
                    release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)
                self.assertTrue(all(call.args[0] == 'api' for call in github.call_args_list))
        candidate = self._candidate(author_name='Yawar')
        with patch.dict(os.environ, {}, clear=True), patch.object(
                release, 'gh', side_effect=[json.dumps({'login': 'wayri'}), json.dumps(candidate)]):
            with self.assertRaises(ValueError):
                release.require_publication_identity(release.CANONICAL_REPOSITORY, 'a' * 40)

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
