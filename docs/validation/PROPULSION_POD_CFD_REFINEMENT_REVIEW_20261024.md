<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent geometric derivation for localized pod tetra refinement

This derivation was written by the integration owner before inspecting the
new refinement implementation. The implementation author is a separate agent.
It establishes a geometric construction and polynomial initial-guess transfer,
not CFD error control or load convergence. Implementation review and executed
oracles are recorded separately below when available.

## Partition and boundary conformity

Let a positively oriented nondegenerate parent tetrahedron have vertices
v0,...,v3, volume V, and barycentric coordinates lambda0,...,lambda3.
Its centroid g has coordinates (1/4,1/4,1/4,1/4). Child i is the convex
hull of g and the three original vertices other than vi.

For any parent point, choose i attaining min(lambda). Set t=4*lambda_i and
mu_j=lambda_j-lambda_i for j!=i. Then t and all mu_j are nonnegative,
t+sum(mu_j)=1, and x=t*g+sum(mu_j*vj). Thus the children cover the parent.
Child i consists precisely of points where lambda_i is minimal; interiors
of distinct children cannot overlap, and ties lie on their shared facets.
Multilinearity of the oriented determinant gives child volume V/4 when g
replaces vertex i in the original ordered tuple. This construction adds
one interior vertex and three net cells per selected parent.

On the original face opposite vi, lambda_i=0 and t=0: the entire original
triangle remains one child face. Every original exterior/shared face is
therefore retained without subdivision. Refining one side of an original
interior face creates no hanging face or edge on the neighbouring parent.
New edges connect g to an original vertex, and their open interiors lie
strictly inside the parent. Selection of adjacent parents is also conforming.

The same partition argument works for any strictly interior g with positive
barycentric coordinates alpha: choose i minimizing lambda_i/alpha_i, then
t=lambda_i/alpha_i and mu_j=lambda_j-t*alpha_j. This matters because a
floating-point computed centroid need not be the exact real centroid. Actual
strict containment, positive determinants, volume accounting, condition and
global intersection/topology checks remain necessary. The algebra is not a
license to waive those checks or manufacture a geometric tolerance.

