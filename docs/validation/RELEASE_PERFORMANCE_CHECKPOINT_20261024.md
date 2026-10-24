<!-- SPDX-License-Identifier: Apache-2.0 -->
# Optimized release performance checkpoint - 24 October 2026

## Objective

Continue large-assembly, dense-result and project-loading improvements, produce
an isolated optimized release app, and execute the retained native checks and
10/20-board memory/interaction/plateau benchmarks when Windows CIM reports at
least 6,000,000,000 free physical bytes. Preserve equations, precision,
capabilities, limits, provenance, per-occurrence identity and all solver gates.
The start gate remains distinct from the 16 GB installed / 10 GB available
product target and from hard memory-limit qualification.

## Changes and evidence

- `ASSEMBLY_PROJECTION_PERFORMANCE_20261024.md`: request-local retained-design
  presentation reuse. Thirty synthetic occurrences with 10,000 nets reduce
  retained net-field reads from 600,000 to 20,000 and derived dictionary
  construction from 60 to two. Both dictionaries are read-only and frozen
  before sharing. Mutation/deletion rejection and exact sibling/source identity
  are covered; transforms, occurrence IDs and the first active occurrence stay
  independent. Independent review caught the initially mutable shared-map risk;
  that finding was fixed before source capture.
- `LAYOUT_RESULT_MEMOIZATION_PERFORMANCE_20261024.md`: scalar/vector filtering
  and thinning depend on exact selected result layers, not unrelated controls
  in the visualization object. Forty playback-only updates no longer repeat
  dense scans when all data/filter inputs are unchanged. Layer order, actual
  result/board/net/layer/mode dependencies and display limits remain intact.
  Bounded representative avoided scan work was 39.46--51.88 ms over 40 updates.
- `PORTABLE_VISUAL_LOADING_PERFORMANCE_20261024.md`: GLB preflight now uses the
  existing visual decoder's preallocated exact byte conversion. A 131,164-byte
  synthetic GLB measured 10.6063 to 0.38393 ms median in seven alternating pairs.
  Full converted bytes and malformed/external-URI rejection were verified.
  No security validation, digest, decode stage or resource limit was removed.

These component measurements do not establish native frame rate, end-to-end
project-open speed or general millisecond CFD/multiphysics execution.

## Checks executed

- Harness projection and scene tests, including picking, selection, bounds,
  identity, disposal and frozen-map mutation rejection: passed.
- Full result-performance suite, including geometry masks, SVG batching,
  frame/scalar caches and dense memoization: passed.
- Project persistence and visual byte-conversion tests: passed.
- Board visual bundle tests: passed.
- Board parser regression command: passed.
- Architecture check: passed.
- Independent review found no new stale-result or GLB-validation regression.

## Optimized release build

Source was captured into `output/native-release-20261024/source`: 6,627 files,
336,926,537 bytes, with a SHA-256 manifest in that directory's parent. All
three optimization workstreams were frozen before capture. Later concurrent
main-checkout changes are intentionally absent from the captured build.
The version captured is 0.4.0-alpha.2. Existing locked Node dependencies are
reused through a junction. No shared source, installed app or build output is
overwritten.

The previous chat-owned copied compiler caches under
`output/native-performance-20261024/target/debug/{deps,build,.fingerprint}` were
proven idle and removed after checking their resolved paths. The sealed dev
executable, resources, profile, manifests and native smoke evidence remain.
Shared release dependency caches were copied into the new private target;
shared outputs were not modified. Do not remove other tasks' caches or outputs.

Frontend checking/build and pinned PyInstaller worker packaging passed.
Worker TEMP/TMP point inside this workspace, and all standard qualification
gates remain enabled. The host built using offline/locked Cargo
`--release --features custom-protocol`, with one compiler job and incremental
compilation disabled, in the private target. It embeds the immutable frontend.

