# Actual-source P2 field adapter and static domains — 23 October 2026

## Exact implementation boundary

`python/spike_core/propulsion_pod_real_motor_p2.py` provides `RealMotorP2FieldModel(geometry,spec)`. It reuses the same audited native sections, explicit material/winding assumptions, source hashes and bounded ALE map as the P1 adapter. Its separate prepared `P2MagneticOperator` is owned by `propulsion_pod_magnetic_p2.py`; see the independently authored `PROPULSION_POD_MAGNETIC_P2_DERIVATION_20261023.md` and full-loop review for the operator equations and exact patch/oracle evidence. No existing P1 solver is silently changed into a quadratic solver.

Six-node scalar Az uses vertices plus shared edge nodes on straight native-section triangles. With constant element J, vertex shape integrals vanish and each edge shape integrates to area/3. The adapter therefore computes each full physical phase linkage as `source_load(chi_phase) dot A`, including stack depth. It independently checks this against the explicit edge quadrature. The same chi excites the field; no Clarke relabeling or zero-sequence flux deletion occurs. Three symmetric quadrature points exactly integrate linear-material P2 stiffness, PM load and energy on each affine triangle. Four actual field states reuse one factorization and yield `Wprime=.5*i^T*Lfull*i+psi_full^T*i+C`, where C uses the same full recoil-PM reference. P2 magnetic B is linear within each element; actual clipped-annulus quadrature evaluates that linear B, never a centroid-constant substitute.

`evaluate(currents3,theta,include_field)` retains the physical full-phase flux/energy/torque contract. Viewer fields contain geometric vertices/triangles and vertex Az/centroid B, while explicit `p2_nodes_m`, `p2_triangles`, `p2_potential_a_wb_per_m`, `p2_quadrature_b_t` and `p2_barycentric_b_t` retain the higher-order solution. The weighted ALE shape derivative integrates the quadratic stress with the same exact three-point quadrature. A fixed-central-P2-potential perturbation and an independent two-re-solve coenergy perturbation check that derivative. Source material and intended-winding interpretation remain unqualified independently of numerical discretization.

## Executed fixed-support P2 ladder

All rows use the SAME 2 micrometer native section, theta=.002 rad, i=(1,-1,0) A, frozen mesh-motion support [.04426,.04454] m and no red refinement (P2 supplies edge degrees of freedom itself).

| Boundary target | P2 DOFs | Weighted torque (N m) | Same-band Arkkio (N m) |
| --- | --- | --- | --- |
| 1 mm | 67245 | .402438658170 | .417744050677 |
| .7 mm | 85661 | .368785501742 | .362460080763 |
| .6 mm | 91837 | .367147710966 | .360940721898 |

Final weighted change is .444%, Arkkio change .419%, and final discrepancy 1.72%. At zero current the final values are .254328008203 and .247874183015 N m (2.54% difference). These provide useful local discretization corroboration, not a rigorous error bound or full-angle/hardware qualification. First actual source ports at 67245 DOFs required one factorization for four solved states and completed in 3.422 s in this session. Raw results, input hashes and numerical limitations are retained under `output/promo-propulsion-pod-20261023/real_motor`.

Crucially, independently remeshed angular energy does NOT yet yield an admitted global motor Hamiltonian. At 91837 P2 DOFs, zero-current local torque is +.254328008203 N m, but independent-anchor C(theta+1e-4)-C(theta-1e-4) divided by2e-4 is +.146943665422 N m. The analogous P1 result even had opposite sign. Delta convergence on one mesh does not cure mesh-dependent angular energy bias. No raw 97-angle table is called qualified. Local adapters preserve these failed admission findings rather than hiding them behind smooth plots.

## Static source domains for a separate rotation interface

`python/spike_core/propulsion_pod_real_motor_domains.py` exports:

- `build_real_motor_domains(geometry,spec,trace_vertex_count=257,edge_m=.001)`.
- `p2_interface_trace(operator,domain)`.

The native rotor/PM disk ends at radius .04430 m, stator/copper annulus begins at .04450 m, and the vacuum annulus between is omitted for the separately owned analytic coupling. All physical rotor material lies inside .04420 m and all native stator/copper lies outside the stator cutoff, verified by polygon coverage. Geometry is static in its own rotor/stator frame; PM directions are fixed in the rotor frame and winding chi is fixed in the stator frame. No angle-dependent remesh is performed by this helper.

