# Public KiCad and ODB++ import validation

Measured 2026-09-05. This corpus exposes failures; it does not qualify complete CAD or solver parity.

22 inputs: 20 produced normalized designs; 15 completed copper-geometry-checked project save/reopen. All 720 downloaded source files were hash-checked; changed files: 0.

| Input | Format | Components | Pads | Vias | Import | Save/reopen |
|---|---|---:|---:|---:|---|---|
| constraints | kicad_pcb | 0 | 0 | 0 | with warnings | passed |
| ecc83 | kicad_pcb | 15 | 33 | 0 | completed | passed |
| pic-programmer | kicad_pcb | 63 | 247 | 6 | completed | passed |
| interf-u | kicad_pcb | 25 | 379 | 84 | completed | passed |
| microwave | kicad_pcb | 1 | 8 | 0 | with warnings | passed |
| stickhub | kicad_pcb | 94 | 278 | 87 | completed | passed |
| cm5-minima | kicad_pcb | 112 | 633 | 444 | with warnings | passed |
| video | kicad_pcb | 189 | 2118 | 808 | completed | passed |
| tiny-tapeout | kicad_pcb | 173 | 757 | 405 | completed | passed |
| vme-wren | kicad_pcb | 1508 | 6883 | 4374 | with warnings | FAILED |
| jetson-thor | kicad_pcb | 1124 | 4862 | 3235 | with warnings | FAILED |
| olimex-a64 | kicad_pcb | 459 | 2913 | 1130 | with warnings | passed |
| beaglebone-black | odb++ | 413 | 7611 | 0 | with errors | FAILED |
| merit-badge | odb++ | — | — | — | failed | FAILED |
| odb-simple | odb++ | 2 | 0 | 0 | with errors | passed |
| odb-kitchen-sink | odb++ | 3 | 8 | 3 | with errors | passed |
| odb-rigidflex | odb++ | — | — | — | failed | FAILED |
| ecc83-odb | odb++ | 15 | 66 | 0 | with errors | passed |
| stickhub-odb | odb++ | 90 | 0 | 87 | with errors | passed |
| cm5-minima-odb | odb++ | 84 | 572 | 444 | with errors | passed |
| video-odb | odb++ | 189 | 3791 | 808 | with errors | FAILED |
| olimex-a64-odb | odb++ | 452 | 2710 | 1130 | with errors | FAILED |

## What the comparisons establish

The 22 inputs comprise 12 KiCad boards (including an empty development-format control), two published hardware ODB exports, two synthetic ODB fixtures, one supplemental rigid-flex sample with unresolved hardware licensing, and five ODB exports generated from the KiCad boards. Complexity ranges from the 15-component ECC83 board to 1,508-component, 12-copper-layer VME-WREN. All eight completed ODB imports report errors; save/reopen only establishes persistence of the geometry that was imported. It does not recover unsupported source geometry.

SPIKE's source-worker import route, typed conversion, real desktop parsers, and `.spike` save/reopen were exercised. Copper geometry rows were compared across persistence. KiCad 10.0.5's native reader supplied an independent inventory; it rejected the development-format Constraints file and timed out on Tiny Tapeout and OLIMEX A64. Those reference failures are not SPIKE passes or failures.

KiCad circular arcs currently become eight line segments in the backend; track-count comparisons account for that representation explicitly. Matching counts do not prove curve, copper-area, thermal-relief or 3D placement equivalence. Footprint/zone representations also differ: filled islands and copper graphics are not one-to-one with native zone objects.

All eight completed ODB imports retain the source CMP record count, including the exporter-excluded footprint differences in paired boards. Pads and features still have observed omissions. Diagnostic entry counts in the JSON count retained report entries, which can repeat across categories and are bounded; they are not total affected source-feature counts. Original per-input reports and worker logs remain under `build/public-board-corpus/final`.

## Fixes exercised

- Modern KiCad physical layer ordering now preserves through-via spans.
- Silkscreen footprint polygons stay drawings; repeated source pad UUIDs and identical anonymous records retain separate occurrences.
- Uppercase ODB matrix entity names map to lowercase directories without changing reference-designator case.
- Legacy `U` units, empty attribute strings, repeated first contour vertices, full-circle contour splitting and profile feature-count headers are handled.
- Drill metadata satisfies the canonical contract; unresolved spans/plating remain explicit. Unsupported `.Z` files now fail with a useful cause. Repeated missing-net diagnostics are counted without flooding the report.

## Remaining failures and limitations

- VME-WREN, Jetson Thor, BeagleBone Black and the larger generated ODB exports hit existing project JSON member limits. Rigid-flex ODB hits the extension result-size limit. These are actual usability blockers, not passes.
- The CERN-licensed Merit Badge Kit's DipTrace ODB export uses Unix compress `.Z`, which is not yet supported.
- Rounded/custom ODB symbols, rounded source arc radii, unresolved drills and plating, connectivity gaps and physical stackup extraction prevent full electrical readiness. Source component counts distinguish exporter exclusions from importer omissions.
- KiCad Microwave and Jetson footprint counts, and several boards' model-reference counts, differ from the native reader. Multiple/no-pad footprints and multiple model assignments need further work.
- Model resolution records discovered paths, not verified 3D geometry or transforms. Neither viewport pixels, routing/plane area equivalence, nor solver physics were qualified.

## Provenance and rerun

The manifest includes immutable repository commits, file hashes, project/license documents and URLs. Data stays under `build/public-board-corpus/sources`; it is not included in the installer. Repository software licenses do not automatically establish the license of every hardware example. The rigid-flex sample's original hardware license is unresolved and it is treated only as a public local-test sample. Generated ODB files record the KiCad exporter and parent board; they are not independent vendor exports.

Run from the repository root with the project Python and frontend dependencies installed. The native oracle and exporter use KiCad 10.0.5 at the paths below. Allow several minutes for each complex input. Generated archive hashes may differ on re-export; the exporter records new hashes.

```powershell
New-Item -ItemType Directory -Force build/public-board-corpus | Out-Null
Copy-Item benchmarks/public-board-corpus/manifest.json build/public-board-corpus/manifest.json
.venv/Scripts/python.exe scripts/fetch_public_board_corpus.py --manifest build/public-board-corpus/manifest.json
.venv/Scripts/python.exe scripts/export_public_board_odb.py
.venv/Scripts/python.exe scripts/validate_public_board_corpus.py --label final
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/public_board_native_oracle.py build/public-board-corpus/manifest.json build/public-board-corpus/native-oracle.json
node app/scripts/validate-public-board-corpus.mjs
.venv/Scripts/python.exe scripts/summarize_public_board_corpus.py
```

[Detailed machine-readable results](summary.json) · [Pinned download manifest](manifest.json)