The frozen worker build has now passed 15/15 benchmark cases (no failures or
skips), 8/8 source-versus-frozen runtime checks, 508 Python module comparisons
and 263 schema-file comparisons. TypeScript checking passed and Vite production
build passed in 26.30 seconds, retaining the existing large-chunk warning.
Cargo completed the **release profile [optimized]** in 5m 31s. The local
executable is `output/native-release-20261024/target/release/spike-desktop.exe`,
29,129,216 bytes, SHA-256
`e4c54e0545f43aaa3098ad38d9b3ecadccba50e9657f9e3c235cc0b0b3814504`.
It is a local build, not an installed or published release. Python bytecode
optimization/assertion removal was not enabled to manufacture a speed gain.

`output/native-release-20261024/build-manifest.json` records all 6,627 captured
source inputs unchanged and verifies all 1,475 packaged worker files in the
native resource copy. It records embedded frontend hashes, worker manifest
hash and the executable hash. There is no hot reload. After sealing and
confirming no compiler remained, only the new private target's disposable
`deps`, `build` and `.fingerprint` caches were removed; executable, runtime
resources, libraries, source, manifests and logs remain. C: had about 6.04 GB
free afterward. Shared caches/outputs and the prior dev app were not removed.

The optimized release app has not yet been interactively smoke-tested. The
earlier empty dev instance was observed at the known task-owned executable
path. Two graceful-close attempts were blocked by the desktop input guard,
including after refreshing state. Neither attempt was forced or replaced by
process termination, and the instance was left intact. This is a desktop input
availability blocker, not evidence of a SPIKE close defect.

## Related live-update patterns and next profile target

A read-only audit of related Quick PI lessons found SPIKE already implements
RAF-coalesced 2D pan and 3D hover picking, adaptive viewport cadence, persistent
camera/selection objects, generation rejection for async model loads, worker
cancellation/result guards, and a tested PI quick-tune scheduler with one
running and one latest pending input. The solver debounce is 500 ms, not a
16 ms display loop; the generic automatic queue is FIFO with caller-supplied
freshness checks. No general latest-only scheduling claim is made for it.
The frozen release's `test:pi-quick-tune` command was executed and passed,
including anchored selection, occurrence isolation, debounce, serialization,
generation invalidation/recovery, busy guard, undo and stale cancellation.

The strongest remaining profile target is the saved-frame 3D result effect in
`BoardViewport.tsx`: new frame data clears/recreates result geometry, typed
arrays, materials and instancing even when topology is unchanged. Native CPU,
GC and GPU-upload timings are not yet measured. Profile that path before
introducing topology-bound buffer reuse, retaining exact sample/triangle
mapping, camera, selection and generation checks. Animation export also has a
minor existing same-event-loop guard gap because it uses React state rather
than a synchronous ref lock; the frozen release was not changed by this audit.

No numerical current-scaling shortcut was adopted. Its applicability would
require an independently derived and validated fixed-temperature linear
conductance model, unchanged topology/material/electrode membership and an
explicit suitable load basis. It cannot authorize nonlinear, package, coupled
return, 3D or electrothermal shortcuts or new capability claims. Follow
`NUMERICAL_METHOD_EVIDENCE.md` before any such physics-affecting change. Related
tool measurements are not native SPIKE measurements or parity evidence.

## Follow-up evidence and desktop stop

The captured app/worker snapshot's architecture check completed successfully;
see `output/native-release-20261024/frozen-architecture-check.log`. A later
check of the shared checkout failed because concurrent Tauri resource edits
removed the `../../python/core`, `../../python/spike_core` and `../../extensions`
entries still required by its guard. Those entries are present in the sealed
snapshot. `concurrent-configuration-drift.json` records the distinction; no
concurrent configuration was overwritten and no guard was weakened.