For N=257, exact uniform CCW geometric trace vertices produce 514 actual P2 trace degrees of freedom; all are retained and ordered vertex/midpoint by ideal-circle angle. The helper performs no Fourier projection and makes no unsupported mode-alias assumption. Rotor mesh: 4709 geometric vertices, 9159 triangles, 18576 P2 DOFs. Stator: 10537 vertices, 20273 triangles, 41347 P2 DOFs. All 480 physical copper-side regions and signed gauge-balanced chi survive exact constitutive grouping. Material/air interfaces and trace-edge topology are audited; outer stator vertices are tagged for zero Dirichlet conditions. Rotor interface is an outer boundary; stator interface is an inner boundary with inward radial outward-normal convention. This helper does not assemble or validate the annulus coupling.

Straight trace chords and P2 midside coordinates do not lie exactly on the ideal circle. At N=257 the worst radial error is 3.324743 micrometers; this remains explicit in each domain/trace receipt. Ideal-circle analytic coupling requires a separate trace-resolution/geometry-consistency check. Native section tessellation, field discretization, Fourier truncation, interface geometry and global energy/torque convergence are distinct gates. The root-owned Schur/annulus implementation must establish them before admitting a full-angle coupled motor run.

## Tests and release boundary

### Separated-domain rotation check (additional experimental path)

The root-authored `propulsion_pod_separated_motor.py` now couples these static
P2 domains to its Fourier annulus operator. The retained runner is
`output/promo-propulsion-pod-20261023/real_motor/run-separated-convergence.py`.
It evaluates full phase ports, actual coenergy finite differences, analytic
vacuum-gap Maxwell stress at three radii, and independent period endpoints.
No prior failed independently-remeshed angular-energy result is replaced.

The optional `repeat_rotor_sector=True` first proves the native 14-fold rotor
geometry and alternating PM-vector permutation. It clips one native sector,
then rotates its exact triangle connectivity and material identities 14 times.
The uniform ring must have N divisible by14; even N is admissible because the
root's odd-dimensional Fourier space remains strictly smaller than the full
2N P2 trace. Source-body intersections on the radial seams are welded with an
explicit 0.1nm radial-coordinate rounding tolerance; there is no material-law
or PM-source averaging. The generic unstructured domain remains the default.
An actual-source test establishes the rotated nodal permutation, exact triangle
permutation, equal scalar permeability, rotated PM vectors, and zero rotor chi.
At N1008/mode895 the computed torque period defect is about3.2e-9Nm.

For currents[1,-1,0]A and angles(.002,.012)rad, N1008/edge1mm torques are
(.415106,.531102),(.417310,.525511),(.415236,.517788)Nm for modes447,639,895.
At N2016/mode895 they become(.417965,.511156)Nm. Energy-FD torque and analytic
gap-stress torque agree with the model derivative (about1e-6Nm and1e-12Nm,
respectively); this is functional consistency, not mesh convergence.
The N2016 run recorded peak process RSS662MiB and28.6s total case time.
Critically, reducing domain edge1mm to.6mm at N1008/mode895 changes torque to
(.364269,.469640)Nm: the domain FEM error remains consequential. Numerical
motor admission and an energy-table claim remain withheld pending refinement.

The final adapter/domain suite executed18tests with zero skips in19.774s,
including the new native rotational mesh/source test. Fixtures remain derived
from the licensed source and all material/winding qualifications remain false.

Subsequent discrimination found that `edge_m` only segmentizes geometry
boundaries before constrained Delaunay triangulation. It is NOT a global
element-diameter control and supports no Richardson/order claim. Actual
per-constitutive-region maximum edge, minimum angle and maximum area are now
returned. At N1008, the stator trace-adjacent triangles originally span100--986um
radially, whereas mode895 has vacuum decay length about50um.

The optional `uniform_refinements` performs conforming red refinement internally
with green closure beside protected original trace and outer polygon edges;
it changes no polygon geometry or trace count. Refinement occurs before rotor
sector replication. Actual-source tests preserve source areas, balanced chi,
domain area and trace topology and verify that long interior air edges shrink.
An edge1mm/ref1 case changes torque to(.322301,.377276)Nm; an edge.4mm/ref1 case
gives(.297742,.357088)Nm. These large changes keep admission false. The latter
reported4698s wall time includes a machine/tool interruption; no active CPU
runtime is inferred from that receipt.

