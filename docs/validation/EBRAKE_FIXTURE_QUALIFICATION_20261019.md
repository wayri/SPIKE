<!-- SPDX-License-Identifier: Apache-2.0 -->
# EBrake optional fixture qualification, 19 October 2026

This is a source-inventory correction and retained failure diagnosis, not a
numerical-method change or board-accuracy qualification. The optional real-board
regression remains required to complete AC extraction and pass DC convergence;
its failed acceptance expectations have not been converted into rejection tests.

## Source identity and independent inventory

Source: `app/public/demo/ebrake1.kicad_pcb`, SHA-256
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Native read-only inspection used KiCad 10.0.6's installed `pcbnew` interpreter,
`C:/Program Files/KiCad/10.0/bin/python.exe`. No refill or source edit occurred.

`pcbnew.LoadBoard`, `board.Zones()`, `zone.GetIsRuleArea()`, each zone UUID,
`zone.GetLayerSet().Seq()`, and
`zone.GetFilledPolysList(layer).OutlineCount()` independently established:

- 17 authored zones: 14 copper sources and three keepouts.
- 26 filled copper polygons across physical layers; the complete source-UUID /
  layer multiplicity map is retained in `tests/python/test_kicad_fixture.py`.
- One additional F.Cu footprint polygon on JP5, UUID
  `388e6d16-82ed-4c7b-b385-33da3fae27dd`, independently inspected through
  `footprint.GraphicalItems()`.
- `/AOUT1`: eight tracks, one via, four pads and one filled zone polygon.

SPIKE's 27 zone-like records are therefore 26 filled regions plus the one
footprint graphic, not 150 or more zones. The regression now pins the input hash,
checks exact source/layer multiplicities, unique filled IDs and retained fill
state, and separately checks the graphic identity. Existing non-zone count
floors remain unchanged. The latent AC geometry expectation also changes from
two zone polygons to the independently measured one, without altering its
required completed result or positive resistance/inductance checks.

## AC failure retained

The original `/AOUT1` request at 1 kHz to 100 kHz, three frequencies,
1.5 mm target / 1 mm zone cells, 1,000 zone-cell / 1,200 conductor caps fails:

- Legacy inductance has four negative-energy modes; minimum eigenvalue
  `-3.44305149905448e-11 H`, admission tolerance `1e-18 H`.
- The automatic finite-volume retry rejects 46 zone current bases extending
  beyond their source copper. No projection is applied and `solved=false`.
- First offending basis:
  `9a8c62d9-1a90-4414-9d24-b9def4ab082d:B.Cu:1:link:0:0:0:0:1:0`.
  Its endpoints are `(78.9940157471, 60.8416666667, -1.5725)` and
  `(78.6606824137, 61.5416666667, -1.5725)` mm, width
  `0.992952758842` mm and thickness `0.035` mm. Its rectangle extends
  `0.04407490138 mm^2` beyond the source against `1e-8 mm^2` tolerance.
  An independent Shapely polygon-difference calculation returns
  `0.04407490137999689 mm^2`, corroborating the support rejection.

Ownership: `hybrid_mesh.py` connects clipped zone-cell centroids using shared-face
width and centerline containment. `peec_volume_resistance._basis` interprets this
edge as a centered uniform rectangular current support. A contained centerline
does not imply containment of that rectangle. `peec_volume_support.py` correctly
rejects this before native integration in `peec_volume_adapter.py`.

Next repair gate: independently derive a conforming finite-support current basis
and shared-contact formulation, with matching R and L normalization and retained
source ownership, then test this exact boundary fragment and its refinement.
Shrinking/clipping only the magnetic rectangle or excluding rejected branches
would change the circuit/field relationship and is not an acceptable patch.
`peec_conforming_mesh.py` is an existing isolated prototype, not a qualified
production replacement. Follow `NUMERICAL_METHOD_EVIDENCE.md` and the existing
`PEEC_REFINEMENT_REPAIR.md` record before numerical implementation.

A bounded follow-on should start with the recorded two-centroid boundary
fragment, then the unchanged `/AOUT1` source selection, not whole-board routing:

1. Define retained support, current normalization and shared-face/contact
   incidence in an independently reviewed derivation. Record the applicable
   primary-source sections before writing numerical code.
2. Give the mesh/compiler explicit finite-support and source/contact identity;
   do not reinterpret a DC graph width as proof of magnetic support. Preserve
   source copper, holes, existing terminal identity and branch connectivity.
3. Assemble resistance and inductance on that same basis through the volume
   adapter and native kernels. The support and energy admission modules remain
   acceptance authorities, not repair mechanisms.
