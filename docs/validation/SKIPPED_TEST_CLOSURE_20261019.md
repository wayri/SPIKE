<!-- SPDX-License-Identifier: Apache-2.0 -->
# Optional-runtime qualification — 19 October 2026

## Acceptance and current outcome

The prior full Python run executed 4,293 tests with 69 skip records. A class-level
skip is one record, not necessarily one test. Qualification must execute the real
runtime and unchanged assertions. Replacing numerical/integration execution
with mock output, expected failures, CPU substitutions for CUDA, or merely
removing decorators does not close a record. Rejection controls may mock a
forbidden launch; those controls are functional/security evidence, not physics
validation.

**66 of those 69 records have passing actual-runtime evidence. Release
qualification is not complete.** The three remaining records are:

| Record | Actual outcome | Required next action |
| --- | --- | --- |
| EBrake fixture class (four tests) | Geometry and DC smoke pass; AC and DC convergence fail | Consistent conforming current support/contact discretization and numerical qualification, not relaxed tolerances |
| CUDA linear systems | Not executed: only Intel Arc hardware is available | Owner explicitly chose to keep CUDA blocked until NVIDIA hardware is available |
| Xyce independent divider | Not executed | Owner explicitly requested deferral for now; no qualified Xyce claim |

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
the unbundled local `full-python-suite-post-timeout-fix-20261018.log` record.

Final passing source-bound receipts use an isolated local source copy at
`build/qualification-20261019-frozen-source`. Each records unchanged project
inputs, runtime controls and explicitly bound artifacts during its execution.
Scratch output is kept outside that source copy when a test creates files in
its working directory. Earlier failed/drifted receipts remain diagnostic, not
acceptance evidence.

| Actual profile | Baseline records / tests | Receipt |
| --- | --- | --- |
| Admitted Windows CPython 3.11 OCC, retained-volume thermal/CalculiX, EMCAD, EMerge and Optycal | 27 / 27 | `build/qualification-20261019-optional/frozen-occ-em-004.json` |
| Native compiled boards/faults, equation/lumped devices, SMPS and fresh TCAD console | 31 / 31 | `build/qualification-20261019-native/frozen-native-003.json` |
| Actual Renode firmware, including three newer execution/plant/load tests | 7 / 7 | `build/qualification-20261019-native/frozen-extra-firmware-001.json` |
| Actual ngspice sine-source/synthetic PDK and KLayout hierarchical GDS inspection | 3 / 3 | `build/qualification-20261019-optional/frozen-reference-solvers-004.json` |
| Actual Linux symlink escape rejection | 1 / 1 | `build/qualification-20261019-optional/frozen-linux-symlink-004.json` |
| Three PWM/electrothermal class records and smooth-source native/ngspice record | 4 / 17 | `build/qualification-20261019-native/frozen-extra-pwm-smooth-002.json` |

There are **73 unique passing skip records, expanded to 86 unique actual test
cases**: 66 records from the original baseline plus seven additional records
identified in the later full run. All 54 non-deferred skip records in that later
run have passing re-execution evidence; the remaining two are owner-deferred
CUDA/Xyce. The EBrake class was executed, not skipped, and still has two failures.
No record is counted twice. The Linux
case ran under Ubuntu WSL and is Linux unit evidence, not clean-machine release
evidence. Native TCAD was rebuilt in an isolated build directory. The current
Radau C API DLL was not overwritten. Runtime prerequisites are local test inputs,
not newly approved redistribution dependencies.

The EMerge integration test now accepts `SPIKE_EMERGE_TEST_PYTHON` as an explicit
installed interpreter, retaining its original default and every mesh assertion.
This avoids assuming that a developer virtual environment exists inside a
relocated source snapshot. No copied/synthetic solver or installed-payload
qualification is substituted. Native firmware and PWM profiles retain actual
compiled-plant, switching-ODE, stored-energy, rollback and CalculiX-history tests.

The qualifier binds all Git-tracked/nonignored project inputs, including
non-Python fixtures, examples, schemas and build scripts. Declared generated /
external runtime directories require explicit artifact binding. Baseline
selection and its hash come from the same read; interpreter, Git executable
and runtime controls are checked before/after. Six unit tests cover rejection
paths, fixture/root-build-script drift and runtime mutation. Source changes
after a run require impact review and affected revalidation; these are
individually bounded profiles, not an independently signed release cohort.

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

## Full regression and importer repair

The broad live-workspace run completed **4,327 tests in 956.524 seconds: two
failures, four errors and 56 skips**. Log:
`build/qualification-20261019-optional/full-python-suite-final-v2.log`, SHA-256
`f064ce2e0ac8f49e9405f04daca6bc333f67c118523a59002a4ff60acd4df2d5`.
Its before/after project fingerprints differ, so it is diagnostic/inconclusive
for coherent-source release qualification, not a pass. An earlier interrupted
run is also retained and never counted as passing.

Both failures are the unchanged EBrake AC and DC-convergence gates. The four
errors were stale WF01 importer evidence after another contributor changed
`source_package.py` logical compressed-matrix root discovery. That change was
reviewed; 68 focused ODB/source/corpus tests passed. All six real CLI imports
were then re-executed from the live root with all 34 bound runner-source hashes
equal to the frozen copy before and after. Each new receipt passed its actual
Done-stage validator, including the retained component-solid/native gate.
No cached native facts were invented or hash-patched.

Fresh `*-refresh-20261019.json` receipts and `*-import-refresh-20261019.json`
artifacts are under `docs/validation/parity/`; the six backlog pointers were
updated only after validation. Previous evidence remains byte-identical.
Tracking/PISI tests subsequently passed **43/43**, and the backlog checker
passed. Logs: `build/import-refresh-20261019-live/`. This fixes the four
receipt errors but does not retroactively turn the broad run green.

The replay also established a useful boundary: moving a source copy changes
absolute imported artifact paths and therefore some native design digests.
Do not transplant cached solid evidence or remove path binding to bypass that
check. Replay at the correct source identity or obtain fresh native evidence.

The final 86-case profiles resolve the applicable skip coverage but do not
replace a coherent full-suite rerun after the numerical repairs. EBrake needs
consistent finite-support/contact and vector-density work, and the general
production packaging/platform/human-review gates remain open. No gate was
weakened, no production capability promoted, and no release published.

Final tooling checks passed: six qualification-tool unit tests, the architecture
check, scoped documentation checks for the three qualification/status documents,
and the owned-file whitespace check. The unit-test rerun used a workspace-local
temporary directory after the sandbox temporary-directory ACL rejected writes;
that environmental attempt is not counted as a passing run.
