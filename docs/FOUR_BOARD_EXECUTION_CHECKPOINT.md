# Four-board execution checkpoint — 2026-09-06

Immediate target: four Marble-scale boards, retaining the longer-term 30-board target.

## Executed evidence

- Fixed canonical `board::connector` harness endpoint parsing: connector IDs
  are preserved, with legacy single-colon endpoints still supported.
- Four-board translation/rotation, distinct design identity and three-harness
  projection regression checks passed. The fixture uses Marble-scale envelopes,
  not loaded Marble geometry. Harness visualization tests, 36 assembly/backend
  tests and the frontend production build passed.

- Four independent SI uniform-channel reference jobs execute numerically with
  four distinct board namespaces. This is not four Marble geometry extractions.
- Batch preflight now validates every job's suite structure and aggregate lane
  and frequency counts before any channel execution. An invalid final board or
  an over-budget batch cannot waste the earlier board solves.
- Numeric-result budgets remain enforced by the existing runner; this change
  does not establish a hard process-memory limit or general out-of-core solving.
- Three focused four-board tests passed; the latest combined multiboard and SI
  runner regression run passed 49 tests. Reproduce with:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_four_board_execution tests.python.test_multiboard_analysis tests.python.test_si_protocol_test_runner
```

## Still required before saying four Marble boards work end to end

Follow-up: the assembly editor now mounts an explicit independent-SI batch
panel. Each board receives its own imported suite JSON; unassigned boards are
skipped. Runs show per-board namespaces/status and export the complete result.
Dirty assembly edits block dispatch. These local setups/results are explicitly
session-only, not silently claimed to persist in the native project. TypeScript,
batch wiring and harness projection checks pass; native interactive testing is
still required. It does not dispatch PI or solve harness coupling.

The frontend production build now passes. The evidence builder now streams the
canonical digest instead of constructing a second complete JSON copy, with a
hard 128 MiB admission ceiling enforced during encoding. The 79,878,048-byte
Marble request fits that ceiling; 34 focused evidence/geometry tests passed.
A fresh full Marble preflight has not yet been observed to complete, so this
is not proof that Marble is ready to solve. The earlier 500-branch limit and
truncated preview remain unresolved until a fresh run verifies otherwise.

- Actual four-board import/save/reopen and interactive viewport measurements.
- Resolve single-Marble DC transport/branch limits; run reviewed terminals and
  coarse/fine convergence before scaling dispatch to four boards.
- Exercise the new assembly SI batch panel natively, including per-board setup,
  result inspection, exporting and error recovery; add interactive plot drilling.
- Harness electrical coupling, cross-board fields and EMI domain generation
  require their own executable solver integration. Independent jobs exclude them.
- Install a rebuilt package and verify exact runtime and user workflows.
