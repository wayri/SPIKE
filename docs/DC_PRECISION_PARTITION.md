<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit precision geometry for conservative planar DC

`partition_polygon_groups(..., geometry_grid_mm=g)` now offers opt-in fixed-grid
linework noding. Default g=0 retains the previous double-precision arrangement.
It does not change any solver residual, triangle-shape or board convergence
threshold. The selected geometry is approximate and remains experimental.

## Root cause, method and reviewed sources

The independently rotated 2x1 mm finite-contact sheet at angle 0.61 rad produces
nine initial triangles with default noding. One has edge-squared/area ratio
about 2.2e16: independently transformed nominally collinear copper/contact
vertices no longer lie on precisely the same binary64 line. The unchanged RT0
shape guard correctly rejects it. A 1e-12 mm grid nodes the original linework
together, yielding six well-shaped initial triangles in this fixture. No
triangle is discarded, merged after solving, zero-filled or admitted by a
weakened numerical threshold.

Reviewed 2026-10-21, without reading external implementation source:

- Shapely 2.1.2 [unary_union API](https://shapely.readthedocs.io/en/2.1.2/reference/shapely.unary_union.html):
  documented `grid_size` input/output coordinate snapping and precision behavior.
- Shapely 2.1.2 [set_precision API](https://shapely.readthedocs.io/en/2.1.2/reference/shapely.set_precision.html):
  narrow feature collapse and duplicate removal warnings. We do not call this
  operation to silently clean the inputs.
- JTS core 1.20.0 [SnapRoundingNoder documentation](https://locationtech.github.io/jts/javadoc/org/locationtech/jts/noding/snapround/SnapRoundingNoder.html),
  class method discussion: a common grid makes a fully noded arrangement;
  rounding vertices independently before noding can distort topology. This is
  conceptual lineage only; no JTS dependency or implementation is incorporated.

The independently authored adapter calls existing public GEOS operations via
Shapely; it does not implement a new snap-rounding algorithm. Governing steady
conservation/Ohm/RT0 mathematics and units are unchanged; see
[DC density derivation](DC_RT0_DENSITY.md) and
[finite-contact work oracle](PI_FINITE_CONTACT_BENCHMARK.md).

## Admission and uncertainty

The caller supplies g in mm, with 0<g<=target_mm*1e-6 and coordinates no larger
than 2^50*g in magnitude. Each original copper/contact polygon must have
minimum clearance >32g. The noder operates once on all original boundaries.
Regions retain their original copper and finite-contact ownership via interior
representatives. Every positive-area region and undriven component is retained.

Before triangulation, unioned admitted regions and each admitted contact are
checked against original support: same polygon component/hole counts, valid
nonempty polygons, Hausdorff boundary displacement <=r=4g and symmetric-difference
area <=2r*P+pi*r^2, P original perimeter. The latter is a deliberately conservative
tube-scale admission budget, not a universal theorem for arbitrary multiply
connected geometry. Both measured quantities and budgets are retained. Close
distinct contacts with 0<distance<=32g and multiply owned regions reject.
Z-overlapping copper groups also reject positive separation <=32g and must
retain their pre/post DE-9IM relation. Interior contact-to-exterior/hole
clearance <=32g rejects; each contact/copper DE-9IM relation must be preserved.
Boolean and nonfinite grid values reject. These checks retain independent
review counterexamples where an insulating gap or contact margin otherwise
collapsed while all per-shape area checks passed.
The old source-area/overlap/omission checks still apply after refinement.

These are floating GEOS measurements, **not outward-rounded certificates**.
Matching component/hole counts alone does not prove arbitrary topology; the
small displacement, clearance and area checks constrain the admitted examples.
This is not permission to delete thin copper, bores, contact gaps or insulation.
Unresolved features, topology change or remaining bad triangles fail closed.
Inputs and electrode identity are not mutated. A fixed grid changes support
within a measured uncertainty, so exact geometry identity must not be claimed.

The strengthened finite-contact benchmark now rotates the actual source
polygons and uses this explicit grid. The original g=0 rejection is retained
as a diagnostic regression. The positive ladder must pass its original 0.2%
resistance and 2% density thresholds. No EBrake contact footprint is inferred;
full PI01-S02, axial transition fields and board qualification remain open.
