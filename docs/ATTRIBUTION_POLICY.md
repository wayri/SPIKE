# SPIKE Attribution and Publication Policy

SPIKE source commits, tags, and releases are authored and published only as the
GitHub account `wayri`.

## Canonical identity

Use this repository-local Git identity:

```text
user.name=wayri
user.email=16292067+wayri@users.noreply.github.com
user.useConfigOnly=true
```

Before committing, both commands must report that identity:

```powershell
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Do not use a work account, work email address, alternate author, committer, DCO
sign-off, tagger, or publisher for SPIKE. Do not add a work email to `wayri` to
transfer attribution.

## Push enforcement

The repository owns `.githooks/pre-push`, which runs
`scripts/check_push_identity.py`. The guard verifies the live local author and
committer identity, reads Git's proposed ref updates from standard input, and
checks only commits reachable from the proposed tips that are absent from the
known remote refs. Each outgoing commit must have the canonical author, a
canonical or GitHub `web-flow` committer, and only canonical DCO sign-offs.

Enable the repo-owned hooks only when no other hooks path is configured:

```powershell
git config --show-origin --get-all core.hooksPath
git config --local core.hooksPath .githooks
```

Do not replace an existing hooks path. Integrate the guard into that hook chain
instead. Hook installation is local state and is not implied by checking in the
hook files.

## Release enforcement

`scripts/release_automation.py` applies the publication guard only when a
release will be published. Ordinary contributor builds and nonpublishing source
checks remain available.

Before any release mutation, the guard verifies through GitHub that:

- the repository is exactly `wayri/SPIKE`;
- a local publisher is authenticated as `wayri`, or a GitHub Actions run was
  started and retriggered by `wayri` in that repository for the candidate SHA;
- the candidate commit is linked to `wayri` and carries the canonical author
  name and noreply email; and
- its committer is either the same canonical identity or GitHub's `web-flow`
  merge identity for a canonical `wayri` author.

The release workflow also checks GitHub's protected actor environment before
building publication artifacts. The Python guard independently reads the
workflow-run and candidate-commit records through the GitHub API; a free-form
actor environment variable is not accepted as proof.

Identity checks supplement the existing version, tag, package completeness,
checksum, draft, and immutable-release checks. They do not correct historical
commit metadata.

## Historical records

Published history is not rewritten during routine development. A correction
must be prepared in an isolated mirror, preserve original refs separately,
show the complete old-to-new mapping, retain every tree, identify invalidated
signatures and releases, pass repository integrity checks, and receive an
explicit publication decision. Removing an email from another GitHub account
may change profile attribution after GitHub refreshes its contribution graph,
but it does not change the author, committer, or DCO text stored in a commit.
