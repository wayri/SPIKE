# Import assurance parity fixture

SPDX-License-Identifier: Apache-2.0

The coupon and expectations are original SPIKE fixtures under Apache-2.0.
They were authored from explicit dimensions, not copied from a vendor board
or generated from importer output. The manifest hash identifies the exact
source bytes. Git preserves those bytes through a `-text` attribute for this
coupon. The `repository:` source URL identifies the checked-in fixture.

The board has two 10 mm tracks: F.Cu from (2.5, -3) to (12.5, -3), width
0.25 mm; B.Cu from (12.5, -3) to (12.5, 7), width 0.5 mm. One 0.8 mm via with
a 0.4 mm drill joins them on SIGNAL. Copper layers are each 0.035 mm thick
around a 1.53 mm core; the back copper starts at z = 1.565 mm. Canonical
layers include the core and Edge.Cuts, giving four layer records and one net.

The manifest checks 24 independently specified entity values/references.
Numeric geometry uses absolute tolerance 1e-9 mm. Reference assertions select
the independently named source layer/net and compare its canonical ID with the
track/via binding. They do not use UUIDs copied from an importer run as an oracle.

Run from the repository root, using a fresh evidence output directory:

```powershell
.venv/Scripts/python.exe scripts/benchmark_board_corpus.py --manifest benchmarks/parity-import/manifest.json --corpus benchmarks/parity-import --output build/parity-import-my-run
.venv/Scripts/python.exe scripts/check_parity_backlog.py
```

The first WF01 run is retained locally at `build/parity-import-wf01/summary.json`.
It passed the real CLI import, source-digest, frame, identity, count and all
24 entity assertions. This is bounded import assurance, not arbitrary KiCad
support, native KiCad round-trip verification, physical connectivity validation,
viewport fidelity or solver accuracy. Other formats and curved/cutout/package
geometry still need separate fixtures and acceptance evidence.

Verification on 12 October 2026: 14 focused corpus/backlog tests and 73 broader
import regression tests passed in the project's Python 3.12 environment. The
architecture guard and backlog integrity check passed. The broader test log
is retained locally at `build/parity-import-regression.log`. GUI, other solver
families and clean-machine release checks were not part of this import increment.

Warnings, inferred data and solver-readiness metadata remain in the report.
A passed import benchmark does not promote those metadata flags to physical
qualification. Error diagnostics, unsupported objects, geometry errors,
incomplete status, wrong units, duplicate canonical IDs and failed expectations
prevent a pass. Assertions use a scalar, a flat vector of up to 16 entries,
or an explicit entity reference; arbitrary executable expressions are unsupported.

## Completed and remaining stages

| Stage | Status | Scope |
| --- | --- | --- |
| WF01-S01 | Done | Original straight-track/via coupon; 24 assertions. |
| WF01-S02 | Done | `geometry.kicad_pcb` rotated pad/native footprint origin and constant material values; 12 assertions. |
| WF01-S03 | Done | Exact nondegenerate copper arcs, strict legacy projection and straight-outline cutout transport; 18 import assertions and recomputed consumer gates. |
| WF01-S04 | In progress | Further geometry classes, formats and package models. |
| WF01-S04A | Done | Three KiCad model occurrences, 30 CLI assertions and native pcbnew agreement on paths and placement triples. |
| WF01-S04B | Done | Actual native ODB archive: 14 assertions, source/member/geometry gates and 56 pose/shape cases. |
| WF01-S04C | Planned | Package-model placement, solids/materials and broader format coverage. |

`geometry-manifest.json` defines S02. KiCad 10.0.6 opened and rendered the
fixture; its DRC coordinates independently confirm pad (21, 8) mm and native
footprint origin (20, 10) mm. The native render shows the board cutout, arc and
rotated pad. Native DRC retained two warnings (dangling arc and absent external
Parity footprint library), one unconnected pad/arc pair, and five ignored checks.
The fixture is not a manufacturing-ready or physically connected board.

`arc-fidelity-manifest.json` now passes the original requirement of one exact
canonical arc: three source points, width, net and layer are retained, with zero
duplicated canonical chord tracks. The legacy solver view restores its eight
original chords in order and retains `KICAD_ARC_LINEARIZED`. Anonymous duplicate
occurrences have stable separate source identities. Initial and restored
surrogates are checked against the exact source, including JSON that recomputes
its own digest. Edited/omitted arcs fail numerical projection instead of silently
dropping copper. Display/persistence can explicitly request a metadata-only view;
that permission does not admit numerical geometry.

