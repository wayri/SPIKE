<!-- SPDX-License-Identifier: Apache-2.0 -->
# Result workbench verification — 2026-09-20

## Changes

Live PI/SI spatial result rendering now shares connected-face display values
between 2D and 3D. Smooth fields use geometry rather than Gaussian blur;
contours use continuous heights and isolines. Exact-face and instanced-glyph
cursor hits retain source sample identity, with opaque depth occlusion and
depth-tested cursor annotations. Unsupported topology has bounded fallbacks.

Probe calculations use stable aliases and unit-aware expressions, persist in
project snapshots, and export with their formulas and visible errors. Results
controls, probe tables, and trace graphs have detached presentation windows.
The main workspace owns state; children receive bounded snapshots and send
validated actions. Detached controls now use consistent SPIKE styling.

## Automated evidence

- `npm.cmd run build`: passed TypeScript and production Vite build. Existing
  large-chunk warnings remain; this is not a bundle-size qualification.
- `python scripts/check_architecture.py`: passed.
- `npm.cmd run test:results-workbench`: passed interpolation topology/output
  budgets, affine/exact/degenerate reconstruction, source immutability,
  cursor mapping/occlusion rules, probe units/errors/zero values, stable IDs,
  save/reopen state, native creation lifecycle, and snapshot/source-ID checks.
- `test:parser`, `test:project`, `test:project-snapshot`,
  `test:result-performance`, `test:result-layers`, `test:viewport`,
  `test:trace-plots`, `test:report-runtime`, `test:form-contrast`: passed.
- `.venv/Scripts/python.exe -m unittest discover -s tests/python`: 1,811 tests,
  OK with 9 skips. Log: `artifacts/results-workbench-python-tests.log`.
  The system Python run lacked jsonschema and was not accepted as validation.
- `cargo test --quiet`: 38 passed, 1 ignored.
- `cargo build`: debug desktop build passed.

## Interactive evidence and limits

`app/test-fixtures/results-workbench.html` uses explicitly synthetic values
on 416 connected square faces; it is a presentation fixture, not solver
validation. Browser review confirmed clean 2D fields without blurred edges,
continuous 3D contours with isolines, and a cursor identifying `cell-247`
with its original 1.500000 V value. The geometry alignment diagnostic reported
416 samples with zero outside-board or off-conductor samples.

The same detached content component was reviewed at 1280-pixel and 520-pixel
widths. Controls retain the theme; compact windows scroll the table within
its boundary. Editing a calculated row and committing with Enter recomputes
its value or exposes division-by-zero errors. A browser popup opened and
received the main workspace's `2+3 = 5` calculation, evidenced in the user's
supplied screenshot. That popup was not exposed by the available browser
automation inventory, so a complete live parent/child edit-and-redock test
was not performed.

Native window movement across monitors, OS focus/close behavior, and packaged
installer acceptance remain unverified. Native windows use meaningful SPIKE
titles; browser popup origin/security chrome such as `127.0.0.1` cannot be
hidden by application styling. The main board viewport remains in the main
workspace; detachable trace graphs provide separate result surfaces.

The display tests do not validate numerical solver accuracy or every large
production board/assembly. These changes have not been installed as a release.
