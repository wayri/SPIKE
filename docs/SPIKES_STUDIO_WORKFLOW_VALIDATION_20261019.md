<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES job overhead, wiring and packaged models - 19 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](validation/RELEASE_040_LOCAL_EVIDENCE.md).

This iteration targets SPIKES Studio, the separate native circuit workbench.
It remains `0.3.0-beta.6`, an unsigned engineering preview. No public release
or additional numerical qualification is claimed.

## Changes and measured scope

A public `run_native_project` call now owns one explicitly loaded ABI binding.
Nested STEP/DC points share that binding; every point still constructs and closes
its own native circuit and result. The binding is not cached globally or reused
across public jobs. The DLL, equations, integration controls and result channels
are unchanged. Independent review compared complete old/new results for nested
STEP/DC, stepped transient and singular failure, and checked handle cleanup.
Regression tests cover these lifetimes, failed loads and concurrent jobs.

A 101-point DC divider sweep measured 183.102 ms before and 16.330 ms after
(one warm-up, ten in-process repetitions): 91.1% lower orchestration time.
Parsing precedes the timed repetitions; timing includes execution and result
serialization to a Python dictionary. The old sweep loaded/bound the ABI 101 times; the new sweep did so once.
Complete result JSON is identical. This is a small in-process sweep result,
not a general solver throughput or cold-process speed claim.

The native CLI constructs only its selected command parser. The complete parser
remains available for global help and other commands. Shared option definitions
and regression checks preserve native-run defaults, every integration alias,
required arguments, help and error text. Fresh-process observations are retained
in the benchmark report (unbundled local record: `../artifacts/studio-iteration-20261019/benchmark-report.md`).
All nine cases pass their unchanged tolerances for SPIKES, ngspice and LTspice.
All three engines slowed in the final observed run on this busy workstation;
these data do not establish a startup speed gain or simulator superiority.

Wire exit now clears preview state and synchronously resets toolbar state.
Snap feedback is recalculated after viewport pan/zoom so labels and halos do not
lag behind the transform. Electrical connectivity rules remain unchanged.
Native focused wiring/route checks passed 12/12. Source acceptance checks include
real wide and narrow captures and immediate toolbar deactivation.

The library adds `physics.packaged.resistor3` and
`physics.packaged.kelvin_shunt4`, composing existing lumped cores and the existing
package-parasitic builder. Kelvin sense terminals retain exact links; only force
leads receive the explicitly supplied R/L. The browser contains 7,917 records,
including four packaged families. All remain `generic_unqualified`; record count
is not a count of manufacturer-qualified models. See the
[model topology and provenance](../standalone/spikes_project/studio/docs/PACKAGED_DEVICE_LIBRARY.md).
Source/frozen/installed acceptance checks exercise exact pin contracts,
engineering-value fields, generated-source reuse guards, save/undo, and actual
native voltage drops for both new families.

## Acceptance evidence

Evidence is retained in `artifacts/studio-iteration-20261019`.
Source acceptance passed 84 checks. Focused native/CLI regressions passed 51.
The source manifest and all 282 staged runtime Python modules matched the current
source at snapshot verification. Architecture, TypeScript, parser and control
standards passed. Rust passed 74 tests with one ignored.

The Windows candidate was frozen, compiled into an Inno installer, and installed
into `C:/Users/yawar/AppData/Local/Programs/SPIKES Studio`. Source, frozen and
installed application checks each passed **84/84**. All **1,690 installed files**
match the candidate payload and no Qt payload was found. Installer registration
and the Start-menu shortcut exist. Appearance settings match their pre-upgrade
hash. Normal installed startup was observed with Midnight theme, revision 0,
three parts and no probes; the application was left open.

Source and frozen narrow captures showed the actual wiring controls and canvas.
The installed PrintWindow narrow capture was black and is not visual acceptance;
normal installed rendering was independently observed with native Computer Use.

Installer: `SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`, 111,701,406 bytes,
SHA-256 `577c4c7a24bce629e013e43658d5ec42922712108d1b45b42dd8e0874e78c435`.
Source-manifest SHA-256:
`0ef02322f08d9e181c31026787918e72c2799e928420f8efdfab5d7a342aa3ae`.
The package manifest and `SHA256SUMS` are retained beside the installer.

The full Studio run executed 596 tests: 590 passed, two skipped and four failed.
The failures are newer firmware-electrical checks requiring the GPIO-pad API,
which the unchanged benchmark/package DLL lacks. The firmware module passes
seven checks with its designated GPIO DLL and skips its opt-in real-firmware
check. That separate DLL is not the installed engine; electrical GPIO pad
execution remains unavailable with the packaged engine and fails explicitly.
No ideal-source fallback or blanket full-suite success is claimed.

The complete repository Python run executed **4,351 tests in 991.583 seconds**:
**4,279 passed, 65 skipped, seven errors**. All seven errors are in
`test_spikes_native_io_pad`, whose tests require symbols absent from the selected
benchmark/package DLL. All seven pass when rerun with their designated
`build-spikes-io-pad-20261019/Release/spikes_c_api.dll`. This separate fixture
result does not qualify or change the installed engine. The broad run therefore
remains a failed gate with an explicit capability mismatch. Architecture,
TypeScript, parser, button controls and Rust results above passed.

The bound validation receipt (unbundled local record: `../artifacts/studio-iteration-20261019/validation.json`)
records the installer/source identities, full-suite failures, installed payload,
acceptance counts and limitations. The
independent ABI review (unbundled local record: `../artifacts/studio-iteration-20261019/abi-review.json`)
retains all three fixture sources, exact old/new result equality, per-point handle
closure counts and reviewed input hashes. Its script is retained alongside it.
