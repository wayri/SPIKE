# Python IDE UI verification — 2026-10-03

## Scope

SPIKE's integrated Python IDE now has a fixed add-tab button, explicit draft,
unsaved, saving, saved, and save-failure states, debounced local recovery
snapshots, a restore-copy panel, open-buffer navigation, folder history, and
read-only discovery of existing Git worktrees. Panels can be hidden or
collapsed, tabs scroll independently of the add button, and controls use the
shared theme palette with compact laptop layouts. Recovery does not write to
the original script. Existing execution and result-admission contracts remain
unchanged.

## Passing checks

- `npm.cmd run test:python-workspace`: workspace interactions, saves during
  edits, failed saves, browser downloads, recovery persistence and corruption,
  storage failures, explorer refresh, root selection, and template checks.
- Project Python environment:
  `python -m unittest tests.python.test_script_workspace_files tests.python.test_script_workspace_worktrees -v`:
  12 tests passed, including a real Git repository with a linked worktree.
- TypeScript `tsc --noEmit`, production `npm.cmd run build`, architecture checks,
  parser checks, generated-help checks, and help tests passed.
- Browser fixture `scripts/fixtures/python-ide.html`: dark, light, and high
  contrast themes; 1366 × 768 and 900 × 620 CSS viewports; overflowing tabs with
  long names; keyboard tab navigation; sidebar hiding; output collapse; and
  restoration into a separate `.recovered.py` unsaved tab were checked.

Local screenshots were saved as `python-ide-wide.png` and
`python-ide-narrow.png`. They show browser previews,
not native desktop acceptance. The temporary browser viewport override was
reset after capture.

## Broader suite and native limits

The project-environment Python suite ran 2,395 tests in 500.780 seconds and
reported one failure, two errors, and 13 skips. Both errors involved SQLite
model-library cache access outside the writable workspace. Both affected tests
passed when rerun with `SPIKE_MODEL_INDEX_PATH` pointing to a writable workspace
cache. The remaining failure is
`test_current_candidate_is_technical_but_externally_blocked`: its expected
release blocker `PUBLIC_RELEASE_DEPENDENCY_APPROVAL_REQUIRED` was absent. This
separate release-readiness assertion was left unchanged; the full suite is not
reported as passing.

A fresh native Tauri build failed while creating the Rust library archive with
Windows error 112 (insufficient disk space). Native visual checking with an
existing local binary encountered the locked Windows desktop; desktop input
stopped. Native dialogs, fresh native rendering, and Cargo checks are therefore
not qualified by this record.

## SPIKE-Em staged update

The separate SPIKE-Em workspace shown in the user's screenshot has an
independent eight-file IDE update staged under `.codex_emide_stage/`.
`README.md` describes the files and `SPIKE_EM_IDE_REVIEW.patch` contains the
review diff. Staged resilience tests, workspace-model checks, and overlay
TypeScript checks passed. Its interpreter selection, research library, and
script output features are preserved.

The owner subsequently requested pushing to both projects. After confirming
the existing file hashes matched the review diff and preserving originals,
the eight replacements were applied to SPIKE-Em. Its workspace and resilience
tests, TypeScript check, and production build passed. Its local repository has
a local Git history on codex/spike-em and no configured remote, following the owner's offline instruction. Native
SPIKE-Em UI success is not claimed, and none of these UI checks establish
numerical solver validity.
