<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental signed-flux DC density and complete planar support

This bounded increment does **not** fix or pass the original EBrake board
convergence gate. Production hybrid DC, its branch p95, terminals, tolerances,
and AC dispatch are unchanged. No source/load footprint is inferred. This is an
experimental planar-field helper and an opt-in output of the existing offline
RT0 probe, not a registered solver or a release qualification.

## Reviewed foundations and independent derivation

Reviewed 2026-10-19, without inspecting external implementation source:

- Haus and Melcher, *Electromagnetic Fields and Energy*, MIT online edition,
  [7.2, Steady Ohmic Conduction](https://web.mit.edu/6.013_book/www/chapter7/7.2.html),
  governing-law discussion, continuity conditions, insulating boundary and
  conductance subsections: steady conservation, Ohmic constitutive relation,
  and integrated terminal current. The associated discussion was reviewed;
  equation images are not claimed as separately transcribed sources.
- Vohralik, *Equivalence between mixed finite element and multi-point finite
  volume methods*, C. R. Math. 339 (2004), pp. 525-528,
  [DOI 10.1016/j.crma.2004.08.004](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2004.08.004.pdf),
  equations (1)-(3) and section 1's oriented compact face basis, pp. 525-526.
  This supplies the mixed flux/potential foundation; its elimination algorithm
  is not copied or implemented by this increment.
- Shapely public API documentation, `constrained_delaunay_triangles`,
  [API reference](https://shapely.readthedocs.io/en/stable/reference/shapely.constrained_delaunay_triangles.html),
  reviewed signature, polygon-boundary constraint guarantee and GEOS >=3.10
  requirement. Runtime tested here: Shapely 2.1.2. This is already a project
  geometry dependency, not copied external mesher code or a guarantee of good
  triangle quality.

All derivations, code, test geometries and analytical oracles below were
independently authored. No external solver source, mesh, test or numerical
recipe was copied. The existing Apache-2.0 boundary applies to these files.

Let t be thickness in mm, sigma conductivity in S/m and k=sigma*t*1e-3
sheet conductance in S. On a CCW triangle of area A in mm2, q_i is the signed
outward integrated current in amperes through the edge opposite vertex v_i.
The field is

`K(x) = sum_i q_i*(x-v_i)/(2*A)` in A/mm, and `J(x)=K(x)/t` in A/mm2.

The face normalization follows because `(x-v_i).n` is the corresponding
altitude on its opposite edge and zero on the other edges. Integrated
divergence equals `sum(q_i)`. Shared-face opposite signs conserve current.
This is a vector reconstruction from the same unknowns as the mixed solve,
not a least-squares smoothing of independent absolute branch densities.
For divergence-free cells K is constant; source cells retain their affine
variation. Signed axes, rotation and full vector magnitude are retained.

The existing exact mass is `M_ij=integral(w_i.w_j)/k`. The new independently
evaluated degree-two triangle quadrature computes
`P = integral(|J|^2/sigma) dV`, with numerical conversion factor 1000 for
J in A/mm2 and volume in mm3. It agrees with `q^T M q`. Its three positive
quadrature weights are for exact quadratic dissipation, not percentile samples.
The mixed/hybrid solver still checks cell/face conservation and terminal work.

For each triangle, affine J lies in the convex hull of its three vertex
vectors. If c is their mean, the lower bound
`max(0, |c|-max_i|J_i-c|)` and upper bound `max_i|J_i|` enclose every magnitude.
Weighted quantiles of those lower and upper bounds enclose the physical-volume
quantile. Midpoint subdivision quarters a triangle's volume exactly and gives
new affine values. Refine only intervals intersecting the quantile enclosure.
The returned p95/p99 are **intervals**, not a passing scalar selected from an
unresolved interval. A budget failure is explicit. The norm/quantile tolerance
is unrelated to, and does not change, the original 10% board convergence gate.

The geometric bounds hold in exact arithmetic; the implementation is not
outward-rounded interval arithmetic and does not provide a formal floating-point
certificate. Independent review exposed a separate rank-rounding defect:
constant magnitudes 0 and 1 with volumes `[19, 1+5*epsilon]` incorrectly returned
p95 `[0,0]`. The exact supplied binary64 weights require p95 1. The correction
screens cumulative-sum uncertainty conservatively; ambiguous ranks are resolved
with exact integer sums of the binary64 weights and quantile. No tolerance or
positive-volume cutoff is used. Writing each weight as `n_i/2^s_i`, let
`S=max(s_i)` and `T=sum(n_i*2^(S-s_i))`. If `q=a/b`, the first sorted prefix
`P` with `b*P >= a*T` is the exact rank. The fallback is linear in the number
of supplied weights, with bounded binary64 integer widths. The separately
rounded reported total volume is not used to resolve an ambiguous rank.
This fixes the rank jump, not spatial error or formal roundoff certification
of the affine-norm bounds. Python's
[exact float ratio contract](https://docs.python.org/3.11/library/stdtypes.html#float.as_integer_ratio)
was reviewed for this independently authored arithmetic.

## Support, contacts and explicit limits

`dc_copper_domain.source_copper_groups` prepares selected full planar unions
from straight tracks (including caps), source-filled polygons and admitted
standard/custom pads. Fixed 128-side curved outlines are inscribed; drills are
circumscribed. These are bounded polygonal approximations, not exact circles.
All intersecting drill voids are subtracted regardless of drill net, including
unassigned NPTH and foreign-net drills; via drill spans are retained. Centered
circle/oval pad bores are admitted; unsupported source fills/arcs/offset drills
fail closed. The separate axial-source inventory is never a solved barrel.
Pad `type` and normalized `pad_kind` must agree when supplied. Drilled SMD,
missing/unknown drilled kinds and contradictory plating metadata are rejected
before subtracting a through-stack bore. Selected NPTH copper support is
explicitly rejected as ambiguous rather than silently dropped or converted to
a plated barrel; an authored planar NPTH land may be real, but this helper does
not infer its admission policy. Foreign/unassigned NPTH bores still cut selected
copper. Two regressions cover these independent-review findings. This follows
the distinct plated/nonplated/SMT vocabulary in the
[KiCad pad format](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/index.html),
reviewed for type semantics, not as external implementation source.

`dc_triangle_partition.partition_polygon_groups` accepts explicit planar
polygons and explicit finite-area contact polygons. It nodes copper/contact
boundaries, triangulates constrained regions, and performs shared-edge midpoint
refinement. No boundary region or disconnected copper component is discarded.
It checks union coverage, overlap and cross-group physical prism overlap.
The compiler checks disjoint support; `volume_percentile_enclosure` by itself
cannot prove ownership from vectors and volume weights alone. Every undriven
retained triangle has zero flux and remains in the quantile distribution.

Contact current is uniformly distributed over the *supplied* fixed area;
voltage is its power-conjugate area average. No equipotential metal patch is
created. `explicit_terminal_contacts` is an experimental helper accepting
`contact_polygon_mm` in supplied source/load dictionaries; this is **not** a
new public schema or production CLI option. A position-only input remains a
permitted approximate graph diagnostic under `docs/DC_SOLVER.md`, but does not
define this finite-area continuum boundary. Existing source geometry does not
by itself specify which region a physical electrode contacts.

The RT0 assembler admits generated triangles as well as the previous rectangle
fan mesh. Triangle partitions have no rectangle spokes; that optimization is
disabled without altering the mixed equations. Existing axial branch resistance
handling recognizes via/pad-barrel records, but this increment does not compile
or qualify board barrel contacts. In particular, overlapping land thickness
and barrel endpoint support require a consistent 3D ownership convention.
The opt-in field output always sets `complete_physical_volume=false`, reports
axial count/status, and identifies its planar-only scope. The legacy rectangle
route's omitted boundary area also cannot be relabeled complete. No planar
p95 is substituted for a whole-board physical-volume statistic.

Limits: 1024 planar groups, 4096 contacts, bounded source/contact vertex count,
at most 250000 generated triangles, existing RT0 unknown/mass-conditioning
limits, at most 32 refinement rounds, and at most 4000000 percentile subcells
(default 1000000). Quantile default enclosure tolerance is
`1e-10 A/mm2 + 1e-6*upper`. Nonfinite coordinates/results, nonpositive or
underflowed volume, overflowed totals, bad triangles, unsupported geometry and
budget exhaustion fail. Sparse LU fill/runtime and GEOS work inside each
bounded operation remain supervised offline risks; there is no new in-kernel
cancellation guarantee. No measurement or human release review is supplied.

## Independent checks executed

The original 33-test focused command passed on 2026-10-19. Five additional
rank-rounding, loss-arithmetic and pad-admission regressions bring this group to 38 tests,
including 100 deterministic comparisons against an independently evaluated
rational oracle. Independent review also executed 3,716 exact-rational rank
comparisons over subnormal through large finite weights without disagreement:

```powershell
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_dc_copper_domain tests.python.test_dc_rt0_density tests.python.test_peec_conforming_dc tests.python.test_peec_rt0_iterative -v
```

A final arithmetic check also exposed a false zero from intermediate overflow
in `6*sigma` at finite conductivity `1e308 S/m`. Regrouping the scale factors
recovers the independently known uniform-sheet result `5e-306 W`; nonzero
fields whose loss underflows now fail explicitly. Zero current remains exact
zero. This extreme-value regression does not qualify arbitrary material ranges.

Coverage includes signed uniform/45-degree rotated fields with large origins,
quadrature versus independent uniform-sheet power, contact work and charge,
finite-contact sheet convergence, exact quadrant-disk quantile enclosure,
retention of zero-current volume, holed-domain ownership, foreign-net/NPTH
voids, cross-layer overlap, malformed inputs, overflow/underflow and budgets.
The same explicit contact dictionaries are reusable across .5/.25 mm meshes;
both successful compilation and a later budget failure leave them unchanged.
Allocated node identities are returned only in the mesh contact metadata.

The angular annulus field oracle uses a=.5 mm, b=1 mm, t=1 mm and I=1 A.
Conservation gives `|J|=I/(2*t*ln(b/a)*r)`, and integrating the annular volume
below a given magnitude gives p95 at `r=sqrt(.05*b*b+.95*a*a)`.
The exact value is 1.3453200624534145 A/mm2. Independently integrated chord
flux is `-C*ln(r_end/r_start)`, C=I/(2*ln(b/a)). The field interpolant produces:

| Radial/angular divisions | Triangles | p95 A/mm2 | Relative error |
| --- | ---: | ---: | ---: |
| 8/64 | 1024 | 1.36103944315427 | 1.168449% |
| 16/128 | 4096 | 1.31979205976487 | 1.897541% |
| 32/256 | 16384 | 1.33834639725037 | 0.518365% |

The predeclared finest error <1% and improvement over the coarsest pass; the
sequence is explicitly **not monotone**. Each energy error is <0.4% against
`2*pi*C*C*ln(b/a)/k`. This tests flux interpolation and its observable, not a
new annulus terminal solve or arbitrary-board convergence. Exact local field
enclosure does not remove spatial discretization error.

## Original EBrake remains unclosed

The pinned original board is
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Actual source-union preparation retained planar areas (mm2) B.Cu
137.98470253475028, F.Cu 63.583482927269145, In1.Cu 14.124773744568625 and
In2.Cu 20.13430519629135, plus an explicit ten-source axial inventory.
The original load (149.05,116.3) B.Cu is outside this planar copper; the source
(165.1,116.3) is inside. Independent native inspection locates the load inside
J7.2's drill void. A track primitive crossing a bore is not conductor in it.
Mapping that point to a pin/barrel contact would require an explicit physical
boundary definition, which the owner has chosen to leave unspecified.

The distinction matters independently of numerics. For radial sheet conduction
from a circular electrode of radius a to radius b, conservation gives
`K_r=I/(2*pi*r)`, `R=ln(b/a)/(2*pi*k)` and `P=I*I*R`. Two electrodes with the
same center but radii differing by two change R by `ln(2)/(2*pi*k)`; for
sigma=5.8e7 S/m and t=.035 mm this is 54.34374387996345 micro-ohm. Thus a
coordinate does not uniquely define resistance or dissipated power. A point
limit has divergent energy in this model, but this alone does **not** prove
that a bulk p95 has no limit. Nor does it invalidate the established 1D graph
diagnostic. It blocks silently treating that graph terminal as a specified
finite-area physical electrode in this continuum model.

No original EBrake request, test, four-level ladder [2,1,.5,.25], threshold or
production density result is changed here. The retained original failures in
[PI01 evidence](validation/PI01_OWNED_PAD_DC_20261019.md) remain failures;
this increment makes no new original-board pass claim. Remaining work is an
owner-specified physical contact model, consistent axial/landing ownership,
real-board field convergence and required independent/human numerical review.
