<!-- SPDX-License-Identifier: Apache-2.0 -->
# Studio workflow and library update — 2026-10-18

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](validation/RELEASE_040_LOCAL_EVIDENCE.md).

The Windows per-user **SPIKES Studio** installation was updated successfully and
opened normally with the user's saved Midnight theme. The component library was
opened in the installed application. This is local build
`studio-workflow-library-20261018-r3`, an unsigned engineering preview of
`0.3.0-beta.6`; it is not a qualified public release.

## Delivered behavior

- Selected-component copy/paste and **Duplicate** (`Ctrl+Shift+D`) start an
  isolated placement preview. Space rotates; clicks repeat placement; Escape
  cancels. Actual symbols and terminals are drawn without creating selectable
  ghost components. Each placement is one undo transaction. Source/dependency
  admission, same-sheet identity, fresh references and non-ground net isolation
  are checked before mutation.
- The browser contains 7,913 generic presets across 105 archetypes: 3,563
  circuit-ready and 4,350 bench-only. Five established configurable lumped-model
  families now expose ordered bulk, substrate, feedthrough and Kelvin terminals.
  Parameters, source hashes and qualification state survive serialization and
  undo. These records are generic and unqualified; there are zero qualified
  manufacturer models in this catalog.
- The expanded icon system has 56 bounded glyph families. Quick insert supports
  distinct-family browsing, collections, keyboard paging and full-library access.
  Repeated library queries use a bounded index/cache while preserving ranking
  and live signal completion.
- The floating library retains a readable inspector after narrowing to
  1000 × 720. Model descriptions open at their beginning. Closing an active
  quick-insert palette with its parent no longer invokes destruction twice.

See [editing contracts](../standalone/spikes_project/studio/docs/SCHEMATIC_EDITING.md),
[model scope](../standalone/spikes_project/studio/docs/LUMPED_PHYSICS_LIBRARY.md)
and [competitive targets](SPIKES_STUDIO_ADVANCEMENT.md).

## Executed verification

| Check | Result |
| --- | --- |
| Complete Studio suite with native DLL, wx and clipboard access | 522 run; 521 passed; one symlink test skipped because the host denies symlink creation |
| Focused suite after final painting, resizing and palette-close changes | 31 passed |
| Source application smoke | 41 checks passed |
| Frozen application smoke | 41 checks passed |
| Installed application smoke | 41 checks passed |
| Installed payload comparison | All 1,682 files matched; no forbidden Qt files |
| Architecture and button/control gates | Passed after final source changes |
| TypeScript compilation and parser tests | Passed |
| Rust host tests with writable temporary directory | 70 passed; one ignored |
| Root Python failed-module recheck with explicit verified native DLL | All 91 checks across seven modules passed |

The broad root Python run used Python 3.12 and ran 4,154 tests, with four
failures, 47 errors and 77 skips. It lacked the explicit native DLL selection in
that shell and encountered concurrent solver-block changes. The seven failing
modules were subsequently rerun with the verified DLL and passed all 91 checks.
The broad run is retained as a failed run; it is not reported as a clean full
root-suite pass. Earlier default-runtime/dependency and sandbox-denied clipboard
runs are also retained in the evidence directory.

The accepted Studio run used the actual native engine, ngspice and installed
KiCad CLI. All five new library adapters executed native operating-point smoke
checks. Native and frozen coverage includes clipboard ownership across window
closure, preview rotation/repetition/cancellation, undo, model serialization,
BSIM gate-charge transients and a spawned RC transient worker. Independent
read-only review checked clipboard handle ownership and bounded memory reads.

The discovery benchmark (unbundled local record: `../artifacts/studio-workflow-20261018/discovery-benchmark-final.json`)
compared result identity and order. Median repeated `r` search changed from
36.58 ms to 2.14 ms; `resistor` changed from 62.99 ms to 1.87 ms. Index
construction took 47.94 ms in that run. These are local search/model timings,
including hot cached queries, excluding rendering and solver execution.

Actual native source captures were inspected at wide and 1000 × 720 sizes:
schematic (unbundled local record: `../artifacts/studio-workflow-20261018/duplicate-wide.png`),
wide library (unbundled local record: `../artifacts/studio-workflow-20261018/library-wide.png`),
narrow library (unbundled local record: `../artifacts/studio-workflow-20261018/library-narrow.png`) and
palette (unbundled local record: `../artifacts/studio-workflow-20261018/palette.png`).
All ten retained visual/transaction checks passed. Installed-app startup and
library opening were additionally observed through the native UI.

## Artifact and installation

Installed directory: `C:\Users\yawar\AppData\Local\Programs\SPIKES Studio`.
Installer exit status: 0. Existing installation payloads were backed up before
replacement; project and preference storage outside the install directory was
preserved. The updated application is left open on the component library.

Final installer:
SPIKES Studio Windows setup (unbundled local record: `../artifacts/studio-packages/20261018/windows-workflow-library-preview-r3/SPIKES-Studio-0.3.0-beta.6-windows-x64-setup.exe`)
— 111,503,512 bytes.

SHA-256: `2debf66e2f4cfa3e195865d30b3bfc4aaf4cd045a7f4766448c9ade1d6df5e8c`.

Package manifest (unbundled local record: `../artifacts/studio-packages/20261018/windows-workflow-library-preview-r3/package-manifest.json`),
source manifest (unbundled local record: `../artifacts/studio-packages/20261018/windows-workflow-library-preview-r3/source-manifest.json`),
checksums (unbundled local record: `../artifacts/studio-packages/20261018/windows-workflow-library-preview-r3/SHA256SUMS`)
and validation receipt (unbundled local record: `../artifacts/studio-workflow-20261018/workflow-validation.json`)
retain the exact dependency, source, native-engine and installation evidence.

The verified desktop snapshot has SHA-256
`99007dc5e87b1416363646482abdda95801eb1a52589e3fa14cf4069e5096e18`.
Unrelated controller-board work arrived afterward and remains in the checkout;
it was not folded into this verified package. The Studio Python-module comparison
against the most recent previously installed snapshot showed only the intended
three UI file changes and the shared symbol-renderer addition.

## Limits

No new numerical kernel or governing equations were introduced. The native DLL
remains SHA-256
`6b9014073366d7f43b003aa93a6ee740c3f750fbc978074b83c784320122ca5d`.
Hierarchical children, explicit junction branches and dependent-source fragments
remain outside selected-fragment duplication. General schematic text-collision
avoidance remains unfinished; rotated node/reference labels can still crowd.

The small common comparison subset completed nine native and nine ngspice cases.
LTspice completed eight; its first DC case timed out while its library setup
dialog was active. Missing or timed-out comparisons are not wins. No overall
superiority over ngspice, LTspice, Qucs/Qucs-S, QSPICE or SIMPLIS is established.
