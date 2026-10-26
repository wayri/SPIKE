# 0.4.2 release-blocker follow-up — 26 October 2026

Status: source-only follow-up. No installer, installation, tag or release changed.

## Debugger repair

`python/spike_core/script_debug_child.py` now disables user tracing as soon as
script execution unwinds, before traceback formatting and terminal-state
bookkeeping. Previously the exception formatter itself ran under the user
tracer, performing unnecessary path checks and exposing reporting to debugger
commands. A deterministic regression checks that traceback reporting executes
without an active tracer and that the failed state and stderr are retained.
The regression failed before the change and passed after it. No timeouts or
acceptance tolerances changed. The original full-suite timing failure did not
reproduce before this fix; its exact historical cause remains unproven.

## Executed checks

Python 3.12.9 from `.venv`, `-B`, with TEMP/TMP in the existing task-owned
D: candidate scratch directory. Tests requiring child processes ran outside the
restricted execution sandbox.

| Check | Actual result |
| --- | --- |
| `test_python_debug` | 17 tests passed; repeated by integration owner |
| `test_multiport_native_evidence` | 7 tests passed; combined debug/evidence run: 24 tests in 10.467 s |
| `test_rlgc_line_junction_contract` and `test_rlgc_loaded_cascade_contract` | 6 tests passed in 5.316 s, unchanged 60-second subprocess deadlines |
| `TetraStokesTests.test_affine_sheared_quadratic_manufactured_solution` | Passed in 10.612 s, unchanged three meshes, accuracy criteria and runtime controls |
| `scripts/check_architecture.py` | Passed |
| `scripts/check_parity_backlog.py` | Failed: `Stale native evidence validator` |

The first sandboxed SI contract invocation stalled. Its exact two-process tree
was identified by PID and full command line and terminated; the subsequent
unsandboxed run passed. This does not establish the cause of the historical
full-suite CLI timeouts. The original failed full-suite log remains valid
historical evidence; no new full-suite success is claimed.

The multiport validator tests exercise synthetic validator fixtures. They are
not fresh interactive native observations. SI08-S05 still requires new
source-bound wide/narrow, invalidation, failure and recovery evidence. Existing
receipts and fail-closed validators were preserved; no hash-only rebinding or
qualification promotion was performed.

## Candidate and publication limits

The previously built [r1 candidate](RELEASE_042_CANDIDATE_20261026.md) predates
this debugger fix. Its frozen worker does not contain this change; its immutable
artifact hashes and earlier checks remain historical. Rebuild and verify a new
worker from stable source before installing or distributing this repair.
A complete stable-input required suite, fresh native UI evidence, knowledgeable
human numerical review and final Windows/Linux/macOS delivery qualification
remain open. Focused passing checks do not replace these gates.

## Source identity

- `python/spike_core/script_debug_child.py`: `1fa8a7bb2313305c2f57fc46bdadc83b121fb07eb87f7b0de430ba46ca3db194`
- `tests/python/test_python_debug.py`: `c762382c7073ef4dc8d7f80fdc5b0716d157f7d9230e6791e45b59bcfef4b7ee`
