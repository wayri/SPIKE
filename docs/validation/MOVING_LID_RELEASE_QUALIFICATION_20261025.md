<!-- SPDX-License-Identifier: Apache-2.0 -->
# Moving-lid integration and local 0.4.1 candidate qualification

Date: 25 October 2026. This record concerns a local engineering candidate,
not publication or production qualification. No acceptance threshold was relaxed.

Latest status: **not release-qualified**. The corrected full-suite attempt was
interrupted by a delegated Linux copy error that exhausted C:. Ubuntu starts
again, retained Linux artifact hashes match, and all 6,475 guarded Windows inputs
are unchanged. Only proven duplicate task staging was removed. See the
[incident and recovery record](QUALIFICATION_DISK_INCIDENT_20261025.md).
A fresh complete full suite remains required after host capacity is restored;
the partial run is not acceptance evidence.

## Numerical change

The returned native cavity fields now pass an independent conservative MAC
momentum residual check before runtime admission. The checker reconstructs
convection, diffusion, pressure gradients and wall ghosts using exact rational
arithmetic on the declared binary inputs. Its tolerance is derived from the
requested steady-state tolerance and a bounded timestep, not the solver's
self-reported residual. Pressure corruption and inflated-timestep cases reject.

See [the independently authored derivation and limits](NATIVE_CAVITY_MOMENTUM_20261025.md).
This is a discrete returned-field verification gate, not a continuum convergence,
turbulence, arbitrary-enclosure or measured validation claim. Knowledgeable human
numerical review is still required before release.

The V1 result schema adds optional diagnostics for archived-result compatibility.
Fresh runtime output must pass the new check; missing archival diagnostics never
establish verification. The frozen-worker builder now mandates an actual n=8,
Re=100 moving-lid execution and verifies its bundled native executable identity.

## Executed checks

- Focused integration: 47 tests passed; contract/archival compatibility run: 22
  tests passed. These overlapping selections are not 69 unique tests.
- Independent momentum module: 11 tests passed, including actual native cases
  (n, Re) = (8,1), (8,100), (8,400), (12,100), (16,100), and adversarial
  mean-zero pressure corruption. These five cases are not a refinement study.
- Windows frozen builder: all eight runtime qualification checks passed,
  including mandatory momentum, conduction/incomplete-state, EM co-simulation,
  tetrahedral CHT and SI execution probes.
- Installer build: frontend build passed; Rust tests reported 81 passed and one
  ignored live OS-counter test. That one test subsequently passed when invoked
  explicitly; see `build/moving-lid-rust-live-counters-20261025.log`.
  MSI and NSIS builds completed successfully.
  This does not establish installed lifecycle or native visual acceptance.
- Fresh Windows native CTests: 2/2 passed in 137.22 seconds, including the
  native airflow and CHT executables. Log:
  `build/moving-lid-native-windows-ctest-20261025.log`.
- Frontend board-parser regressions and the architecture check passed.

Windows evidence is retained under `build/moving-lid-*20261025*` and the
task-owned `D:/SPIKE-moving-lid-qualification-20261025` directory. The prior
local 0.4.1 installer cohort was retained byte-for-byte in its
`retained-previous-041` subdirectory. Existing alpha releases were not overwritten.

## Linux worker evidence

Ubuntu 24.04.3 under WSL2, x86-64, CPython 3.12.3 and GCC 13.3:

- Source comparison: 815/815 exact files (550 modules, 265 schemas).
- Fresh native CTests: 2/2 passed, with builds limited to one parallel job.
- Momentum suite: 11/11 passed with actual native execution.
- Frozen builder runtime checks: 8/8 passed.
- Frozen CLI: 106 surfaces plus help/version/inspect/error probes passed.
- Six retained AC/CHT full-field comparisons passed with unchanged absolute and
  relative tolerances of 1e-10; analytical refinement gates were not altered.