The next optional preparation, `vacuum_trace_layers_m=[25e-6,50e-6,75e-6]`,
splits ONLY source-free air beside each analytic interface. Exact polygon
intersection with the union of every native rotor/stator/copper part must be
empty for each ring. Exact radial source bounds are rotor maximum44.200000000672mm
and stator minimum44.598181830061mm; a100um layer is rejected, so no native source
is trimmed to manufacture clearance. Each trace-adjacent element now spans25um
radially. Uniform circular rings retain explicit chord geometry error and the
actual 14-fold rotor material/PM permutation. The7-test domain suite passed in
15.902s including per-material/source area preservation and crossing rejection.
This is mesh preparation for the same PDE, not a new material or torque law.

The layered N2016/edge1mm/mode895 coarse/ref1 comparison gives torques
(.400339,.484835)/(.322822,.369276)Nm, still a consequential difference.
Its nested variational oracle uses the full4x4 source response formed from
retained L,psi,C: all eigenvalues of fine-minus-coarse are positive at both
sampled angles (minimum2.69e-7; PM-source entry response about.49J).
Coenergy increases by.247101/.245704J for[1,-1,0]A. This independently supports
the conforming nested-space/source-preservation implementation; it does not
establish torque accuracy. Raw receipt: `layered-nested-variational-oracle.json`.
The final boundary-protection correction uses topological edge incidence1 in
addition to endpoint radius, avoiding protection of internal boundary chords.
Seven domain tests passed after that correction; the preceding combined
adapter/domain suite passed20tests in35.618s. Physical/numerical motor admission
remains false and no full-period interpolation table has been accepted.

### Bound iterative adaptive preparation

`refine_existing_domains(domains,marks)` adds a conforming red/green refinement
level by replaying retained native preparation and previous marking levels.
Each binding is `{'mesh_sha256':domain['mesh_sha256'],'triangle_ids':[...]} `
under both rotor/stator keys. The exact fingerprint includes nodes, triangles,
physical region labels, original geometry/specification and trace mapping.
A separate full-domain payload hash rejects altered coordinates, sources or
materials. Stale bindings are rejected at every replayed level. No arbitrary
replacement mesh is admitted. Nodes100000/triangles200000 per domain remain
hard limits during construction; the existing P2 operator limits also apply.

Rotor marks close over entire14-fold triangle orbits before subdivision.
Only topological outer/interface boundary edges are protected; all other
selected edges split and adjacent elements receive conforming green closure.
Every added node is checked against a coarse-edge midpoint with2e-12m tolerance.
Original source polygons, trace chords and material laws are unchanged, so the
coarse conforming quadratic space embeds in the refined space. With fixed
Fourier space and PM reference, the stationary coenergy is a maximum over that
space; refinement therefore makes the full4x4 source-response difference PSD.
The actual-source unit test checks this after scaling phase-source coordinates
to10A, independently of any residual-based marking indicator. It also executes
two adaptive levels, orbit/source/area preservation, stale-mark rejection and
coordinate-tampering rejection. The8-test domain suite passed in19.140s.
Indicator-guided selection is separately owned/reviewed and supplies marks,
not a certified numerical error bound.

The latest16-angle diagnostic covers the complete2pi/14 period at N2016,
edge.6mm/ref1,25/50/75um vacuum layers and mode895. Maximum|torque|=.504776Nm;
maximum energy-FD discrepancy1.003e-6Nm, analytic gap-stress discrepancy
1.934e-12Nm and period discrepancy6.58e-9Nm. Preparation112.7s/evaluation96.5s,
peak process RSS1.559GiB. This establishes discrete functional consistency
across those samples, not spatial or angular-interpolation convergence.
The same preparation at the two original angles gives mode639/895/1007
torques(.298676,.354223)/(.298786,.353716)/(.298764,.353652)Nm; spectral closure
is much improved while spatial convergence remains open.

### Independent read-only audit of adaptive attempt1

