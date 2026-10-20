<!-- SPDX-License-Identifier: Apache-2.0 -->
# Studio wiring, packaged models and comparison — 2026-10-19

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](validation/RELEASE_040_LOCAL_EVIDENCE.md).

The per-user Windows SPIKES Studio installation was rebuilt and updated to
local build `studio-wiring-models-20261019`, version `0.3.0-beta.6`. This is an
unsigned engineering preview, not a qualified public release. Work and
benchmark artifacts retain the request-start date, 2026-10-18.

## Delivered behavior

- Wire hover and click share a live geometry resolver. Moving or zooming the
  viewport before repaint no longer leaves a stale terminal target. Terminal
  halos, explicit branch markers, net names and snapped bend previews expose
  the connection being made. The compact guide shows bend switching,
  Backspace and Escape. The first Escape cancels a segment; the next exits
  Wire. Entering Wire clears pending controller-board placement.
- Reference, value and MPN text stack upright beside 90°/270° component bodies.
  General collision avoidance remains unfinished: a transient wire-target
  label can still cross nearby component graphics.
- The browser now contains **7,915 generic presets across 107 archetypes**:
  3,565 circuit-ready and 4,350 bench-only. The two new packaged-device
  archetypes compose the existing four-terminal NMOS and NPN builders with
  existing series R/L and optional G–S or B–E capacitance. The body/substrate
  terminal remains explicit. Labeled SI fields, generated source, provenance,
  save serialization and undo are exercised together.
- Reusing an internal generated model requires exact, unique core and wrapper
  bodies. Edited, duplicate or incomplete definitions are rejected before any
  document mutation. This also covers earlier internal model families.

These are configurable generic models, with zero qualified manufacturer models
in this preset catalog. See the
[packaged-device contract](../standalone/spikes_project/studio/docs/PACKAGED_DEVICE_LIBRARY.md)
for topology, parameter units, assumptions and existing derivation references.
No new numerical kernel or governing equations were introduced.

## LTspice and ngspice comparison

All three engines passed all nine existing common fixtures against unchanged
accuracy tolerances. Each case used one unmeasured warm-up and five measured
fresh processes on an Intel Core Ultra 7 255H workstation with 31.5 GiB RAM.
The external versions were LTspice 26.0.1.0 and ngspice 46.

| Engine | Cases passed | Median of case medians |
| --- | ---: | ---: |
| SPIKES owned C++ workflow | 9/9 | 760.434 ms |
| ngspice | 9/9 | 57.950 ms |
| LTspice | 9/9 | 551.364 ms |

SPIKES was slower in this timing scope. Measurements include process startup,
adapters and result parsing; output volumes differ. They are neither kernel
throughput nor GUI input-to-frame measurements. A separate same-process native
diagnostic measured 1.4213 ms for the divider and 18.4731 ms for the RC case;
external engines were not measured in that scope, so those values are not a
competitive comparison.

The benchmark report (unbundled local record: `../artifacts/studio-wiring-models-20261018/benchmark-report.md`)
contains case timings, errors, tolerances and limitations. The
raw report (unbundled local record: `../artifacts/studio-wiring-models-20261018/competitive-benchmark.json`)
and input provenance (unbundled local record: `../artifacts/studio-wiring-models-20261018/benchmark-provenance.json`)
retain repetitions, executable identities, decks and wrapper hashes. Medium
and large decks, AC/noise, compact-model parity, memory and scaling remain
outside this corpus. Overall superiority over these or other simulators is
not established.

## Executed verification

| Check | Result |
| --- | --- |
| Full root Python suite with explicit native DLL | 4,255 run; 4,200 passed; 55 skipped; no failures |
| Full Studio working-tree suite with native wx and clipboard access | 549 run; 545 passed; four skipped; no failures |
| Available optional Studio checks subsequently enabled | ngspice reference traces, native background analysis and actual KiCad export passed; host symlink restriction remains |
| Exact staged-source wiring/model/catalog regressions | 45 passed, including native wx, native analysis and KiCad checks |
| Source, frozen and installed application acceptance | 58 checks passed in each layer |
| Native source library visual/transaction checks | Seven passed; NMOS/NPN inspectors inspected wide and at 1000 × 720 |
| Installed payload comparison | All 1,685 files matched; no forbidden Qt files |
| Architecture, button standard, TypeScript compilation and parser | Passed |
| Rust host suite | 70 passed; one ignored |

