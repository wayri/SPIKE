# Optimized native playback rebuild — 2026-10-24

## Build and preserved scope

The user authorized safe disposable-cache cleanup, an optimized native rebuild
with the latest playback improvement, and native 10/20-board runs only when
Windows CIM reports at least 6,000,000,000 free physical bytes. Concurrent work,
numerical accuracy and all existing capability gates remain protected.

The new immutable app is:

`output/native-release-playback-20261024/target/release/spike-desktop.exe`

- Version: `0.4.0-alpha.2`; local optimized release, not an installed/published release.
- SHA-256: `6a7408a75357e458d4461b4545064e5d2e23cd44bac66ea992388c82c29b1770`.
- Size: 28,906,496 bytes.
- Cargo: `build --release --offline --locked --features custom-protocol`;
  successful optimized profile in 2m58s, with two build jobs.
- Embedded production frontend; no dev server or hot reload.
- Frozen architecture check passed.
- Build seal verified 6,627 captured source inputs and 1,475 worker resource files.

The source is the prior sealed optimized snapshot plus only the two reviewed
production playback files, `BoardViewport.tsx` and `resultGeometryMask.ts`, from
the sealed production frontend in `output/dense-playback-20261024/`. See
`source-manifest.json`, `build-manifest.json`, `native-host-build.log` and
`build-seal.log` under the new output directory. Neither the live checkout's
unrelated changes nor the prior sealed native build was overwritten.

The packaged worker is byte-identical to the prior qualified worker:
manifest SHA-256 `839deff57fa12cca7ccf536e975b1145322b40db0a903c25bd5c5576bfab05aa`.
Its existing successful runtime qualification is reused, not represented as a
new execution of the qualification suite. No solver mathematics, precision,
admission rule or execution gate changed in this rebuild. Existing unsupported
or experimental capabilities retain their existing status.

The playback change reuses exact face triangulation with full coordinate
invalidation and frozen cached indices. Focused/full result-performance tests,
TypeScript, independent alias review and the isolated production frontend build
passed before capture. See
[CPU evidence and limits](RESULT_FACE_TOPOLOGY_CACHE_PERFORMANCE_20261024.md).
The 5.25x synthetic warm triangulation ratio does not establish native FPS or
end-to-end solver speed. GPU uploads and result scene recreation remain unchanged.

## Native smoke and benchmark gate

The new executable's seal hash was verified before an empty native launch at
06:20:32 UTC. Its launch recorded 5,573,746,688 free bytes, below the board
benchmark gate. No board was loaded. CPU budget 14, BLAS budget 1, the sealed
worker workspace, and fresh task-owned WebView/TEMP directories were explicit.
Startup accessibility shows the embedded workbench, empty assembly viewport,
normal commands and ready status. See
`native-smoke-after-rebuild-20261024/launch.json` and
`startup-accessibility.json`. Another application's file dialog occluded part
of the desktop capture; that capture is not full visual acceptance. Other
debug and installed SPIKE instances were left untouched. The task-owned empty
rebuilt app was closed through native Alt+F4 and its process was confirmed absent.

All six retained benchmark fixture files passed their recorded size/SHA-256
checks; receipt:
`output/performance-20261024/playback-fixture-verification.json`.
The fixtures include 10/20 repeated Marble occurrences and available two-design
CM4/Sailor assemblies. White Rabbit/server-board inputs remain unavailable;
unresolved Marble model bindings remain unresolved. Source and occurrence
identity must not be replaced with synthetic distinct designs or unauthenticated
loose models.

No native 10/20-board load, interaction or close/reopen-plateau result is claimed
here. Start each native workload only after a fresh successful RAM gate and use
`scripts/measure_native_process_tree.ps1`. Record full host/WebView/worker private
bytes and working sets, separate shared/dedicated GPU counters, actual hardware,
settings and timed phases. Native retained-board selection/layers/nets/links,
analysis, persistence/import/export and scoped tab checks remain outstanding.
The 6 GB operational gate does not qualify the 16 GB installed/10 GB available
target, the 32 GB recommendation, or a hard runtime memory limit.

