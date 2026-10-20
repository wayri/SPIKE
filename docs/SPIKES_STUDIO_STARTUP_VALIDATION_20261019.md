<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES startup overhead and wiring — 19 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](validation/RELEASE_040_LOCAL_EVIDENCE.md).

The installed Windows SPIKES Studio now contains the startup, simulation and
wiring improvements described here. It was independently checked and opened
normally with the saved Midnight theme. This remains version `0.3.0-beta.6`,
an unsigned engineering preview; public release qualification remains false.

## Measured result

| Fresh-process workflow | Before: median of case medians | After | Accuracy cases |
| --- | ---: | ---: | ---: |
| SPIKES owned C++ | 1,377.165 ms | 252.539 ms | 9/9 |
| ngspice 46 | 82.615 ms | 78.699 ms | 9/9 |
| LTspice 26.0.1.0 | 680.850 ms | 649.703 ms | 9/9 |

SPIKES' observed workflow median decreased **81.7%**. ngspice remains faster
in this scope. Both runs used the same nine fixtures, unchanged tolerances,
identical engine executable/native-library hashes, one warm-up and five measured
fresh processes per case. The host was an Intel Core Ultra 7 255H workstation
with 16 logical processors and 31.5 GiB RAM, using Python 3.12.9.

These timings include startup, adapters, solve, serialization and parsing.
Output volumes differ by engine; filesystem caches may be warm. This was an
interactive workstation with other user work. Our heavy validation/build jobs
finished before the after measurement. These are neither kernel-throughput
nor GUI input-to-frame timings, and do not establish whole-product superiority.

The benchmark report (unbundled local record: `../artifacts/studio-performance-20261019/benchmark-report.md`)
contains individual cases, errors, tolerances and limitations.
Before (unbundled local record: `../artifacts/studio-performance-20261019/competitive-before.json`),
after (unbundled local record: `../artifacts/studio-performance-20261019/competitive-after.json`) and
provenance (unbundled local record: `../artifacts/studio-performance-20261019/benchmark-provenance.json`)
retain repetitions, identities, input decks and wrapper hashes.

## Implementation

- Owned solves previously imported the reference MNA and unrelated field-provider
  stack through the measurement reducer, including for decks without `.meas`.
  `python/spikes/measurements.py` now owns the solver-free reducers. Four function
  bodies moved unchanged, verified by source hashes and independent review.
  The reference runner retains its helper reexports. Empty measurement sets
  return immediately; Studio workers use the lightweight module directly.
- A native regression exposed an existing DC-sweep dispatch bug: each temporary
  operating-point project retained DC-only measurements and failed its contract.
  Temporary points now clear those directives; the completed sweep performs the
  original reductions. Constant-voltage transient and DC measurement checks pass
  while imports of NumPy, SciPy, the reference runner and field stack are blocked.
- Three hidden startup placeholders now use deferred native painting. Native
  tests verify no synchronous placeholder draw during construction and actual
  rendering after tab activation and theme changes. Overall GUI startup speed
  was not quantified: source observations had high variation and concurrent
  manufacturer-interface changes prevent a controlled before/after claim.
- Wire-target labels rank six clamped positions against current component and
  annotation bodies, then render on an opaque bordered pill. Right-click retracts
  a corner, cancels the active segment, or closes idle Wire. The guide and status
  expose the gesture. Electrical connectivity semantics are unchanged. Crowded
  sheets can still have label collisions; placement minimizes overlap.
- Manufacturer discovery keeps its new hub while quick insert and electrical
  part editing retain their established panel interface. Human library navigation
  opens product discovery; electrical-model review opens the sourced-parts tab.
  The loader accepts the shipped schema tag and rejects conflicting tags.

No governing equations, integration settings, output channels or comparison
tolerances changed for speed. The native DLL remains SHA-256
`6b9014073366d7f43b003aa93a6ee740c3f750fbc978074b83c784320122ca5d`.

## Verification and open gates

