# SPIKE performance target and evidence

## Target

Optimize the complete supported desktop without removing functions, board
objects, saved fields, selection identities, undo states or analysis capabilities.
The recommended running specification is 32 GB system RAM. Retain the lower
baseline below as an optimization and resource-pressure testing target.
The baseline is a 16 GB machine with only 10 GB available to SPIKE, a CPU from
2022 or later, and integrated graphics. Test both distinct designs and repeated
occurrences: a server motherboard, CPU interposer, and 10 and 20 Marble/White
Rabbit class boards. These are acceptance workloads, not currently certified
capacity claims. A retained source/model fixture is required for each claim.

Keep Three.js/WebGL as the portable presentation boundary across Intel, AMD and
NVIDIA. Integrated graphics is the baseline; discrete graphics provides optional
headroom. GPU rendering and optional numerical CUDA execution are separate.

## Measurement contract

Record the exact executable/source revision, OS, CPU, GPU/driver, physical and
available RAM, screen size, board/model counts and fixture digest for each run.
Measure cold and warm open time, event latency, active navigation frame cadence,
desktop-tree private memory, process commit, dedicated/shared GPU counters and
worker peaks. Report GPU and process counters separately where allocations may
overlap; do not add them into a misleading unique-memory total. Include loading
and saving peaks, not just settled idle memory. Keep reserve inside the 10 GB
available budget; a 10 GB steady state leaves no room for load/save or workers.

Initial engineering acceptance thresholds to validate on the baseline:

- All objects, models, per-occurrence layers/nets, explicit connector mappings,
  selection, probes, results, undo/redo and save/reopen retain their behavior.
- Navigation sustains at least 30 FPS; ordinary UI actions have p95 event-to-
  response latency below 100 ms. Record worst stalls and loading progress.
- No crash, WebGL loss loop or out-of-memory failure through 20 repeated
  open/interact/save/close cycles. After warmup and settling, memory must plateau
  rather than increase with every cycle. Record ranges and retained owners.
- Workload admission accounts for worker and integrated-GPU pressure within the
  available budget. Full-wave and other numerical runs still require their own
  accuracy and capacity qualification; a render benchmark does not qualify them.

## Implemented first pass (2026-10-12)

`App.tsx` stores admitted immutable assembly domains by reference in its 50-state
undo history. Presentation edits no longer clone every retained board, package
shape and model index into each entry. Assembly edits must replace their root
and changed branches. Restoring an internal snapshot uses those admitted values
directly, preserving unknown fields and unchanged identities. External project
input still passes the admission guards. Project loading opts into sharing the
already admitted design records with the retained package; other normalization
callers keep defensive copies.

The history regression executes the actual App snapshot/restore/undo/redo
functions with 20 synthetic retained designs and 60 presentation edits. Its 50
retained entries share three heavy-domain identities representing 1,067,328 JSON
bytes. JSON size is an explanatory payload measure, not JavaScript heap size.

`assemblyBoardScene.ts` creates one local pad geometry for its physical copper
layers, while retaining a separate mesh, transform and source pick per layer.
Copper materials share only within an occurrence/kind/layer/net/highlight scope.
Sibling occurrences retain independent resources. Existing batching, all source
objects and exact picking remain. Teardown disposes shared resources once.

The synthetic 64-pad, 30-layer regression retains all 1,920 pad/layer picks.
Source pad geometry uses 64 allocations and 8,960 attribute/index bytes instead
of 1,920 allocations and 268,800 bytes. Source materials use 60 allocations
instead of 1,920. Merged display geometry, scene nodes, GPU overhead and whole-
process RAM are excluded from these counts. These are deterministic allocation
checks, not installed-app frame-rate or 20-real-board memory measurements.

The development host reports an Intel Core Ultra 7 255H, 31.5 GiB physical RAM
and Intel Arc 140T graphics (driver 32.0.101.8991). The headless checks were not
run under a 10 GB memory constraint and do not establish the baseline capacity.

## First-pass verification

Focused history, MCAD, large-scene, assembly layout/nets/workspace, parser,
project package/snapshot, TypeScript, architecture and control-standard checks
passed. The production frontend build passed. Native Cargo tests reported 48
passed and one ignored live-counter test. The Windows sandbox denied realpath
access for Vite and Python temporary directories; the final build and native
Python run used approved unrestricted execution with the project environment.

Full Python discovery completed: 3,400 tests in 916.229 seconds, one failure,
five errors, 50 skips. The log is
the unbundled local `optimization-python-native-tests-20261012.log` record. The two failure causes
were reproduced independently: the public-release gate rejects a missing or
duplicate schema ID in `assembly-em-request-v1.schema.json`; four SI analytical
tests use a fixture missing `signal_width_m`, now required by
`si_coupled_channel.py`. Neither implementation was modified by this performance
pass. The complete repository gate is therefore not green. Do not treat the
focused passes as full release qualification.