Worker SHA-256:
`6e85e12820fb4547f4bd337d4b7156f03bfdfaec3b974c501774e7463280df4d`.
Evidence: `build/linux-ac-cht-20261024/moving-lid-final-r2/`, including source
comparison, native build/test logs, runtime qualification, full-field replay
and an evidence hash ledger. The initial missing-environment skip was retained;
the corrected execution ran all 11 momentum tests without skips.

Linux desktop, Flatpak, installed lifecycle and a separate clean machine remain
unqualified. WSL2 evidence does not establish all supported Linux platforms.

## Installer identity and extraction

The corrected R3 cohort completed the normal build/test recipe, with no
`SkipTests`: frontend build passed; Rust 81 passed/one ignored; internal MSI
version admission passed. Read-only inspection confirmed
`ProductVersion=0.4.1`, ProductCode
`{C2C5B16D-8A06-4CD2-9AD5-352FC803FAC9}` and unchanged UpgradeCode
`{BBA57EF9-76C0-5C52-A979-C69A18367266}`.

| Corrected R3 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `SPIKE_0.4.1_x64_en-US.msi` | 169823189 | `9fecb586b1426c4ca6c01815c3f3458bae859fb494331e0f2bcaaa18a3e2640f` |
| `SPIKE_0.4.1_x64-setup.exe` | 129588484 | `0ccf124dcf5bf93a2913a2b9daaa58075047459510e8723a51b13f5210e041a0` |

R3 remains unsigned and explicitly engineering-preview, not release-qualified.
Evidence: `build/moving-lid-installer-r3-20261025.log`,
`build/moving-lid-msi-metadata-r3-20261025.json`, and the current installer
manifest. Its administrative sequence contained only the eight reviewed standard
actions, and extraction into the fresh `msi-image-r3` directory passed without
installing the product. The source Tauri configuration was restored. A transient
architecture check against staged build resources failed; after restoration,
the Python architecture and Node button/control checks both passed
(`build/moving-lid-architecture-r4-20261025.log`). The failed log is retained.
All 32 MSI-version/release/installer regression tests passed, including CLI
fixture execution and rejection of the original stale version.
The complete corrected-MSI extracted-worker check then passed: all 1,478 file
hashes, 550-module source coherence, 265 schemas, moving-lid/conduction/EM/tetra/
SI probes, 106 CLI surfaces and all six AC/CHT full-field comparisons at unchanged
absolute/relative 1e-10 tolerances. Evidence:
`build/moving-lid-msi-verification-r3-20261025/report.json`.
The extracted worker remains byte-identical to the independently verified
Windows worker (`0ddf2417aaad594b26a76d2261e4c068c166ccd371b5b61229512ac281c821d6`).

The superseded first rebuilt unsigned preview artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `SPIKE_0.4.1_x64_en-US.msi` | 169831384 | `500ee35ec63720a727127ac69da29fa610ff461f85fc8fad5645207aeae88ffa` |
| `SPIKE_0.4.1_x64-setup.exe` | 129595050 | `685d22137d80adef83d80dd4ecb3d64cebff70a8164b813805c5ce39d7e64200` |

