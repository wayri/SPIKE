# GLB and dense playback native continuation — 25 October 2026

## Captured change and verification

`output/native-release-glb-20261025/source` captures the qualified
`native-release-playback-20261024` source plus exactly two production deltas:
the reviewed GLB header/JSON preflight slices and four scalar-overlay scratch
color writes. The frozen viewport received only five textual edits, rather
than the concurrent live viewport's unrelated changes. The backend, numerical
methods, execution gates and qualified worker are inherited unchanged. This
continues version 0.4.0-alpha.2; it does not incorporate the concurrent live
0.4.1 capability work or establish that work's release acceptance.

The source manifest contains 6,628 inputs and has SHA-256
`6281e1f3cebd3c23f173ebd167b327f6d2531ff569e3c76bff151235e9544c8f`.
The isolated frontend installed 85 exact locked packages offline from the
existing machine npm cache; the sandbox cache alone lacked `yallist`.
No shared dependency directory was modified.

Executed in the captured source: Python architecture check, TypeScript and
production Vite build, project-persistence/GLB integrity checks, board-visual
checks, exact scratch-color check, and the complete `test:result-performance`
command all passed. Logs are in the new output root. Vite completed in 51.27 s
and retained its existing large-chunk warning. No code splitting or capability
removal was used to suppress it. All six retained benchmark fixture hashes
were freshly verified; see
`output/performance-20261025/native-fixture-verification.json`.

The color test compares 12,000 Float32 components exactly, including invalid
and extreme HSL inputs, and verifies that `InstancedMesh.setColorAt` copies
values before scratch reuse. It removes per-write Color construction without
changing sample mapping or geometry. See
[bounded color evidence](RESULT_COLOR_SCRATCH_PERFORMANCE_20261025.md) and
[GLB evidence](GLB_PREFLIGHT_SLICES_20261024.md). Neither bounded CPU observation
establishes native FPS, project-opening time, or solver acceleration.

## Build and operational state

The private release build completed in 3m28s and sealed at 15:30:53 UTC.
The executable is `output/native-release-glb-20261025/target/release/spike-desktop.exe`
(29,129,216 bytes), SHA-256
`f4841066715f637878409a05370fc4bb0f53bfdceb0d4269b9b13dcdd5944ffd`.
The seal verified all 6,628 source inputs and all 1,475 worker resources;
the worker manifest remains byte-identical to the qualified baseline
(`839deff57fa12cca7ccf536e975b1145322b40db0a903c25bd5c5576bfab05aa`).
Worker qualification is reused on that identity, rather than claimed as a new
runtime qualification campaign. Production frontend resources are embedded;
there is no HMR. Source capture and build helpers live in
`output/performance-20261025/`. The initial disk guard stopped
before cache copying; a revised copy excludes more than 590 MB of stale app
binaries that must rebuild for the embedded frontend. Shared cached files
remain untouched. After private cache preparation, a low-RAM guard deferred
the compiler. `resume_glb_native.ps1` then passed a fresh check at
15:25:23 UTC: 10,040,717,312 physical bytes free and 6,728,118,272 disk bytes free.
Compilation uses one job, offline locked Cargo, optimized release and
`custom-protocol`. Do not rerun source capture or the initial cache-copy helper
over these prepared directories.

Fresh hardware evidence at 15:27:13 UTC records Lenovo 83KF, Core Ultra 7 255H
(16 cores/16 logical processors), 33,820,106,752 installed physical bytes,
Arc 140T integrated GPU driver 32.0.101.8991, Windows build 26300 and
3000×1876 display resolution. Display scale is unobserved. RAM then free was
8,516,468,736 bytes. Raw CIM AdapterRAM is not a measured GPU-memory counter.

Desktop enumeration returned ordinary application windows and no SPIKE window;
the previous recorded PID must not be reused. No desktop inputs have been sent
in this continuation. Require fresh native window identity after launch.
The prepared `launch_glb_native.ps1` always requires 6,000,000,000 free physical
bytes before launch and a new owned profile; after startup recheck the gate
immediately before every board workload and verify the sampler's first free-RAM
observation. The 6 GB operational gate remains separate from the 16 GB
installed/10 GB available target, 32 GB recommendation and hard-limit testing.

## Native launch and desktop-input interruption