## Stage-two verification gate

The focused multiboard gate and isolated memory proof are recorded in
[multiboard optimization verification](validation/MULTIBOARD_OPTIMIZATION_GATE_20261012.md).
After the user resumed native verification, the current-source host loaded the
retained Arduino/relay assembly. Native 3D rendering, independent board
selection, per-board layers/nets and explicit connector mappings were observed.
Actual 2D verification exposed a blank UNO occurrence despite visible layers;
the initially labelled 2D capture was a top camera view in 3D. A renderer fix now
retains parsed vector art while SVG alignment is pending or unavailable. A fresh
native load reached 100% import quality with both populated 2D boards and
independent selection. The final post-toggle 3D capture was interrupted by
physical Escape; prior post-optimization 3D captures remain the recorded evidence.
Automated analysis, persistence and handling checks also passed. Native pointer
automation was unavailable at the host/WebView boundary; narrow-window and
native save/reopen checks remain separate from this bounded gate.

## Implemented second pass (2026-10-12)

`mergedGeometryTransforms.ts` owns exact transformed buffer merging for assembly
copper and residual imported mesh batches. Compatible immutable sources are
merged once; position, normal and tangent transforms write through subarray views
into the final allocation. This removes the temporary transformed source copies.
Morph, interleaved, normalized, instanced and unusual attribute layouts retain
the prior clone/transform/merge fallback. Failed preparations dispose owned
temporary/final geometry and preserve the original error. Source picks, matrices,
materials, occurrence scope and draw-call grouping remain in their existing owners.

The production-helper regression compares all attribute and index bytes with
the prior algorithm, plus metadata, bounds, groups, draw ranges, error/fallback
behavior and source immutability. Its instrumented synthetic 60,000-vertex,
16-occurrence case observes zero source clones on the fast path versus 16 on
the reference path, removing 51,840,000 temporary attribute/index bytes per round.
Timing samples alternate execution order and have no pass threshold. These are
allocation and equivalence measurements, not a certified whole-app speedup,
process-RAM reduction or 20-real-board capacity result.

Focused geometry, large-scene, assembly layout/nets/workspace/tools/handling,
field-study, persistence, history, MCAD, parser and architecture checks passed,
as did TypeScript and the production build. Current native tests report 54 passed
and one ignored. An independent read-only review found no actionable issue.
Broad Python discovery completed: 3,434 tests in 995.826 seconds, one failure,
five errors and 50 skips, with the same schema and SI fixture causes above.
Log: unbundled local record `optimization-stage2-python-tests-20261012.log`. Reproduce the exact geometry check with
`npm run test:geometry-batching` from `app`; it is also part of `test:large-scene`.

## Remaining work

The [gamma viewport pass](validation/VIEWPORT_GAMMA_OPTIMIZATION_20261018.md)
removes full source-array traversal from warm indexed picks, reuses assembly 2D
artwork through camera changes, and repairs shader/nested-Scene texture ownership
and accounting. It records allocation/lifecycle checks separately from pending
native frame/event and capacity evidence. The work targets `0.3.12-gamma.1`.

1. Run the baseline native workloads with real board/model fixtures and retained
   counter/event traces. Locate the next bottleneck from those profiles.
2. Profile per-occurrence procedural geometry and imported batch preparation;
   consider shared immutable prepared geometry with explicit ownership before
   changing resource lifetimes. Avoid reducing electrical or model detail.
3. Profile retained studies/results in generic history: they still use defensive
   clones. Extend sharing only after each writer's mutation contract is audited.
4. Measure backend non-active design validation, IPC/decompression, normalized
   source copies and save-time merging. Preserve every validation and field.
5. Verify installed WebView/GPU recovery, narrow/wide interaction, distinct
   designs, repeated occurrences and long-duration memory behavior. Native
   screenshots and traces are required before marking the target achieved.

Reproduce focused checks from `app`: `npm run test:history-memory`,
`npm run test:large-scene`, `npm run test:assembly-layout`,
`npm run test:assembly-nets`, `npm run test:assembly-workspace`,
`npm run test:project-snapshot`, `npm run test:mcad`,
`npm run test:parser`, `npm run test:project`, `npm exec tsc -- --noEmit`,
and `npm run check:architecture`. Use `npm.cmd` on Windows. Follow
`CONTRIBUTING.md` for the Python and native gates. No installed desktop scaling
claim follows merely from these headless checks.
