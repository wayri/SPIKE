# SPIKE Test Fixtures

## Public Marble prerequisite for the full Python suite

`test_board_terminal_contacts` checks native geometry from the public
BerkeleyLab/Marble v1.4.4 source. Prepare its local cache before running the
full Python suite. The test deliberately fails when the required source is
missing or its SHA-256 differs; an absent fixture is not a passing audit.

The pinned upstream commit is
`a426777d92c0f22a546d4740b419a3937e0c1f90`. The upstream README credits
The Regents of the University of California through Lawrence Berkeley National
Laboratory, records CERN OHL v1.2, and includes the U.S. Government rights
notice. Keep that README alongside the unchanged board. This preparation
downloads inert data into ignored `build/`; it neither executes upstream code
nor adds the upstream board to SPIKE's release archive. Source and license
context are also recorded in [Help maintenance](HELP_MAINTENANCE.md) and
[third-party notices](../THIRD_PARTY_NOTICES.md).

Run the following Python from the repository root (save it to a temporary
script or paste it into a Python interpreter). Existing cached files are
verified before reuse. A hash mismatch stops preparation without replacing
the existing file.

```python
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

commit = "a426777d92c0f22a546d4740b419a3937e0c1f90"
base = f"https://raw.githubusercontent.com/BerkeleyLab/Marble/{commit}/"
cache = Path("build/marble-qualification/sources/Marble-v1.4.4")
files = {
    "README.md": "8cfd50651c0562e26380286b3c7f931c4f9d79af115675b224d6660a7b558533",
    "design/Marble.kicad_pcb": "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512",
}
for name, expected in files.items():
    target = cache / name
    if target.exists():
        payload = target.read_bytes()
    else:
        request = Request(base + name, headers={"User-Agent": "SPIKE-fixture-validation"})
        with urlopen(request, timeout=60) as response:
            payload = response.read(64 * 1024 * 1024 + 1)
    if len(payload) > 64 * 1024 * 1024:
        raise ValueError(f"Fixture exceeds size limit: {name}")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"Pinned fixture digest differs: {name}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)
    print(f"Verified {target}")
```

Then run `python -m unittest tests.python.test_board_terminal_contacts -v`.
The check establishes the stated source geometry facts only; it does not
qualify full-board PI/SI physics or a hardware result.

The annular-contact gate test also runs its existing acceptance generator in
a fresh `.local/test-temp/annular-gate-*` directory. This executes the numerical
suite and solves, validates their new source-bound receipt, and checks rejected
completion and corrupted-evidence cases. Native source bindings contain
absolute file paths, so a new checkout needs its own execution. Historical
receipts retain their original paths and hashes. Temporary test outputs are
removed when the test finishes; the generator's preceding finite-contact and
land-transition receipt checks remain required.

## E-brake fixture

`test_parity_backlog` runs the unchanged `check_ebrake_owned_dc.py` and
`parity_owned_pad_gate.py` generators once per test module, using the existing
`app/public/demo/ebrake1.kicad_pcb` as a local input. Install the normal Python
worker dependencies first. The replay executes the real CLI solve, all four
mesh levels (2, 1, 0.5 and 0.25 mm), and the owned-pad numerical tests. Its
subprocess timeouts are 300 seconds for the board study and 180 seconds for
acceptance. The existing diagnostic's nonconverged result remains
nonconverged; acceptance does not promote it to production qualification.

The test creates fresh evidence below `.local/test-temp/owned-pad-backlog-*`,
validates it with the unchanged gate, and selects that receipt for PI01-S01
in the test's in-memory backlog only. All other stage selections, the static
backlog, historical receipt, source hashes and qualification flags remain
unchanged. Temporary outputs are removed after the module completes.
Corruption checks reject altered source bindings, qualification, test coverage,
skips and board artifacts.

This local replay does not bundle the historical board-derived request/results
under `build/si02-s13-development-20261020/ebrake-owned-replay`. The archived
PI01-S01 receipt still requires those exact original local artifacts if it is
validated directly; passing the fresh replay does not claim that the archive
ships them. EBrake redistribution provenance remains unconfirmed as recorded
in [the multiboard acceptance record](validation/MULTIBOARD_ACCEPTANCE_20261001.md).
No license or redistribution permission for the board or derived geometry is
inferred from its existing presence in this checkout.

The e-brake driver board is a useful real-world KiCad regression fixture. It contains routed copper, internal layers, vias, zones, stackup data, components, manufacturing outputs, STEP models, and schematics.

