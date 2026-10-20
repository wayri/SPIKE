<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES Studio cold-path and GPIO validation - 19 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](validation/RELEASE_040_LOCAL_EVIDENCE.md).

**Status: local engineering preview; public release qualification is incomplete.** This record covers the
current source and bounded evidence in
`artifacts/studio-cold-gpio-20261019`. SPIKES Studio remains a local, unsigned
engineering preview. The model additions are generic and
`generic_unqualified`; they are not manufacturer-qualified parts.

## Implemented scope and current evidence

The `native-run` cold path now constructs only the selected command parser and
defers unrelated command imports. Standard output is compact JSON by default;
`--pretty` restores indented output, and file output remains indented. Native
result extraction validates each channel once and reuses the ctypes output buffer,
pointer and function lookup across samples. The scalar C ABI still receives one
checked foreign call per point; no native bulk-transfer ABI was added. The retained channel review (unbundled local record: `../artifacts/studio-cold-gpio-20261019/channel-review.json`)
found complete old/new JSON and raw-channel equality for operating-point,
fixed and adaptive transient, and nested STEP/DC fixtures. It also exercises
invalid names, closed handles, and a mid-channel native error without returning
partial data. The focused cold/contract regressions passed 27 tests.

The solve-excluded channel microbenchmark (unbundled local record: `../artifacts/studio-cold-gpio-20261019/channel-benchmark.json`)
transferred nine channels of 1,000 points over ten paired repetitions. Median
extraction time was 15.0476 ms through scalar calls and 5.7806 ms through the
channel extraction helper, with all values equal. This is an ABI-transfer result from an
earlier immutable GPIO candidate (SHA-256
`342145556cee39b552eff681dc911812f2f38146750c94dbe5824dfda478b5b5`);
it excludes solve time and does not establish final-package performance.

Wire hit selection now compares geometric distance across visible candidate
routes, so parallel routes resolve to the nearest visible net rather than the
first route encountered. The current source smoke explicitly passes the
parallel-wire nearest-net check, together with branch target and wire-exit
checks. This evidence covers editor selection and source-authoritative net
identity; it does not add connectivity from visual crossings.

The component browser exposes 7,918 records across 110 archetypes: the existing
catalog plus five configurable lumped families and five packaged families. The
packaged feedthrough capacitor is included with ordered `IN`, `OUT`, `GND` pins,
explicit package R/L/C, editable SI-valued fields, definition-reuse guards,
serialization and atomic undo checks. Record and archetype counts are discovery
counts, not counts of independently qualified physical models.

The frozen/package GPIO admission path calls `require_io_pad_api` before any pad
operation. That guard requires all six symbols: add pad, update state, receive,
observe, schedule an edge, and query pending edges. Current source smoke passes
the complete-symbol guard and executable checks for a finite pull divider,
state update, checkpoint restore, receiver classification, and two retained
subinterval edges.

## Native provenance

The final native candidate is
`artifacts/studio-cold-gpio-20261019/engine-final/spikes_c_api.dll`, 810,496
bytes, SHA-256
`1ab15364ecf9ebd66ed48ec8e82be25d1a421b1d1654c8962959f67460373ba1`.
The retained native snapshot manifest (unbundled local record: `../artifacts/studio-cold-gpio-20261019/native-snapshot-manifest.json`)
binds copied source and test files by SHA-256; the manifest itself is bound in
the build review (unbundled local record: `../artifacts/studio-cold-gpio-20261019/native-build-review.json`)
as `84418f5d2eb26c957885ad22e24b18bb4b2f7b189db8c722850caf4646e3380a`.
The isolated Visual Studio 2026 x64 Release build reported no snapshot mutation.
Seven selected CTest executables and 46 Python GPIO/ABI/job/startup tests passed
against that isolated DLL with both native-library environment variables pinned.
This supplies source-to-binary provenance for the candidate; it is not a
hermetic build or an installed-payload receipt.

## Controlled cold competitive observation

