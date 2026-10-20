<!-- SPDX-License-Identifier: Apache-2.0 -->
# Gamma workspace shell and scoped assembly tabs, 2026-10-18

## Scope

Implemented against the current `0.3.12-gamma.1` working tree; preserved unrelated
concurrent changes. No commit, release installation or publication was performed.
No numerical method, geometry source, solver gate or saved project format changed.
The requested 10 GB available-memory/16 GB installed baseline and 32 GB recommended
specification remain targets, not measured acceptance claims for this pass.

## Delivered behavior

- Permanent workspace shortcuts in clean mode; existing classic shortcuts remain.
  Header track sizes match the 52px main row and optional 34px shortcut row.
- Wider central search and 900px dialog, strict match tiers, partial/prefix/fuzzy
  matches, Tab completion, explicit execution, local action frequency/recency
  ranking, pins, and one compact Recent/Most used strip of at most five actions.
  Preferences are bounded (24 pins, 120 action usage entries, counts capped at
  10,000), validated and resilient to unavailable storage. No query log is stored.
- Project-name dropdown exposes existing New/Open/Import/Save/Save As/project,
  result and STEP exports, and project manager. It closes an obstructing command
  menu. Open saved results uses the existing unsaved-change guard.
- Fixed-scope board-occurrence and mechanical-part tabs with individual view
  mode, camera, filter and selection. Detach button or drag outside the window
  creates a presentation root; closing/redocking retains the tab descriptor.
  Up to eight scoped views may be open; this does not reduce assembly board limits.
  Only active docked and detached views render; closed-view CPU caches are evicted.
- The parent owns edits, undo, saves and solver dispatch. Scoped children use
  token/project/revision-bound actions and request CPU geometry only on source
  revision changes. Removed scopes and stale sessions fail closed. Owner loss
  disables owner-dependent controls. Main assembly retains all existing tools.
- Main camera/layout is captured before scoped tabs unmount the main renderer.
  Analysis navigation clears prior board/part/harness/highlight context. Header,
  search and command-menu workspace routes share the existing transition handler.

## Executed checks

- `npm run test:workspace-shell`: header, bridge, hook lifecycle and actual App
  callback integration tests.
- `npm run test:search-sentences`: sentence grammar, completion, command execution,
  disabled/stale actions, learning/pins and local-control discovery.
- Existing `test:assembly-tools`, `test:assembly-nets`, `test:assembly-workspace`,
  `test:assembly-layout`, `test:assembly-handling`, detached tool windows and
  editable shortcut checks passed. Real fixture layer parsing, transformed picks,
  linked-net identity, draft protection and saved result handling remain covered.
- Parser, architecture/button standards, TypeScript and production build passed.
  Build retains existing large chunk/mixed import warnings.
- Native library tests: 70 passed, one ignored. Sandbox-only transport failures
  were resolved by rerunning with the local loopback/application-data access the
  existing native test fixtures require. Full `cargo test` also passed all library, binary and doc-test targets (70
  passed, one ignored; binary/doc targets contain no tests).

## Broad Python outcome

The full required discovery run completed: **4,133 tests, 4,060 passed,
69 skipped, three errors and one failure** (1,077.470 s). It was not a clean
full-suite pass. The three parity-backlog errors reported `stage receipt identity
mismatch` during concurrent parity evidence work. The debugger failure remained
in `starting` while waiting for `paused`; resource contention is a possible cause,
not an established diagnosis. Separate module rechecks passed all **14 parity
backlog** and **8 debugger** tests. No receipt, debugger code or test threshold
was changed in this UI pass.

The raw `workspace-ui-python-validation.log`, `workspace-ui-parity-recheck.log`
and `workspace-ui-debug-recheck.log` are unbundled local records. Rechecks demonstrate current focused
behavior; they do not turn the earlier full run into a pass.

## Native observations and acceptance limits

Continuation used the exact repository gamma debug host with a frozen production
frontend (manifest in the unbundled local `native-gamma-verification-20261018-session2` run).
This prevented concurrent Vite edits from resetting the native test session.

Executed against the retained three-eBrake assembly:

- Native Open selected and loaded the authenticated three-board project.
- Fixed source and stacked-load tabs retained independent board scope.
- Button detach and dragging the source tab beyond the client created native
  windows. Detached 2D/3D, model rendering, component selection and owner inspector
  identity were observed. Dock back and native title-bar close both returned the
  tab with its 3D/selection state. Existing 65-model-gap diagnostic remained.
- Native Save As selected a disposable output path and produced a valid package.
  Production-reader comparison confirms exact AssemblyIR (including occurrence
  and link data), canonical entity ID sequences, source digest and retained
  design IDs. Output: `native-save-roundtrip.spike`, with comparison evidence
  `native-save-validation.json` in the session output directory. Native Open of
  this saved copy reached Project usable with retained models and visible harness;
  screenshot `native-reopened-scene.jpg` records the scene.