Board under test:

```text
<path-to-ebrake1.kicad_pcb>
```

Run the parser and normalized-design regression with:

```powershell
$env:SPIKE_FIXTURE_BOARD = '<path-to-ebrake1.kicad_pcb>'
python -m unittest tests.python.test_kicad_fixture -v
```

Current extraction baseline:

- 26 declared layers, including 4 copper signal layers.
- 102 canonical nets. Track, via, pad, and zone names are resolved from the
  KiCad numeric net-code table.
- 787 tracks.
- 103 vias.
- 489 pads.
- 165 zones.
- 135 component groups derived from pad ownership.
- 115 component 3D-model references extracted from the KiCad footprint model nodes.

The fixture contains STEP assets and KiCad model references. SPIKE records both the source reference and local resolution status; browser rendering will use converted glTF assets or explicit proxy geometry rather than pretending that an unresolved STEP path is renderable.
- 13 stackup entries with FR-4 dielectric properties.
- Board outline approximately 143.9 mm by 83.5 mm.

The fixture now also runs:

- A routed-copper DC regression on `3Vin`.
- A native hybrid PEEC RL regression on `/AOUT1`, containing 8 traces,
  2 zone polygons, 1 via, and 4 pads.

The current `/AOUT1` result is stored in
`docs/validation/ebrake-aout1-hybrid-peec.json`. It remains `Approximate`,
because its ports are inferred and the current PEEC mode does not yet include
capacitance, dielectric loss, proximity effect, or surface roughness.

## IPC-2581 qualification fixture

The external qualification fixture is the IPC-2581 Consortium **Rev C
Testcase 10 Full XML** archive, available from
<https://www.ipc2581.com/ipc-2581-revc-test-cases/>. It is not committed to this
repository: redistribution and licensing status have not been established.

- Full XML payload size: 20,982,496 bytes.
- SHA-256: `6c10fea08943ca7261505bd531a8724bc1dffe8f9fec9e53a2f22d52bc83d347`.
- Qualification command: `python scripts/qualify_ipc2581_fixture.py <full-xml>`.
- Parser: `ipc2581-conductor-primitives-v13`.
- Latest report: 44 layers, 37 stackup entries, 514 nets, 56 components, and
  46,483 source records;
  27,147 typed track segments, zero arcs, one exact zone, 1,611 pads, 1,690
  vias, and 1,859 typed manufacturing-drill records. The copper candidate total
  is 39,094 true-copper records after excluding 7,012 non-copper pads, 346
  non-copper polylines, 11 out-of-scope polylines, and 20 out-of-scope polygons;
  seven contours are in scope. The report retains 1,152 exact heterogeneous
  per-layer land-profile records.
- The exact `PWR1/GND` `SOLID_FILL`/`FILL` zone has 202 ordered rings (one outer
  plus 201 cutouts), six line segments, and 402 circular-arc segments.
- The report retains all 39,094/39,094 declared true-copper source records and
  records a true residual of zero. Retained contour contract v2 accepts and
  preserves optional profile `Xform` plus bounded `xOffset`, `yOffset`,
  `rotation`, `mirror`, `faceUp`, and `scale` raw and normalized facts without
  applying or composing them. Its 98 source-only occurrences partition into 32
  declared-layer matches and 66 mismatches. Normative composition and
  TOP-to-BOTTOM semantics remain unproven, so no typed, Arrow, mesh, solver, or
  physics promotion occurs. The one zone and typed pads/vias/drills remain
  1/1,611/1,690/1,859, with 1,152 profiles. All
  readiness flags are false, including
  `LAND_PROFILE_MESHING_PENDING` and `ZONE_CURVE_MESHING_PENDING` because
  land-profile and curve-aware zone meshing/ownership are not implemented. The
  zone and land profiles are exact persistence only, without sampling,
  tessellation, frontend exposure, or solver readiness. Manufacturing drills are
  retained solely for provenance and package round-trip: they do not create
  copper, barrels, or mesh voids.

The unchanged fixture digest binds the official qualification of this bounded
IPC-2581 conductor-primitives v13 slice. The report at
`build/ipc2581-testcase10-revc-v13-qualification.json` is
`passed_with_declared_gaps`; the focused IPC/package slice passes 74 tests, the
pinned-venv suite passes 787 with one skip, and the architecture check passes.
It must
not be presented as complete IPC-2581 import support or as a solver-qualified
design without resolving the documented unsupported and unresolved content.