The saved3-level/4-angle/10A-hexagon attempt is independently inspected by
`output/promo-propulsion-pod-20261023/real_motor/audit-adaptive-attempt.py`.
It performs no duplicate field solve. Its receipt is
`adaptive-attempt-1/independent-geometry-source-audit.json`.
Across both refinement transitions, original nodes are exact array prefixes;
all added nodes lie within7.08e-13m of coarse-edge midpoints; every fine triangle
has a unique coarse parent and inherits its physical region and identical chi.
Maximum parent-area discrepancy is1.65e-14m2; material tables are identical.
Thus there is no observed source, nesting, seam or material-identity corruption.

At all4 retained angles, the source-response difference scaled to10A is PSD:
minimum eigenvalue at least2.23e-6J for level0→1 and2.57e-7J for1→2.
The actual PM zero-current coenergy corrections decrease from.06314--.06321J
to.0032045--.0032092J, approximately20-fold. Torque has not stabilized.

The rotor marking moves from large inner-air cells (area8.309e-5m2,
maxedge33.3mm, minimumangle8.61deg) to existing/refined inner-air slivers near
radius33.22mm (area6.24e-9m2,maxedge4.98mm,minimumangle.0574deg), then their
children (area1.56e-9m2,maxedge2.49mm,similarangle). These are not the25um
analytic-gap layers. The residual indicator uses maximum element diameter and
explicitly disclaims certified shape-regularity constants; its growth while
actual coenergy corrections shrink is insufficient evidence of a source or
field-algebra defect, and is insufficient justification for blind further
levels. Uniform4-angle sampling aliases the12 cogging harmonics within one
14-pole-pair mechanical period; these samples cannot establish angular coverage.
Spatial/torque admission remains false. No indicator was weakened or result
relabeled as converged by this audit.

### Actual two-grid field-energy identity and candidate marking

One bounded actual field audit used attempt1 domains1/2, mechanical angle.002rad,
mode895, PM-only plus all6 vertices of the balanced10A phase-current hexagon.
It recovered the4 source basis fields once per model and retained them in
`adaptive-attempt-1/two-grid-energy-audit/actual-basis-potentials.npz`.
The original dimensionless barycentric containment gate stopped postprocessing:
about0.7pm coordinate rounding on a2.5um-altitude triangle produces a barycentric
violation about1.95e-7. The independently reviewed replacement tests actual
Euclidean distance to the closed coarse triangle, with the existing explicit
2pm welding allowance and swept-area coverage allowance; strict default remains0.
No failed gate was silently waived, and its failure receipt is retained.

The completed postprocessor rebuilds P2 operators but performs NO additional
factorization or field solve. It validates the full uniform Fourier Gram matrix
(relative maximum error8.76e-14) and recovered trace projections (relative
error1.16e-13). Independently assembled source responses sumF^T Abasis reproduce
retained phase inductance/PM linkage to about1e-15 relative and zero-current
coenergy to about1e-14J. PM reference is identical28.393449056657154J.

For each state it integrates .5 depth times deltaB^T nu deltaB over fine cells
using the admitted nested-field helper, and separately evaluates the analytic
gap's coefficient-difference energy. Their sum agrees with the independently
reconstructed coenergy gain to maximum4.246e-11J (about1.3e-8 relative to the
approximately.0032J correction). Actual Euclidean outside distances are at most
7.03e-13m rotor/7.07e-13m stator; this is explicitly approximate coordinate
geometry, not an exact-arithmetic nesting theorem. Field preparation recorded
95.704s/1.143GiB peak; factorization-free completion7.344s/.899GiB peak in a
separate process. Both processes exited; no new refinement was executed.

Per-fine-cell maxima across the6 current vertices and fingerprint-bound bulk.3
candidate marks are retained. The10 rotor and13 stator marks have zero overlap
with the earlier residual-bulk marks: rotor candidates are large inner-air
cells nearR27.7mm (h16.66mm,h2/area26.7), while stator candidates lie near
R44.684mm (h.284mm,h2/area9.86). Thus this energy correction avoids the observed
extreme-sliver residual chase in this case. The marker measures enrichment,
not true error or torque accuracy. All spatial/hardware qualification flags
remain false. Raw postprocess receipt, source hashes, candidate marks and shape
comparison are retained together under `adaptive-attempt-1/two-grid-energy-audit`.