The native round trip exposed a real backend bug: rebuilding authoritative v2
from its lossy v1 projection rejected source-native IDs reused across entity
kinds. Saving now validates and uses the retained canonical design during
migration, preserves assembly fields, and synchronizes only its matching active
retained record after import/model enrichment. JSON arrays and hydrated tuples
compare equivalently while keys, values and canonical IDs remain checked.
Malformed duplicate canonical IDs still fail. Independent focused persistence,
assembly-design and v3-package tests passed: **62 tests in 1.928 s** with normal
local application-data/temp access. A sandbox-limited attempt errored and was
stopped; it is not counted as a pass.

Export without results correctly reported that a simulation/result must exist;
no completed native result export is claimed. Import completion, two simultaneous
native sibling windows and the narrower main-window layout remain outstanding.
Scoped transport tests cover sibling isolation, stale revisions, owner loss,
close/reopen races, and the eight-view bound; these do not replace native stress
qualification.

## Large-assembly benchmark preparation and deferral

The user explicitly deferred responsiveness testing until enough RAM is free.
Heartbeat `spike-10-20-board-ram-benchmark` waits for at least 10,000,000,000 free
physical bytes before running. No 10/20-board stress result is claimed here.

`scripts/prepare_large_assembly_memory_fixtures.py` generated and authenticated
intact 10/20-occurrence Marble fixtures and repeated/two-design CM4/Sailor fixtures.
Marble retains its exact 44,993,740-byte source, 997 components, 37,380 tracks,
5,272 pads, 1,374 nets, 3,664 vias, 124 zones and 937 model assignments. Both
packages reopen through production readers with exact occurrence ownership.
The 76,570,879-byte retained design member now uses the existing 512 MiB design
budget; ordinary control JSON remains capped at 64 MiB and digest validation
remains enforced. See the unbundled local `large-board-memory-benchmark/fixtures/manifest.json` record.

Captured loose Marble GLBs lack authenticated package binding metadata and were
not fabricated into artifacts. These fixtures alone do not qualify complete
resolved-model rendering. No retained White Rabbit/server/interposer fixture was
available. Two distinct designs repeated 20 times is not evidence for 20 distinct
large designs. Full latency, process-tree RAM/GPU plateau and crash-free soak
acceptance remains pending. The sampler is
`scripts/measure_native_process_tree.ps1`; its instrumentation self-tests are not
application benchmarks. Observed machine: Core Ultra 7 255H, 32 GB RAM and Intel
Arc 140T integrated graphics.

## Import/export follow-up, 2026-10-18

Native continuation was blocked by Computer Use transport failures (`unknown
screenshotId`, `coordinate input geometry is unavailable`, and an active request).
The previous attempt also ended on physical Escape. These are not evidence of
a SPIKE product defect; native import/export completion and simultaneous sibling
windows remain unverified. Do not reuse stale screenshot coordinates or claim
the transport harness is a native two-window acceptance run.

Code review exposed a separate reproducible result-export defect: a project with
only `thermal.scenario.board_thermal_result` was rejected as having no results,
and its result-free export still retained that output. `projectSnapshotState.ts`
now admits this existing result type and clears it only in the cloned result-free
snapshot, retaining `board_thermal_request` and the live solution. The regression
failed before the fix and passes afterward, including exact result-file round
trip, input preservation, non-mutation, and rejection of the resulting setup-only
snapshot as a result bundle. No solver or result-validation gate was changed.

Rechecked snapshot/result round trips, project persistence artifacts, staged
board import and workspace shell isolation tests: all passed. Native inspection
still used the earlier frozen frontend; it does not verify this new fix in a
renderer. TypeScript and production build passed (existing mixed-import and
large-chunk warnings remain). The updated immutable frontend is
the unbundled local `native-export-followup-20261018/frontend` record, with a SHA-256 manifest alongside
it; use that snapshot for the next native acceptance run.

Further export review reproduced the same rejection for a project whose only
output is a saved coupled multiboard study. Result bundle eligibility now also
recognizes result records in `assembly_ir.extensions["spike.multiboard-studies"]`.
Regression checks cover PI, SI, thermal and EM, exact assembly/link/request/result
round trips, rejection after result omission, and rejection of null or scalar/array
placeholders. This changes export eligibility only; existing solver-result
binding and validation remain authoritative. Snapshot, persistence, import and
workspace shell checks pass. Native confirmation remains blocked: even a fresh
helper session reports another active request before input can be sent.
Production build passed with existing warnings; the updated immutable frontend
is the unbundled local `native-export-followup-20261018/multiboard-frontend` record, with SHA-256
manifest `multiboard-frontend-manifest.json` alongside it.

## Architecture and operator guidance

See `docs/adr/0103-scoped-assembly-view-windows.md`, `docs/SUBSYSTEM_INDEX.md`
and `docs/USER_TASK_SEQUENCES.md`. Run `npm run test:workspace-shell` from `app`
for the new focused acceptance harnesses.