| Executed check | Result |
| --- | --- |
| Complete Studio suite with native wx, clipboard, ngspice, KiCad and native analysis | 576 run; 575 passed; one host symlink skip |
| Exact staged runtime regressions | 62 passed, including wiring, clipboard, models, rendering and navigation |
| Source application acceptance | 67 checks passed |
| Corrected frozen application acceptance | 67 checks passed |
| Independently repeated installed application acceptance | 67 checks passed |
| Installed payload comparison | All 1,688 files matched; no forbidden Qt files |
| Additional available ngspice sine/model-fixture tests | 16 passed |
| Rust host suite | 70 passed; one ignored, after allowing loopback sockets |
| Latest TypeScript, parser and button-standard checks | Passed; 13 interactive previews checked |
| Complete root Python run | 4,308 run; 4,245 passed; 62 skipped; one parity-backlog failure |
| Parity-backlog recheck | 14 run; 10 passed; four stale-stage-runner evidence errors |
| Latest global architecture check | Failed: concurrent `app/src/FileDropImport.tsx` contains native IPC outside a desktop bridge |

The broad root run loaded an older expected parity-stage list while that file
changed during execution. Its recheck reports stale runner evidence. These
unrelated repository gates remain open; their evidence was not rewritten to
manufacture acceptance. The standalone payload excludes the main Tauri frontend.
The broad root run is not reported as green.

Earlier Studio runs caught four manufacturer integration regressions, then one
clipboard lifecycle failure with a different document's payload. The clipboard
test now establishes focus after layout and asserts source identity immediately
after copy and before paste. The final full run passed. The exact cause of the
earlier clipboard mismatch is not proven; cross-document protection was retained.
Failed runs remain in the evidence directory.

Visual acceptance used actual native windows. The
source narrow capture (unbundled local record: `../artifacts/studio-performance-20261019/source-smoke-ui/wire-narrow.png`),
frozen wide capture (unbundled local record: `../artifacts/studio-performance-20261019/frozen-smoke-r3-ui/wire-wide.png`)
and installed narrow capture (unbundled local record: `../artifacts/studio-performance-20261019/installed-smoke-ui/wire-narrow.png`)
show the new label position and guide. The frozen narrow capture had a black
client area and is retained as unusable capture evidence; the installed narrow
capture was inspected instead. The normal installed startup was additionally
observed through native accessibility and a screenshot, at revision zero with
three parts. The app is left running.

## Built and installed identities

The independently built candidate is `studio-startup-wiring-20261019-r3`:
installer (unbundled local record: `../artifacts/studio-packages/20261019/windows-startup-wiring-preview-r3/SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`),
111,653,571 bytes, SHA-256
`33f12b34e93b848b916cca22360cb4083c20e71f4d0f62dd06aa1bbb38d8a05d`.
Its immutable runtime derives from reviewed r2, with only one acceptance-helper
hub-field correction. Both superseded candidates are marked accordingly.

During validation, concurrent work installed the newer `artifacts/mfr19e` build.
The rollback guard stopped our planned overwrite. The newer build contains
byte-identical versions of the startup, rendering, simulation and wiring code;
it differs in the component-panel, manufacturer-hub and acceptance-helper files.
We retained it and independently
verified all installed files and repeated acceptance. Thus r3 was built and tested,
but was not installed over the newer update.

Actual installed directory: `C:\Users\yawar\AppData\Local\Programs\SPIKES Studio`.
The preserved installed-build installer (unbundled local record: `../artifacts/mfr19e/SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`)
is 111,669,351 bytes, SHA-256
`badf2548e680d6d79bfad69efda63721d65f4310692abec2b8803646da96e6cb`.
Its source-manifest SHA-256 is
`f3537127dd375e3386f605c43067a136cf8ce6b3e8be574f93f29c28b7896839`.

Source binding (unbundled local record: `../artifacts/studio-performance-20261019/installed-source-binding.json`),
payload check (unbundled local record: `../artifacts/studio-performance-20261019/installed-payload.json`),
validation receipt (unbundled local record: `../artifacts/studio-performance-20261019/startup-wiring-validation.json`),
installed-build checksums (unbundled local record: `../artifacts/studio-performance-20261019/installed-build-SHA256SUMS`)
and r3 manifest (unbundled local record: `../artifacts/studio-packages/20261019/windows-startup-wiring-preview-r3/package-manifest.json`)
and checksums (unbundled local record: `../artifacts/studio-packages/20261019/windows-startup-wiring-preview-r3/SHA256SUMS`)
retain exact artifact and verification identities. Previous application payload,
recovery and appearance data were backed up; user project storage was preserved.