### Bounded energy-marked levels3 and4

Level3 applied the verified two-grid marks to domain2, retaining the same PDE,
Fourier cutoff895 and2016-vertex traces. Four-angle ports and4-column basis
fields were saved at(.002,.012,.279373005532,.107947060552)rad, where the latter
two use deterministic golden-fraction phases. Previous-mesh fields at the3
new angles were paired without repeating the old residual computation.
All4×7 energy identities passed (maximum defect5.243e-12J), and scaled10A
source-response increments were PSD. Total recorded successful serial runtime
was109.47s and maximum sequential process RSS1.081GiB. Candidate marks from the
pointwise maximum over all4 angles and all6 current vertices were retained.

Level4 applied only that fingerprint-bound marking. Its meshes contain
14057 rotor vertices/26096 triangles and23675 stator vertices/44438 triangles,
well inside unchanged resource gates. Field preparation/four-angle recovery
recorded42.953s/.828GiB. Subsequent field-energy postprocessing performs no
new PDE solve and has maximum identity discrepancy1.197e-11J. Actual source
response increments remain PSD at every angle (minimum scaled eigenvalue
1.408e-7J). The sampled10A phase-box torque-difference bounds are:

| Angle(rad) | Level2→3(Nm) | Level3→4(Nm) |
| --- | --- | --- |
| .002 | .012445 | .002376 |
| .012 | .008166 | .001696 |
| .279373005532 | .006856 | .001879 |
| .107947060552 | .004527 | .001546 |

Full physical linkage difference bounds at level4 are3.76--4.02e-6Wbturn.
These are sampled differences between discretizations, not bounds to the
exact solution. No convergence order, full-period accuracy or hardware
qualification is inferred from this contraction. Candidate level4 marks
(21 rotor/8 stator) remain unapplied in this record.

The newly generalized postprocessing script initially shadowed its numeric
level variable with a coarse/fine loop string; this reporting-code failure
occurred after operator reconstruction and before any correction result.
Its partial receipts are preserved, the loop variable was corrected, and all
four completed actual-field identities were rerun. No solver or physics code
changed. Level4 successful serial runtime is81.891s; failed-stage receipts add
at least8.719s overhead (not an exact total failure CPU measurement). Maximum
sequential process RSS is1.083GiB. Measured postprocess CPU times are separately
recorded, while field CPU time is unavailable for this already-started run;
future runs capture `time.process_time()` explicitly. All processes exited.
Receipts, bases, bound marks and coefficient comparisons live under
`adaptive-attempt-1/energy-marked-domain3` and`energy-marked-domain4`.

### Level5 separated spatial and Fourier checks

Level5 prepares the1007-mode Schur system once, then uses the independently
tested exact leading-subspace restriction to895 for matched spatial comparison
with level4. Both sets of actual fields and ports are retained at every one of
the4 matched angles. No1007-vs895 combined space/mesh gain is used as a pure
FEM correction: the28 two-grid energy checks use895 on both meshes exclusively.
Their maximum identity discrepancy is2.08e-12J. Source-response increments are
PSD for both spatial refinement (minimum scaled eigenvalue1.16e-7J) and the
same-mesh Fourier enrichment (minimum1.56e-9J).

The sampled10A phase-box torque-difference bounds are:

| Angle(rad) | Level4→5 at895(Nm) | Same level5,895→1007(Nm) |
| --- | --- | --- |
| .002 | .000774 | .000150 |
| .012 | .000825 | .000072 |
| .279373005532 | .000932 | .000065 |
| .107947060552 | .000869 | .000153 |

Full physical flux-linkage differences are3.39--3.53e-6Wbturn spatially and
6.03e-9--1.33e-8Wbturn for the cutoff comparison. These differences do not
certify exact-solution error or unsampled-angle behavior. Three successive
energy-marked differences are now retained, but13-new-angle validation and
angular-interpolant error remain open. No port, angular-table or hardware
qualification flag is promoted.

Level5 recorded80.143s serial wall time,175.875s aggregate process CPU time
and maximum sequential process RSS1.086GiB. The parent clarified the budget
as120s WALL/2GiB peak, with aggregate CPU measured separately. Earlier wall
figures are not retroactively called CPU measurements. The raw executed
runner/postprocessor source snapshots accompany result hashes. Level5 combined
future marks (19 rotor/6 stator) are retained and remain unapplied. All owned
processes exited after the bounded case.

