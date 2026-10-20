# Arduino routed copper preparation

`scripts/prepare_arduino_assembly_em.py` retains source repair receipts, native
KiCad refill/DRC evidence, neutral copper polygons and explicitly assigned
material-volume jobs for the two boards in the October enclosed Arduino case.
This preparation is separate from an executed assembly EM result. It never
substitutes a mechanical board box for routed copper.

Run the native OCC option with the supported installed CPython 3.11 runtime:

```powershell
& "$env:LOCALAPPDATA/Programs/Python/Python311/python.exe" scripts/prepare_arduino_assembly_em.py --output "$env:TEMP/spike-new-arduino-em" --mesh
```

Without `--mesh`, Python 3.12 can prepare the neutral jobs. KiCad 10.0.6 Python
is launched separately for native source geometry. Existing output directories
are refused, original sources are hash-checked after extraction, and each native
OCC process is limited to 180 seconds, 2 GiB and 100,000 tetrahedra. A rejected
job retains its source geometry and diagnostic log. The existing OCC runtime
pin is a local development dependency, not a bundled or qualified runtime.

The full Arduino geometry uses the original planar fallback, requiring Shapely
2.1's constrained Delaunay triangulation:

```powershell
.venv/Scripts/python.exe scripts/prepare_arduino_assembly_em.py --output "$env:TEMP/spike-new-arduino-em" --planar-mesh
.venv/Scripts/python.exe scripts/run_arduino_routed_em.py --prepared "$env:TEMP/spike-new-arduino-em" --output "$env:TEMP/spike-new-arduino-study" --run
```

The second command writes an executable request and an importable study before
solver admission. A rejected run retains the request; a successful run attaches
the actual result to `study.json`. The output directory must be new.

## Source repairs and evidence

The retained original sources are under
`build/curated-multiboard-20261005/arduino`. Source archives and their Arduino
CC-BY-SA-4.0 notices remain authoritative. Generated board derivatives and
polygon data retain those source rights; the scripts are original Apache-2.0
SPIKE code. No external implementation, sample mesh or example code was copied.

The UNO conversion contains duplicated Edge.Cuts centerlines with different
drawing widths. On a separate derivative, the adapter removes the exact duplicate
line/arc centerlines; the arc midpoint and endpoints must match. Stroke width
does not change a board contour. Native outline recovery then succeeds without
inferred rectangular bounds.

The shield conversion contains 25 lines on `UNDEFINED`. Each is checked against
the exact endpoints of original Eagle layer 41/42 restrict wires. They are
retained as documentary lines, while closed source restrict regions and finite
width restrict strokes become explicit front/back copper-pour rule areas.
The interpretation and generated areas are retained in `shield-repair.json`.
Native refill and DRC run on the repaired copy. Source rules and manufacturing
Gerbers are not thereby qualified; the converted board does not retain a full
Eagle net-class project. DRC findings remain part of the evidence.

Native `Unfracture` restores filled-zone holes before neutral polygon output.
Tracks, pad shapes (including native custom geometry), filled zones, graphics,
via lands and drill slots are retained. NPTH mechanical pads produce drill voids,
not copper. Curves use the recorded 0.01 mm chord-error setting. This is a
piecewise planar study approximation, not an exact curved CAD claim.

## Geometry contract

`assembly_em_board_geometry.prepare_routed_board_volume(snapshot, stack)` takes
`spike/routed-board-polygons/v1`, in board-local millimetres, and explicit physical
layer elevations, material identities and plated-hole wall thickness. It returns
a bounded `spike/gmsh-occ-mesh/v2` job and source/stack digests. It does not apply
assembly placements; the retained occurrence handoff applies each transform once.

Complete same-layer/same-net copper is unioned without ROI cropping or contour
simplification. Source group membership is retained separately. Polygons with
more than 128 holes are partitioned along a coordinate midplane to meet the
existing OCC solid gate; their complete area and holes remain represented.
Known distinct-net conductor contact is rejected. Unassigned copper stays
physical copper, and contacts with it are counted without inferring net labels.

Layer background has priority 0, copper/barrel envelopes priority 10 and drill
voids priority 20. OCC fragments these overlapping construction solids into
nonoverlapping material volumes and verifies source-volume conservation. A
barrel is the explicit drill contour offset by the supplied wall thickness;
the drill void removes its interior. Pad diameter never supplies plating
thickness. Emitting an already-cut ring plus a coincident drill caused a native
OCC access violation; the priority construction avoids that redundant boundary.