The same straight outer/cutout rings reach MCAD and retained-volume preparation.
The latter preserves 647 mm² area, one hole per physical layer and 1035.2 mm³
stack volume. The exact Arc reaches Arrow and an explicitly isolated native
Arc-only handoff. The fixture's rotated pad remains unsupported by that native
layout adapter; no full-board native execution or field accuracy is claimed.
The reduced layered thermal raster still has a rectangular domain and does not
thereby acquire cutout-aware thermal physics. Curved board outlines, unresolved
tiny/degenerate arcs and general package geometry remain follow-on work.
The canonical component position retains its historical pad-centroid meaning;
S02 checks the separately retained native footprint origin, not a new placement
contract or renderer accuracy.

Reproducible evidence is checked in under `docs/validation/parity/`. Done-stage
receipts bind exact fixture manifests, runner/import source bytes and actual
CLI summaries. Git uses LF for the hash-bound manifests and source files.
Historical local artifacts remain in `build/parity-import-stage01-final`,
`build/parity-import-stage02-final` and `build/parity-import-arc-failure-final`.
Current receipts use the later `*-portable` replays after enforcing LF bytes
for all hash-bound sources/manifests. Stage verification passed 22 focused tests,
84 import regressions and 10 parser regressions, plus the architecture and
stage-evidence guards. The broader logs are
`build/parity-import-stage02-verified-regression.log` and
`build/parity-parser-stage02-regression.log`.
The original failed gate is retained at
`docs/validation/parity/WF01-S03-failed-arc.json`; current S03 evidence is
`docs/validation/parity/WF01-S03.json` with the actual canonical import snapshot.
Its recomputed gate rejects forged pass flags or changed area/volume. The latest
local replay is `build/parity-import-stage03`; both commands below should pass:

```powershell
.venv/Scripts/python.exe scripts/benchmark_board_corpus.py --manifest benchmarks/parity-import/geometry-manifest.json --corpus benchmarks/parity-import --output build/parity-geometry-new
.venv/Scripts/python.exe scripts/benchmark_board_corpus.py --manifest benchmarks/parity-import/arc-fidelity-manifest.json --corpus benchmarks/parity-import --output build/parity-arc-new
```

S03 checks: 48 focused geometry tests passed (one optional runtime skipped),
20 backlog/corpus tests passed, and architecture checks passed. The full host
suite completed 3654 tests with one context failure and 68 skips. The failure
was an empty temporary directory inside the parent Git repository; its unchanged
five-test worktree module passed with the normal host temporary directory.
Logs: `build/parity-stage03-focused-final.log` is an earlier 45-test checkpoint;
the subsequent 48-test focused run passed after adding forged-JSON/alias/thermal
guard tests. `build/parity-stage03-full-python-unsandboxed.log` retains the full
run, including its failure. This record does not claim a zero-failure full-suite run.

S04A adds the original Apache-2.0 `models.kicad_pcb` coupon and
`models-manifest.json`. Its three declarations include a repeated model path;
30 assertions cover model paths, placement triples, component bindings and the
earlier pad/material facts. The model files deliberately do not exist. Native
board rendering and DRC do not validate package solids. Native `pcbnew` reads
independently confirm the model occurrence count, paths and declared vectors.
Both the import and native facts are checked in beside `WF01-S04A.json`, whose
gate rejects changed source digests, occurrence coverage, vectors, paths,
component links or a claimed composed transform. Six new tests cover JSON and
legacy round-trip, repeated occurrences, invalid vectors, unknown fields and
native-evidence rejection. All 39 focused import/tracker tests pass.

To replay the bounded gate, use a fresh CLI output directory, then the Python
interpreter distributed with KiCad:

```powershell
.venv/Scripts/python.exe scripts/benchmark_board_corpus.py --manifest benchmarks/parity-import/models-manifest.json --corpus benchmarks/parity-import --output build/parity-models-new
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/parity_model_gate.py --source benchmarks/parity-import/models.kicad_pcb --import-file build/parity-models-new/000-import.json --output build/parity-models-new/native-facts.json
.venv/Scripts/python.exe scripts/check_parity_backlog.py
```

Source placement remains unapplied with projection forbidden. Further format
coverage, model loading, component-to-board placement composition, solid
geometry and material qualification remain open under S04.

