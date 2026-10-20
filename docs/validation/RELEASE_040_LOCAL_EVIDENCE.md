<!-- SPDX-License-Identifier: Apache-2.0 -->

# 0.4.0-alpha.1 local execution evidence boundary

Status: experimental prerelease evidence inventory; knowledgeable human review
remains pending. This record does not waive any technical, numerical, licensing,
attribution, packaging or release gate.

## Publication boundary

The release source does not include the repository-root generated run directory.
That local directory contains browser profiles, private runtime state and about
3 GB of logs and generated artifacts, so publishing it wholesale is prohibited.
References in older documents to files below that directory identify local
development records only. They are not downloadable release artifacts and must
not be treated as independently checkable evidence from the source archive.

The public evidence for this prerelease consists of checked-in source, fixtures,
tests, validation summaries and exact reproduction commands. A command's output
directory is caller-owned scratch storage and is never evidence by itself.
Generated results become public evidence only after a reviewed, sanitized,
licensed summary or fixture is deliberately retained in the source tree.

## Interpretation of migrated references

- **Reproducible:** the document names checked-in source, fixtures and a command
  or test that a reviewer can run in a supported environment.
- **Retained summary:** a checked-in validation document records the method,
  inputs, acceptance criteria, result and remaining limits. Raw local logs may
  still be absent.
- **Local record only:** a historical number or screenshot was observed in a
  developer run, but its raw record is excluded. It remains provisional and is
  not a release qualification claim until reproduced and reviewed.
- **External engine evidence:** a local engine working directory may contain
  licensed or private inputs. Only checked-in normalized fixtures or summaries
  are public evidence.

## Reproduction entry points

Run commands from the repository root and choose a fresh local destination
outside the source snapshot when a script accepts `--output` or `--run-dir`.

```powershell
python scripts/check_architecture.py
python scripts/check_documentation.py
python -m unittest discover -s tests/python -v
cd app
npm.cmd ci
npm.cmd exec tsc -- --noEmit
npm.cmd run test:field-volume
```

Domain validation documents name narrower scripts, fixtures and acceptance
criteria. External runtimes, licensed tools and platform-specific checks remain
conditional on their documented installations. The release must record the
exact source revision, dependency identity, command and sanitized result before
claiming a rerun.

## Documents covered by the source audit

The 45 documents identified by the 2026-10-20 source audit are covered by this
boundary. Their historical generated-path references fall into the categories
above. Code-form paths describe non-shipped local records or scratch destinations;
they are not links. Any Markdown link must resolve to checked-in evidence or an
immutable public artifact.

This manifest does not validate the historical claims. In particular, raw solver
accuracy, mesher performance, viewport memory, external SU2/openEMS, retained EM,
thermal/CalculiX, whole-suite and video/browser records excluded from the source
remain local-record evidence. Their checked-in summaries preserve limitations,
but release qualification requires the named reruns and pending human review.

## Release blockers unaffected by this boundary

- Pending knowledgeable human review remains explicit for numerical code and
  experimental solver claims.
- Missing or failed reproduction, source binding, convergence, applicability or
  environment checks remain failures; this manifest cannot convert them to passes.
- Redistribution rights and provenance for included binaries, media and datasets
  require separate approval.
- Secrets, browser profiles, private keys and private runtime state must never be
  copied from local run storage into release evidence.
- The release must pass the current architecture, documentation, version,
  identity, packaging and clean-worktree gates on the exact candidate revision.

Until those gates pass, this document supports an experimental prerelease review
only. It does not establish solver qualification or publication readiness.