The full shield still crashes native OCC fragmentation; the full UNO exposes
Boolean sliver edges around 1e-14 mm. Both diagnostics are retained. The fallback
`assembly_em_planar_mesher` resolves material priorities independently for every
source Z interval, constrains triangulation to each exact retained polygon and
its holes, then extrudes each triangle into three positive tetrahedra. It checks
planar coverage, region/material volumes and mesh incidence independently.
Its 1 nm XY precision grid is explicit; polygon/hole topology changes and excess
Hausdorff displacement fail. No board region is cropped.

Each homogeneous material region is closed and internally conforming. Different
regions may have different interface triangulations. This path represents
polyhedra for Cartesian EM and is **not a globally conforming thermal/FEM mesh**.
The named `routed_pcb_em_v1` handoff profile admits at most 600,000 tetrahedra,
200,000 vertices and 128 MiB finite JSON. Default thermal/SI limits remain
100,000 cells/vertices and 8 MiB. Compact occurrence-scoped IDs retain explicit
local/global maps and source digests. An original bounded three-dimensional
AABB hierarchy prunes cross-occurrence candidates before the unchanged tetra
separating-axis intersection check; enclosing cavities do not consume an
x-only comparison budget.

For this EM profile only, rigid-placement checks admit source-grid edges when
their absolute coordinate error fits a double-precision forward bound and the
measured normalized Jacobian perturbation is at most 1 ppm. Determinant and
inverse perturbation bounds include computed inverse residuals. The certificate
records condition, relative volume/inverse errors and bounded-cell count.
Unrepresentable geometry is rejected; ordinary thermal checks are unchanged.

Missing fills, malformed contours, missing stack spans, out-of-board copper,
unrepresented castellations, cross-net contacts and resource excess fail
preparation. A native process success still passes the existing independent
tetrahedral volume/interface admission before its mesh can be retained.

## Study parameters and remaining qualification

The shield's original Eagle design declares 35 micrometre copper and 1.5 mm
dielectric in a two-copper-layer arrangement. These are source design values,
not measured manufacturing parameters. UNO's converted source declares 1.656 mm
total thickness. UNO 35 micrometre copper and both boards' 25 micrometre plating
are explicitly specified study assumptions. No manufacturer dielectric constant,
loss tangent, soldermask or connector dimensions are inferred from these values.
The shield dielectric core spans 0.035 to 1.535 mm; the UNO study core spans
0.035 to 1.621 mm. Noncopper portions of the two surface intervals are air.
FR4 is specified as lossless epsilon_r=4.2; copper is 5.8e7 S/m and the retained
aluminium enclosure is 3.5e7 S/m. These constitutive values are study assumptions.

Assembly mappings and native pad centers agree for UNO JANALOG pins 5/6 and
shield POWER0 pins 5/6: +5V and GND. Their world XY centers are respectively
(152.3111, 129.1336) and (154.8511, 129.1336) mm after the shield's retained
(114.2111, 131.6736, 11) mm translation. These facts identify candidate terminals;
they do not supply manufacturer connector geometry. The runnable study declares
1.2 mm square copper contact columns from UNO Z=1.656 mm to shield Z=11 mm for
these two pins and the mapped JDIGITAL/JLOW0 pin 6 at (165.0111,80.8736) mm.
The columns meet the retained annular pad copper. A 50 ohm, X-directed line
lumped port spans the +5V/GND inner faces in the intervening air. Source connector
maps remain evidence; the actual solids supply the conductor paths.

An executed assembly case additionally requires admitted board tetrahedra,
conductive enclosure material assignment, correctly joined connector solids,
explicit exterior conductor-face ports and the existing EM resource/mesh gates.
The preparation report must not be labelled as a solved Arduino simulation.
Unmapped header pins, component packages/device electrical models, dielectric
loss, soldermask, contact resistance and manufacturing tolerances are omitted.
Native source DRC findings remain unresolved: the UNO has legacy no-net copper
short/clearance findings; shield conversion rule fidelity is incomplete. A study
execution does not establish source-board manufacturing validity.

## Verification

Original analytical tests cover complete source inclusion, layer/prism volume,
drill-circle area tolerance, explicit plating, unknown-net physical contacts,
130-hole area preservation and malformed/missing input rejection. The small
plated-via fixture was actually meshed by the pinned OCC runtime: 2,627 cells,
593 vertices. Its no-drill discriminator produced 415 cells, 126 vertices.
These verify the translator path; they do not establish RF accuracy or Arduino
assembly execution. Numerical human review remains required before release.

