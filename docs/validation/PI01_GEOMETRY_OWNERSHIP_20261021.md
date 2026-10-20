<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02 geometry and axial ownership increment — 21 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

**PI01-S02 remains in progress.** This increment verifies opt-in precision
admission for the previously failing rotated polygons and a bounded explicit
annular land/gap ownership model with a fresh reduced DC solve. It does not
close general land-transition fields, full physical-volume density, or original
EBrake/Marble SI/PI qualification. Production dispatch and board gates remain
unchanged. No full-suite, installed or release qualification is claimed.

## Methods and executed evidence

[Precision geometry](../DC_PRECISION_PARTITION.md) records the original sliver
failure, reviewed Shapely/GEOS/JTS API lineage, independently authored admission
logic and measured uncertainty. [Axial ownership](../DC_AXIAL_OWNERSHIP.md)
derives disjoint land/gap support, annular current, SI loss and resistance from
reviewed steady-conduction references. All new code, fixtures and derivations
are original; no external implementation or test data was incorporated.

- Strengthened **PI01-S02A: 18 tests passed, no skips**, fresh source-bound
  [receipt](parity/PI01-S02A-geometry-replay-20261021.json),
  log ([bundled original execution log](parity/PI01-S02A-geometry-replay-20261021.log)), and
  [12-solve ladder](parity/PI01-S02A-geometry-ladder-20261021.json).
  The rotated case now rotates the actual source and contact polygons before
  meshing; it declares g=1e-12 mm. No original resistance/density tolerance
  changed. The old receipt/log remain historical; their hashes were not patched.
- **9 axial helper/integration tests passed, no skips**, source-bound partial
  [receipt](parity/PI01-S02-blockers-20261021.json),
  log (unbundled local record: `parity/PI01-S02-blockers-20261021.log`), and
  [raw ownership and fresh-solve report](parity/PI01-S02-ownership-20261021.json).
  The receipt enforces `stage_complete=false`, `production_qualified=false` and
  revalidates the strengthened finite-contact receipt.
- **47 unchanged DC/Marble regression tests passed**, no skips: copper-domain,
  density, conforming DC, iterative RT0, Marble probe and refinement-audit
  modules. This includes cylindrical/annular and source/contact conservation
  checks; these are focused mathematical checks rather than new board solves.
- **16 tracking/evidence tests passed**, no skips, including corrupted receipt
  rejection and current source envelopes for all Done stages. Architecture,
  scoped whitespace and regenerated reference-inventory consistency checks pass.

Independent geometry review found an initial admission flaw: a 0.4g insulating
gap between different nets could collapse into touching support; an interior
contact margin could likewise disappear. Explicit pre-clearance and post-DE-9IM
relation guards now reject both, with retained counterexamples. Boolean grids
also reject. The reviewer reran all 18 tests and the original counterexamples;
no blocking findings remain in this bounded scope. The independent axial worker
derived and tested cylindrical volume/loss integration and reviewed the fresh
RT0 integration. Knowledgeable human numerical release review remains pending.

Runtime: Python 3.11, NumPy 2.2.6, SciPy 1.17.1, Shapely 2.1.2.

## Observed results

The actual rotated-polygon ladder has resistance errors
1.46484375% / 0.36621094% / 0.09155273% for target lengths
0.5 / 0.25 / 0.125 mm. Measured source boundary movement is about
6.8e-13 mm, below the declared 4e-12 mm budget. Copper and contact
symmetric-difference areas are retained, not silently relabeled exact geometry.
P95/p99 remain plateau tests, not a proof of contact-ramp density accuracy.
Default g=0 still rejects the original sliver; bad triangles and unresolvable
features are never repaired by relaxing the RT0 shape guard.

The annular fixture uses three explicit land slabs and two gap segments. Each
land volume is owned once; segments stop at facing slab surfaces. Clipping the
old 2 mm combined center span to 1.8 mm of gaps changes resistance. Fresh RT0
solutions give **1.350917288843 mOhm** for the old center spans versus
**1.215825559959 mOhm** for the gap branches, matching the independent 0.9 ratio
and integrated Joule work. Old imposed 2/3 A currents are not reused for the
actual 1 A solve. The polygonal annular contact approximation has a retained
0.040154685% area discrepancy from its exact circular annulus. It is not hidden
in a rescaled resistance or exact-interface claim.

General different face patches on a shared land node require separate incidence
and conjugate-potential mapping. Land through-thickness transition current and
heat remain unresolved; their missing heat is null, not zero. Geometry ownership
alone does not supply a complete 3-D vector field or percentile distribution.

## Board admission replay and remaining acceptance

An actual read-only replay at
`build/pi01-s02-blockers-20261021/board-admission.json` retains unchanged source
hashes, complete selected EBrake planar areas, finite-contact rejection and
Marble's native pad/filled-polygon topology check. EBrake source is inside
planar copper; its original load at (149.05,116.3) B.Cu is outside, consistent
with the earlier J7.2 drill-void finding. Both original terminal footprints
remain unspecified. No electrode, pad/barrel assignment or operating boundary
was inferred. Marble native connectivity passes; this is not an AC/SI pass.

To complete PI01-S02, still supply/approve the physical EBrake electrode model;
compile applicable source-backed contacts and planar/axial ownership including
different face patches and transition fields; verify the full-volume observable;
then repeat original board studies with unchanged physical identities and gates.
Original density/AC and broader SI qualification failures stay open. This
increment does not report them passed or complete.
