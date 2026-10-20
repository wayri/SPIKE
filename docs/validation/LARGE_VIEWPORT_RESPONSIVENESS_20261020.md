# Large viewport responsiveness follow-up, 2026-10-20

The user cleared the earlier desktop-automation wait and requested substantial
improvements for large assemblies and dense multiphysics/mesh results. Work
remains uncommitted in the shared checkout; solver methods and gates are unchanged.

## Implemented changes

`BoardViewport.tsx` now gives assembly board and part occurrences independent
geometry revisions. Late model attachment and replacement result overlays
invalidate their owning occurrence. A main-board bounds refresh no longer
invalidates the cached bounds of every unchanged sibling. The occurrence-culling
regression verifies one changed sibling produces one miss and one cache hit.

`emViewportScene.ts` builds one sample-admission mask per scene, avoids
per-triangle slices and Sets, fills surface buffers directly, and generates
contour vertices without temporary vectors/crossing objects. The dense regression
compares the complete 192,246-entry triangle stream and 32,400-entry sample map,
reference transformed positions, and exact masked/malformed-face rejection.
Existing coordinate, selection, mask, contour and disposal checks also pass.

The reproducible bounded CPU benchmark and raw samples are under
the unbundled local `large-board-memory-benchmark/performance-20261020` run. Recorded warmed
medians for 32,400 samples / 64,082 triangles were 12.87 to 4.64 ms for surfaces
and 60.36 to 10.68 ms for seven contour levels. These are scene-construction
measurements, not native interaction or full multiphysics qualification. The
pinned HEAD baseline also predates unrelated dirty angular-anchor/gradient work;
the spatial benchmark does not exercise those branches. See its README for
source hashes and reproduction instructions.

## Executed verification

- `npm run test:large-scene`: passed, including sharing/disposal, exact picking,
  transformed bounds, occurrence layer isolation and cache invalidation.
- `npm run test:em-viewport`: passed; root run surface 10.5 ms, contours 29.1 ms.
  Existing server-render useLayoutEffect warnings remain.
- Workers also passed TypeScript, extension-workflow and architecture checks.
- Root production build passed (2,234 modules, Vite 23.97 s); existing mixed
  import and large-chunk warnings remain. The resulting immutable frontend is
the unbundled local `native-gamma-verification-20261020/frontend` record, authenticated by the
  adjacent `frontend-manifest.json`; it has not yet been visually accepted.
- Full-repository `git diff --check` reports trailing whitespace in concurrent
  `python/spike_core/assembly_tetra_thermal_validation.py` changes. Those files
  were not modified by this task; focused changed-file checks are separate.

## Native session and remaining acceptance

The exact repository gamma.1 debug host ran against the immutable
the unbundled local `native-export-followup-20261018/multiboard-frontend` snapshot, served
locally on port 1420. The initial sandbox-local server was unreachable by the
native process; launching the server/host with approved localhost access resolved
startup. This is environment evidence, not a product regression.

The saved three-eBrake project reached Project usable, displaying retained
models and explicit harness. A fixed eBrake source tab detached successfully;
both native owner and source child were observed. Two simultaneous detached
siblings, import completion, successful result/STEP export, and narrow-window
acceptance remain pending. The running snapshot predates today's rendering
changes; this session does not establish their native visual acceptance.

Computer Use then reported the user's physical Escape stop. No further native
UI input was issued in this turn. The last pre-load RAM check was 9,906,151,424
bytes, below the required 10,000,000,000-byte threshold; subsequent native-session
readings fell further. No 10/20-board load or responsiveness stress benchmark
started. This does not establish either measured operation below a 10 GB budget
or hard memory-limit qualification. The deferred automation remains active.

Next: use a new immutable production snapshot containing these changes, finish
the pending native checks, then run authenticated retained Marble 10/20 and
available CM4/Sailor distinct-design fixtures only after the RAM gate is met.
Record full host/WebView/worker private bytes and working sets, GPU counters,
load/interaction timing and repeated close/reopen plateau with
`scripts/measure_native_process_tree.ps1`. Missing White Rabbit/server inputs
and Marble's unauthenticated loose model files remain explicit limitations.

## Later native continuation and revised gate