The complete planar board meshes retain 313,092 UNO tetrahedra/96,802 vertices
and 153,252 shield tetrahedra/46,086 vertices. Final core/surface preparation
took 28.9 and 14.6 seconds locally. Together they expose 288,904 mesh boundary
triangles; the complete enclosure/header request is 79,571,204 bytes. These are
measured geometry preparation results, not an FDTD convergence claim.

The complete admitted handoff is 127,925,661 bytes with 466,953 tetrahedra and
143,113 vertices including enclosure/headers (98.0 seconds locally). Its 3D
hierarchy checked 653,959 node pairs and found no positive-AABB intersection
candidates between physical occurrences. The surface compiler retains 597,374
material-interface/exterior triangles in 1,466 closed polyhedra, serialized in
48,173,812 bytes (27.8 seconds). The EM profile's surface cap is 600,000; the
ordinary surface cap remains 300,000.

The first full sampled native run reached 10,672/20,000 steps at approximately
43.5 million cell updates/second before the 180-second wall budget expired;
it produced no admitted result. Its log retains 220 unused-polyhedron warnings:
those source solids exist in the native geometry but receive no material samples
on the coarse grid. The reproducible builder consequently allows 600 seconds
for the same 20,000-step diagnostic. Timeouts and unfinalized HDF5 files are not
presented as completed solutions.

An independent terminal-plane check measures 0.79981 mm2 of correct-net copper
contact on UNO and 0.88567 mm2 on shield for each of the three specified pins,
with zero other-net contact. Shield placement requires a bounded precision
certificate on 501 cells: maximum normalized Jacobian perturbation 9.43e-8 and
relative volume error 3.46e-8. These are numerical representation errors, separate
from the much larger polygonization/material/model approximations.

The runnable builder explicitly selects `cartesian_sampling_v1`: full native
polyhedra, material Z extrema and port planes are preserved, while XY grid lines
sample a declared 1 mm target. Anchoring every disconnected copper island's
XY bounds would demand 218,833,362 cells. The declared sampled grid instead has
112 by 97 by 66 cells (717,024), with a 183,558,144-byte memory estimate and
1.16515e-13-second vacuum CFL reference. This is an explicit discretization
approximation: many narrow traces, via holes and copper gaps remain unresolved,
so FDTD rasterization can change effective connectivity and impedance. A run
under this policy cannot be described as Arduino accuracy or convergence
qualification. The strict default grid policy is unchanged.

## Executed diagnostic, 11 October 2026

The unbundled local `arduino-em-20261011/full-study-executed/study.json` record
contains the actual
completed request/result. The fresh saved `compiled.json` digest matches the
native result. OpenEMS completed 20,000 iterations in 339.02 seconds, with
717,024 Cartesian interval cells and finite 4,872-point E and H previews.
The final reported energy was -57.29 dB; the native log explicitly says the
-60 dB end criterion was not reached. Execution completed; decay convergence
and spatial accuracy did not pass. `run/result.json` is the unchanged native
result; the study adds observed native log diagnostics and its SHA-256.

`scripts/audit_arduino_em_sampling.py` measures closed-surface signed volumes
against independent source-tetrahedron determinants. Maximum relative
disagreement is 5.53e-13. Its `sampling-volume-audit.json` reports:

| Occurrence | Unused conductive regions | Unused copper volume | Fraction of occurrence copper |
| --- | ---: | ---: | ---: |
| UNO | 131 | 6.426879 mm3 | 3.0127% |
| Relay shield | 47 | 4.633886 mm3 | 3.5862% |
| Enclosure and three specified pins | 0 | 0 | 0% |

All 178 unused conductive regions exceed 0.001 mm3; these are meaningful
geometry, not numerical slivers. The smallest unused bounding dimensions across
axes are 0.344236, 0.2 and 0.035 mm. Loss of even a small copper volume can break
interlayer continuity. The audit retains all unused dimensions/volumes and the
20 largest regions with positive-area source-construction candidates. No source
geometry was removed to obtain this run.

A prediction for a 0.75 mm target gives 144 by 124 by 80 intervals, or 1,428,480
cells. This exceeds the unchanged one-million-cell limit and was not executed.
Even this refinement alone would not prove that every meaningful conductor is
resolved. The remaining accuracy work includes conductor sampling/connectivity,
spatial and time convergence, source DRC issues and physical model assumptions.