## Cleanup boundaries

The older private builds had no substantial compiler caches remaining. Their
large binary/runtime/source/evidence files were preserved. Shared
`app/src-tauri/target`, live debug/installed apps, source, fixtures, logs,
environments and other chats' work are outside the removal set.

The new private compiler caches can be retired only after successful sealing,
under exclusive ownership of this chat with no new build scheduled during
cleanup. The helper is
`output/performance-20261024/cleanup_private_rust_cache.ps1`; seventeen self-tests
passed, including a complete disposable Prepare/Apply cycle, hard-link exclusion,
JSON byte-total roundtrip, and partial-failure receipt/stop/retry rejection.
It uses exact per-file manifests, hashes,
retained source/configuration/executable guards, compiler-writer checks,
full ancestry checks and literal file-only removals with flushed receipts.
An initial preview safely stopped because Cargo's retained executable is an
NTFS hard link. The revised helper permits read-only hard-linked guards while
excluding hard-linked cache candidates from deletion. No executable link was
broken or rewritten. Removal counts/bytes and observed disk change are recorded
separately after execution; a preview alone is not recovered storage.

The first preview was retained as failed-preview evidence: its ordered-record
byte summation yielded zero, so its totals were inconsistent and it was never
applied. Checked Int64 accumulation fixed this before any deletion. The reviewed
v2 manifest identifies 4,232 removable ordinary compiler-cache files totaling
1,588,686,740 logical bytes, plus 180 preserved hard-link exclusions totaling
823,309,929 logical bytes. Manifest SHA-256:
`4e111b52c57dafdb34c154cbfcecfdd8f030cb793d7851acfc18c0618792d024`.
The reviewed helper SHA-256 is
`894e89fe93862cf399bf7875bd59c7daa207be7a4516e3117e131a8a03923532`.
The v2 manifest and flushed per-file receipt are under
`output/performance-20261024/private-rust-cache-cleanup-evidence/`.
Only a final `complete` receipt establishes completion; a partial receipt must
not be blindly reapplied. `pre-apply.json` records disk space immediately before
the approved removal, separately from the earlier pre-cleanup observation.

Cleanup completed successfully. The final receipt has 4,232 `removed` rows and
one `complete` row; all 180 excluded hard links were subsequently hash-checked
and retained. `cleanup-summary.json` records 1,588,686,740 logical bytes removed.
Observed C: free space changed from 8,212,873,216 to 9,743,122,432 bytes, an
increase of 1,530,249,216 bytes. This measured disk change is distinct from the
logical deletion total and is affected by allocation and concurrent writes.
The retained app/source/worker verification is read-only and reported separately
in `post-cleanup-verification.json`; no seal manifest is rewritten by that check.

The 06:33:30 UTC post-cleanup RAM gate was 5,689,278,464 free physical bytes,
still below 6,000,000,000. No native board-load or responsiveness stress benchmark
was started. The existing temporary automation now points to this rebuilt native
app and checkpoint, preserving its schedule and quiet notification policy. It
remains active because the required retained-board native checks and 10/20-board
measurements are not complete. A fresh gate after verification and immediately
before each future workload remains mandatory.

Post-cleanup read-only verification passed at 06:34:13 UTC: executable SHA-256,
all 6,627 captured source inputs, all 1,475 worker resources, and all 115 sealed
production frontend files match. The verifier wrote only its separate report;
it did not modify sealed inputs. Cleanup is complete, native rebuilding is
complete, and the remaining work is the RAM-gated retained-board native
verification/benchmark campaign.
The final fresh gate at 06:35:38 UTC was 5,627,379,712 free bytes, so the
10/20-board workloads were not started. `latest-ram-gate.json` records it.