Actual-source adapter tests execute four basis states/one factor, reciprocal positive full L and balanced superposition, independent edge-quadrature linkage/gauge, exact weighted torque versus fixed-potential and independently resolved perturbations, and arbitrary barycentric linear-B reconstruction. Static-domain tests execute native region counts, source/gauge preservation, all514uniform trace DOFs, chord-error metadata, straight-polygon area conservation and malformed/crossing-domain rejection. The manufactured vacuum-annulus quadrature oracle is separate from native motor solves. Missing extracted fixtures cause explicit source-dependent test skips; the recorded session executed the actual retained source fixtures.

No field/energy convergence can validate original H070 directional properties, original magnet lot/polarity, literal CAD conductor continuity, end turns, loss maps, thermal coefficients or whole-drone behavior. The user-authorized intended winding/material approximations remain explicit. Knowledgeable human numerical review is required before release.


## Broad golden-angle adaptive level 6 (retained discrete-model evidence)

The 13 golden phases plus the additional 0.012 rad diagnostic were retained exactly from the level4/5 audit. Their union is sampling evidence, not an angular error certificate. The stator scalar-material geometry is eightfold (45 degree rotation), not 24-fold; four uniformly spaced samples within the rotor period can alias cogging harmonics.

The level4/5 correction-marking postprocessor stopped its first attempt after exceeding the declared 2 GiB peak (2.278 GiB); completed numerical records were preserved. A fresh process with explicit collection of temporary triangulation cycles resumed only the missing angles. That resumed attempt completed all14 retained records in145.594 s wall,56.828125 s aggregate process CPU,0.597267 GiB peak. The maximum interior-plus-gap correction/coenergy identity defect was2.077014e-12 J. This does not erase the failed resource attempt.

The resulting broad bulk0.3 marks selected19 rotor cells (28 after exact14fold orbit closure) and6 stator cells. Native level6 preparation has14211 rotor vertices/26404 triangles and23717 stator vertices/44522 triangles; source geometry, trace, material identity and prescribed winding source are unchanged. Maximum added-node midpoint deviation is7.072e-13 m, within the declared native weld policy.

The level6 field run prepared maximum Fourier mode1007 once and restricted the same operators to895. All14 angles retain both complete four-source field bases and port coefficients. Wall54.829 s, aggregate CPU168.75 s, peak0.943855 GiB. SHA authentication checked42 current/previous/high-cutoff basis files. Level5-to6 matched895 maximum balanced10 A phase-box torque-change bound is1.2073261716302167e-3 Nm (previous broad change2.071777233362424e-3 Nm). It still fails the predeclared1e-3 Nm sampled working functional-change screen. The same-level895-to1007 cutoff change is1.5438005063500546e-4 Nm; these errors are reported separately. Spatial full-flux change bound is3.328703372308491e-6 Wb-turn, cutoff1.3340300687313745e-8 Wb-turn. Neither torque convergence, full angular adequacy, calibrated materials nor literal hardware topology is admitted.

Exact retained domain JSON SHA256: `514fedcb849ca47fbf119e7995d6136b34c55d8986557542298b123ab1e4a924`; stack depth0.025 m; prepared maximum Fourier mode1007, spatial-comparison mode895. Receipts are under `output/promo-propulsion-pod-20261023/real_motor/adaptive-attempt-1/energy-marked-domain6/`, including `receipt.json`, `broad-coefficient-comparison.json` and `retained-basis-authentication.json`. No interpolation table has been generated from this failed working screen.


The subsequent level5/6 factorization-free correction audit completed all14 angles and98 zero/hexagon-current states in132.422 s wall,152.71875 s aggregate CPU,0.604389 GiB peak, with zero new PDE solves or factorizations. Interior-plus-analytic-gap correction matched coenergy gain within8.774347e-12 J. Combined bulk0.3 next-level candidates select25 rotor and4 stator cells; these candidates have not been applied. Their summed per-cell sampled-max correction energies are0.00403127054 J (rotor) and2.05418220e-5 J (stator); these are marking quantities, not certified remaining error bounds. The audit and marks are in `energy-marked-domain6/energy-correction-marking/`. All physical/spatial qualification flags remain false.


