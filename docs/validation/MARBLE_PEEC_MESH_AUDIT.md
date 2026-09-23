<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Marble finite-volume PEEC mesh audit

Date: 2026-09-24. Status: diagnostic evidence, not production qualification.
This audit changes no numerical implementation and performs no Git actions.

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

Confidence: high for out-of-copper support, capacitance mesh dependence and
DC/topology sensitivity, all directly reproduced. Moderate for how much each
causes the observed L drift; isolating that requires corrected geometry and
controlled port/contact studies. There is no evidence here that native
quadrature, PSD admission, or the overlap Gram resistance formula is itself
responsible for the measured refinement drift.
