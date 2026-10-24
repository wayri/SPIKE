<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors -->
# Alpha.2 AC/CHT packaging qualification — 24 October 2026

## Identity and boundaries

This is the local **0.4.0-alpha.2 engineering preview**, not an overwrite of
published alpha.1. No public artifact has been published by this work. The
worktree includes concurrent contributions; a Git HEAD alone does not describe
the package. The retained inspected source snapshot binds 508 Python modules
and 263 schema JSON files to the worker below. It is not a complete rebuildable
native-source release archive or an attribution/redistribution approval.

Worker: `build/ac-cht-alpha2-worker-20261024/resources/spike-worker/spike-worker.exe`

SHA-256: `e3aadaac01a76d8d4cfd47cb50505c682e9ee82cdff1d5809df2861fdf1d177c`

Inspected baseline:
`build/ac-cht-alpha2-worker-20261024/inspected-source-baseline/SOURCE_SNAPSHOT.json`.

Build: Windows x64, Python 3.12.9, pinned PyInstaller 6.21.0. The manifest
records 15/15 benchmark cases and 8/8 source/frozen runtime comparisons passing,
plus Arrow, owned linear SPICE, extension and tetra CHT probes. The added
`run_em_network_resistor_cht` route executed in a fresh packaged process:
0.02 W explicit resistor heat mapped to a retained solid cell, nonzero solved
flow, relative cell-energy defect `1.7347234759768068e-16`. Unclassified network
power was not deposited as heat. These synthetic packaging oracles are not fresh
EMerge execution, measured EM-body heating, turbulence or production validation.
Optional Studio/controller execution is not qualified merely by module presence.

## Linux MINRES compatibility repair

The actual Ubuntu SciPy 1.11.4 call failed because it accepts `tol`, not `rtol`.
The implementation now inspects the callable signature and supplies exactly
`1e-14` under the supported name. Unsupported signatures fail explicitly; an
internal TypeError is never caught and retried. Existing independent residual,
conditioning, restart and iteration acceptance gates are unchanged. No new
iterative algorithm, preconditioner, physical model or unit conversion is added.

Primary API material reviewed:

- [SciPy 1.11.4 MINRES reference](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.minres.html):
  `tol` and its relative-residual semantics.
- [Current SciPy MINRES reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.minres.html),
  page reviewed as 1.18.0: `rtol` with relative-residual semantics. This does not
  upgrade the Windows tested runtime, which remains SciPy 1.17.0.

Only API semantics were used; no upstream implementation or example was copied.
Windows compatibility plus Stokes tests passed 16/16. Both previously failing
Linux cases plus the two compatibility tests passed 4/4, followed by post-fix
refinement and runtime/memory benchmarks. See the
[Linux evidence](LINUX_AC_CHT_QUALIFICATION_20261024.md) for exact environments,
source hashes, observations and remaining packaging gates.

## Windows installer evidence (retained R1)

Verified worker resources were staged separately at
`build/ac-cht-alpha2-resources-20261024` using
`build/ac-cht-alpha2-tauri-20261024.json`; the default installed/bundled worker
was not replaced. The preview installer build runs the existing mandatory
architecture, error/schema, frontend and Rust tests without `SkipTests`.
The build completed with both unsigned engineering-preview artifacts. The
existing Rust suite passed 79 tests with one marked live-counter test; that
exact library executable then passed the live-counter test separately (1/1).
The parser regression, architecture, 12 error and 13 schema tests and frontend
build passed. Initial sandbox socket-denial failures are retained separately;
the unchanged Rust tests passed outside the sandbox. No `SkipTests` was used.

The first installers and manifest are retained unchanged under
`artifacts/windows/installer/ac-cht-alpha2-r1-pre-supervision/`.

| R1 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `SPIKE_0.4.0-alpha.2_x64-setup.exe` | 126784905 | `3a776fd00a585a6d19a48cc0a10644d496c1049ab7f7f3d6d7e7843d20fba8a6` |
| `SPIKE_0.4.0-alpha.2_x64_en-US.msi` | 166923268 | `31fbf281dc9e7ff1d001e9d95453502071566f9610d7d3e452a90dac35243da0` |

`SPIKE-0.4.0-alpha.2-preview-installers.json` records `NotSigned` and
`production_qualified:false`. The source Tauri configuration was restored by
the build script; the subsequent architecture rerun passed. A concurrent
architecture check during temporary staged-resource substitution is not
equivalent to that post-build result.

The staged frozen CLI passed all **106 help surfaces**, version, actual inspect
and structured-error comparisons against source. The MSI's inspected admin
sequence contained only standard extraction actions. Administrative extraction
to a fresh build directory exited zero, without installing/registering SPIKE or
executing its WebView download action. The extracted worker hash matches the
retained worker above. Extracted desktop SHA-256:
`7f74445a4d67b11b4b3deb95ce46a8f60b5419059f9a30c2c816a3b09f99b0ec`.
The extracted worker's manifest verifies all **1475** declared file members;
its actual AC/CHT/owned-SPICE runtime probe passed again from the extracted image.
See `build/ac-cht-alpha2-msi-worker-integrity-20261024.json` and
`build/ac-cht-alpha2-msi-cosim-20261024.json`.

