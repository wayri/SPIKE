<!-- SPDX-License-Identifier: Apache-2.0 -->
# EMerge / AC / thermal release-candidate integration - 23 October 2026

## Identity and bounded outcome

Integrated into current SPIKE source version **0.4.0-alpha.1**, not retroactively
into published installers. Existing numerical admission gates and experimental
statuses are retained. Source changes remain uncommitted in a concurrently
modified checkout; this is not a clean, signed release snapshot. No remote push,
tag, installer publication or replacement of the existing bundled worker occurred.

The local AC weak-terminal repair is automatically used by its existing PDN
worker route. New source process exposure is owned by service_em_cosimulation.py
and cli_em_cosimulation.py. These call the actual previously verified kernels,
not duplicate numerical implementations. Methods cover EMerge preparation,
sample-exact circuit AC, conservative external-resistor heat and the same-mesh
dielectric/heat/elastic chain. Request schemas are in the schema catalog.

The desktop EMerge result view exports an editable co-simulation draft. Every
terminal mapping and wave convention is deliberately left unapproved. Four
guarded Python Workspace templates expose reviewed requests without automatic
execution or result promotion. Optional RESULT_FILE retains a complete returned
record at a new path, refusing overwrite. Inputs and workflow are documented in
[the bridge guide](../EMERGE_COSIMULATION.md#desktop-and-cli-workflow).

## Executed verification

- New worker/CLI/schema suite: 6 tests passed. Includes real implementations,
  subprocess worker and CLI, malformed fields, source warning preservation,
  blocking-error refusal and structured failed output.
- Combined new numerical/worker/build/resource integration: 24 tests passed,
  zero skips, 14.503 s, including refusal to reset existing/outside candidate paths.
- Schema catalog, existing CLI and worker entry: 54 tests passed, zero skips,
  20.812 s. Earlier affected numerical suites also passed in the implementation
  worker. These are scoped tests, not the full repository suite.
- Frontend TypeScript check and production Vite build passed (2270 transformed
  modules). Existing large-chunk/static-dynamic-import warnings remain; no
  threshold was raised. The final build completed in 21.97 s; its log is
  build/emerge-release-frontend-20261023.log.
- EMerge draft export, original sampled-network review, runtime-update behavior
  and shared button/control tests passed. The template catalog passed with
  63 templates, 20 categories and 20 guarded execution runners, including
  compilation and guarded dispatch checks for the four additions.
  Draft export refuses nonfinite source values instead of silently serializing
  them as null. Result-file tests verify warning retention and overwrite refusal.
- Native GUI visual inspection at wide/narrow widths was not performed; the
  production frontend build and behavioral checks do not substitute for it.

Tests used repository .venv and writable TEMP/TMP directories under
`.local/test-temp`, with OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and
MKL_NUM_THREADS set to one for numerical checks. No acceptance tolerances or
gates were relaxed.

The shared CLI/worker registration invalidated earlier source-bound receipts.
The integration replays their actual gates instead of relabeling source hashes.
Final refresh: **28 stages / 349 tests passed**, with fresh
`docs/validation/parity/*-em-integration-20261023.{json,log}` artifacts and
matching log hashes. Only the corresponding main evidence pointers were
updated; historical receipts, thresholds, acceptance rules and stage statuses
were preserved. Backlog integrity passed for all 68 capability families;
the post-parity gate remains closed. This is source/evidence integrity, not
whole-suite or engineering sign-off qualification.
The PI01-S01 EBrake replay completed its public CLI and 28 owned-pad tests, but
the original current-density convergence diagnostic remains
`failed_to_converge`, `can_sign_off:false`. This expected failure is retained,
not converted into physical qualification by a passing evidence/execution gate.

## Actual frozen artifact

The pinned PyInstaller 6.21.0 environment built a separate Windows x64 candidate:

```
python scripts/build_packaged_worker.py --candidate-root build/emerge-release-candidate-20261023
```

This preserves app/src-tauri/resources/worker. Candidate executable:
`build/emerge-release-candidate-20261023/resources/spike-worker/spike-worker.exe`.
Its complete onedir payload is required; the executable alone is not portable.
The completed frontend was also retained at
`build/emerge-release-candidate-20261023/frontend`, including the new EMerge
handoff and Python Workspace assets. Its index.html SHA-256 is
`8725c05ec06f5ce5fcc5d5b0a274e75d8660968ae75b3dbcc933ada712c9f4ec`.
These are side-by-side candidate assets, not an assembled native installer.

The builder's existing health, native runtime, source/package parity, Arrow,
native CFD, SPIKES and extension probes passed. Permanent runtime benchmarks
passed **15/15, zero failures/skips**. The new release probe also ran real source
and frozen-worker prepare/AC/resistor-thermal methods: matched 50 ohm circuit,
2 V RMS source, current 0.02 A, known series heat 0.02 W. A one-tetrahedron
discrete conduction oracle produced free-node 300.01500000000004 K against
300.015 K, unchanged 1e-10 K absolute acceptance. These synthetic packaging
checks do not establish physical EMerge field accuracy or continuum mesh
convergence. Their independent power-wave/heat foundations and limits are
in [the method record](../EMERGE_COSIMULATION.md).

The frozen CLI additionally processed all seven frequencies from the retained
patch replay, and the frozen worker executed the 48-tetrahedron dielectric /
thermal / mechanical request, retaining experimental/production-false status.

Local evidence:

| Artifact | Location |
| --- | --- |
| Full build log | build/emerge-release-candidate-20261023.build.log |
| Integrity and runtime manifest | build/emerge-release-candidate-20261023/resources/spike-worker.manifest.json |
| Source probe | build/emerge-release-source-probe-20261023.json |
| Frozen probe | build/emerge-release-packaged-probe-20261023.json |
| Code-to-source comparison | build/emerge-release-source-match-20261023.json |
| Retained-data frozen CLI AC output | build/emerge-release-packaged-ac-20261023.json |

Code verification used:

```
python scripts/verify_packaged_source_modules.py build/emerge-release-candidate-20261023/resources/spike-worker/spike-worker.exe --require-em-cosimulation --output build/emerge-release-source-match-20261023.json
```

**472 modules matched, no changed/missing/required-missing modules.** This
checks instruction/constants/line-table equivalence with normalized filenames,
not the native libraries' source correctness. Their bytes are separately hashed
in the worker manifest. Executable SHA-256:
`567b953d2f53053f30cf45576195abe0c1cbf14f2f0bb509aeae320471f98e3d`.
Manifest SHA-256:
`b48e73724fb4c8da0ce34b39520cedd34d545307e2759840e6441aa71e87e142`.

## Release boundary

This integration does not mean a new published or installed desktop release.
The native installer has not been rebuilt, installed or visually qualified here.
A frozen whole-source identity, full mandatory regression, knowledgeable human
numerical review, supported-platform clean-machine/offline/upgrade/uninstall
qualification and applicable signing/publication policy remain release gates.
Do not replace published artifacts or label this a fully qualified release.

## Subsequent reviewed source increment (not in the above binary)

The new [linear owned-SPICE composition](EM_SPICE_COUPLING_20261023.md),
[supplied-field heating](EM_BODY_HEATING_20261023.md), and
[tetrahedral CHT](CFD_CHT_RELEASE_20261023.md) now have worker routes; SPICE and
body heating also have `em-cosim spice` / `em-cosim body-heating` CLI commands.
The binary and hashes above predate this increment and must not be represented
as containing it. Source/frozen qualification must be rerun.

Independent feedback exposed stale frequency-to-field association; the repair
binds the full field packet and physical context. A refreshed packet digest
does not bypass the independent Poynting closure check. Twenty combined
heating/SPICE tests passed with the stronger corruption regression.
An additional composed distributed-line/native-SPICE test passed at eight
frequencies from 1 MHz to 3 GHz, using an independent spatial matrix exponential
and series-L/shunt-C boundaries. This verifies supplied RLGC circuit algebra,
not board geometry extraction, skin/proximity models or engineering GHz accuracy.

Bidirectional temperature feedback, arbitrary SPICE device coverage, authenticated
EMerge field calibration, a general graphical coupled-study editor and MPI
production capability remain open. No release gate has been removed.
