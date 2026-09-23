# SPIKE 0.2.11 release verification

Built 2026-09-07 as an unsigned engineering preview. EXE and MSI bundles completed.
No installation or clean-machine acceptance has yet been performed for this version.

Includes current shared-tree UI, assembly, SI, meshing and bounded CFD/field
increments. Independent SI batch setup/results are session-only and exportable.
External openEMS/CSXCAD, Gmsh and WSL OpenFOAM are not implied to be bundled.

Qualification boundaries: docs/CROSSBOARD_FIELD_MODE_INCREMENT_20260907.md,
docs/NBS_YAGI_COMPARISON.md, docs/FOUR_BOARD_EXECUTION_CHECKPOINT.md,
docs/FAN_CHT_QUALIFICATION.md and docs/SI_NETWORK_GRAPH_INCREMENT_20260907.md.
The cross-board stability screen failed; no production flags are promoted.
Do not distribute original exploratory NBS absolute-power evidence without its
power-normalization-correction.json sidecar. Large build evidence is not part
of the installer by default.

## Verification record

- All 55 frontend test scripts passed after help regeneration; TypeScript and
  the production frontend build passed.
- Native host: 35 passed, one live OS-counter smoke test ignored.
- Initial full Python run: 1,694 tests, two failures, three errors, 11 skips.
  Log: build/release-0211-python-tests.log. This was not an all-green run.
- Reconciled optional OCC dependency handling (lazy Shapely import with explicit
  fail-closed error). Seven OCC tests pass in installed CPython 3.11; the core
  CPython 3.12 suite skips that optional runtime, and an unconditional missing-
  dependency regression passes.
- Corrected unsupported-model test drift (NPN is now supported; PNP remains the
  negative fixture). Rebuilt stale SPICE DLLs from current source using the
  existing complete Eigen 3.4 headers and Visual Studio developer environment.
  All 29 focused parser/native-ABI rechecks pass. Full discovery was not rerun
  after these corrections; this distinction is retained for preview delivery.
- Packaged worker 0.2.11: runtime parity 8/8 and analytical benchmarks 15/15.
  Owned SPICE interactive replay is bit-exact; observed RC error 2.22e-16 V.
- Source snapshot: 1,050 identities, unchanged through compilation. See
  build/release-0211-source-snapshot-final.json.
- Native Computer Use observation: new workspace-built executable displays
  v0.2.11, renders the workbench (not a directory listing), reports Desktop worker
  ready, and expands the minimized ribbon while preserving workspace tabs.
  No actual four-Marble, installer upgrade or clean-machine UI qualification was
  performed by this check. The binary was launched directly, not installed.

Installer build log: build/release-0211-installer-build.log. Artifact hashes and
final delivery status are recorded in the installer manifest after bundling.

## Delivery

Archived at artifacts/windows/releases/0.2.11-preview-20260907/.

| Installer | Bytes | SHA-256 |
| --- | ---: | --- |
| SPIKE_0.2.11_x64-setup.exe | 97019633 | f6c570abd4375a1adbc481fe844e5332b21082386515d897ea8adcd2ee3627b2 |
| SPIKE_0.2.11_x64_en-US.msi | 136555999 | 8fd311577a53ac9d9fe77167f60583570b6d584acf4190ca4d46778fe32521df |

Both are NotSigned, production_qualified=false. This release was built and
locally launched for verification, not installed or published to an internet
release repository. The archive includes the package manifest, worker manifest,
runtime parity record, input snapshot and this verification record.