## Level7 sampled working screen and proposed interpolation

One additional energy-marked level7 used the full14-angle level6 marks, selecting25 rotor cells (28 after14fold closure) and4 stator cells. The resulting native mesh has14295 rotor vertices/26572 triangles and23729 stator vertices/44546 triangles. The actual1007-prepared/895-restricted run completed in55.031 s wall with0.944485 GiB peak; exact aggregate CPU is in its immutable receipt. All42 basis SHA checks and28 actual field/source response identities passed (maximum absolute identity defect2.486900e-14). The minimum10 A scaled source-response difference eigenvalue is6.774994e-8 J, consistent with nested variational enrichment.

Matched895 level6-to7 maximum sampled balanced10 A phase-box torque-change bound is6.956314126944706e-4 Nm, passing the predeclared1e-3 Nm working functional-change screen. Same-mesh895-to1007 cutoff change remains1.5432397247400954e-4 Nm. Spatial full-flux change bound is2.177521987465339e-6 Wb-turn; cutoff1.336817909329069e-8 Wb-turn. This is sampled functional change, not a certified trueerror or complete angular convergence claim. Physical and spatial qualification flags remain false.

Exact level7 domains JSON SHA256 is `cba923b917736fda053952bf61dacf672c182f3b8fd8c36f15399080be71b6bb`, stack depth0.025 m, maximum Fourier mode1007. All evidence is in `adaptive-attempt-1/energy-marked-domain7/`. `proposed-interpolation-plan.json` records the previously declared128/256/512 interval ladder, common scalar-coenergy construction, measured raw endpoint periodicity, all14 retained offgrid angles,1e-3 Nm entrywise phase-box torque interpolation gate and1e-7 Wb-turn phase flux gate. This tests interpolation against this discrete model only. No heavy table generation has been executed under this plan.


## Executed nested angular interpolation (level7/1007)

The approved128/256/512 ladder executed513 unique actual angular field samples, preserving raw0 andT endpoints and all scalar ports/source evidence. Shared even knots were reused exactly; the processed-key ledger proves no repeated angular field evaluations. Each table uses one common quadratic coenergy, periodic cubic interpolation and derived flux/torque. Exact domain SHA/depth/cutoff are embedded in every table. Raw endpoint discrepancies are5.10414e-16 H,4.41158e-13 Wb-turn and2.00970e-10 J; these were measured before the existing admitted-roundoff periodic closure.

128 intervals failed the14 retained-field offgrid torque gate (3.235562e-3 Nm), although flux passed (9.601398e-9 Wb-turn). 256 passed those offgrids (2.422700e-4 Nm,7.320301e-10 Wb-turn), but the1025-angle128-versus256 comparison exceeded the torque screen (3.395994e-3 Nm). This measured failure justified the512-level run. Final512 offgrids pass at3.145568e-5 Nm and4.343160e-11 Wb-turn; dense1025-angle256-versus512 differences pass at3.282743e-4 Nm and8.253401e-10 Wb-turn. Torque bounds use the predeclared full10 A phase-box entrywise bound; flux bounds use the largest phase row sum. The whole-interval Bernstein balanced-inductance certificate passes with minimum1.95651199e-5 H.

Three serial numerical chunks used80.734/92.860/142.531 s wall,314.515625/363.546875/554.96875 s aggregate CPU, and maximum927772672 bytes peak working set. Entire study totals316.125 s wall and1233.03125 s aggregate CPU; it is not represented as one180-second study. Each chunk separately met180 s wall/2 GiB. Source/operator hashes were pinned before sampling and checked unchanged on restart.

Final table: `adaptive-attempt-1/energy-marked-domain7/angular-table/table-512.json`, SHA256 `f9d83d98f41e6412abb5dffb8cf2384caba52cb2cc2c69ea4021eb5f92d42e03`. `final-interpolation-evidence.json` records raw sample ledger, exact hashes, gates, resources and port diagnostics. This passes the declared sampled discrete-model interpolation working screen only. No true PDE error certificate, full-angular continuum certificate, calibrated material qualification, literal conductive-topology repair or hardware validation follows. All corresponding qualification flags remain false. The retained source bases can supply actual field snapshots independently of the scalar interpolation.