This first rebuilt cohort is not eligible for promotion: read-only MSI metadata
inspection found internal `ProductVersion=0.3.12.1` despite the 0.4.1 filename.
The stale explicit WiX override is a packaging defect. Windows compares only
the first three version fields; the fourth field cannot repair upgrade ordering
([Microsoft ProductVersion documentation](https://learn.microsoft.com/en-us/windows/win32/msi/productversion),
reviewed 2026-10-25). A corrected build must independently pass internal-version
admission, not merely produce the expected filename. The first cohort and all
its evidence remain retained even when superseded.
Its original MSI, NSIS and manifest bytes are retained under the task-owned
`retained-msi-version-mismatch-r1` directory, separate from corrected R3 files.

These first-cohort artifacts were built under `artifacts/windows/installer/`, with
`SPIKE-0.4.1-preview-installers.json`. The MSI administrative extraction completed
successfully into the task-owned `msi-image` directory. All 1,478 extracted worker
files matched the independently verified build's file sizes and hashes.
Extracted worker SHA-256:
`0ddf2417aaad594b26a76d2261e4c068c166ccd371b5b61229512ac281c821d6`.

The extracted runtime passed momentum, conduction/incomplete-state, EM
co-simulation, tetrahedral CHT, SI/PAM3, 550-module source coherence, all 265
schema comparisons, 106 CLI surfaces and all six AC/CHT field comparisons at
unchanged absolute/relative 1e-10 tolerances. Full-field reference report SHA-256:
`f525e0a5ca4fe05ead5069dd5300aa7c6da275e6482d532a7e22f7853be62d0e`.
Evidence: `build/moving-lid-msi-verification-r2-20261025/report.json`.
The first sandbox attempt failed to create its native child's temporary
directory; that failed log was retained and the real probes were rerun outside
that sandbox. No software admission or numerical gate was bypassed.

Administrative extraction is not installation. The existing installed alpha.1
and user data were not upgraded or uninstalled. The terminal source-guarded
full-suite report is recorded separately after completion; no in-progress check
is counted as passed here.

## Importer cohort and preserved gates

The first complete guarded suite ran 5,647 tests in 2,261.258 seconds:
one failure, 45 errors and 79 skips. Its 5,444 guarded source files were
unchanged. The failure/error tracebacks concern stale source-bound receipts;
they are failures, not waived checks. Report and complete log:
`build/moving-lid-qualification-20261025/`. The initial adoption edit had updated
historical audit pointers rather than active `stages[]` pointers. Correcting that
integration mistake requires adoption of genuinely replayed evidence and another
qualification run; the first failed report remains intact.

After actual stage-pointer adoption, all 48 focused receipt/adversarial tests
passed (`build/moving-lid-receipt-adoption-tests-20261025.log`). An independent
walk of all 54 currently completed stages admitted 53; SI08-S05 alone rejected
with `Stale native evidence validator`
(`build/moving-lid-active-stage-audit-20261025.json`). The original canonical
WF01-S04C6 receipt is retained as `WF01-S04C6-pre-movinglid-20261025.json`;
its replacement is the byte-identical newly executed receipt, not edited old
observations. The PI01-S02 base/annular/scaling receipts were genuinely rerun
into `docs/validation/parity/` with 23/30/80 tests respectively, no skips and no
whole-stage completion. Their earlier build-only replays remain retained.

The module migration invalidated historical source-bound receipts. Forty-nine
stages received actual fresh replays; old evidence was retained, not rebound to
new source hashes. Receipt inventory:
`build/moving-lid-receipt-pointer-updates-20261025.json`.

The owner explicitly approved a separately identified fresh WF01-S04B ODB cohort.
It preserves all new UUIDs/hashes and the prior evidence: 23 archive members,
21 byte-identical, two timestamp-only changes and eight disclosed temporary
shape UUID pairs. Physical geometry and counts matched under the unchanged
gate. Evidence and comparison remain in
`build/wf01-movinglid-replay-20261025/WF01-S04B-fresh-cohort-r2/`.

The fresh owned-pad diagnostic still reports `failed_to_converge` and cannot
sign off. A passing receipt-validation test does not turn that physical result
into a passing accuracy gate.

SI08-S05 still needs fresh correctly targeted native visual evidence after the
module migration. The 13-test headless integration passes but explicitly reports
`stage_complete=false` and `native_visual_verified=false`. Native UI automation
was stopped after the launcher resolved to installed alpha.1 rather than the
candidate; no screenshots or old observations were relabelled as new evidence.
This gate remains open, not waived or downstaged.

## Release status

Not release-qualified. Required remaining evidence includes the terminal full
suite with stable source bindings, fresh SI08-S05 native visual acceptance,
authorized disposable install/upgrade/rollback/uninstall checks, Linux desktop
and clean-machine qualification, and knowledgeable human numerical review.
No publication, commit or push is implied by these local artifacts.
