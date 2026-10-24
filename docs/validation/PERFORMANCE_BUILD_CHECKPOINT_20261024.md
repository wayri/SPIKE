<!-- SPDX-License-Identifier: Apache-2.0 -->
# Performance and native build checkpoint - 24 October 2026

## Objective and current boundary

Optimize project opening and large-analysis preparation without changing
accuracy, capabilities, solver gates or source identity. Build an isolated
updated app and complete the retained native checks and 10/20-board benchmark
only when Windows CIM reports at least 6,000,000,000 free physical bytes.
That start gate is separate from the 16 GB installed / 10 GB available product
target and is not a hard memory-limit qualification.

## Verified changes

- `PROJECT_LOADING_PERFORMANCE_20261024.md`: exact detached frontend projection,
  paired retained three-eBrake worker-open median 962.290 to 791.844 ms.
  All ten complete responses retain the same SHA-256 and encoded byte count.
- `ANALYSIS_PERFORMANCE_20261024.md`: exact bounded compact-JSON transport
  preparation, final measured median 2.178375 to 1.12684 ms. Concurrent noise
  prevents an end-to-end CHT speed claim. Equations and convergence gates did
  not change.
- Root verification: 11 loading/CHT tests passed; architecture check passed.
- Independent review found and corrected DEL U+007F escaping before packaging.
  The final reviewed source SHA-256 is
  `3727b884c2663587a7715d1a75fc1cd7578b187bb0417b8cdd7d630522a061a2`.
  Independent checks passed: 222 exact prior-encoder hash/snapshot comparisons
  covering every BMP code point, astral boundaries and 2,000 finite float bit
  patterns; 327 reduced byte-cap boundaries; depth/type/nonfinite/cycle cases;
  five focused encoding and callback/ABA/order mutation tests. No physics
  implementation changed in this pass.

These are bounded component improvements. They do not establish millisecond
execution for arbitrary large CFD, dense meshes or coupled field simulations.

## Isolated build

`output/native-performance-20261024/source-manifest.json` records 6,589 copied
source/build inputs (about 326 MB) in
`output/native-performance-20261024/source`. The corrected reviewed CFD source
and its validation document were refreshed before starting the worker build.
The snapshot uses the existing locked Node dependency directory through a
junction; source and output artifacts are separate from the shared checkout.

Worker packaging uses the existing pinned Python 3.12 `.venv` and PyInstaller
6.21.0. Full runtime/source/schema/extension/native solver packaging gates remain
enabled. Logs: `output/native-performance-20261024/worker-build.log` and
`typescript-check.log`. The initial TypeScript attempt ran before the dependency
junction could be created and failed module resolution; the fresh linked check
passed. Do not interpret the first attempt as a product regression.

TypeScript checking passed after linking the existing locked dependencies.
Vite production frontend build passed in 45.51 seconds, retaining its existing
large-chunk warning. The native host built offline/locked with the
`custom-protocol` feature in a private target in 4m 03s. The resulting
`output/native-performance-20261024/target/debug/spike-desktop.exe` embeds the
frozen frontend, bypasses the development HTTP server and has no hot reload.
Its Cargo profile is **dev, unoptimized with debuginfo**, not a release build.
Any measurements of this artifact must retain that distinction.

The worker executable was built successfully. The first qualification reached
the Arrow-package probe, timed out, then failed cleanup in sandbox TEMP. A
workspace-TEMP retry passed that probe and reached the SI workflow, where the
isolated source copy lacked `tests/python/test_si_material_scenario.py`, a
fixture imported by the standard qualification script. That exact fixture was
added to the source manifest. Every standard gate passed on the same worker
binary with workspace TEMP; neither gates nor timeouts were relaxed.
The logs preserve both unsuccessful attempts and the full rerun.

The final `worker-qualification-complete.log` and packaged worker manifest
record 15/15 benchmark cases passed, zero failed/skipped, 8/8 source-versus-frozen
runtime checks passed, 506 Python modules matching source, and 262 schema files
matching source. Arrow persistence, owned native interactive RC replay,
experimental cavity/CHT, extension execution, SI and EM/SPICE/heat co-simulation
packaging probes passed. These synthetic packaging oracles retain their
existing approximate/experimental/non-production states; they are not general
physics or board qualification.

`output/native-performance-20261024/build-manifest.json` seals all 6,589 source
inputs, verifies all 1,474 worker files copied into the native runtime, and
records frontend hashes and executable SHA-256
`28ffd5f26fb405b393657168654d8b66595a1af293ffb07fd7ba63f637f0144e`.
The captured source remained unchanged through the build. Concurrent changes
made later to the main checkout are intentionally absent from this snapshot.

The built native app launched with its own WebView profile and the sealed
`target/debug` worker workspace (which chooses the packaged worker rather than
development Python). CPU budget was explicitly 14 threads. The empty assembly
viewport and offline Help displaying version 0.4.0-alpha.1 were observed at
`http://tauri.localhost/`. Evidence: `native-help.png`,
`native-help-accessibility.json` and `native-launch.json` in the build directory.
The default `board_power_review.spike` title is the initial empty-project label,
not evidence of opening a retained board. Physical input/window state changed
and the window was minimized during the next UI attempts; no further inputs
were sent and no dialog, import, export or scoped-tab pass is claimed.

Native retained-board dialog/tab checks and all 10/20-board load, interaction,
process-tree/GPU and close/reopen plateau measurements remain outstanding.

## Memory gate and preserved work

Windows CIM free physical RAM observations this turn: 4,734,312,448 bytes;
2,139,766,784 bytes; 150,519,808 bytes during compilation; 6,302,818,304 bytes
after TypeScript completed; 1,638,031,360 bytes during packaging; and
3,128,193,024 bytes after native compilation. The final recorded gate at
19:53:24 UTC was 3,197,452,288 bytes, below the required 6,000,000,000 bytes;
see `output/native-performance-20261024/latest-ram-gate.json`.
No board-load or responsiveness stress workload was started. No other
application or process was closed.
No commits, publication, board uploads or messages to other chats were made.

Use the retained fixture manifest and sampler described in
`output/large-board-memory-benchmark/native-20261020/README.md` for the pending
10/20 Marble and distinct-design runs. Missing White Rabbit/server-board inputs
remain missing; unresolved Marble model bindings are not resolved-model
qualification. Preserve the existing native dialog/tab checks and plateau
requirements. The existing temporary automation remains active and now points
to this checkpoint and sealed build, preserving its configured schedule. Keep
it active until all requested native verification and benchmark evidence is
complete. Reobserve current windows/process identities on resume; do not reuse
the launch record's PID without verifying the process path and executable hash.