The extracted MSI worker also replayed all **six** already-gated analytical
refinement inputs (conduction limit and tangent shear, levels 1/2/4) through the
public JSON-line route. Full AC sample arrays and full retained CHT fields agree
with the analytical-qualified Windows reference at `rtol=atol=1e-10`; cell and
global heat defects remain at most `1e-9`. The verifier binds the executable,
reference report, every input/output and its own source hash, and rejects source
artifact drift before publishing a passing report. Three negative/shape/drift
tests pass. This is field-equivalence replay of an independently derived
reference, not an additional independent solver or measured dataset.

Reproducer (fresh output required):

```powershell
.venv/Scripts/python.exe scripts/verify_packaged_ac_cht_refinement.py `
  build/ac-cht-alpha2-msi-admin-image-20261024/PFiles/SPIKE/bundled/spike-worker/spike-worker.exe `
  build/em-network-cht-runtime-20261024 build/new-frozen-refinement-replay
```

Retained final report:
`build/ac-cht-alpha2-msi-refinement-replay-r2-20261024/report.json`.
Earlier R1 evidence is retained; R2 additionally binds the verifier and checks
all reference artifacts again at the end. No solver tolerance changed.

## Windows-matched Linux worker

The final R4 isolated Linux candidate matches **775/775** retained Windows Python
and schema files byte-for-byte. It preserves the earlier Linux candidate and
does not replace later live-workspace edits. Its native build and dependency
identities are separately recorded; this Python/schema comparison is not proof
of complete native-source or compiler reproducibility.

Linux executable SHA-256:
`996a5e1c67d89669de16bb463b125893e8d4fe473b6417886e2267720b5d730b`.
Its mandatory source/frozen checks pass 8/8, packaged CLI checks cover 106 help
surfaces plus version/inspect/errors, and all six frozen AC/CHT field replays
pass against the same Windows analytical-qualified reference at `1e-10`.
Native airflow/CHT CTests pass 2/2; initial focused source checks pass 62/62.
The [Linux record](LINUX_AC_CHT_QUALIFICATION_20261024.md) retains exact runtime,
wheel locks, native identities, source comparisons and executable paths.
This establishes a bounded Windows/Linux worker preview, not an installed Linux
desktop release, Flatpak qualification, measured physics or all-suite clearance.

Administrative extraction is **not installation acceptance**. The fixed GUI
verifier refused to proceed while an unrelated development frontend occupied
port 1420; its guard has not been bypassed. Clean-machine installation, normal
workspace GUI, offline WebView coverage, upgrade/uninstall, full-suite coherence,
license/notice approvals and knowledgeable human numerical review remain
independent gates. Neither source tests nor extracted-payload execution waives
them. No existing user installation or data was replaced by these tests.

## Desktop supervision follow-up

Final integration inspection identified missing heavy-job classification for
AC-network, resistor/thermal/CHT, owned-SPICE, EM-body and tetra-CHT calls. The
source now routes these explicit methods through the existing heavy-job claim,
cancellation and watchdog policy; it adds no new numerical fallback or tolerance.
The focused Rust classification test passes. R1 does not contain this late
desktop fix, so it is not silently relabeled as the corrected installer.

A separate R2 installer build retains the exact R1 worker and frontend assets
while compiling the corrected native desktop. The preview builder's optional
`FrontendSnapshot` accepts only an existing directory strictly below this
checkout's build root, rejects reparse points, and is forbidden for production.
It still runs all mandatory tests; eight script-boundary tests pass. This avoids
mixing a later concurrent SI frontend with the older verified worker. R2 build
and extracted-payload results must be recorded separately before acceptance.

## Corrected R3 candidate and regression rerun

R2 is an intermediate build, not the final preview: its retained frontend still
contained the alpha.1 solver-block catalog version. That source version is now
alpha.2. The corrected R3 Windows worker includes 510 modules and 265 schemas;
its SHA-256 is
`8c5d2a7038b467126663e1ff2f8189e00893f39e499b94fc655947b37e733308`.
The matching Linux R4 candidate above includes the same 775 inspected files.
Both final workers pass all six frozen AC/CHT field replays. The Windows R3
worker also passes the actual JSON-line multiport fixture-removal recovery and
late-singular-sample rejection test; this is not vendor AMI or board validation.

