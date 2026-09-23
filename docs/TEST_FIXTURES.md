# SPIKE Test Fixtures

The e-brake driver board is a useful real-world KiCad regression fixture. It contains routed copper, internal layers, vias, zones, stackup data, components, manufacturing outputs, STEP models, and schematics.

Board under test:

```text
C:\Users\example\Documents\Projects-kicad\Exercise-machine-ebrake-driver - Copy\Exercise-machine-ebrake-driver\ebrake1_rel1\ebrake1.kicad_pcb
```

Run the parser and normalized-design regression with:

```powershell
$env:SPIKE_FIXTURE_BOARD = 'C:\Users\example\Documents\Projects-kicad\Exercise-machine-ebrake-driver - Copy\Exercise-machine-ebrake-driver\ebrake1_rel1\ebrake1.kicad_pcb'
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