The sealed app launched at 15:31:19 UTC with fresh owned WebView/TEMP,
CPU14/BLAS1, verified path and process creation identity. Launch free RAM was
8,184,991,744 bytes; the post-startup gate recorded 6,939,783,168 bytes.
The unmodified `scripts/measure_native_process_tree.ps1` then recorded its
first empty-host sample with 7,505,289,216 free physical bytes, passing the
6 GB gate. All receipts are under
`output/native-release-glb-20261025/native-board-bench-20261025-evening/`.

The single empty-host sample observed seven host/WebView processes, working
set 861,978,624 bytes, private bytes 589,107,200, shared GPU 402,259,968 and
dedicated GPU zero. These counters overlap and must not be added. No worker
was observed. One sample establishes neither plateau nor board memory use.

Supported Computer Use observed the native SPIKE shell and activated the
verified window. The subsequent Menu action was rejected with
`user input was detected in this window; call get_window_state before continuing`.
After read-only re-observation, focus was back in Chrome. Desktop inputs were
stopped to preserve user activity and the human was asked when the desktop
would be free. This supersedes the previous lock-screen blocker; no unlock or
authentication was attempted. No board load or responsiveness stress workload
has started. The task-owned empty app was left running; refresh process/window
identities before reusing it, without relying on the recorded PID alone.

Native selection, layers, occurrence nets/links, analysis, actual native file
workflows, scoped tab detach/redock, 10/20 Marble and distinct CM4/Sailor loads,
full process/GPU traces, interaction timing and repeated reopen plateau remain
outstanding at this checkpoint. White Rabbit/server inputs remain missing and
Marble model bindings unresolved. Do not represent proxy geometry as resolved
model coverage. Preserve other apps and concurrent work; no commits or uploads.

## Superseding measured failure and physical input stop

The human subsequently confirmed the desktop was free. A fresh check passed
with 7,879,790,592 bytes. The immediate pre-load gate later fell to
4,898,787,328 bytes, so the Marble load was held. The attempted native dialog
cancellation was not qualified: a later state showed the previously selected
small `original-transient.spike` project open. That unplanned action is excluded
from benchmark evidence; no clean-cancellation success is claimed. The file
path was then set through the native editable control and visually verified;
keyboard submission replaced indexed dialog clicking.

After RAM recovered, the Marble10 sampler start gate passed with 7,572,459,520
bytes. Its first observation independently recorded 7,472,857,088 free bytes.
The retained 10-board Marble fixture was submitted at 15:39:48.889 UTC. Package
verification completed, but the scene/model stage reached 85% and its elapsed
display froze at 24 seconds. At 181.579 seconds after submission, supported
Computer Use observed `This page is having a problem` and
`Error code: Out of Memory`. The scene never became usable.

The 180-second trace contains 111 samples, with separate maxima:

- Process-tree private bytes: 14,440,976,384.
- Aggregate working set: 12,175,814,656 bytes.
- Shared GPU usage: 2,135,248,896 bytes; dedicated GPU usage zero.
- Minimum host free physical memory during the run: 11,628,544 bytes.

These are overlapping counters with potentially different peak times; do not
add them. The trace spans native host, WebView and transient worker/KiCad
children, up to 47 observed processes. The package workers exited while the
renderer and GPU-process allocations continued growing. Renderer 214160
disappeared between sampler seconds 160.823 and 162.384; the subsequent memory
drop is crash recovery, not a normal close/reopen plateau. Raw trace, process
CPU snapshot, role flags and the native OOM screenshot are retained in the run
folder. This run failed the requested usable-scene outcome; it is not a 10 GB
budget pass or hard memory-limit qualification. No limit was imposed.

Code inspection identifies repeated procedural tessellation plus retained pick
geometry and merged display buffers as an allocation candidate. The archive
contains no GLB artifacts, but a transient KiCad child also ran during loading;
late generated visual/model participation still needs discrimination. Neither
allocation attribution nor a fix is claimed as verified. Do not infer causality
from source inspection alone or rerun Marble20 unchanged after Marble10 OOM.

A normal Alt+F4 close was requested, but closure was not confirmed. No force
close/kill or confirmation of data loss was performed. The human then stopped
Computer Use with physical Escape. All desktop inputs stopped immediately;
fresh human instruction is required before any later desktop continuation.
Marble20, distinct-design runs, native retained-board functional acceptance,
dense-result native FPS and the reopen plateau remain incomplete.