4. Verify independent support area, current conservation, overlap energy and
   analytical/reference R/L fixtures, then the exact real-board request under
   refinement. Retain approximate status and require human numerical review.

This proposal does not select or qualify a new discretization. Native support
for the chosen nonrectangular basis, numerical cost, contact treatment and
independent physical validation remain design gates.

## DC convergence failure retained

All requested levels complete as `approximate`, without error issues, and grow
the resolved mesh. Final resistance/drop/loss comparisons pass, but the required
95th-percentile current-density comparison does not:

| Cell size (mm) | Nodes | Edges | Load drop (V) | p95 density (A/mm^2) |
| --- | ---: | ---: | ---: | ---: |
| 2 | 105 | 115 | 0.01127726953 | 40.81632653 |
| 1 | 338 | 357 | 0.01127726953 | 40.81632653 |
| 0.5 | 1,377 | 1,608 | 0.01064661469 | 10.75043113 |
| 0.25 | 2,835 | 3,966 | 0.01055600023 | 7.41691870 |
| 0.125, diagnostic only | 8,592 | 13,851 | 0.01067666222 | 3.46921815 |

At 0.5 -> 0.25 mm the density delta is 31.0082%; adding a diagnostic fifth
0.125 mm level increases that delta to 53.2256%. Both exceed the unchanged
10% gate. The fifth-level drop/loss/resistance delta is 1.13015%, which passes
their unchanged gates. `can_sign_off=false` remains authoritative. The checked-in
test keeps its original four-level study and `minimum_levels=3`; more refinement
alone has not resolved the current-density behavior. Diagnose density weighting,
active physical branch support and contact discretization before claiming a fix.
The current reported percentile is volume-weighted over active physical edges
in `dc_result_utils.weighted_percentile_density`; `hybrid_dc_solver.py` constructs
those edge densities and `convergence.py` owns the unchanged required threshold.

## Executed checks and retained logs

The initial four-test run had three failures (inventory, AC, convergence) and
one passing approximate DC smoke solve. The corrected exact-inventory test
passes (one test, 20.706 seconds). Four-level and five-level diagnostic studies
both return `failed_to_converge`; they are not passing qualifications.
The final four-test rerun takes 110.187 seconds: geometry and approximate DC
smoke pass, AC and DC convergence fail (two failures, no skips). Python syntax,
scoped diff whitespace and `scripts/check_architecture.py` checks pass.

Local evidence is under `build/qualification-20261019-optional/`:
`kicad-fixture-initial.log`, `ebrake-geometry-exact.log`,
`ebrake-convergence-diagnostic.log`, `ebrake-convergence-fifth.log`, and
`ebrake-ac-basis-support.log`; final acceptance and architecture logs are
`ebrake-fixture-final.log` and `ebrake-architecture.log`.
Build logs are local diagnostic artifacts, not
redistributed board data or substitutes for the checked-in acceptance tests.

Reproduce the acceptance suite from the repository root:

```powershell
$env:SPIKE_FIXTURE_BOARD=(Resolve-Path app/public/demo/ebrake1.kicad_pcb).Path
$env:TEMP=(Resolve-Path build/parity-test-temp).Path
$env:TMP=$env:TEMP
.venv/Scripts/python.exe -m unittest tests.python.test_kicad_fixture -v
```

The native PEEC extension must be present to execute the AC test. No board
source, production solver, acceptance tolerance or sign-off gate was changed.

## Read-only follow-on: drilled-pad width consistency

Native KiCad inspection establishes that the DC `3Vin` selection has no copper
zones and has six drilled pads. The AC `/AOUT1` selection has three drilled
pads (Q3.2, Q2.3 and J6.1). Consequently the DC failure cannot be attributed
to zone-cell refinement alone, and the existing experimental conforming/RT0
path cannot directly accept either selection: `peec_conforming_mesh.py`
explicitly rejects drilled pads before assembling its rectangular partition.

A specific inconsistency exists in the default drilled-pad graph. In
`hybrid_mesh._Builder.pads`, both angular and radial annular links use
`min(width, height) / side_count` as their cross-section width. Their actual
shared copper faces have different lengths. This is a discretization error,
not evidence of a failed sparse linear solve. The opt-in
`hybrid_owned_copper.prepare` already replaces these widths with actual shared
polygon-face lengths; its builder also uses polygon centroids instead of a
triangle-interior representative point. Those differences must be tested
together rather than treating this as a mere configuration alias.

### Reviewed foundations and independent annulus oracle