The before (unbundled local record: `../artifacts/studio-cold-gpio-20261019/competitive-before.json`) and
after (unbundled local record: `../artifacts/studio-cold-gpio-20261019/competitive-after.json`) reports
used the same nine-case corpus, five isolated-process repetitions per case, and
the same SPIKES DLL SHA-256
`891211e317ca14282b778d29101b4021f3eb348f7be5f8c119e3a5e47ab2a889`.
All nine cases passed for SPIKES, ngspice and LTspice in both reports. Median
cold case time changed from 215.6764 to 172.1053 ms for SPIKES, 72.9612 to
65.7408 ms for ngspice, and 674.6873 to 546.9318 ms for LTspice. Because both
host competitors also became faster, host/cache/load conditions contributed to
the observed change. These reports support preserved shared-subset results and
a controlled cold observation only; they do not isolate the CLI change, measure
warm solver throughput, or support parity or superiority claims.

## Final package and regression evidence

The preserved `package-final` source manifest has SHA-256
`b1dd9a0b179ff2cc380d21ffb3e46362447e87f60279892851314bcf49096eff`.
It binds the staged source and the final native engine above. Concurrent edits
continued elsewhere: `source-drift.json` records one later firmware-window
explanatory-text change outside this package snapshot. The earlier `package`
directory contains a rejected intermediate DLL and was never installed.

- Final immutable-engine SPIKES subset: 592 tests, 568 passed, 24 optional skips.
- Final Studio suite: 624 tests, 614 passed, nine skips, one 200 ms controller
  startup timeout under concurrent build/test load. The unchanged timeout test
  passed alone afterward (`deadline-recheck.log`). Six Renode edge tests, one
  real-firmware test, host symlink creation and an unconfigured KiCad CLI were
  skipped. The KiCad test subsequently passed with its correct environment.
- Full repository run: 4,366 tests, four errors and 73 skips. Three errors used
  adaptive test fakes imported before their correction; one layout capability
  probe exceeded its 10 s deadline. All 14 tests in those two modules passed
  afterward (`root-failure-recheck.log`). This does not rewrite the failed full
  run or claim a second complete run against an immutable DLL.
- Architecture, TypeScript, button-standard and parser checks passed; Rust
  reported 74 passed and one ignored.
- Source, frozen and installed smoke each passed all 103 checks. These include
  GPIO execution, model solves, save/undo/reuse and nearest-parallel-wire snapping.
  Wide and narrow source wiring captures were inspected for readable controls
  and branch-target feedback; automated smoke is distinct from interactive QA.

The unsigned installer is
`package-final/SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`, 111,761,332
bytes, SHA-256
`f2821365e88ef71fb4b61ed8e16aa84feb2a837272190b47467e595d32eedcb2`.
Its Inno compile and local update completed successfully. The per-user install
at `C:/Users/yawar/AppData/Local/Programs/SPIKES Studio` matches all 1,692 frozen
payload files with no mismatches or forbidden Qt files (`installed-payload.json`).
The installed DLL matches the final native hash. Appearance settings retained
their original hash; Start Menu shortcut and per-user uninstall registration
exist. This is the explicitly requested local preview update, with
`releasable=false`, not public release promotion.

Normal installed startup was observed through the native UI: RC demo revision
zero, three components, no probes, preserved Midnight appearance, and readable
schematic/toolbars (`installed-normal-startup.png`). The app was left open.

## Final installed-engine timing

`competitive-installed-engine.json` binds the exact installed DLL above and
records five repetitions per case. All nine shared cases passed for each engine.
Median of case medians: SPIKES 268.7344 ms, ngspice 72.1775 ms, LTspice
644.6966 ms. SPIKES remains about 3.72 times ngspice on this small cold-process
corpus. This final observation is slower than the earlier 172.1053 ms result;
it does not establish an end-to-end cold-start improvement for the installed
candidate. The engine artifact changed from the controlled pair, and other
chats had local test processes active. Both reports are retained; the faster
observation is not substituted for the final installed-engine result.

The final engine's solve-excluded paired extraction check
(`channel-benchmark-final-engine.json`) preserved all values across nine
channels: scalar median 14.80855 ms, cached channel-helper median 6.1443 ms,
about 58.5% less extraction time. This verifies a bounded Python extraction
improvement while leaving the larger cold-launch gap unresolved. Each point
still crosses the scalar ABI with its return code checked.

Knowledgeable human numerical/device review and public release review remain
open. Synthetic circuit checks, catalog presence and a successful local build
do not establish GPIO electrical limits, vendor behavior, physical validation,
or production qualification.