The subsequent user-requested WayriCAD handoff pins upstream source
[`d5925fd02be3a8e90b06a9030377d05b1b14833d`](https://github.com/wayri/WayriCAD/commit/d5925fd02be3a8e90b06a9030377d05b1b14833d),
with [reported v3.6.31 release](https://github.com/wayri/WayriCAD/releases/tag/v3.6.31)
and [reported CI run](https://github.com/wayri/WayriCAD/actions/runs/40017847490).
These links could not be independently fetched in this session (cache misses),
so publication, CI and extracted-ZIP claims remain handoff evidence, not
independently reproduced SPIKE results. Retain the model limits described
above. A reported combined upstream report/GUI harness shutdown timeout does
not establish a SPIKE/product shutdown defect. No numerical shortcut or
upstream performance claim was adopted into the frozen SPIKE release.

On the next Computer Use observation, the tool explicitly reported that the
user stopped Computer Use with physical Escape. No further Computer Use calls
were made in that turn. Native desktop checks remain stopped; a cross-chat
handoff is not new human authorization to resume them. RAM monitoring may
continue read-only, but desktop inputs/native workload launch require a new
human instruction to resume, as well as the RAM gate. The earlier two input
guard responses alone should not be treated as proof of physical activity:
the controller had not consistently carried forward `state.window` after
refresh. That usage error was identified before the explicit Escape stop.

## Outstanding native evidence

RAM readings this turn began at 2,613,399,552 bytes and later 4,737,396,736
bytes. The recorded post-build gate at 20:19:10 UTC was **4,823,437,312 bytes**,
below 6,000,000,000; see `output/native-release-20261024/latest-ram-gate.json`.
No native board-load or responsiveness stress benchmark has started.
Recheck the gate immediately before each workload. No other app/process was
closed to obtain RAM.

Use retained fixture/source hashes and
`scripts/measure_native_process_tree.ps1`; preserve full host/WebView/worker
private/working-set measurements and separate shared/dedicated GPU counters.
Complete ordinary native dialog/tab/identity/layer/analysis/save/import/export
checks and repeated close/reopen plateau evidence. White Rabbit/server inputs
remain unavailable, and unresolved Marble model bindings remain unresolved.
Read the prior `PERFORMANCE_BUILD_CHECKPOINT_20261024.md` for the dev smoke check;
do not treat it as release or large-assembly native acceptance. Respect physical
desktop input and reobserve current windows/processes rather than using stale
PIDs. No commits, publication, board uploads or cross-chat messages are allowed.

When desktop input is available and the gate is satisfied, launch with the
sealed `target/release` worker workspace, a task-owned fresh WebView profile and
workspace TEMP/TMP. Use explicit CPU budget 14 and BLAS budget 1 on this
16-logical-processor host, record actual values/hardware again, and measure
native loading/interaction rather than inferring latency from component tests.
The existing temporary automation remains active and references this optimized
release/checkpoint, preserving its configured schedule. Disable it only when
the requested native checks and benchmark evidence are actually complete.

## Renewed desktop authorization and optimized release smoke

The human explicitly renewed desktop/native verification authorization on
24 October 2026. The temporary automation was updated to remove the prior
Escape authorization hold; the 6,000,000,000-byte benchmark gate remains.
The prior stop above is historical, not the current authorization state.

At 05:25:38 UTC Windows CIM reported 1,636,913,152 free physical bytes;
at 05:28:40 UTC it reported 1,562,542,080. No retained-board load or native
responsiveness stress workload was started. The release executable SHA-256
was checked against the sealed manifest before launch. The task-owned old
dev instance was absent from the fresh desktop inventory. A new empty
optimized release instance was launched with the sealed worker workspace,
fresh task-owned WebView/TEMP directories, CPU budget 14 and BLAS budget 1.

Observed release checks:

- Embedded offline Help reports `0.4.0-alpha.2` and loads its 502-article index.
- Help detaches into a separate native window and docks back into the main
  workspace. This is a tool-panel check, not scoped retained-board tab evidence.
- Native Open/import and Save As file dialogs appear with their expected
  source filters and SPIKE project extension. They were cancelled; no fixture
  was loaded and no project was saved. Actual retained-board persistence,
  import, STEP/result export and board-scoped detach/redock remain outstanding.

Evidence is in `output/native-release-20261024/native-smoke-20261024/`:
launch metadata, Help/native-dialog screenshots and accessibility snapshots,
and `empty-release-process-tree.json` from the standard native sampler.
Its 30-second observation produced 16 samples (CIM overhead means the requested
1-second cadence was not achieved). Peak aggregate host/WebView private bytes
were 838,848,512; aggregate working set 1,167,167,488; separate GPU shared
usage 502,845,440; dedicated usage 0. No worker was required by this empty
Help/dialog observation. These overlapping counters must not be added together.
The observed sample is neither a board benchmark nor a repeated-reopen plateau
or hard memory-limit qualification.

The next source improvement is documented in
`RESULT_FACE_TOPOLOGY_CACHE_PERFORMANCE_20261024.md`. It reuses exact polygon
triangulation across saved frames, retaining coordinate invalidation and all
renderer lifecycle/solver gates. This later source change is not embedded in
the previously sealed alpha.2 executable. Keep that build/source distinction
explicit until a new immutable native build is sealed.

The final reviewed cache freezes its index array before publication. Assignment
and deletion regressions prove callers cannot poison subsequent frames; coordinate,
vertex replacement and vertex-count mutations invalidate against the unchanged
uncached reference. The five post-review synthetic runs measured a 69.15 ms
baseline median and 13.17 ms warm median (5.25x CPU ratio, identical index
checksum 1,664,000). Independent review closed the alias finding. Full result
performance tests and TypeScript passed in the shared source; the isolated
snapshot's focused test also passed with the same checksum. No native FPS claim
is made. Geometry/material creation, upload and disposal remain unchanged.

The empty release was gracefully closed through its native Alt+F4 path; a fresh
window inventory and process check confirmed exit. No other app was closed.
At 05:32:28 UTC free RAM was 4,649,627,648 bytes and at 05:34:41 UTC it was
3,866,705,920 bytes, both below the start gate. The temporary automation remains
active with renewed authorization, new source/build distinctions and outstanding
native evidence recorded. The retained-board runs remain unexecuted.

The isolated production frontend with only the reviewed two-file production
delta passed TypeScript and Vite build (37.64 seconds). Its existing large-chunk
warning remains. Captured source, baseline linkage, complete frontend input and
output hashes, build logs and focused regression are under
`output/dense-playback-20261024/`. This is a frontend artifact, not a new native
executable. The original sealed release and packaged worker were not modified.
An initial staging check exposed a missing captured schema dependency; the
baseline schemas were then captured and the isolated checks/build passed.

The final post-build gate at 05:37:57 UTC was 4,666,523,648 free bytes, below
6 GB. C: had 2,848,489,472 free bytes. A new isolated native rebuild remains
pending: the previous private compiler cache was deliberately removed after
sealing, while copying the shared release compiler cache alone would require
about 2.41 GB before source, new crate outputs and runtime resources. Do not
overwrite shared caches or the sealed baseline to force a build into that space.

## Subsequent rebuild

The authorized isolated rebuild is now complete and sealed at
`output/native-release-playback-20261024/target/release/spike-desktop.exe`.
It embeds the reviewed latest playback frontend and reuses the byte-identical
qualified worker, preserving numerical/capability gates and concurrent source.
Its SHA-256 is
`6a7408a75357e458d4461b4545064e5d2e23cd44bac66ea992388c82c29b1770`.
Use [the new native checkpoint](NATIVE_PLAYBACK_RELEASE_20261024.md) for current
build, cleanup, smoke and remaining RAM-gated benchmark evidence. Earlier
statements about a pending native rebuild are historical.