The user explicitly reauthorized desktop input and lowered the operational start
gate to **6,000,000,000 available physical bytes**. The existing heartbeat was
updated to this threshold. This does not change the separate 16 GB installed /
10 GB available target or establish a hard runtime limit.

Two scoped native children (source and side load) were observed simultaneously.
Closing the source child through its native titlebar redocked it; the side child
survived. Switching the side child to 3D exposed a real duplicate-board defect:
the one-board scope retained `active: false`, causing both the primary and
secondary occurrence render paths to draw the same source. `deriveWorkspaceViewScope`
in `useWorkspaceViews.tsx` now clones that sole occurrence as active without
mutating the assembly. Its regression retains the original inactive occurrence
and checks the projected ownership contract.

The fix passed native verification: `scoped-side-3d-fixed.png` shows one retained
board, and Dock back preserved the 3D presentation. Existing 65 model gaps remain
visible and are not claimed resolved. Scoped Analysis setup selected Results and
the owner inspector retained occurrence `ebrake-side` and design
`91ef0441-fa5b-5c3e-9dac-ade91b589441`; see `scoped-analysis-fixed.png`.

An earlier Results action caused a TypeError recovery screen. The server log
recorded a 404 for a stale `viaStressMap-A3q1KgXB.js` chunk at that exact action;
the served snapshot contained a different hash. The actual retained fixture has
no latest result/history, so a sparse-result contract hypothesis does not explain
that failure. Current snapshot dependency audits found no missing files; the
evidence establishes stale/inconsistent runtime assets, not the exact source of
the cache/deployment mismatch. The independently reproduced legacy sparse-result
normalization improvement in `analysisResults.ts` supplies required empty
collections while retaining supplied arrays. Its test is synthetic and is not
presented as this native crash's cause.

The final acceptance build was written directly by Vite into
the unbundled local `native-gamma-verification-20261020/frontend-isolated` run, avoiding shared
`app/dist` copying. Its adjacent manifest authenticates the files.
`serve_frozen_frontend.py` serves localhost with no-store headers, and the test
host uses a fresh task-owned WebView profile. The Results action then completed;
the local HTTP log records 200 responses for the lazy panel and its dependencies.

A further dense-result change caches sample strengths and compact layer/net
identity during display thinning, reducing repeated allocations and array
passes. A bounded 50,000-sample comparison retained the exact same selected ID
sequence, with reported warmed median 26.24 to 19.75 ms. This is CPU presentation
preparation, not solver performance or native frame-rate qualification.

An eight-second diagnostic of the existing small three-eBrake native session
captured three samples: peak private bytes 2,897,006,592; summed working sets
3,310,432,256; shared GPU bytes 1,212,370,944; dedicated GPU zero; nine observed
processes. These categories are separate and must not be added. The short trace
`native-20261020/three-ebrake-diagnostic.json` is not a steady plateau or a large
assembly acceptance benchmark. Other host activity pushed free RAM as low as
611,033,088 bytes during this session; the native process tree alone does not
account for whole-host pressure.

Header STEP export was initiated on the retained real source. It remained in
the exporting state without a native save dialog; Stop reported no cancellable
worker operation. Its cause is still under investigation and no successful STEP
export is claimed. Import and successful result export also remain pending.
The original 3,031,498-byte source was extracted locally for the next native
import check; SHA-256 `d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.

The last readiness query reached 6,664,351,744 free bytes, satisfying the revised
start gate, but native prerequisites were incomplete. Computer Use then reported
another physical Escape stop; no more native input was issued in that turn.
No 10/20-board load benchmark was started. The temporary automation remains
active at the revised 6 GB gate. Preserve this incomplete status until actual
load/interaction/close-reopen traces and native import/export evidence exist.

The bounded STEP source audit found a potentially expensive boundary: the worker
returns the entire STEP text in JSON, then the frontend sends that text through
a second Tauri invoke before the native save dialog opens. The absent worker and
save dialog are compatible with time spent marshalling that payload; they do not
prove this exact cause. The export's elapsed display is static and cannot prove
an event-loop freeze. Record worker completion/returned bytes and native command
entry/dialog timing before changing this path. No speculative export patch was
made. After preserving evidence, only the verified disposable test host and its
owned descendants were terminated to release memory; saved fixtures and other
work were preserved.