Primary geometric reference actually read: CGAL **6.1.1**, official
[`Triangulation_3::insert_in_cell`](https://doc.cgal.org/6.1.1/Triangulation_3/classCGAL_1_1Triangulation__3.html),
section at lines1194-1207 on23October2026UTC. It specifies four-cell subdivision
and strict interior-point preconditions. No CGAL implementation was copied;
the partition and conformity argument above is independently derived.

## Polynomial transfer is an initial guess

On a straight tetrahedron the existing P2 scalar shape functions are
lambda_i*(2*lambda_i-1) at vertices and4*lambda_i*lambda_j at edge midpoints.
They have the Kronecker property at the ten P2 nodes. There are ten independent
quadratic monomials in three dimensions; these ten nodal functions form a basis.
Restricting an old quadratic to an affine child remains a quadratic. Evaluating
the old polynomial at all child P2 nodes therefore reproduces it exactly in
real arithmetic. Apply this independently to each velocity component. P1
pressure restriction follows identically from its four barycentric shape
functions. New nodes internal to a parent cannot create cross-parent trace
ambiguity on a valid conforming old mesh. Existing shared trace values remain
unchanged.

For a general interior split, child i has volume V*alpha_i and
p(g)=sum(alpha_i*p_i). Exact P1 integration gives

```
sum_i (V*alpha_i/4) * (p(g) + sum_{j!=i} p_j)
    = (V/4) * sum_j p_j.
```

Thus the physical pressure integral is preserved in real arithmetic. The new
algebraic pressure scaling and normalized gauge vector may differ; recompute
their actual mean/residual instead of assuming numerical identity. Field
evaluation and containment roundoff require source-bound executed checks.

Preserving the continuous velocity and pressure polynomials does **not** make
them a new discrete solution. Newly available velocity/pressure test functions
can expose nonzero residuals. SUPG tau depends on cell geometry, and its
quadrature nodes change, so neither the discrete stabilized operator nor its
work is invariant. Weak load extraction can also differ between extensions
until the new free residual is solved. Direct Cauchy stress on unchanged
boundary facets should agree for exact restriction at equal quadrature, but
that is a transfer check, not a refined-solution load result.

## Admission boundaries

The intended first marker set selects internal/bulk support cells from a saved
torque-gap diagnostic. Some marked centroids lie beyond the propeller radius;
they are not automatically wall cells. The construction improves no original
boundary triangle's tangential resolution and does not establish a boundary
layer mesh. Indicators are not certified error bounds. Thirteen selected
parents changing10602cells to10641 cannot be presented as a uniform-grid
refinement/GCI ladder. Source geometry, actual positive volumes/condition,
full intersections/topology, pressure kernel, nonlinear residual, energy,
continuity, raw/weak traction and domain/load convergence gates remain intact.

## Implementation review and separate owner-layout oracle

Subsequently inspected implementation SHA256
`b5ff47e5cdd86c12ef3ab7348d8501e088fb68e6ab9f0779ba7b2119d3f277ca`
and its five focused tests. The implemented replacement/appending order and
parent map match the construction. Original vertices and patch triangles are
copied unchanged. Transfer maps canonical old edge pairs to new owner-layout
DOFs; it does not assume old P2 edge numbering survives inserted vertices.
Candidate status, source/refined mesh hashes and unsolved-field markers remain
distinct from full geometry/pressure/flow admission.

Executed a separately authored Cartesian polynomial oracle using the actual
`SymmetricStokes` owner constructor for old/new P2 layouts and bilinear forms.
A stub factor interface supplies no numerical factorization and no solve is
called. For a sheared translated six-tetrahedron box with two selected parents,
transferred velocities and pressures agreed with direct Cartesian evaluation
within8.88e-16 in their SI units. New-cell velocity gradients agreed within
6.42e-15 /s; pressure-volume integral difference was0 Pa m3; symmetric viscous
bilinear-form difference was2.14e-14 W. Both actual owner node/connectivity
layouts matched exactly. These are independent small-fixture transfer checks,
not a new pressure-kernel or PDE validation.

Oracle script and versioned receipts are under
`output/promo-propulsion-pod-20261023/inertial_cfd/`:
`independent_refinement_owner_oracle.py`,
`independent_refinement_owner_oracle-b5ff47e5cdd8-834bf001c41d.json` and
`independent_refinement_owner_oracle-51ec9615f008-834bf001c41d.json`.
The latter two were actually executed against the preserved initial source and
the hardened current source respectively. Receipt filenames bind both helper
and oracle source hashes; reruns no longer replace a different-source receipt.

Review found unconditional float conversion could discard imaginary parts or
coerce bool/object values. The author closed this by requiring original real
numeric dtype before conversion. The owner inspected the fix and reran six
focused tests, including complex/bool/object rejection. Current implementation
SHA256 is
`51ec9615f00814482a758ca9a754ccdd13024d31b8b0b6f5c3a4f9de88ee8919`.
The independent owner-layout oracle passed unchanged on both versions; actual
float candidate outputs also retained byte identity in the separate author's
dtype-hardening equivalence receipt.

The actual 10641-cell destination passed the unchanged complete geometry
validator separately in 109.932 s wall / 108.125 s CPU, with sampled extra peak
RSS 222.02 MiB, 946100 candidate pairs, 7594400 SAT axis tests and 722575 exact
predicates. Maximum cell condition was 9325.4523. Exact predicate screening
does not qualify nonshared zero-measure contacts. Receipt:
`centroid13-refinement-20261024/destination-admission-receipt.json` under the
same output directory. This invocation used the preserved initial helper
source and did not reuse an old source-admission result. The earlier bounded
240 s double-admission timeout remains failed/incomplete; neither it nor the
helper's strict double-admission path is reported as successful.

The subsequent unchanged owner pressure-kernel preflight also passed on this
actual destination: 3552 pressure / 23994 free velocity DOFs; exactly one
numerically small mode, constant-pressure/gauge alignment 1.0; eigenvalues
5.904084e-19 and 5.442266e-6 against zero threshold 3.194818e-13. Maximum
relative eigen residual was 4.009711e-16; the first nonzero residual interval
was separated. Existing full geometry/operator preparation was repeated under
the then-current source snapshot, without reuse of prior geometry proof.
Source hashes before/after matched. Total externally bounded wall time was
389.058 s inside 420 s / OS-enforced 2 GiB, with thread environment set before
scientific imports. Receipt:
`centroid13-refinement-20261024/pressure-kernel-20261024/pressure-kernel-evidence.json`,
SHA256 `3ad528d070d9e6bfafa4704fa6dcb1946599255f29364e35ba0be3eb7c6c8aca`.

This numerical small-mode check is not a uniform inf-sup proof. The callback
stopped before velocity factorization; no nonlinear flow, energy or
load-convergence result was established by that preflight. The transferred
field was still an unsolved initial guess at that point.

## Subsequent fixed-auxiliary-density solve

The separate output-only `fixed-aux001-v20` study then solved this destination
at rho=0.001225 kg/m3, mu=1.81e-5 Pa s, Omega=200 rad/s, preserving the source
surface, boundary conditions and outer domain of the coarse v12 0.001 case.
It used isolated v20 owner snapshots and the explicit signed current-Schur
policy; full geometry and pressure-kernel checks were repeated. The transferred
initial residual was 0.2904315, correctly requiring a new solve. Six Newton
steps reached relative nonlinear residual 2.434708e-10 and energy residual
2.41757e-13. Source/input hashes stayed unchanged. Total external wall time
was 665.06 s inside 900 s / OS-enforced 2 GiB; peak private commit was about
1.747 GB. This is a passed fixed auxiliary study, not an accepted actual-air
continuation stage.

Weak torque changed from the matched coarse result by -16.014 percent to
0.000376890884 N m; thrust changed -22.783 percent to 0.000509081916 N.
Raw Cauchy torque changed -2.056 percent to 0.00006556362068 N m. The relative
weak/raw torque gap remains 82.604 percent, versus 85.083 percent coarse.
Thirteen refined bulk parents therefore have material influence on the weak
load and do not establish load convergence. Neither the small cell-count
increase nor this one comparison is a near-wall, uniform-grid or GCI study.

Result under the same output tree:
`centroid13-refinement-20261024/fixed-aux001-v20/fixed-auxiliary-result.json`,
SHA256 `66dad51007d72e5e243bb23f85f60ab748c1c8a82cbe40a35294bba4ace59338`.
Accepted fixed-auxiliary field file SHA256 is
`635f7527114e85f66bb81bf30badb04b58fde66361ca1ff506117f0f12744256`.
# Independent whole-edge-star design review, 24 October 2026

This addition precedes inspection of the new edge-star implementation. The
integration owner read CGAL 6.1.1's `insert_in_edge` and `insert_in_cell`
member descriptions and preconditions, lines 1194--1234 of the
[Triangulation_3 reference](https://doc.cgal.org/6.1.1/Triangulation_3/classCGAL_1_1Triangulation__3.html).
That is a topological construction reference, not an imported dependency,
implementation, quality bound or physics validation.

For an oriented tetrahedron (a,b,c,d), insert the exactly represented midpoint
m=(a+b)/2 and use (m,b,c,d), (a,m,c,d), preserving original vertex slots.
By determinant linearity each signed volume is half the parent. In parent
barycentric coordinates the first child satisfies lambda_b>=lambda_a and the
second lambda_a>=lambda_b. Their interiors are disjoint and their union is the
parent. Refining every incident tetrahedron replaces both owners of every
face containing the edge by identical two-triangle partitions. Faces not
containing the edge remain unchanged. Cell-disjoint selected stars cannot
introduce mismatched refinement across their shared faces: a face containing
a selected edge would have placed both owners in that star already.

A boundary triangle containing the edge splits into two coplanar, equally
oriented half-area triangles; its underlying support is unchanged. Floating
midpoint rounding is not automatically coplanar. Check equality to the exact
rational average of the binary64 endpoints before use, reject coincidence with
an existing or another inserted vertex, retain original points, and update all
boundary/parent identities. Complete-star, positive-volume, condition,
topology, overlap/SAT and patch checks remain required; the partition argument
alone does not qualify an initially unqualified contact or geometry.

Wall height h=3V/area is unchanged by this tangential split because volume and
wall area both halve. An additional strictly interior centroid split of the
wall-adjacent child reduces that child's wall height by its actual barycentric
opposite-face weight (ideally one quarter). These operations resolve different
directions. Untouched triangle sides prevent a claim of uniform diameter
reduction or a Richardson/GCI ratio, and a 16-edge local patch cannot establish
whole-blade load convergence.

Old piecewise P2 velocity/P1 pressure functions restrict to the nested children.
Use the actual owner's global edge numbering. A split midpoint becomes a new
vertex whose velocity is the old edge DOF; its pressure is linear endpoint
interpolation. Surviving edges preserve canonical-pair identities, and other
new edge DOFs are evaluations of the old polynomial in a containing parent.
Continuous shared-face traces agree, while arbitrary piecewise polynomials
need separate parent-aware checks. Pressure integrals and weak viscous forms
are invariant in exact arithmetic for the same transferred fields, not for a
new solution in the enlarged test space. SUPG cell scales and quadrature change.

The author's inventory proposes 16 exact-midpoint, cell-disjoint rotor-edge
stars: 32 parents, 32 wall faces, 1.702 percent of rotor area. Predicted counts
are 10634 cells/3555 P1 vertices for tangential-only and 10826/3619 for the
paired wall-normal candidate. These are design counts and a geometric heuristic,
not constructed/admitted meshes or an error estimator. Implementation review,
independent transfer/topology execution, actual candidate admission and PDE
comparisons are pending. No source/load qualification is promoted here.

The integration owner subsequently inspected the complete edge-star construction
and transfer implementation SHA256
`2143826c7b15779bbe894e00cde6af1ad93c63adfcefb3f7faf1075ba588dcde`.
The complete-star, cell-disjoint, named-patch, exact-midpoint, coincident-vertex
and preallocation guards agree with this derivation; source data is copied
before construction. A separately authored dyadic sheared/translated cube
oracle used the actual owner DOF and weak-operator layouts, with factorization
stubbed and no PDE solve. Six source tetrahedra became eight after one complete
boundary-edge-star split. P2 velocity, P1 pressure and pressure-volume integral
errors were zero; gradient error was 1.33e-15/s and symmetric viscous-form
difference 4.00e-14 W. Full small-fixture source/destination geometry admission
passed. The source-bound script/receipt are
`output/promo-propulsion-pod-20261023/inertial_cfd/independent_edge_star_owner_oracle_20261024.py`
and the adjacent receipt ending `2143826c7b15-cbea78759aef.json`.
This independently executed small transfer check does not admit the actual
blade candidate, establish its pressure kernel or resolve its load error.

