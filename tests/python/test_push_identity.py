# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch

from scripts import check_push_identity as identity


CANONICAL = 'wayri <16292067+wayri@users.noreply.github.com>'


class PushIdentityTests(unittest.TestCase):
    def test_parse_updates_rejects_malformed_input(self):
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            identity.parse_updates('refs/heads/main only-two-fields')

    @patch.object(identity, 'git')
    def test_local_work_account_override_is_rejected(self, git):
        git.return_value = 'y-w-r <work@example.invalid> 1 +0000\n'
        with self.assertRaisesRegex(ValueError, 'author identity'):
            identity.require_local_identity()

    @patch.object(identity, 'commit_metadata')
    def test_wrong_outgoing_author_is_rejected(self, metadata):
        metadata.return_value = (
            'y-w-r <work@example.invalid>', CANONICAL, [CANONICAL]
        )
        with self.assertRaisesRegex(ValueError, 'author must be'):
            identity.require_commit_identity('a' * 40)

    @patch.object(identity, 'commit_metadata')
    def test_wrong_dco_signoff_is_rejected(self, metadata):
        metadata.return_value = (
            CANONICAL, CANONICAL, ['y-w-r <work@example.invalid>']
        )
        with self.assertRaisesRegex(ValueError, 'noncanonical DCO'):
            identity.require_commit_identity('a' * 40)

    @patch.object(identity, 'commit_metadata')
    def test_canonical_direct_commit_passes(self, metadata):
        metadata.return_value = (CANONICAL, CANONICAL, [CANONICAL])
        identity.require_commit_identity('a' * 40)

    @patch.object(identity, 'commit_metadata')
    def test_canonical_author_with_github_committer_passes(self, metadata):
        metadata.return_value = (CANONICAL, identity.GITHUB_COMMITTER, [])
        identity.require_commit_identity('a' * 40)

    @patch.object(identity, 'git')
    def test_outgoing_commits_exclude_known_remote_tips(self, git):
        local = 'a' * 40
        remote = 'b' * 40
        tracked = 'c' * 40
        git.side_effect = [local + '\n', tracked + '\n', 'd' * 40 + '\n']
        updates = [('refs/heads/main', local, 'refs/heads/main', remote)]
        self.assertEqual(identity.outgoing_commits('origin', updates), ['d' * 40])
        self.assertEqual(
            git.call_args_list[-1].args,
            ('rev-list', '--topo-order', local, '--not', remote, tracked),
        )

    @patch.object(identity, 'require_commit_identity')
    @patch.object(identity, 'outgoing_commits')
    @patch.object(identity, 'require_local_identity')
    def test_check_validates_only_computed_outgoing_commits(self, local, outgoing, commit):
        outgoing.return_value = ['d' * 40]
        line = f"refs/heads/main {'a' * 40} refs/heads/main {'b' * 40}\n"
        self.assertEqual(identity.check('origin', line), ['d' * 40])
        local.assert_called_once_with()
        commit.assert_called_once_with('d' * 40)


if __name__ == '__main__':
    unittest.main()