Two earlier combined wx runs ended in a native access violation at a modal
quick-insert test. The runner now retains one `wx.App` through discovery and
test completion, with exit-on-last-frame disabled. The subsequent complete
suite passed, including that modal test. The earlier crash logs remain in the
evidence directory; the precise native corruption mechanism is not proven.

The initial staged regression attempt used source-checkout asset lookup against
the differently arranged staging directory and failed three resource lookups.
The corrected harness binds the exact staged assets; all 45 checks then passed.
It records every imported Studio module path to establish source identity.
The hidden frozen-window attempt failed because its wiring acceptance helper
expected painted geometry. The visible frozen run passed all 58 checks and
produced native captures at 1380 × 900 and 1000 × 720. All failed attempts are
retained and are not counted as successful runs.

Concurrent firmware changes arrived after freezing. They remain in the checkout
and were not folded into this reviewed package. The broad working-tree suite
and exact staged-source checks therefore establish distinct facts. Frozen and
installed acceptance exercise the final bundled implementation independently.

Native frozen captures:
wide wiring (unbundled local record: `../artifacts/studio-wiring-models-20261018/frozen-smoke-ui/wire-wide.png`),
narrow wiring (unbundled local record: `../artifacts/studio-wiring-models-20261018/frozen-smoke-ui/wire-narrow.png`).
The wide capture's bottom edge extends beyond its capture surface; the compact
wire guide and target remain visible, and the narrow capture includes the
status bar. Source library captures:
NMOS (unbundled local record: `../artifacts/studio-wiring-models-20261018/packaged-nmos-narrow.png`),
NPN (unbundled local record: `../artifacts/studio-wiring-models-20261018/packaged-npn-narrow.png`).

## Installation and artifact identity

Installed directory: `C:\Users\yawar\AppData\Local\Programs\SPIKES Studio`.
Installer exit status: 0. The previous payload and user recovery/preferences
were backed up before replacement. The old installed process was unresponsive
to graceful close; its last observed document was the unchanged startup circuit.
Only that verified process was stopped. User project and preference storage
was preserved.

The updated installed window was observed through native accessibility and a
native screenshot, showing the saved Midnight theme and revision-zero startup
circuit. The final interactive Parts-button attempt was blocked by the
computer-use helper's `foreground window did not report a process id` error.
Installed library behavior passed through package acceptance; an interactive
button click is not claimed as passed. The updated application is left running.

Final Windows installer (unbundled local record: `../artifacts/studio-packages/20261018/windows-wiring-models-preview-final/SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`):
111,622,734 bytes; SHA-256
`eea854531c1d0ab7b3ba9b39b9951cc5d20f9af5b98e3b9c26883c3986c2dba0`.

Package manifest (unbundled local record: `../artifacts/studio-packages/20261018/windows-wiring-models-preview-final/package-manifest.json`),
source manifest (unbundled local record: `../artifacts/studio-packages/20261018/windows-wiring-models-preview-final/source-manifest.json`),
SBOM (unbundled local record: `../artifacts/studio-packages/20261018/windows-wiring-models-preview-final/sbom.cdx.json`),
checksums (unbundled local record: `../artifacts/studio-packages/20261018/windows-wiring-models-preview-final/SHA256SUMS`)
and validation receipt (unbundled local record: `../artifacts/studio-wiring-models-20261018/wiring-models-validation.json`)
bind the completed artifact to its checks. The first incomplete package directory
is marked superseded and was never installed.

The reviewed packaged desktop source SHA-256 is
`b98cf2b211661eff68784d431c690f9a8907fc77b5169af093e64e6e82b5c61f`.
The unchanged native DLL SHA-256 is
`6b9014073366d7f43b003aa93a6ee740c3f750fbc978074b83c784320122ca5d`.
Release qualification and knowledgeable human numerical review gates remain.
