<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Marble finite-volume PEEC mesh audit

Date: 2026-09-24. Status: diagnostic evidence, not production qualification.
The initial audit below changed no numerical implementation; later follow-up
sections record experimental implementation and verification separately.

## Finding

The routed U37.18-to-R195.1 sensitivity is not mesh converged. Its drift cannot
be dismissed as native integration error or repaired by PSD projection. There
are concrete geometry and capacitance discretization defects, plus substantial
mesh-dependent attachment resistance. Their individual contributions to L
have not been separated, so no unique quantitative root cause for L is claimed.
U37.18-to-C383.1 is a different, disconnected terminal case; it is not a
comparison point in this refinement series.

Inputs: `build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb`,
SHA-256 `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
Original AC evidence is in
`build/marble-volume-20260924/marble-ac-routed-1mm.json` and
`marble-ac-routed-0.5mm.json`. Both retain approximate model status and use
the same reported native binary digest. The 1 mm issue wording predates a
wording-only change visible in the 0.5 mm report.

| Quantity | 1 mm | 0.5 mm | Change relative to 1 mm |
| --- | ---: | ---: | ---: |
| Physical bases | 45 | 120 | +166.7% |
| Partial L, nH | 1.342280298 | 1.263706531 | -5.854% |
| Starting R, mOhm | 4.778865685 | 5.251177243 | +9.883% |
| Estimated C, pF | 3.621510024 | 5.199251714 | +43.566% |

Both native matrices pass the implemented energy admission without projection.
Maximum estimated pair errors are 1.5043e-16 H and 9.1121e-17 H. These are
entry integration estimates, not a bound on mesh error or port error. Positive
energy establishes neither correct copper support nor converged topology.

## Independent cheap discriminating checks

Executed with `build/qualification-py311/Scripts/python.exe`, NumPy and Shapely.
Import the board using `_design_from_kicad`; retain only
`Net-(C383-Pad1)` tracks, vias, pads and zones and the original layers/stackup.
For each h below, use `AnalysisSpec(mode="ac", net_names=[net])` with
`target_size_mm=zone_cell_mm=h`, `max_zone_cells=1000`, `max_conductors=2000`,
and `memory_budget_mb=512`. Build `build_hybrid_mesh` and resolve both pad
terminals through `nearest_mesh_node` with their original pad geometry anchors.
Use `_connected_component` from the source terminal and `solve_port` for a
one-ampere DC solve, with no C, L or frequency-dependent skin increment.
The full R matrix starts with each branch's `resistance_ohm` on its diagonal;
replace its physical-branch block with `assemble_overlap_resistance`.

| Diagnostic | 1 mm | 0.5 mm | 0.25 mm |
| --- | ---: | ---: | ---: |
| Physical bases | 45 | 120 | 431 |
| DC port R, mOhm | 4.778865323 | 5.251177223 | 4.324709769 |
| Zone-attachment loss / I^2, mOhm | 0.279059401 | 0.220254340 | 0.081519750 |
| Pad-attachment loss / I^2, mOhm | 0.396052099 | 0.304072910 | 0.190057728 |
| Pad-zone attachment loss / I^2, mOhm | 0.188818892 | 0.590558877 | 0.029054462 |
| DC MNA relative residual | 2.10e-16 | 1.37e-16 | 7.02e-16 |

Thus R drift already exists without any native magnetic integration. Attachment
resistors account for approximately 18.1%, 21.2%, and 7.0% of DC loss. The
0.5-to-0.25 mm R change reverses direction and is about -17.6%. Changes in
attachment loss explain a large part of this reversal, but are not a full
decomposition of geometry/current redistribution effects. The 0.25 mm check
is DC-only; it does not claim a completed native L extraction.

An additional controlled perturbation in
`scripts/probe_marble_contact_loss.py` scaled **all** graph-attachment
resistances to 1% of their extracted values, leaving the physical overlap
matrix unchanged. The routed DC values at 1, 0.75, 0.5 and 0.25 mm became
3.822225, 3.804859, 4.136519 and 3.970494 mOhm, respectively. They remain
nonmonotone, so simply making graph links nearly ideal is not a valid cure.
The perturbation is diagnostic only; it is not a new contact formulation.

### Definite geometry-support defect

`hybrid_mesh.py`, `_Builder.zones`, clips display/control cells and checks
contact and centerline containment, then creates rectangular zone branches
with width equal to the uncut grid-cell size. `peec_volume_adapter.py`,
`_add_basis`, turns these directly into full rectangular current volumes.
It never clips the current basis to the filled zone boundary.

For every zone branch, construct the actual rectangle using
`peec_volume_resistance._basis(design, branch).polygon`. Compare it to its
source zone polygon with Shapely `Polygon(rectangle).difference(zone).area`;
use `buffer(0)` for polygon normalization and report outside areas above
1e-8 mm^2. This check found:

| Zone basis support | 1 mm | 0.5 mm | 0.25 mm |
| --- | ---: | ---: | ---: |
| Zone bases total | 18 | 82 | 315 |
| Bases extending outside filled copper | 7 | 19 | 40 |
| Sum of outside areas, mm^2 | 0.558522869 | 0.710276566 | 0.294066074 |
| Sum of zone rectangle areas, mm^2 | 14.678914216 | 18.553491658 | 18.737865113 |

Sums are basis-support areas, not union copper areas: overlapping bases must
not be interpreted as separate copper volume. At 1 mm,
`zone-102:B.Cu:1:link:2:0:0:2:1:0` alone has 0.182384376 mm^2 outside copper
out of 1.001156137 mm^2 rectangle support. This is a concrete basis-geometry
error, not a hypothetical concern. The exact volume integrator and exact
overlap-loss integral faithfully integrate the supplied, incorrect support.

### Definite capacitance mesh artifact

`quasistatic_capacitance.py`, `estimate_branch_capacitance`, assigns
`0.5 * C_line(width, dielectric_height, epsilon_r) * length` to every planar
pad/zone current branch. Internal grid subdivisions are thereby treated as
separate narrow microstrips with their own fringing. The factor 0.5 does not
remove this width-dependent artifact.

| Estimated contribution, pF | 1 mm | 0.5 mm | 0.25 mm |
| --- | ---: | ---: | ---: |
| Tracks | 0.104631160 | 0.104631160 | 0.104631160 |
| Zone | 3.168686590 | 4.441732885 | 5.343836722 |
| Pads | 0.348192273 | 0.652887668 | 1.215066119 |
| Total | 3.621510024 | 5.199251714 | 6.663534001 |

Reproduce by calling `estimate_branch_capacitance` and summing only branches
outside `TOPOLOGY_ONLY_BRANCH_KINDS`, grouped by branch kind. Vias contribute
zero under the existing unsupported-via-capacitance policy.

A fixed 2 mm square with an n-by-n grid has 2*n*(n-1) branches of length and
width h=2/n mm. The implemented rule gives
`C=n*(n-1)*h*1e-3*C_line(h, 0.2, 4)`.
Direct evaluation for n=2,4,8,16,32,64 gives respectively
0.4477275, 0.7971439, 1.2117576, 1.8486885, 2.9288303, 4.8019359 pF despite
fixed physical area and dielectric. In the narrow-strip limit this rule
scales approximately as n/log(n), so refinement is not an electrostatic
convergence process. This is an independently derived oracle using only the
repository's stated estimator equation, with no external implementation.

The audit also found a reporting error: `peec_plugin.py` overwrote the
estimator's actual `estimated_branch_count` with the number of all physical
branches, including the 11 skipped via/barrel branches. This overwrite has
since been removed; older evidence still carries the misleading count.

## Smallest corrective path and acceptance gates

1. Preserve fail-closed/approximate status. Do not increase integration budgets
   or add PSD repair as a remedy for these mesh errors. An immediate safe
   guard should reject unsupported out-of-copper rectangular field bases,
   reporting owner ID, outside area and violated boundary. Do not silently
   shrink width: that changes current normalization, shared-face flux and R.
2. Give boundary current bases geometry conforming to the actual copper,
   with physical shared-face area and distance. Either integrate clipped
   polygonal volumes with consistent R/L normalization, or construct a
   conforming interior rectangular partition plus an explicitly bounded
   omitted-boundary approximation. The latter needs an area/error gate;
   centerline containment alone is insufficient.
3. Replace arbitrary full-pad-width nearest-node attachments with shared
   contact/face flux coupling consistent with that partition. Use ideal
   graph constraints only for truly coincident physical degrees of freedom;
   making every finite-length link ideal would remove real spreading loss.
   Keep the original pad terminals and document finite terminal contact area.
4. Decouple C from the current-branch tessellation. A minimum bounded surrogate
   is a unique-copper-area parallel-plate estimate with any external-perimeter
   correction explicitly separate, counted once, and still approximate.
   For general geometry, implement a qualified electrostatic panel solve.
   Preserve the estimator's actual estimated/skipped counts after filtering.
5. Before running another expensive native mesh level, require the mesh/DC
   checks above to pass on both manufactured clipped-zone/attachment cases
   and this Marble terminal pair. Verify basis support within a declared
   geometry tolerance (proposed outside area <=1e-8 mm^2 per basis), unchanged
   connected components, stable terminal contact support, and conservation.
6. Proposed numerical convergence gate, not an existing product guarantee:
   use at least three actual refinements, require each of the last two
   consecutive changes in port R and L <=2% relative to the finer result,
   and no worsening trend; require normalized network residual <=1e-7 and
   current balance <=1e-8 of port current. Keep pair-integration sensitivity
   below 0.2% at fixed mesh, separately from discretization sensitivity.
   Use <=2% tessellation sensitivity for the bounded C surrogate without
   promoting its physical accuracy. A trusted independent reference and
   knowledgeable numerical review remain required before release claims.

An independent affine-potential patch audit also blocks promotion of a
cell-centred shared-face rectangular prototype. For a left cell
`[0,1] x [0,2]` and two right cells `[1,2] x [0,1]`,
`[1,2] x [1,2]`, the exact potential `V=y` has zero flux through each
vertical common face. The prototype's normal-distance two-point rule uses
cell-centre potentials 1, 0.5 and 1.5 and instead gives opposite nonzero
face currents (`+/-0.5 sigma*t` in unit-width coordinates). Their net KCL
cancels, so conservation alone would miss the inconsistency. Require each
face's affine-potential flux to match to roundoff under hanging refinement
and rotation before using that prototype for DC/AC qualification. A
nonoverlapping copper-union RT0 face-current discretization with explicit
finite pad/via contact coupling is a candidate, not yet an implemented cure.

Confidence: high for out-of-copper support, capacitance mesh dependence and
DC/topology sensitivity, all directly reproduced. Moderate for how much each
causes the observed L drift; isolating that requires corrected geometry and
controlled port/contact studies. There is no evidence here that native
quadrature, PSD admission, or the overlap Gram resistance formula is itself
responsible for the measured refinement drift.

## 2026-09-24 conforming RT0 DC follow-up

The experimental `scripts/probe_marble_rt0_dc.py` repeats the same board SHA,
net, and U37.18-to-R195.1 terminal pair using the interior-rectangle partition
and mixed RT0 DC discretization. The command accepts explicit mesh, partition,
and unknown budgets; its output is `diagnostic_only`, does not enforce an OS
memory limit, and does not construct a compatible PEEC inductance or
capacitance matrix. The probe rejects requested h < 0.05 mm because the base
builder would otherwise silently clamp it. Its output excludes the unbounded
contact list.

From the repository root, with the optional Shapely/SciPy environment and the
pinned board at the path above, reproduce one row with:

```powershell
python scripts/probe_marble_rt0_dc.py --board build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb --mesh-size-mm 0.25 --boundary-depth 6 --area-limit 0.02 --max-cells 100000 --max-unknowns 250000
```

The script verifies board SHA-256 before importing geometry. Replace only
`--mesh-size-mm` for the other rows, not source/load identities or budgets.

These runs used boundary depth 6, maximum omitted-area fraction 0.02, and
up to 100,000 partition cells and 250,000 mixed unknowns. The earlier 1 mm run
used a 20,000-cell partition budget; all listed accepted solves returned
`model_status=experimental` and `production_qualified=false`.

| Requested h, mm | Routed RT0 DC R, mOhm | Change vs. previous, relative to finer R | Connected triangles | Connected current unknowns | Result |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1.0 | 5.005036809 | -- | 42,388 | 57,422 | Experimental solve |
| 0.5 | 4.490019274 | 11.470% | 44,550 | 60,384 | Experimental solve |
| 0.25 | 4.313441318 | 4.094% | 49,980 | 67,909 | Experimental solve |
| 0.125 | 4.211180359 | 2.428% | 64,407 | 87,892 | Experimental solve |
| 0.0625 | -- | -- | -- | -- | Admission refused: 307,521 mixed unknowns exceed 250,000 budget |

For h=0.25 mm, relative linear residual was 3.64e-13, maximum triangle KCL
error 1.84e-13 A, and energy mismatch 6.31e-14. Those checks validate the
linear algebra for that admitted discrete problem, **not** physical accuracy.
Neither of the last two consecutive mesh changes is <=2%, so the proposed
port-R mesh gate fails. The 0.0625 mm run did not solve and cannot be used for
an extrapolation. The 2% omitted-area admission is an area bound, not a port
error bound; at h=0.25 mm, the F.Cu represented area misses 0.9152% and B.Cu
misses 0.3966% of their respective copper unions.

Two independent production-builder audits identify why more refinement alone
is insufficient:

1. At h=0.75 mm and depth 6, a 5.70e-7 mm2 B.Cu interior rectangle on
   `zone-102:B.Cu:1` is corner-only connected at
   `(235.3009,158.79395)` mm. The true zone has a diagonal full-copper
   boundary there. The area gate passes while the positive-face topology gate
   correctly rejects a disconnected retained island. A diagonal graph link
   would fabricate copper; repair must use boundary-conforming cells or
   topology-directed boundary refinement, and still fail if the budget is
   exhausted.
2. The builder represents each finite pad contact by one fixed rectangle.
   In a 0.5 mm square manufactured pad, requested h of 0.25, 0.125, 0.0625,
   and 0.03125 mm yielded maximum contact-triangle edges of 0.125, 0.125,
   0.0883883, and 0.0883883 mm. The fixed physical footprint is appropriate,
   but its discretization must subdivide while preserving total contact area
   and terminal identity. A manufactured 2-by-1 unit sheet with fixed 0.5-unit
   source/sink strips has exact R = 4/3 ohm; holding each contact unrefined
   plateaued near 1.38094 ohm despite interior refinement. This is a contact
   discretization error, not a KCL failure.

AC remains blocked by a separate formulation gap: the live PEEC path constructs
rectangle/annulus branch R/L, whereas experimental RT0 DC uses triangle-face
currents, a non-diagonal resistance matrix, and distributed via contacts. The
native affine-prism test currently admits no self-inductance at its bounded
work budget; its test tolerance for a mutual case is 25%. A dense L for the
57,422-current 1 mm RT0 component would be about 26.4 GB in real doubles
before complex solve storage. Correct AC requires the same signed RT0 basis in
R and an error-controlled sparse/matrix-free magnetic operator, plus separate
quadrature, contact, mesh, and solver qualification. None of the DC results
above should be reported as Marble AC accuracy.

### Finite-contact subdivision follow-up

The experimental conforming builder now subdivides each unchanged finite
contact footprint at the effective mesh size, preserving one terminal ID and
area-weighted RT0 injection/measurement. A production-builder regression
checks footprint area, maximum subcell edge, normalized contact weights, and
total-cell budget refusal. It also rejects requested conforming h below the
base builder's 0.05 mm floor instead of silently labeling a clamped mesh as a
refinement.

On the pinned Marble pair, h=1, 0.5, and 0.25 mm had no contact subcells to
add and retained the resistance values above. At h=0.125 mm, nine contact
subcells were added across the reviewed net and R changed from
4.211180359 to 4.210952454 mOhm. The h=0.25-to-0.125 change is still 2.434%
relative to the finer result, above the proposed 2% gate. Thus the contact
fix repairs a discretization invariant but does **not** close Marble port
convergence. At h=0.125 mm, relative algebraic residual was 5.60e-13,
maximum cell KCL error 1.46e-14 A, and relative energy mismatch 8.45e-15;
these do not certify mesh accuracy. At h=0.0625 mm, the original mixed system already exceeded its
250,000-unknown budget; the subdivided system cannot be assumed affordable.
The isolated matrix-free RT0 trace-CG prototype fails closed on Marble at
h=0.125 mm under both 2,000 and 10,000 Jacobi-preconditioned iterations;
conditioning work is separate from geometry and AC qualification.

### Current legacy-mesh copper-support audit

The committed `hybrid_mesh.py` shared-face change (`77f297c`) preserves the
18/82/315 zone-basis counts at h=1/0.5/0.25 mm. For each basis, an independent
Shapely `Polygon(basis).difference(Polygon(raw_source_zone).buffer(0)).area`
measurement was compared with `zone_basis_support_report` by branch ID. The
source is the one filled C383-net zone from the pinned board SHA above; its raw
polygon is valid. All violating basis IDs and areas agree within 1e-9 mm^2.

| Requested h, mm | Zone bases | Bases outside copper | Summed outside area, mm^2 | Largest single outside area, mm^2 |
| ---: | ---: | ---: | ---: | ---: |
| 1.0 | 18 | 4 | 0.0456514967673704 | 0.0363005379715354 |
| 0.5 | 82 | 12 | 0.0455070827196954 | 0.0083648055827902 |
| 0.25 | 315 | 23 | 0.0066317543541249 | 0.0014351988530894 |

The areas above are independent Shapely values; the support report sums differ
by less than 1e-13 mm^2 due to arithmetic order. The earlier 7/19/40 table
records the historical pre-change mesh and historical ungated R/L results; it
must not be used as the current mesh baseline. The updated pinned-board test
asserts these measurements, board SHA, and `PEEC_ZONE_BASIS_OUTSIDE_COPPER`
with the complete rejection report. Geometry leakage is smaller but remains
far above the 1e-8 mm^2 per-basis admission threshold. No current Marble AC
R/L result is admitted.

## Release checkpoint (2026-09-24)

The conforming geometry/RT0 DC/finite-contact/unique-area-capacitance files
are experimental source, not a release capability. The Marble production AC
route remains blocked before native extraction. A local checkpoint preserves
the implementation and this evidence; it does not waive numerical review.

Focused Python 3.11 tests for conforming mesh/DC, finite contacts, iterative
RT0, unique-area capacitance and the pinned-board diagnostic passed 49/49.
The architecture check passed. A separate CP312 Release-native adapter run
passed 7/7 when explicitly loading the newly built binary. That binary was
not installed into the shared runtime because other Python processes held the
old extension open. The optional Marble support regression now reflects the
committed shared-face mesh and still requires fail-closed admission. The
complete project test suite was not run in a stable tree and is not claimed green.

The bounded matrix-free RT0 DC trace-CG prototype is not a Marble solve:
Jacobi exhausted 10,000 iterations at h=0.125 mm; an experimental symmetric
multilevel variant remained at residual 0.002815 after 2,000 iterations.
Local RT0 mass condition numbers across 70,896 assembled triangles ranged up
to 2.01e7 (99th percentile 5.88e3), exposing severe hanging/skinny triangle
conditioning. Both iterative attempts correctly refused a result.

Resume order: repair the remaining out-of-copper zone bases, positive-face
boundary topology and RT0 triangle quality under explicit work
budgets; demonstrate two consecutive <=2% Marble R refinements with fixed
terminal footprints; implement error-controlled self/touching RT0 magnetic
integrals and a shared-basis scalable R/L operator; then qualify L/AC against
independent references. No passivity repair or expanded native work budget is
a substitute for these gates. Knowledgeable human numerical review is required
before release of any promoted field result.