The completed first full loopback-enabled Python regression run executed 5392
tests with two failures, six errors and 84 skips. Findings included transient
Windows extension-directory rename denials, missing new multiport schema IDs,
the stale frontend catalog version and three stale SI receipts. The directory
rename fix retries only Windows sharing/access denials within a fixed budget;
collision, permanent-error and rollback checks remain enforced. Its focused
and neighboring checks pass (11 and 20 tests). The schema owner supplied exact
unique IDs, and 16 release/catalog checks pass. SI receipts must be genuinely
replayed by their owner, not edited to match hashes. The complete rerun is
recorded in `build/ac-cht-alpha2-full-unittest-r2-20261024.log`; it completed
5421 tests with **two failures, 30 errors and 84 skips**. All 30 errors reject
stale/foreign SI evidence; the failures concern catalog equality and capability
mapping. Fresh isolated catalog checks pass 14/14 afterwards, which does not
erase the failed mutable-worktree run or distinguish concurrent-edit effects
from in-process state contamination. The SI owner is replaying receipts under
a source freeze. No coherent full-suite green result is claimed.

Subsequent scoped SI repair evidence is retained separately in
`docs/validation/parity/SI08-S05-integration-r2-20261024.json` and its logs.
Root independently verified all 27 recorded current source hashes, equal
before/after hashes, passing bounded status, and false native-visual, stage,
family and production flags. Its log records 13 Python checks passing; the SI
owner additionally reports genuine replay of 27 affected suites (321 checks),
updated receipt pointers/history, 15 backlog checks and 16 catalog/readiness
checks passing. These later scoped checks do not retroactively pass the full
5421-test run or qualify the retained installer against later source edits.

A first R3 installer attempt failed on a locked shared `app/dist/demo` output.
Preview frontend builds now use an isolated GUID output under `build/`, with
the existing immutable embedded snapshot and all mandatory tests retained.
Production frontend policy is unchanged. Nine build-script boundary tests pass.
The isolated final installer run is recorded in
`build/ac-cht-alpha2-final-installer-isolated-r3-20261024.log`; its Rust library
suite passes 81 tests with one ignored live-counter test. Build completion and
final extracted-payload checks must be recorded before accepting this candidate.
The exact current debug-library executable used by this build subsequently
passes that ignored live-counter check explicitly (one passed, 81 filtered),
recorded in `build/ac-cht-alpha2-r3-rust-current-live-counter-20261024.log`.
The similarly named earlier release-library probe has only 41 tests and is not
substituted for this current-library evidence.

The isolated R3 build subsequently completed both bundles with mandatory tests
enabled, and the post-build architecture check passed after source config
restoration. These are the corrected current engineering-preview artifacts:

| R3 artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `SPIKE_0.4.0-alpha.2_x64_en-US.msi` | 167018464 | `56c97805228aaa78c2c2e8893d0e6e071e13c6e5d896bfe0e92413004d0cdbe1` |
| `SPIKE_0.4.0-alpha.2_x64-setup.exe` | 126859181 | `3e41d586fd5edbfced27ae0e2499731cf8d847a5d3a00e5e881caba695fa8768` |

Both remain unsigned and `production_qualified:false`. Read-only inspection of
the final MSI administrative sequence found only standard extraction actions.
The fixed desktop verifier still refused the live port-1420 development
frontend before launching the GUI; this is retained in
`build/ac-cht-alpha2-r3-desktop-20261024.json`, not bypassed or called a GUI pass.

Final MSI administrative extraction exited zero into a fresh isolated D: image
without installing SPIKE. Every declared worker member passes its size/hash
check; the executable SHA-256 matches R3 above. All 510 modules and 265 schemas
match the retained baseline. The actual extracted worker passes the AC/CHT and
owned-SPICE probe and all six full-field refinement replays at unchanged
`1e-10` field and `1e-9` energy limits. Extracted desktop SHA-256:
`d9c5c9244be4748e105145e1d037e18f1ff907a82ea82c7c65c478e9fdbbb873`.
Evidence:

- `build/ac-cht-alpha2-r3-msi-extraction-20261024.log`
- `build/ac-cht-alpha2-r3-msi-integrity-20261024.json`
- `build/ac-cht-alpha2-r3-msi-modules-20261024.json`
- `build/ac-cht-alpha2-r3-msi-cosim-20261024.json`
- `build/ac-cht-alpha2-r3-msi-refinement-20261024/report.json`

These tests do not establish normal installation, GUI workflows, uninstall,
rollback, offline WebView installation or clean-machine acceptance.

The first complete run's 84 skips are not passes: two are explicitly deferred
CUDA/CuPy and Xyce checks; 31 require other optional external runtimes/fixtures
(23 OCC/Gmsh, one EMCAD, one EMerge, two Optycal, two ngspice, one KLayout and
one KiCad fixture); seven require the opt-in native emulator suite; 42 require
native artifacts/environment bindings (15 board engine, seven CHT executable,
seven test library, four native DLL, three PWM, three TCAD, two SMPS and one
analysis library); two are Windows symlink/junction conditionals. Availability
must be qualified separately before advertising any corresponding feature.
In particular, the bounded retained tetrahedral CHT route verified here does
not imply that the optional native cavity-CHT executable is packaged.
