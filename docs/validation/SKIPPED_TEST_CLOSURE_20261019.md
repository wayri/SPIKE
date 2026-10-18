<!-- SPDX-License-Identifier: Apache-2.0 -->
# Optional-runtime qualification — 19 October 2026

## Acceptance and current outcome

The prior full Python run executed 4,293 tests with 69 skip records. A class-level
skip is one record, not necessarily one test. Qualification must execute the real
runtime and unchanged assertions; mocks, expected failures, CPU substitutions
for CUDA, and merely removing decorators do not close a record.

**66 of those 69 records have passing actual-runtime evidence. Release
qualification is not complete.** The three remaining records are:

| Record | Actual outcome | Required next action |
| --- | --- | --- |
| EBrake fixture class (four tests) | Geometry and DC smoke pass; AC and DC convergence fail | Consistent conforming current support/contact discretization and numerical qualification, not relaxed tolerances |
| CUDA linear systems | Not executed: only Intel Arc hardware is available | Owner explicitly chose to keep CUDA blocked until NVIDIA hardware is available |
| Xyce independent divider | Not executed: no admitted executable | Provision a reviewed GPL-only build or an appropriately licensed external runtime |

The EBrake failure is detailed in
[its qualification record](EBRAKE_FIXTURE_QUALIFICATION_20261019.md). The former
arbitrary zone-count expectation was replaced by a stricter source-hash-bound,
native KiCad inventory oracle. No completed-solve, passivity, copper-support,
current-density convergence, or release acceptance requirement was removed.

## Re-execution evidence

`scripts/qualify_skipped_tests.py` parses the actual baseline verbose skip IDs,
selects explicit prefixes, expands a class skip through unittest discovery, and
retains an exclusive-create JSON receipt and execution log. It fails on any
skip, failure, error, expected failure, unexpected success, missing test, empty
selection, or source/bound-artifact drift. A passing receipt is scoped test
evidence, never a release qualification claim. Changes after a run require
impact review and revalidation; receipts must not be silently refreshed.

Baseline:
`output/acc01-radau-20261018/full-python-suite-post-timeout-fix-20261018.log`.

Passing source-bound receipts:

| Actual profile | Baseline records / tests | Receipt |
| --- | --- | --- |
| Admitted Windows CPython 3.11 OCC, retained-volume thermal/CalculiX, EMCAD, EMerge and Optycal | 27 / 27 | `build/qualification-20261019-optional/occ-em-final.json` |
| Native compiled boards/faults, equation/lumped devices, SMPS and fresh TCAD console | 31 / 31 | `build/qualification-20261019-native/final-native-profile-20261019-001.json` |
| Actual Renode firmware execution and rejection controls | 4 / 4 | `build/qualification-20261019-native/final-firmware-profile-20261019-001.json` |
| Actual ngspice sine-source and synthetic PDK reference cases | 2 / 2 | `build/qualification-20261019-optional/ngspice-final.json` |
| Actual Linux symlink escape rejection | 1 / 1 | `build/qualification-20261019-optional/linux-symlink-final.json` |
| Actual KLayout hierarchical GDS inspection | 1 / 1 | `build/qualification-20261019-optional/klayout-final.json` |

The 66 selected baseline IDs are unique; no record is counted twice. The Linux
case ran under Ubuntu WSL and is Linux unit evidence, not clean-machine release
evidence. Native TCAD was rebuilt in an isolated build directory. The current
Radau C API DLL was not overwritten. Runtime prerequisites are local test inputs,
not newly approved redistribution dependencies.

## External-runtime provenance and boundaries

Renode's pinned SVD assets were fetched from the exact platform-definition URLs.
Their decompressed bytes matched the existing local Renode cache before use in
an isolated qualification cache. Neither `ApplySVD` nor the shared platform/cache
was modified. The hashes, platform inputs and actual tests are retained in the
native receipts. No redistribution approval is inferred from a successful test;
the STM SVD has no embedded license declaration.

KLayout 0.30.12 win64 portable was obtained from the
[official binary download page](https://www.klayout.de/build.html).
The archive matched the published MD5
`e1faa8a419f85579daf187e23f39c71c`; additionally recorded SHA-256 is
`1ccabcd8ef14e04bc1d3383e83d50747db845b4f9939d3b1901e20f444f9967b`.
MD5 alone is not treated as a security admission. Windows independently verified
the executable's Authenticode signature as valid, signer Open Source Developer,
Matthias Koefferlein, certificate thumbprint
`A1E3A445CD8861E6CBA23A0A20A877107BE8A674` (subject uses the German umlaut).
The portable copy stays in ignored qualification storage; no application was
installed or bundled into a SPIKE release.

The [official Xyce executable page](https://xyce.sandia.gov/downloads/executables/)
explicitly identifies its binaries as **XyceNF**, not the GPL source build. The
downloaded archive contains `Install_XyceNF_7.10.0.exe` and a non-free/export
notice. Archive SHA-256:
`e3073b6335a43ecc732f56944806005c99b1a378c7d21e293779ae05453b955a`.
Only archive metadata and the notice were inspected. The installer was not run,
its solver was not executed, and no license/export approval or numerical pass
is claimed. Do not substitute the separately tested ngspice run for Xyce.

## Packaging qualification

The retained SPIKES 0.3.0-beta.1 archive passes integrity but fails an isolated
import because it omits `python/spike_core`. Existing current packaging source
already includes that tree. New regressions require the native-MNA module,
board parser and runtime requirements in the manifest.

A **fresh development candidate**, leaving the retained archive unchanged,
passes the full verifier from outside the repository with `PYTHONPATH` unset:
726 manifested files, CLI version and functional probe, native console, staging
and removal. SHA-256:
`30bd84715dcadabb9228d9d190bca2d57bdeef564111421c78ac852ab4135f11`.
See `build/qualification-20261019-release/SPIKES_PACKAGING_REPAIR.md` and adjacent
verifier/public-gate reports. This is a dirty-tree development package using
retained version-matched native binaries, not a current-source clean release.

The public gate remains `BLOCKED_EXTERNAL`: signing, clean-machine evidence and
auditable CI are absent. The broader SPIKE desktop has no matching current
four-platform artifact set, dependency approvals remain pending, and required
knowledgeable human numerical review is not supplied by agent testing.

## Full regression

A final full run with the real EBrake fixture and available native/reference
runtime opt-ins is required after source/receipt coordination. An initial run
was stopped when the parity owner identified a stale expected-stage catalog;
it is interrupted/inconclusive, not a passing qualification result. Preserve
the execution logs and source hashes rather than suppressing failed cases.
