# SPDX-License-Identifier: Apache-2.0
"""Reject SPIKE pushes made by, or containing commits from, another identity."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys


CANONICAL = 'wayri <16292067+wayri@users.noreply.github.com>'
GITHUB_COMMITTER = 'GitHub <noreply@github.com>'
ZERO_SHA = '0' * 40


def git(*args: str, data: str | None = None) -> str:
    result = subprocess.run(
        ['git', *args], input=data, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def identity(value: str) -> str:
    match = re.match(r'^(.*?) (\d+) [+-]\d{4}$', value.strip())
    if not match:
        raise ValueError(f'Cannot parse Git identity: {value.strip()!r}')
    return match.group(1)


def require_local_identity() -> None:
    for kind in ('AUTHOR', 'COMMITTER'):
        actual = identity(git('var', f'GIT_{kind}_IDENT'))
        if actual != CANONICAL:
            raise ValueError(f'Git {kind.lower()} identity must be {CANONICAL}; got {actual}.')


def parse_updates(stream: str) -> list[tuple[str, str, str, str]]:
    updates = []
    for number, line in enumerate(stream.splitlines(), 1):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f'Malformed pre-push input on line {number}.')
        local_ref, local_sha, remote_ref, remote_sha = fields
        if not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (local_sha, remote_sha)):
            raise ValueError(f'Invalid object ID in pre-push input on line {number}.')
        updates.append((local_ref, local_sha, remote_ref, remote_sha))
    return updates


def outgoing_commits(remote: str, updates: list[tuple[str, str, str, str]]) -> list[str]:
    tips = []
    exclusions = set()
    for local_ref, local_sha, remote_ref, remote_sha in updates:
        if local_sha == ZERO_SHA:
            continue
        if not (local_ref.startswith('refs/heads/') or local_ref.startswith('refs/tags/')):
            raise ValueError(f'Unsupported pushed ref: {local_ref}.')
        try:
            tips.append(git('rev-parse', '--verify', f'{local_sha}^{{commit}}').strip())
        except ValueError as error:
            raise ValueError(f'Pushed ref does not resolve to a commit: {local_ref}.') from error
        if remote_sha != ZERO_SHA:
            exclusions.add(remote_sha)
    tracked = git(
        'for-each-ref', '--format=%(objectname)', f'refs/remotes/{remote}/'
    ).splitlines()
    exclusions.update(value for value in tracked if re.fullmatch(r'[0-9a-f]{40}', value))
    if not tips:
        return []
    return git(
        'rev-list', '--topo-order', *tips, '--not', *sorted(exclusions)
    ).splitlines()


def commit_metadata(commit: str) -> tuple[str, str, list[str]]:
    raw = git('cat-file', 'commit', commit)
    headers, _, message = raw.partition('\n\n')
    author = next((line[7:] for line in headers.splitlines() if line.startswith('author ')), '')
    committer = next((line[10:] for line in headers.splitlines() if line.startswith('committer ')), '')
    signoffs = [
        line[len('Signed-off-by:'):].strip()
        for line in message.splitlines()
        if line.lower().startswith('signed-off-by:')
    ]
    return identity(author), identity(committer), signoffs


def require_commit_identity(commit: str) -> None:
    author, committer, signoffs = commit_metadata(commit)
    if author != CANONICAL:
        raise ValueError(f'Outgoing commit {commit} author must be {CANONICAL}; got {author}.')
    if committer not in {CANONICAL, GITHUB_COMMITTER}:
        raise ValueError(
            f'Outgoing commit {commit} committer must be {CANONICAL} or '
            f'{GITHUB_COMMITTER}; got {committer}.'
        )
    invalid = [value for value in signoffs if value != CANONICAL]
    if invalid:
        raise ValueError(f'Outgoing commit {commit} has a noncanonical DCO sign-off: {invalid[0]}.')


def check(remote: str, stream: str) -> list[str]:
    require_local_identity()
    commits = outgoing_commits(remote, parse_updates(stream))
    for commit in commits:
        require_commit_identity(commit)
    return commits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', required=True)
    args = parser.parse_args()
    try:
        checked = check(args.remote, sys.stdin.read())
    except ValueError as error:
        raise SystemExit(f'SPIKE push identity check failed: {error}') from error
    print(f'SPIKE push identity check passed for {len(checked)} outgoing commit(s).')


if __name__ == '__main__':
    main()