## Retained-model motor constant plausibility audit (no fit)

A4096-point read-only evaluation of the retained512 table computes physical backEMF from `e = omega_mech * dpsi/dtheta`, after balanced projection removing common mode. Fundamental phase RMS backEMF constants are0.064973/0.065004/0.065002 V/(rad/s); line-line RMS are0.112556/0.112606/0.112551. Harmonic distortion of balanced PM backEMF is about2.07-2.08 percent. Fundamental-aligned balanced sinusoidal currents produce mean PM torque0.1949784 Nm per phaseArms (phase RMS deviations below0.031 percent); unrestricted balanced waveform optimum under the same aggregate RMS norm is0.1950204. The corresponding per-phase peak-current coefficient is0.13787 Nm/Apk. Cogging torque averages zero and peaks at0.459809 Nm; angle-dependent inductance/reluctance torque remains a separate term.

The datasheet explicitly labelsKt0.13 Nm/Arms. Under that same phase RMS interpretation the uncalibrated linear model coefficient is49.98 percent higher: a consequential physical plausibility discrepancy, not a numerical convergence success. No coefficient is rescaled to force agreement. The table is only admitted within the declared10 A phase-current envelope; these linear coefficients are not evidence of saturation/continuous-rating behavior at61/138 Arms.

ModelKv is84.80-84.84 rpm per line-line fundamental RMS volt, or59.96-59.99 rpm per ideal linear-SVPWM DC-bus volt at zero resistive/inductive drop. Other phase/peak conventions differ and are retained in `datasheet-constant-convention-audit.json`. DatasheetKv74 rpm/V does not specify its voltage convention in the retained source. DatasheetKt andKv nearly satisfy the simple scalar `60/(2piKv)=0.129045` relation, but that scalar relation does not identify threephase line/phase/peak/RMS/DC-bus conventions. Interpreting datasheetKt as sinusoidal phaseArms would imply127.23 rpm/line-line-RMS-volt or89.97 rpm/DC-bus-volt under ideal linearSVPWM. The undefinedKv convention prevents a unique direct quantitativeKv comparison. Relabeling the explicitArms unit as peak current is not justified.

This mismatch reinforces the already explicit substituted isotropicmu_r200 steel, uncalibratedBr/recoil and intended-winding-topology assumptions. Directional saturation and calibrated magnet properties remain absent. The audit uses no new PDE solves or parameter fitting and establishes no hardware qualification; exact retained table and source-text hashes accompany the small output receipt.


## Retained steel-flux diagnostic

A no-solve diagnostic reconstructed the actual1007 P2 basis at0.002 and0.08293635224512971 rad for zero winding current (PM sources remain active) and all six balanced10 A hexagon vertices. Operators were rebuilt sequentially per domain without LU. Runtime4.172 s wall/4.0625 s CPU, peak259534848 bytes; no PDE solves or factorizations. Exact domain/basis hashes, solver-region identities and linear materialmu_r200 are in `steel-flux-diagnostic.json`.

At zero winding current, rotor steel area-weighted3-point-Gauss medianB is2.541-2.543 T,95th percentile3.369-3.370 T and99th percentile4.247-4.269 T;79.49-79.58 percent of quadrature-weighted rotor area lies above the illustrative2 T marker. Stator zero-current median is1.474-1.493 T,99th percentile2.806-2.825 T;24.28-26.61 percent lies above2 T. Across all tested10 A currents, rotor element-side vertex maximum reaches7.089 T and stator15.339 T. Vertex maxima can reflect corner singularities/local discretization and are not bulk field values. The bulk percentile/fraction results independently show that the linear model samples strong-flux ranges even before winding current is applied.

Thresholds1.5/1.8/2.0/2.2 T are declared diagnostic markers, not a substitute for directional H070-20 B-H data or a saturation criterion. Area fractions/percentiles are three-point Gauss sample estimates of the continuous P2-gradient field, not exact superlevel-set integrals; interface B is not averaged across element sides. These results flag substantial material-model plausibility risk. They do not establish a causal explanation of the torque-constant mismatch, validate nonlinear behavior or qualify hardware. A converged solution of this linear constitutive model remains different from a validated physical motor.