S04A regression evidence: the full host Python suite ran 3706 tests in
1031.175 seconds, with 69 skips and one Python-debug session-start deadline
failure. Its unchanged eight-test module passed on rerun in 22.517 seconds.
The timeout did not reproduce; its root cause remains unestablished. Both logs
are retained at `build/parity-stage04a-full-python.log` and
`build/parity-stage04a-debug-rerun.log`. This is not a zero-failure full-suite
claim. Architecture, backlog and the three changed documentation checks pass.

S04B extends the runner to explicit `format: "odb++"` archive entries with
pinned bytes and the existing bounded package policy. `odb-candidate.zip` is
reproducibly packed from original Apache-2.0 source records in `odb-candidate/`.
It is hand-authored, not a native export. Its 14 assertions cover arc/pad and
component placement facts plus net/layer/component references. Stackup and
models are deliberately absent; the summary retains canonical source warnings
and no solver-readiness flag is true. Canonical source errors fail the runner
even if an import report omits them.

Initial native-export acceptance was incomplete. The actual candidate snapshot,
source-bound runner summary and native startup/writer failures are retained in
`docs/validation/parity/WF01-S04B-progress.json`. Its progress contract cannot
be substituted for a Done-stage receipt. Replay with a fresh output directory:

```powershell
.venv/Scripts/python.exe scripts/benchmark_board_corpus.py --manifest benchmarks/parity-import/odb-candidate-manifest.json --corpus benchmarks/parity-import --output build/parity-odb-new --timeout-s 120
```

On hosts with sandbox temporary-directory restrictions, use the workspace
temporary directory described in the preceding validation records. The runner
does not install, modify or repair native KiCad. Native-export qualification
requires a successful native export followed by independent geometry checks.

The completed S04B receipt is `docs/validation/parity/WF01-S04B.json`. Its actual
native `geometry-native-odb-qualified.zip` export was produced by public native
`PCB_IO_MGR.Save(ODBPP, absolute_path, board, str_utf8_Map())`. All included
member bytes are bound to the native capture. Generated `fonts/standard` is
omitted from this redistributed geometry-only archive. Stackup and model
assignments are missing in the exported job and remain diagnostic. Fourteen
CLI assertions, independent native arc/pad/component/profile/connectivity
comparisons and 56 source pad pose/shape cases pass; solver readiness stays false.

The native comparison corrected the earlier pad-angle oracle and importer:
saved board angles are absolute, not footprint-relative. Neutral numerical
angles have opposite sign to native display angles. Back-side positions and
custom primitives do not acquire another reflection. Native integer-grid
position/bbox tolerances are 1e-6/2e-6 mm; original exact scalar assertions retain
1e-9 tolerance. Circular-anchor union stays unsupported. Historical evidence
is `WF01-S02-native-angle-failure.json`. Older saved geometry requires source
reimport. Reproduce native facts with the installed KiCad Python interpreter
and `scripts/capture_parity_native_geometry.py`, selecting fresh output paths.

Final S04B checks pass: 58 focused tests, 81 downstream geometry/import tests,
three frontend scripts and TypeScript compilation. The full suite ran 3761 tests
with 69 skips, two failures and one error. The Marble isolation expectation was
corrected against retained native KiCad connectivity facts; its eight-test module
passes with no-zone separation controls. Debugger and native Gerber deadline
failures remain unresolved. Original failures and the subsequent correction are
recorded separately in the stage evidence; no clean full-suite claim is made.

## Explicit component solids (WF01-S04C1)

`component-solid.step` is an original 2x3x4 mm cuboid exported through the existing
FreeCAD/Open CASCADE adapter. `component-models-placed.step` is the actual native
export of the three explicit neutral placements. Source, owner, license and
digests are recorded in `component-solid-provenance.json`. No vendor model was
copied. The new gate checks volume 24 mm3 and transformed bounds to 1e-6 mm/mm3,
STEP round trips, model/occurrence ownership and source design integrity.

The three retained source references receive explicitly supplied fixture assets;
this does not establish original URI content, KiCad placement composition or
materials. Canonical source transforms stay empty and readiness remains false.
See [the mechanical handoff workflow](../../docs/MCAD_EXPORT.md),
[C1 evidence](../../docs/validation/parity/WF01-S04C1.json) and
[remaining parent-stage evidence](../../docs/validation/parity/WF01-S04C-progress.json).

S04C1 is marked Done for this explicit handoff: 57 focused tests and all three
actual native solid references pass. The full suite ran 3770 tests with 69 skips,
two debugger deadline failures and one Gerber timeout. C1's tests pass in the
full run; the broader failures remain recorded and unresolved. S04C remains in
progress for native KiCad composition and applicable material evidence.
