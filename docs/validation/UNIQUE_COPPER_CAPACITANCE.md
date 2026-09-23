<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Unique copper-area capacitance surrogate

Date: 2026-09-24. Status: approximate surrogate, not electrostatic qualification.

`python/spike_core/quasistatic_copper_area.py` provides the common
`estimate_branch_capacitance(design, spec, branches)` API. It returns shunt C
in farads, dielectric loss tangents, and actual estimate/omission metadata.
Its use in AC and transient orchestration must be verified independently of
the focused helper tests below.

## Method and independently derived oracle

For a uniform plate, Gauss' law gives electric displacement D = Q/A. In a
stack of dielectric slabs, the voltage is the sum of E_i*d_i, with
E_i = D/(epsilon_0*epsilon_i). Therefore

`C = epsilon_0 * A / sum(d_i / epsilon_i)`.

The implementation converts source area from mm^2 and slab thickness from mm
with the net factor 1e-3. For A = 4 mm^2, d = 0.2 mm, epsilon_r = 4, the
independent plate oracle is 0.708335025024 pF. A two-slab oracle checks series
electrical thickness, not arithmetic averaging of dielectric constants.
Small-loss series dielectric loss tangent uses weights d_i/epsilon_i;
unknown loss in any contributing slab leaves loss unknown for the plate.

Planar zones and pads consume their original source area once. Zone ownership
precedes pad ownership, which precedes tracks; owner IDs break ties. Straight
tracks retain the existing microstrip C' estimator, multiplied by uncovered
source-rectangle area divided by original track width. Thus tracks covered by
pads/zones contribute no duplicate area or internal-edge fringing. This
remains a local microstrip approximation on the uncovered area, not a solved
electrostatic field at its artificial interface.

A pure-Python polygon sweep computes unique area, without adding a package
dependency. Vertical strip cuts include every polygon vertex and every edge
intersection. Inside each open strip, edge order is fixed and interval height
is linear; midpoint height times strip width is the exact polygonal area
integral. Ownership selects the first active source rather than adding
overlaps. Explicit return copper is intersected in the same sweep. The nearest
active reference layer is selected. If one source requires several reference
layers, its estimate is rejected because a v1 branch shunt cannot represent
that allocation honestly. Reference-net branches receive no self-capacitance.

This code, derivation, manufactured polygons, and test oracles were authored
independently for SPIKE. No external implementation or fixture was copied,
translated, or adapted. The work implements the minimum surrogate proposed in
[the Marble audit](MARBLE_PEEC_MESH_AUDIT.md), not a general panel/BEM solver.

## Distribution and limits

An owner's total C is distributed to its physical branches by positive branch
length normalized by their sum. Internal current-link widths and link counts
cannot change the owner's total. This distribution is an approximate nodal
assignment; it does not establish charge-density, AC, or transient convergence.

Supported geometry is simple authoritative filled-zone polygons, undrilled
rectangular/circular/oval pads, roundrect pads with an imported radius ratio,
and straight rectangular tracks. Curves use a fixed 128 arc-chord perimeter,
independent of mesh size. For roundrect/capsule arcs, the omitted area is at
most `pi*r^2*(1 - sin(2*pi/128)/(2*pi/128))`; relative total-area error is no
greater than 0.0402%. Circle chords obey the same relative bound. Track end
caps are omitted.

Via/antipad fields, drilled/custom/chamfer pads, arc tracks, unresolved holes,
incomplete fill provenance, missing source geometry, missing dielectric data,
and intervening copper layers are unsupported. Missing roundrect radius is
not replaced by a bounding rectangle. An implicit reference assumes a full
plane; an explicit reference uses only projected return copper. Neither mode
includes exterior fringing, screening by arbitrary neighboring conductors, or
multiconductor coupling. No bound on physical capacitance error is claimed.