Reviewed on 2026-10-19: Haus and Melcher, *Electromagnetic Fields and Energy*,
MIT online edition, [section 7.2, Steady Ohmic Conduction](https://web.mit.edu/6.013_book/www/chapter7/7.2.html),
the governing-law discussion, continuity/insulating-boundary conditions and
conductance definition. These establish the uniform-conductor potential
problem and terminal flux relation; the annulus oracle below is independently
derived, not copied from an external implementation or example.

Take a uniform thin annulus with inner/outer radii a,b, thickness t and sheet
conductance k=sigma*t in siemens. Insulate its circular boundaries. Apply a
potential difference V between two complete radial electrodes separated by
angle theta. In each intervening sector, a potential linear in angle solves
the homogeneous conduction equation and insulating radial-normal condition.
Its angular current magnitude is sigma*V/(theta*r). Integrating through the
radial section gives sector conductance k*ln(b/a)/theta. The complementary
sector is parallel, hence

`R = theta*(2*pi-theta) / (2*pi*k*ln(b/a))`.

At theta=pi and total injected current I, the current-density magnitude is
`I/(2*t*ln(b/a)*r)`. For unique physical-volume weighting over that annulus,
the p95 magnitude is
`I/(2*t*ln(b/a)*sqrt(0.05*b^2 + 0.95*a^2))`.
Use one consistent length unit: t and r in mm produce A/mm^2. This smooth,
finite-electrode oracle has no point-electrode singularity. It does not model
barrel injection, solder, noncircular pads, crowding at discrete contacts or
the EBrake routing.

An in-memory diagnostic generated the existing circular annular mesh with
a=0.5 mm, b=1 mm. All nodes along each of two radial columns are taken as
equipotential electrodes; this boundary condition is for the manufactured
oracle only, not a change to EBrake's terminals. Rotational symmetry makes
each radial ring a uniform series circuit and all rings parallel; direct
series/parallel reduction therefore evaluates this graph without a new solver
implementation. With N angular cells and m=floor(N/2), use
theta=2*pi*m/N, including odd N. Normalize k to 1 S.

| Target (mm) | Angular cells | Radial rows | Default graph R (ohm) | Continuum R (ohm) | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 or 0.5 | 24 | 1 | 15.56140883 | 2.26618007 | 6.86680 |
| 0.25 | 26 | 2 | 7.82773523 | 2.26618007 | 3.45415 |
| 0.125 | 51 | 4 | 7.44476041 | 2.26530880 | 3.28642 |
| 0.0625 | 101 | 8 | 7.26140797 | 2.26595792 | 3.20456 |
| 0.05 | 126 | 10 | 7.22559595 | 2.26618007 | 3.18845 |

The trend is not convergence to the continuum oracle. Before mesh caps,
for this particular a=b/2 geometry, N is approximately 2*pi*b/h and radial
width is approximately h, while the implemented angular-link width 2*b/N is
approximately h/pi. Thus its limiting angular resistance has a factor-pi
bias. This asymptotic argument is conditional on continued angular/radial
refinement; the production minimum target and angular cap prevent an
unrestricted h->0 limit.

For a separate diagnostic, retaining those default node locations but replacing
only link widths in the series/parallel calculation with their exact shared
polygon-face lengths gives relative resistance errors 15.4428%, 7.0680%,
3.2997%, 1.5799% and 1.2520% at 0.5/0.25/0.125/0.0625/0.05 mm. This is a
hypothetical isolated correction, not execution of a changed production solver
or qualification of an arbitrary nonorthogonal mesh. Separately generating the
existing `owned_shared_faces` mode at 0.5/0.25/0.125 mm produces no error issue
and pad widths exactly matching the shared-face helper. Existing
`test_hybrid_owned_copper.py::test_radial_annulus_resistance_and_area_converge`
provides the complementary radial-conduction oracle; the angular case is not
yet a checked-in numerical regression. No source edits were made for these
in-memory diagnostics, whose numeric results are retained above.

### Real-board owned-mode attempt and default-dispatch limit

The separately authorized diagnostic changed only the requested mesh option to
`pad_zone_coupling=owned_shared_faces`; the original levels [2,1,0.5,0.25],
minimum three levels, terminals and tolerances were retained. It stopped at
the first 2 mm level with `status=failed`, `model_status=unsupported` and
`OWNED_COPPER_UNSUPPORTED: Owned pad-zone coupling does not admit pad shape
roundrect`. There are no convergence comparisons and `can_sign_off=false`.
Report: `build/qualification-20261019-optional/ebrake-convergence-owned-diagnostic.log`.

Native inspection identifies the blocker as drilled rounded-rectangle J11.1,
UUID `176a9c39-6f0a-4ef3-b6a9-db189321b513`, drill 0.95 mm and imported
roundrect ratio 0.147059. Simply removing the guard is incorrect:
`_annular_pad_local_cells` currently routes noncircle/nonoval boundaries through
the rectangular ray-radius fallback, and `quasistatic_copper_area._source_polygon`
rejects drilled pads. A bounded extension needs a dedicated outer-boundary
helper retaining the imported radius, conservative drill subtraction and
positive shared-face geometry. Validate outer area
`width*height-(4-pi)*radius^2`, subtract the actual drill area, and check native
J11.1 copper/void containment and rotated equivalents before admitting it.
Existing owned mode also rejects other shapes, overlapping pad outlines and
unsupported contact evidence, and it is DC-only. Automatic default dispatch is
therefore not justified by this attempted run.

### Density semantics, finite contacts and the smallest repair sequence

Mesh-only inspection at 0.5 and 0.125 mm resolves each original DC terminal to
one track node, with unchanged source IDs; this check does not reveal a
switching inferred terminal or a point contact newly appearing under refinement.
The candidate mesh's summed pad-edge pseudo-volume changes from
1.38561517 to 2.60556663 mm^3, whereas track pseudo-volume remains
6.20777766 mm^3. These are all candidate branches, not a claim about the solved
active-component histogram. The real-board contribution of each mechanism to
the failed p95 comparison remains unisolated.

The current p95 implementation weights each branch by length*width*thickness
and uses absolute axial current/cross-section. It is not a unique-volume
distribution of a reconstructed vector-field magnitude. For example, an
independently prescribed uniform sheet field with Jx=Jy=J/sqrt(2) produces
J/sqrt(2) on both orthogonal edge families, although its physical magnitude is
J. More refinement cannot repair that interpretation. Topology attachments
also enter the default DC edge list with `current_density_supported=true`.
This does not authorize deleting the existing convergence gate or substituting
a passing scalar; it identifies what a consistent field observable must verify.

Smallest bounded follow-on:

1. Add the angular annulus oracle beside the existing radial test. Extract or
   reuse the owned shared-face widths and centroid policy with explicit source
   boundaries, including the drilled J11.1 roundrect extension above. Preserve
   unsupported cases, terminal identity and actual barrel resistance. Repeat
   the unchanged EBrake convergence gates only after those geometry/numerical
   fixtures pass; there is no prediction that this alone will close p95.
2. Define unique physical cell support and recover vector current consistently
   from signed face fluxes. Check the affine 45-degree sheet and annulus p95
   oracles before changing the reported physical-density implementation. Keep
   the old branch statistic explicitly distinguished during comparison.
3. For nonorthogonal/shared-contact geometry, extend the existing RT0 support
   contract rather than dropping tangential terms from a two-point graph.
   The current `peec_conforming_dc` reconstructs local fluxes internally but
   returns only aggregate diagnostics, not the field required for p95.
   Its rectangular-only mesh reader and absent drilled-pad contact compiler
   are concrete integration work, not settings. Fixed finite contacts must
   preserve integrated current and power-conjugate averaged voltage.

For the third step, the primary method text reviewed was Vohralik,
*Equivalence between mixed finite element and multi-point finite volume
methods*, C. R. Math. 339 (2004), pp. 525-528,
[DOI 10.1016/j.crma.2004.08.004](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2004.08.004.pdf),
equations (1)-(3) and section 1's oriented face basis on p. 526. It supports
the mixed flux/potential formulation and compact triangle support; its
elimination algorithm was not copied or newly implemented. Independently,
on a CCW triangle of area A, outward integrated-face basis
`w_i(x)=(x-v_i)/(2*A)` has unit flux on its own edge and zero on the other
edges. Signed shared-edge assembly enforces normal continuity. With sheet
conductance k, `M_ij=integral(w_i dot w_j)/k`, `M*q-B^T*u=0`, `B*q=s`
give the energy identity `q^T*M*q=s^T*u`; this is the existing prototype's
testable invariant. Local vector current is reconstructed from that same
basis and divided by thickness, not inferred from independent axial bars.

For AC, this still requires consistently supported R and L on the same
piecewise basis. `src/peec/affine_triangle_basis.hpp/.cpp` already provides
isolated affine-prism unit-face normalization, local resistance and experimental
mutual integrals, but is not bound to the extractor; its self/touching integral
envelopes and resource limits remain unresolved. Do not insert rectangular
legacy inductance around RT0 DC currents. The precise next acceptance tests are
compact support, shared-face cancellation, exact local dissipation, finite
contact work, self/mutual integration error, and the unchanged real-board
energy/support/refinement gates. No new method, default route or board result
is qualified by this read-only analysis.