Sources lacking a physical branch are listed in `unrepresented_source_ids`.
They cannot receive a nodal charge assignment. `complete_source_coverage`
is false for omissions, reference failures, vias, or unsupported geometry;
stable totals with incomplete coverage do not pass a full-geometry C gate.
Topology links and return-conductor branches are separately excluded.
`estimated_branch_count` is exactly the nonzero returned C count; category
counts and `skipped_branch_count` expose what was actually skipped.

Resources are bounded to 2000 source vertices, 2000 nonvertical sweep edges,
and 4,000,000 edge-strip checks per net/layer group. Exceeding a bound returns
zero for that group with an explicit geometry failure. Positive area sums
avoid cancellation between large overlapping source areas; edge crossing
positions use coordinates relative to the intersection interval. Floating
point intersections near coincident edges remain subject to ordinary double
precision limits. No epsilon inflation or silent polygon repair is applied.

## Acceptance evidence

Run:

```text
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_quasistatic_copper_area -v
python scripts/check_architecture.py
```

The focused suite checks analytic overlapping rectangles and duplicates,
crossing triangles (union area 3 mm^2), owner partitions, translation by
1,000,000 mm, area-to-C units, series dielectric thickness, actual omission
counts, disabled/unsupported states, source overlap with tracks, partial
explicit-reference overlap, roundrect/capsule analytic area bounds, and
resource rejection. These are numerical/geometric checks, not external field
correlation.

Actual `build_hybrid_mesh` refinement of the same 2 mm square gives:

| Target h, mm | Physical branches | C, pF |
| --- | ---: | ---: |
| 1.0 | 4 | 0.7083350250240001 |
| 0.5 | 24 | 0.7083350250239999 |
| 0.25 | 112 | 0.7083350250239999 |

Both consecutive changes are below the proposed 2% surrogate tessellation
sensitivity gate (roundoff here). This does not validate full-board coverage,
terminal contact behavior, R/L convergence, or physical capacitance accuracy.
Independent field/measurement correlation and knowledgeable numerical human
review remain required before release qualification.

## Direct Marble check and outstanding coarse-mesh omission

Freshly import the pinned Marble board from the audit, using
`import_kicad_design`, and keep `Net-(C383-Pad1)` in tracks, vias, pads, and
zones. The retained counts are 2 tracks, 1 via, 7 pads, and 1 zone. Preserve
the original stackup. Build the ordinary hybrid mesh with the audit's
`h=target_size_mm=zone_cell_mm`, `max_zone_cells=1000`,
`max_conductors=2000`, and `memory_budget_mb=512`; call this helper directly.
No native L extraction is involved.

| h, mm | Physical branches | Estimated branches | Area, mm^2 | C, pF |
| --- | ---: | ---: | ---: | ---: |
| 1.0 | 45 | 31 | 11.076811422979 | 4.206835434878487 |
| 0.5 | 120 | 106 | 12.461211422979 | 4.729905391790334 |
| 0.25 | 431 | 407 | 12.461211422979 | 4.729905391790334 |

Zone C is constant at 3.62809194360828 pF and uncovered-track C is constant
at 0.05615794268786 pF. Pad C changes from 0.52258554858235 pF to
1.04565550549420 pF because the ordinary 1-mm mesh has no physical branch for
two B.Cu pads: `343c944f-22b3-46aa-9d1d-a2fdcd46e930` and
`85000c51-f4d3-4827-913e-7135c82041c6`. Both appear explicitly in
`unrepresented_source_ids`; the finer meshes represent them. No geometry
failures were returned. All levels skip 11 via/barrel branches.

Consequently `complete_source_coverage` is false at every level, and the
coarse-to-medium total change is about 11.06% relative to the finer result.
This three-level Marble series does **not** pass the proposed 2% C gate.
The medium/fine agreement demonstrates removal of the old internal-link
fringing artifact only for represented planar sources. Completing the coarse
mesh's physical pad ownership, or an explicit node-shunt contract for a
singleton pad, is needed before its total can enter a convergence comparison.
Via/antipad fields remain independently unsupported. This record does not
claim a Marble port or full-geometry capacitance qualification.
