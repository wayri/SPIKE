<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental rotating-blade inertial CFD â€” 23 October 2026

This owner implements actual incompressible laminar inertial flow with moving
no-slip blade boundaries in a constant-speed rotating frame. It is neither BEM
nor a prescribed torque/body-force replacement. It is **not yet a mesh/domain/
physical-regime qualified real-air propeller load**. The separate creeping-flow
owner retains its Re<=0.1 gate; this implementation adds and verifies the
inertial terms rather than relabelling that owner.

## Equations, units and frame

All solver geometry is in metres; velocity m/s, density kg/m3, dynamic viscosity
Pa s, angular speed rad/s, pressure Pa, forces N, moments N m and powers W.
Original ENOLA STL files use mm and are explicitly divided by1000 for solver
coordinates. No silent size fitting is performed.

Let x=Q(t)y, dQ/dt=Q[Omega]cross, and absolute physical velocity U(x,t)=Q u(y)
for a steady rotor-coordinate field and constant angular velocity Omega. The
material acceleration expressed in rotor coordinates is

`((u - Omega cross r).grad)u + Omega cross u`, r=y-origin.

Set w=u-Omega cross r. The governing momentum equation is

`rho[(w.grad)u + Omega cross u] - div(sigma) = f`,
`div(u)=0`, `sigma=-p I + 2 mu D(u)`.

Since D(Omega cross r)=0, this is equivalent to the relative-velocity equation
with both2Omega cross w and Omega cross(Omega cross r). It is not a fixed-blade
inertial solve with the rotational terms dropped. No unsteady fluid derivative,
changed-speed Euler acceleration, turbulence/transition, compressibility or
fluid total-energy equation is owned. Independent quasi-steady trials at
separate speeds do not form an unsteady stored-fluid-energy model.

For the public rotor trial, blade absolute velocity is Omega cross r and the
stationary cylindrical far boundary is absolute u=0. The axis, cylinder radius,
half-length and origin are explicit. Exterior vertices must match the declared
coaxial cylinder/caps. Linear triangles facet the cylindrical boundary; exact
rotation tangency between vertices is a geometric approximation requiring
refinement. Rectangular outer walls are rejected by the public rotor wrapper.
Generic manufactured-test boundary data remain supported by the internal
class, with the correct explicit boundary kinetic flux.

## Conforming discretisation and nonlinear solution

Velocity is continuous quadratic P2 and pressure continuous linear P1 on
positive, manifold, overlap-screened tetrahedra. Full symmetric stress is
retained, not vector-Laplacian pseudo-traction. The pressure has a volume-mean
zero gauge. The viscous matrix is the established symmetric-stress owner; its
new optional solver/resource parameters preserve previous defaults.

The inertial weak form uses the skew convective volume term

`c(w;u,v) = rho/2 integral[(w.grad)u.v - (w.grad)v.u]`

plus `rho/2 integral_boundary(w.n)u.v`. Integration by parts gives the
advective form plus `rho/2 integral div(w) u.v`. Continuous incompressibility
makes this correction zero. P2/P1 only imposes weak incompressibility; therefore
this finite-mesh Temam correction is explicitly measured and is not hidden as
physical fluid heating. The angular cross-product matrix is skew and its
self-work is zero.

Newton differentiates both transported and transporting velocity, rotation and
boundary consistency flux. A backtracking line search must reduce the actual
nonlinear residual. Scaled momentum/continuity residuals remain admission
checks. A failed linear or nonlinear solve raises rather than returning a
completed field. The linear method uses restarted GMRES, an ILU of the current
velocity block, and the pressure-mass/gauge block. The Stokes start uses the
same strategy with the viscous velocity block. No pressure penalty or altered
physical momentum equation is introduced by this preconditioner.

At the 3000-tet reference, a read-only comparison of block ILU with the previous
monolithic LU used~2.0M versus19.9M factor entries. GMRES needed149iterations,
2.61s, relative residual9.2e-11 and relative state difference2.3e-9. This is a
single measured comparison, not a universal performance claim. Updating the
velocity ILU for each Oseen/Newton block was necessary: the initial fixed
Stokes-only preconditioner failed the nonlinear linear-residual gate at the
Re~9 blade reference. That failure was retained before the corrected run.

## Residual-consistent SUPG option

`stabilization='supg'` adds only the momentum streamline residual term

`S(v)=sum_elements integral tau (w.grad v).Rm`,

`Rm=rho[(w.grad)u+Omega cross u] - mu[Delta u+grad(div u)] + grad p - f`.

The full constant P2 shape Hessians are retained:
vertex `H_i=4 g_i tensor g_i`; edge
`H_ij=4(g_i tensor g_j+g_j tensor g_i)`.
Omitting second derivatives as for a P1 element would be incorrect here.
Pressure gradient, rotation and supplied manufactured force also enter Rm.
No PSPG term is added to the inf-sup P2/P1 pair.

The implemented smooth steady blend is

`tau = [(2|w|/h)^2 + (12 nu/h^2)^2]^(-1/2)`, `nu=mu/rho`.

The declared research length h is the minimum tetra altitude,
`1/max_i |grad lambda_i|`, fixed by geometry. It gives the finite zero-speed
limit h^2/(12nu). It is a conservative anisotropic geometric choice, not a
qualified P2 wall-model or a claim that the published P1 constants transfer
without refinement. The full Newton derivative includes tau's derivative
`d tau/d w = -4 tau^3 w/h^2`, changes in the SUPG test weight, both advective
velocity occurrences, the symmetric viscous Hessian and pressure coupling.
Thus no undocumented lagged-tau Jacobian is used.

The default four-point-per-coordinate Duffy volume rule exactly integrates the
degree-five Galerkin transport polynomials. SUPG has a nonpolynomial tau and is
quadrature approximated. Explicit orders4,5,6 are supported; nonexact cubic
manufactured checks use order6 also on boundary triangles so higher-degree
forcing/work terms are not aliased by the lower rule. Quadrature convergence
for a real high-Re geometry remains separate from the method checks.

## Energy and load evidence

With B_ij=integral q_i div(v_j), the assembled finite-mesh boundary reaction is
`r=K u+C(u)u+S(u,p)-B^T p-F` at Dirichlet nodes. Free entries satisfy the
nonlinear momentum residual. Its exact algebraic ledger is

`Pboundary + Pbody = Pvisc + Ptransport + PSUPG - p^T B u`.

Viscous power is the actual symmetric-stress dissipation. Transport self-work
equals the explicitly integrated boundary kinetic flux. SUPG work need not be
nonnegative because Rm includes pressure, viscosity, rotation and body force.
It is reported separately and **must not be deposited as physical viscous
heat**. The uncorrected advective energy difference
`rho/2 integral div(w)|u|^2` is separately recorded. Small weak continuity
residual does not imply that this physical energy correction is negligible.

Rotor torque uses the consistent moment of the finite-element boundary loads;
shaft power is Omega dot rotor moment. Recovered Cauchy surface stress from
actual gradients/pressure is independently integrated and reported. Corrected
weak work closure alone is not traction validation. Every public result retains
`load_qualified=false` and `production_qualified=false` while mesh, recovered
traction, outer-domain and physical-regime studies remain open.

## Independent analytical checks actually executed

The new inertial suite initially passed6tests, including full transport-Jacobian
finite differences, degree-five quadrature, exact rotating quadratic
manufactured velocity/pressure, no-slip blade density-to-zero Stokes limit,
resource admission and deterministic broadphase pair equivalence. The prior
six creeping-owner tests also passed after the resource/linear-factory changes.
The updated ten-test inertial suite plus the separate bordered-Schur oracle
passed together (11tests,19.414s) on23October2026 after the fixed-forcing
change. This includes SUPG Jacobian/strong-viscosity/MMS refinement checks
and the faceted-cylinder side-interior-node admission case. These are
verification cases, not full-speed blade-load validation.

The exact quadratic manufactured field is
`u=(a x^2,-2a xy,0)`, `p=beta(x-.5)`, Omega=Omega e_z,
with a=.2,mu=.3,rho=1.2,Omega=.4,beta=.1 on the unit cube. Its independently
derived force is

`f_x=rho(2a^2 x^3+4a Omega xy)-2mu a+beta`,
`f_y=rho(2a^2 x^2 y+a Omega(3x^2-2y^2))`, `f_z=0`.

SUPG/order6 gives nodal velocity error2.1e-14, physical strong residual
L2~7.9e-13, SUPG power~-9e-16W and complete work residual4.25e-15.
A randomized combined velocity/pressure SUPG Jacobian difference is4.17e-10.
An independent non-divergence-free polynomial test of the strong residual
checks that both Delta u and grad(divu) are included (it does not claim an
incompressible solution for that helper-only test).

The nonexact cubic manufactured field supplied independently by the reviewer is
`u=(a x^3,-3a x^2 y,0)`,
`p=beta(x-.5)+gamma(y^2-1/3)`, gamma=.07. Its force is

`f_x=rho(3a^2 x^5+6a Omega x^2 y)-6mu ax+beta`,
`f_y=rho(3a^2 x^4 y+4a Omega x^3-6a Omega xy^2)+6mu ay+2gamma y`.

| Tetrahedra | Velocity L2 | Pressure L2 | SUPG work fraction |
| --- | --- | --- | --- |
| 48 | .00205037 | .0189786 | .000260679 |
| 162 | .000554180 | .00501015 | .0000675716 |
| 384 | .000226143 | .00195695 | .0000234313 |

These are approximation and numerical-ledger checks with prescribed analytic
boundary data, not wind-tunnel or propeller validation. Full requests and
results are retained in the owned `output/.../inertial_cfd/` directory.

## Bounded blade and resource observations

An original60mm-span twisted-plate reference was actually solved at nominal
tip Reynolds numbers~.9,9,45,90, using mu=.001Pa s,rho1kg/m3 and speeds
1,10,50,100rad/s. These fluid/geometry assumptions differ from the real300mm
air propeller. The completed public Re_tip9.2598 case retains request, complete
fields and result: torque1.6624285905e-6N m, thrust3.7298886255e-6N,
shaft power1.6624285905e-5W, nonlinear residual2.77e-13,
work residual3.08e-14. The advective continuity correction is~.052% and the
weak/recovered torque gap39.35%; its loads are not qualified.

Stokes inspection of that original geometry with stronger near-wall/global
resolution gave:

| Tets | Weak torque N m | Recovered torque N m | Relative gap |
| --- | --- | --- | --- |
| 3000 | .000150492820 | .0000893481120 | 40.63% |
| 6456 | .000147734509 | .0000902764264 | 38.89% |
| 30564 | .000138626057 | .000103624595 | 25.25% |

The last case used267GMRES iterations,33.76M ILU entries,184s total,
peak working set1.96GB and peak private commit4.32GB. Its geometry screening
performed592094candidate pairs,4755806axis tests and573536exact predicates.
It required an explicit60M-entry experimental case budget, not a blanket
increase to the public30M factor budget. A241k-tet Python P2 solve was therefore
not launched without a new measured resource strategy. Far-domain expansion
at fixed coarse topology changes both domain and far mesh; that exploratory
record is not an isolated domain-convergence proof.

## Geometry provenance and source-mesh investigation

Source: ENOLA/Universitat Politecnica de Valencia,
DOI[10.5281/zenodo.20111572](https://zenodo.org/records/20111572), v1,
CC-BY-SA4.0. The selected `CASALINO_D30cm_pitch+5deg.stl` SHA256 is
`4659b1f740d6e2ea30819b7a2ce3cdddd54703600ff0d0919d0529ff1db62afd`.
It has35744triangles,17868vertices, no zero-area facets, coherently oriented
2-owner edges, Euler characteristic-4 and signed solid volume24.507802cm3.
Edge closure does not establish absence of global self-intersections.
The bounding box is xÂ±15.548571mm,yâˆ’1.302941..21.433569mm,zÂ±150mm.
Shaft+y is the explicit meshing interpretation; source mounting/flow context
must still match any experiment used for comparison.

Native ordinary Delaunay fluid meshing succeeded but created one exact
zero-volume tetra wholly in the planar hub cap y=0. Native Netgen optimization
retained an invalid near-coplanar cell. Neither cell was deleted to bypass the
gate. A classified-surface remesh encountered parameter-space curve
intersections and was stopped without presenting a completed mesh.

The alternate native HXT kernel resolved the degeneracy on the unchanged
source surface:241771tets,49271nodes, all positive volumes,
max cell condition613573 below the existing1e6 gate, and total fluid
volume.557927936586m3 in the450mm-radius/900mm-length outer cylinder.
This is actual retained meshing evidence; no flow solve or convergence claim
follows from it. Raw SI arrays, native mesh and quality evidence are retained.

Installed VTK9.5.2 `vtkDecimatePro` is used for explicitly adapted simulation
surfaces, preserving topology with splitting off,30deg feature handling and
native accumulated error control. Its error parameter is not called a
Hausdorff certificate. A separate bidirectional distance check recursively
covers every triangle: distance to a fixed surface is1-Lipschitz, so for a
triangle centroid c and max vertex radius eta,
`sup_triangle distance <= distance(c,target)+eta`. A failing sample or query
budget exhaustion fails the bound; it is not converted to a sampled success.
Native nearest distances are floating-point computations with an explicit
1e-7mm margin, not interval-arithmetic certification. Derived surfaces remain
CC-BY-SA4.0 with source attribution, modifications and no endorsement stated.
Geometry distance, topology, volume, feature/thickness and force convergence
are distinct checks. Coarsening itself never promotes a load to qualification.

## Primary method references and clean-room statement

* NASA Glenn, [Navierâ€“Stokes equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/navier-strokes-equation/), governing conservation context.
* NASA Wind-US [ROTATE keyword](https://www.grc.nasa.gov/www/winddocs/user/keywords/rotate.html), rotating-frame modelling context and warning that merely imparting rotating grid velocity is not a high-speed rotating-frame model.
* Ansys Fluent2025R2, [moving-reference-frame equations](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/flu_th/flu_th_sec_rotate_equations.html), absolute/relative formulation context. The explicit transformation above is independently derived; no implementation was examined or adapted.
* Tezduyar, Mittal, Ray and Shih1992, CMAME95:221â€“242, [primary author-hosted paper](https://www.tafsm.org/PUB_PRE/jALL/j28-CMAME-PSPG.pdf), DOI10.1016/0045-7825(92)90141-6, equations11â€“20 for residual-consistent stabilization. Its P1 equal-order validation is not adopted as evidence for this P2 rotating-blade case.
* FEniCS Project [Taylorâ€“Hood Stokes method documentation](https://docs.fenicsproject.org/dolfinx/v0.9.0/python/demos/demo_stokes.html), conforming mixed-space context.
* VTK [DecimatePro API](https://vtk.org/doc/nightly/html/classvtkDecimatePro.html) and [implicit closest-surface distance API](https://vtk.org/doc/nightly/html/classvtkImplicitPolyDataDistance.html), native tool operation only; no vendor source was copied.

All new numerical assembly, derivations, manufactured forcing, broadphase,
checks and prose are independently authored. Installed Gmsh/VTK are optional
local geometry tools, not redistributed solver implementations or qualified
runtime dependencies. Independent agent review is recorded separately in
`PROPULSION_POD_REAL_DATA_AND_REVIEW_20261023.md`. Knowledgeable human numerical
review remains mandatory before release. Real full-speed air predictions,
transition/turbulence and conjugate cooling remain open until supported by
appropriate numerical and physical validation.

## Same-case pressure-preconditioner experiment

The actual adapted ENOLA mesh has10733 tetrahedra. At fixed200rad/s,
rho_target=1.225kg/m3 and mu=1.81e-5Pa s, density continuation v3 accepted
only rho/rho_target=1e-6, with nonlinear residual4.046e-15. The next stage
and its reduced step exhausted4000 GMRES iterations. The last true linear
relative residual was1.670e-9, but GMRES had not reached its requested1e-11.
The existing acceptance rejected it. This is not a full-air solution.
Exact source snapshots, failure and accepted auxiliary fields are retained
under `output/promo-propulsion-pod-20261023/inertial_cfd/air_omega200_coarse005_v3/`.

An optional fixed SIMPLE pressure-graph preconditioner is independently
implemented in `propulsion_pod_inertial_cfd_schur.py`. For scaled saddle
matrix `[A,C^T,0;C,0,g;0,g^T,0]`, approximate the positive Schur operator by
`S=C diag(A_Stokes)^-1 C^T`. The positive Stokes diagonal is fixed, even while
the velocity ILU is updated between Newton steps. Factor the complete
bordered matrix `[-S,g;g^T,0]`. Its action on arbitrary rhs is:

1. `y=A_ILU^-1 r_u`;
2. `(p,lambda)=bordered^-1(r_p-C y,r_g)`;
3. `u=y-A_ILU^-1 C^T p`.

The gauge functional g need not be the pressure-null vector; no such
projection is assumed. All factors remain fixed during a GMRES call, so
ordinary GMRES applies. The PDE, nonlinear residual, momentum/continuity
and energy checks are unchanged. The dedicated bordered-diagonal oracle
passed on23October2026, including a non-null-aligned gauge and arbitrary
last rhs. Actual-case performance is an experiment, not established by that
oracle. Combined pressure/velocity factor storage remains explicitly bounded.

Primary rationale: Pimanov etal., arXiv2307.05266v2,21October2023,
[author paper](https://arxiv.org/pdf/2307.05266), studies mass-preconditioner
degradation and diagonal-velocity Schur alternatives for tight no-slip
geometries. Its staggered finite-difference results do not validate this
P2/P1 blade mesh. Wathen2015,
[Preconditioning, section5](https://people.maths.ox.ac.uk/wathen/preconditioning.pdf),
provides the general saddle-point Schur framework. No implementation from
either source was copied. Independent review checked the bordered signs and
the distinction between gauge functional and pressure null mode.

The v4 fixed SIMPLE experiment failed its initial Stokes gate after217.84s;
it did not improve this actual mesh. Its failure and exact source snapshot
are retained. This negative result is not a preconditioner validation.

The subsequent pressure-mass experiment uses fixed inexact-Newton forcing
`||J delta+F|| <= eta ||F||`, requesting eta=5e-9 from GMRES while retaining
the existing independently recomputed true-linear-residual gate1e-8 and
requiring successful GMRES status. The nonlinear residual target1e-9,
backtracking requiring actual residual decrease, continuity, energy, Mach
and load-convergence checks are unchanged. The previous requested1e-11
could reject true1.67e-9 linear residual despite satisfying the independent
1e-8 gate. No failed status is retrospectively accepted.

For nonsingular J, let e=J delta+F. Then the linearized residual is exactly e;
Taylor expansion gives `F(x+delta)=e+O(||delta||^2)`. A forcing bound eta<1
therefore gives a local residual contraction when the quadratic remainder
is sufficiently small. Actual line search and final residual checks remain
necessary; no global guarantee follows for this blade case. This is a
constant forcing choice, not the adaptive Eisenstatâ€“Walker rule. Primary
reference: Eisenstat and Walker1996, SIAM J Sci Comput17:16â€“32,
[DOI10.1137/0917003](https://epubs.siam.org/doi/10.1137/0917003), whose inexact
Newton condition is used; no implementation was copied.

## Actual-source adapted geometry checkpoint

Original ENOLA +5deg STL SHA256
`4659b1f740d6e2ea30819b7a2ce3cdddd54703600ff0d0919d0529ff1db62afd`.
The coarser5362-facet simulation surface includes explicit local hub geometry
regularization. Its10733-cell mesh passes the unchanged positive/condition
and full topology/intersection admission; this supplies the v3â€“v5 cases.
Global0.3mm bidirectional triangle-cover checks pass. At12 blade sections
the maximum thickness-proxy change is12.57%, so this coarsening is not
independently established aerodynamically adequate.

A finer17872-facet adapted surface uses native decimation error0.01mm.
Its first HXT volume mesh had26088 cells and one condition8.56e6 sliver.
The four corners belonged to the hub surface but no cell face was a surface
face. The two-face-quad regularizer correctly rejected that case. Fixed
surface Netgen optimization retained the failing sliver and added cells;
it was not admitted. A separate Delaunay attempt failed native node-reference
extraction; no usable mesh or physics result is claimed from that attempt.

`regularize_roundoff_hub_vertex` supplies an explicitly modified simulation
hub: one original hub vertex displaced0.001mm along its local near-plane
normal. All faces/connectivity remain, all adjacent old/new normals have
positive dot product, topology/orientation screens pass, and bbox is unchanged.
For the same-connectivity affine triangle mapping, displacement at any
barycentric point is bounded by the largest vertex displacement. Native STL
floating readback is handled by the separate original-source distance check.
This is an explicit geometric approximation, not original supplier CAD,
and no invalid tetrahedron is deleted or admitted.

The resulting surface SHA256 is
`dbde893982067b95d5af438f3d20719e9ff79ef722f1b6fdb4df0b246a47d5fb`.
Complete bidirectional triangle covers pass0.15mm, with upper bounds
0.149997126mm and0.149991336mm. This includes the micron hub modification.
At12 blade sections chord/orientation proxies are unchanged and the maximum
thickness-proxy change is2.0832%. These sampled feature checks do not establish
leading/trailing-edge or aerodynamic load qualification.
The resulting native HXT mesh has26542 positive cells, maxcondition107941,
raw-SI NPZ SHA256
`8a8fc546e77ff7e49d294f88bf7e1aaffcf0db946e8df392f63a35c95f5e6b1a`.
Full topology/intersection admission and actual fluid solve are recorded
separately; positive cell quality alone is insufficient. Geometry generators,
native mesh, original-distance proof, section checks and explicit changes are
retained in `output/promo-propulsion-pod-20261023/inertial_cfd/`.
All adapted ENOLA surfaces remain CC-BY-SA4.0 with source attribution and
modifications declared; no manufacturer or source-author endorsement.

## Bounded residual refinement of the same Newton system

The v6 fixed-forcing case failed with info40 and true relative residual
5.00117099e-9, just above the requested5e-9. Its failed status was retained;
it was not promoted to a successful air point. Threshold nudging was rejected
as a response. The next method instead recomputes `r=b-Ax`, solves the
fresh equation `A d=r`, then updates `x<-x+d`. At most two correction rounds
follow the initial Krylov solve. Every equation uses the same full matrix,
rhs, scaling and fixed preconditioner. Exhausted intermediate status supplies
an initial iterate only. Acceptance requires a successful final GMRES status,
finite iterate and the unchanged independently recomputed full-system
relative residual<=1e-8. Final nonlinear/physical checks are unchanged.

Independently, if the computed correction leaves `e=r-A d`, then in exact
arithmetic the new full residual is exactly e. In floating arithmetic, fresh
residual evaluation and addition incur rounding; the implementation measures
the full residual again rather than inferring success from that identity.
For nonsingular A, forward error obeys `||x-x*||<=||A^-1||||r||`; conditioning
still limits the forward information obtainable from a small backward
residual. No higher-precision residual or mixed-precision theorem is claimed.
Primary method reference: Carson and Higham2018,
[SIAM J Sci Comput40:A817â€“A847](https://epubs.siam.org/doi/10.1137/17M1140819),
describes residual/correction/update refinement and GMRES correction solves.
Its three-precision guarantees are not assumed here. No source implementation
was copied. Three dedicated checks passed: an ill-conditioned small direct
oracle, a forced exhausted-status initial iterate followed by a fresh
correction, and rejection of exhausted/nonfinite results. Actual-case benefit
still needs its own retained execution evidence.

On the v7 actual case, correction round1 lowered the full linear residual
from5.001e-9 to8.996e-14, but its own5e-9-relative-to-correction-rhs Krylov
target still exhausted its status budget. The next method keeps initial
forcing5e-9 and uses correction forcing0.01. For `r_new=r-A d`, a correction
condition `||r-A d||<=.01||r||` reduces a5e-9 original residual to approximately
5e-11, apart from rounding. The final full1e-8 gate, finite check and final
successful Krylov status remain mandatory. This is inexact residual
refinement, not retrospective acceptance of the v7 failed status. The
exact v7 matrix/rhs/iterate are retained for controlled replay, avoiding
repeated meshing/assembly while comparing linear algorithms.

Independent review also identified underflow of an ordinary sum-of-squares
norm on nonzero1e-300 rhs. The helper now tests exact zero separately, uses
a robust BLAS norm, rejects nonfinite/nonpositive nonzero norms and scalar
normalizes only extreme correction rhs magnitudes before GMRES. This avoids
SciPy's internal unscaled norm under/overflow. The correction is scaled back
and the full original-system residual is measured robustly. Tests include
2I with rhs magnitudes1e-300 and1e308. The current18-test numerical/certificate
suite passed in10.987s; physical blade convergence remains unestablished.

Research restart uses source-bound prior field artifacts only after exact
mesh hash, surface hash, fluid/omega/quadrature inputs, P1/P2 coordinates,
cell connectivity and P2 numbering agree. It does not accept old residuals:
the current solver recomputes the complete nonlinear, continuity and energy
checks at the saved density fraction before advancing. This is a new
revalidated auxiliary stage, not a resumed or inferred full-air result.

## Batched face-separation certificate candidate

The finer actual mesh has7,326,264 nonadjacent AABB candidate pairs, measured
without intersection decisions in52.61s. Its existing explicit65536-cell
resource profile allows1.6million candidates and correctly rejects this job;
the preceding quality/distance checks do not override that rejection.
The new `propulsion_pod_inertial_cfd_geometry_screen.py` is currently a
non-admitting experiment. It batches at most256 pairs through the existing
`_filtered_determinants` arithmetic with the same eight face axes, vertex
pair differences,128eps error factor and strict signs. It introduces no new
floating sign or rational fallback implementation.

For one candidate axis n, if all16 filtered signs of
`n dot(right_vertex-left_vertex)` are certified positive (or all negative),
the two projected vertex intervals have a strict gap. Convex combinations
preserve the gap, so the two tetrahedra are disjoint. A zero/uncertain sign
cannot certify separation. Such pairs still require the existing exact
rational/cross-edge owner. The batched test compares boolean results with
the existing scalar eight-axis fast path on300 randomized pairs; overlap
and tangent fixtures defer. Two tests passed in0.215s. This does not yet
establish end-to-end admission equivalence or actual runtime improvement;
no current shared/default admission path uses this helper.

## Superseding outer-refinement convergence contract

The preceding v7/replay records required a successful final *inner* Krylov
status even when the original full residual was already far below its target.
That requirement is superseded in the next method, not retroactively changed
in those receipts. An inner solve addresses a correction rhs, while the
refinement algorithm solves the original full system. Their relative targets
are different. Independent convergence of the original system is the relevant
outer criterion: finite x and robust `||Ax-b||/||b||<=1e-8`, unchanged from the
existing independently recomputed full-linear-residual gate.

The driver now checks that criterion before any correction and after each
update. An already converged nonzero initial iterate needs no Krylov call,
just as the exact zero-rhs case needs none. Positive inner budget status is
retained verbatim as diagnostic information; it is neither rewritten to0
nor called a converged inner solve. The outer status independently records
`converged_original_system`. Negative inner failure status, nonfinite values,
exhausted outer budget without full convergence and unchanged final nonlinear
or physical gates still reject. Initial GMRES forcing5e-9 and correction
forcing0.01 are unchanged. The additional tests require no call for an
already-converged nonzero iterate and preserve an inner40 diagnostic even
when the independently evaluated original full residual is zero.

This is a linear-algorithm convergence correction, not a relaxation of the
original full-system accuracy or a full-speed load validation. A small
linear backward residual still cannot establish forward accuracy without
conditioning information, nor physical blade traction convergence without
the separate mesh/domain/stabilization checks. No prior failed CFD receipt
is promoted by these changes.

Controlled replay of the exact saved27763-by27763 Newton matrix (1,524,337
nonzeros) from a zero iterate passed in98.57s: initial inner budget status40
with full residual5.00117e-9, followed by correction forcing0.01, status0
after1275 iterations, full residual4.98043e-11. Starting instead from the
already-overrefined9e-14 iterate failed the old unnecessary tiny-rhs status
requirement; that negative receipt is retained separately. The new outer
pre-correction criterion explicitly fixes this distinction.

Direct-factor reference experiments used the existing `sparselizard_process`
OS containment owner, creating the child suspended before assigning a Job,
with hard2048MiB process memory,120s wall timeout,30million factor-entry
postcondition and bounded streams. SuperLU default COLAMD ordering reached
MemoryError in9.75s; MMD_AT_PLUS_A ordering reached MemoryError in15.53s.
Neither produced a direct reference or passed a residual check. Both contain
enforcement receipts; no larger-memory retry or direct-solver qualification
follows. This negative measured cost evidence supports continuing the bounded
iterative route on this workstation. Matrix/vectors, scripts and receipts
are retained under the v7 output folder.

## Explicit experimental inexact-Newton absolute budget, v1

The strict-relative method remains available as `strict_refined` and remains
the default. The distinct `inexact_absolute_budget_v1` method is opt-in and
recorded in every request/result/source snapshot. It changes the inner linear
accuracy algorithm, not the governing equations or final accepted nonlinear
and physical residuals. Earlier strict receipts are not reinterpreted.

Observed motivation: v8 reached nonlinear error4.838e-9 against target1e-9,
but a strict-relative linear solve exhausted12000 iterations at relative
4.10e-6. The absolute linear error was already approximately2e-14 of the
current PDE scale. Continuing to demand relative1e-8 accuracy on that tiny
rhs was not required by the final nonlinear1e-9 target. V8 was stopped under
the parent instruction after retaining the failure, exact source identity
and a separately accepted auxiliary density3.16227766e-6 stage with current
nonlinear residual2.005e-12. No full-air result was produced or promoted.

Let R be the full scaled nonlinear residual and S its current positive PDE
normalization, so E=||R||/S. For E>t, choose
`eta=min(0.1,0.1*t/E)`, t=the unchanged nonlinear target. Require the independently
computed full linear residual `||J delta+R||<=eta||R||`. Hence
`||J delta+R||/S<=min(0.1E,0.1t)`, an absolute inner budget at most one tenth
of the outer target in the current scale, while eta<1. GMRES requests eta/2;
outer residual refinement independently enforces eta. The scale can change
with the nonlinear state; no trial is accepted from this estimate alone.
The actual nonlinear residual and scale are recomputed for backtracking and
the final target. Max-iteration/nondecreasing-residual states still reject.

Independent local derivation: with e=J delta+R, Taylor expansion gives
`R(x+delta)=e+O(||delta||^2)`. Eta<1 controls the local linearized residual;
the quadratic term and conditioning prevent a global guarantee. Actual
backtracking and final full nonlinear1e-9, energy1e-7, weak continuity,
Mach and blade-load convergence requirements remain unchanged. This is an
explicit absolute-budget inexact Newton choice, not an implementation of
the adaptive Eisenstatâ€“Walker rule. Primary reference: Eisenstat and Walker,
SIAM J Sci Comput17(1996):16â€“32,
[DOI10.1137/0917003](https://epubs.siam.org/doi/10.1137/0917003), inexact Newton
forcing inequality. No implementation was copied.

Three dedicated checks passed in3.484s: absolute-budget/direct-small-system
oracle, rejection after an admitted linear step when the nonlinear field
remains unconverged, and nonexact cubic rotating SUPG MMS refinement with
unchanged final gates. For48->162 tetrahedra the velocity L2 errors are
0.00205037->0.000554180, observed order about3.23 for h=1/2->1/3.
The first test mistakenly applied a factor4 reduction to that1.5 mesh ratio;
it was corrected to an explicit observed-order check>2.5, not a relaxed
physical residual requirement. Actual full-speed convergence remains a
separate execution/mesh/domain/physical-validation question.


## Hub repair and pressure-kernel preflight (superseding old coarse runs)

The original coarse adapted mesh had two additional numerically resolved pressure-null modes beyond the physical constant. Direct continuity and upper-pressure block residuals confirmed the modes; no pressure penalty or extra pressure pin was introduced. Runs v8/v9 were stopped and remain unqualified. Native VTK hub-only cleaning merged input surface vertices 384 and 433 onto retained vertices 383 and 431, respectively, each distance 0.00041909320645407513 mm. This removed four collapsed surface triangles; a new volume mesh was generated rather than deleting fluid elements. Closed oriented topology, Euler characteristic -4 and bounding box were preserved. Maximum retained-face normal change was 0.33674529146989635 degrees and volume change 8.82e-7 mm^3. Bidirectional whole-triangle source-distance screens passed the declared 0.3 mm bound, which does not establish aerodynamic adequacy.

The repaired surface SHA256 is 1acd73405d9bfb2c9961511f336f487bb8dfafbc37225940cd51a7cbde0e8abd; repaired volume mesh SHA256 is c95c93da935b1c8b9114ca79be3a9f1996b9acdbc5addd7e99166a270630c6ef. Its 10,602 positive tetrahedra have 3,539 pressure vertices and maximum mapped condition 9325.4523233559. The saved numerical Gram spectrum has one near-zero eigenvalue and next eigenvalue 5.442266004964988e-6 versus declared zero threshold 3.1910035794255913e-13; eigenpair residuals are below 1e-16. This is finite-mesh numerical evidence, not a uniform inf-sup theorem.

The explicit research preflight v2 retains inputs before eigensolving, fails closed on eigensolver errors, verifies the actual matrix gauge row/column, obtains the physical constant mode from actual pressure scaling, checks both continuity-left and upper-pressure null identities, and requires residual-separated eigenvalue intervals around the numerical classification threshold. General public dispatch defaults are unchanged. Three focused tests executed successfully (0.073 s), including an ambiguous eigenvalue classification rejection. The combined inertial/inexact/preflight/older rotor selection passed 21 tests in 19.807 s before the extra interval test. Fresh v10 starts on repaired geometry with no old pressure-field interpolation; actual-air completion, load refinement and domain independence remain open.


### Repaired-system linear replay

v10 retained two auxiliary-density converged stages (fractions1e-6 and1e-5), then rejected both1e-4 and geometric-mean fallback3.162277660168379e-5 at their unchanged true linear-residual gates. The repaired current Jacobian SHA2562b88137985bd58583d552533bd8f8836923b4386d79d6a0877c2d98905b7f91e and vectors SHA2562602911b95d51cef3c64f3a1ed6b127112654c6c467b7dc6bb7db73475f83c4f were replayed from zero with SIMPLE using the SAME initial-Stokes scaled continuity/gauge and current velocity ILU. This passed in386 GMRES iterations/info0, true full relative residual1.4487291857847316e-9 versus required2.9289380026866373e-9, 19.32s childtime. Existing OS owner enforced2GiB/120s. This discriminates against the old singular-mesh failure; it is neither an aerodynamic validation nor a general speedup claim. The initial replay harness incorrectly densified a continuity comparison and hit the memory limit before solving; sparse equality replaced that harness operation and its separate failure note is retained. Fresh v11 explicitly selects SIMPLE and revalidates the same-geometry accepted v10 stage; no physical gate is relaxed.


## Separate fixed-relative forcing and fixed-vector Armijo method

v11's explicitly absolute intermediate accuracy budget demanded eta~9.84e-11 at normalized nonlinear residual1.0163; its first step passed but cost minutes. It was controlled-stopped with exact source snapshot and accepted fraction1e-4 fields retained, without promoting an air result. The separate opt-in `fixed_relative_forcing_v1` retains the old methods/default and uses eta=0.1, initial GMRES request0.05. This follows established inexact Newton mathematics, not an adaptive Eisenstat-Walker claim (Eisenstat and Walker1996 section1 eq1.2 and globalization section3.1; author primary PDF https://users.wpi.edu/~walker/Papers/forcing_terms%2CSISC_17%2C1996%2C16-32.pdf).

Let F denote the ACTUAL scaled velocity/continuity/pressure-mean residual, and d the actually applied velocity/pressure update. The gauge multiplier is auxiliary: subtract [0,g delta_lambda,0] from the bordered matrix-vector product when obtaining Jd. Require independently ||F+Jd||<=0.1||F|| and norm-merit directional derivative F dot Jd/||F||<0. Since ||F+Jd||<=eta||F|| implies F dot Jd<=-(1-eta)||F||^2, descent follows in exact arithmetic; the implementation checks the actual vector. With Lipschitz Jacobian, ||F(x+alpha d)||<=[1-alpha(1-eta)]||F||+O(alpha^2||d||^2), giving sufficiently local norm Armijo. Bounded backtracking checks ||Ftrial||<=||F||+1e-4 alpha (F dot Jd/||F||) using the SAME fixed scaled vector. No state-dependent divisor is used in this merit comparison. The new method includes actual g dot(p/sp) in F, so final pressure mean is checked rather than a hardcodedzero.

Fixed eta yields local linear convergence, not superlinear convergence or an unconditional global guarantee. Failure of physical-direction forcing, descent, all bounded backtracks, final actual nonlinear1e-9, existing energy1e-7 or other physical/source checks rejects the study. The variable normalization is retained only for the existing final nonlinear acceptance; it cannot produce a false Armijo decrease. Seven focused new+old inexact tests passed in45.617s: discarded-lambda false-pass counterexample, changing-divisor false decrease, nonlinear nonclosure despite an admitted inner step, and nonexact SUPG MMS velocity/pressure refinement. Additional actual-mean restoration and existing inertial regressions are recorded separately after execution.

The output-only independently assembled rigid angular ledger on v10 stage2 (request-bound rho1.225e-5kg/m^3, Omega200rad/s) reproduces weak rotor torque6.321529406282e-5Nm and outer torque-6.355842772482e-5Nm. Free residual torque-9.03e-17Nm and global weak identity defect2.01e-20Nm establish the discrete identity. Raw recovered rotor/outer Cauchy torques1.477649872697e-5/-6.100520933980e-5Nm leave4.616e-5Nm imbalance, much larger than Temam/SUPG angular corrections6.82e-8/2.75e-7Nm. This identifies recovery/interface-jump or underresolution error as unresolved; it does not prove physical traction accuracy or eliminate formulation error. No new flow solve was performed by that postprocessor.


### v12 accepted stage and fixed-field quadrature audit

The explicit relative method accepted density fraction0.001 at Omega200rad/s with true final normalized nonlinear residual7.443577721933939e-10. This is AUXILIARY rho0.001225kg/m^3, not full-density air; the case expired at its wall budget while solving fraction0.003. The accepted stage2 field SHA256cf7b9298e0465e85f1fb659169810efa7ddc927a9a0c3b91a5ad963c0c72e0cb is retained. Evaluating the SAME fixed field with volume/face quadrature orders4 and6 gives weak rotor torque0.00044875510516387377 and0.0004488318235881197Nm (relative change0.0171%), while raw Cauchy rotor torque6.693983135169748e-5Nm is unchanged to floating roundoff. SUPG rotor test torque changes0.000170494999862508 to0.0001705717182867539Nm. Thus quadrature does not explain the approximately85% weak/raw discrepancy; substantial stabilization contribution and unresolved physical traction require matched near-wall/geometry/outer-domain studies. This is an audit of retained fields, not a q6 re-solve or a qualified load. Request/history contexts and exact mesh/field/script hashes are retained under v12/quadrature-audit/q4 andq6.

### Resource and component timing disclosure

Previous main nonlinear runs were bounded by case wall budget, mesh/factor entry budgets and cancellation, but did NOT have the OS2GiB memory cap used by standalone replay/direct reference children. They must not be retroactively described as OS-memory-capped. The new v13 child uses the existing process owner to enforce2GiB before execution and3600s OS wall timeout, with3540s internal case budget for orderly retention. It writes a live console tee and component wall/CPU timings for Jacobian/matrix assembly, preconditioning, Krylov/refinement and line search. Partial fields retained on exceptions are explicitly unqualified, never accepted automatically. These instrumentation changes passed15 forcing/inertial tests in47.139s; an earlier focused command named a nonexistent test selector and was corrected to the full modules. The default research case wall budget remains1800s, while an explicit up-to3600s option amortizes repeated admitted preparation. No equation or numerical acceptance gate changes in this timing snapshot.


### Enforced-memory failure and allocation-only correction

v13 OSJob2GiB enforcement rejected the coarse case during SIMPLE construction, before Newton: copying the already-factored ILU L matrix merely to read its nonzero count required another21.6MiB beyond availableprocesscommit. The run/log/source/OS receipt remain immutable. Direct `SuperLU.nnz` was checked against `L.nnz+U.nnz` on LU and ILU matrices of sizes3,10,50, agreeing in all six observations. Owned factor accounting now uses the scalar property, using a native stored-entry resource counter at the numeric30million threshold without materializing factor copies; this has different, generally more restrictive semantics than exposed CSC nonzero counting. Completed Stokes element assembly chunk lists are released before factorization rather than at constructor return. The allocation changes and resource-counter change passed17 Schur/rotor/inertial tests in34.750s. A fresh v14 repeats the same geometry/physics/method/OScap and accepted-v12 restart; no increased memory ceiling or reduced physical accuracy is implied.


### Correction: native factor storage counter is not CSC nonzero parity

Independent tridiagonal counterexamples invalidate general parity inference from the earlier dense toy checks: at n10 native SuperLU.nnz=110 versus exposedL.nnz+U.nnz=40; at n50 LU290 versus200 andILU281 versus200. Installed SciPy reports1.17.0. Its matching official version source [SuperLU object implementation](https://github.com/scipy/scipy/blob/v1.17.0/scipy/sparse/linalg/_dsolve/_superluobject.c) shows the scalar getter summing native store counters (lines134-137), while CSC conversion omits numerical zeros and checks output sizes against those store counters (lines553-627). Consequently the numeric30M threshold now limits NATIVE STORED entries, not the former exposed CSC nonzero count; this is a different, potentially more restrictive resource guard. The CSC conversion guards establish its generated counts do not exceed the store bounds on successful conversion. No physics or accuracy acceptance gate changes. The binary version/reference correspondence is recorded, not a claim of reproducible binary equivalence to that source tag. The earlier dense observations remain true for those six matrices only.


### Measured BLAS baseline commitment

v15 observational Windows current-process counters showed1,104,715,776 private committed bytes BEFORE Stokes preparation (working set80,072,704). A fresh NumPy/SciPy import with OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1 before import measured77,877,248 private bytes (working set61,145,088). v15 was controlled-stopped during initialization with its source/ledger retained. New v16 sets those variables inside the bounded child BEFORE numerical imports; its actual source-bound case measured93,589,504 private bytes before base assembly, including case data, versus1.1047GB previously. This is runtime concurrency configuration, not an equation, tolerance or OS-cap change. No general performance speedup is inferred. Actual phase memory/CPU/component timings remain required; the OS2GiB guard is retained.


### First measured Newton cost and lifetime correction

v16 initialization completed under the OS2GiB cap: after-base private commitment633,782,272bytes; after preallocated gradients800,526,336; initialization complete837,713,920. The first fraction0.003 Newton step reduced normalized residual1.4284844 to0.08094868 and measured30.3977s Jacobian/matrix assembly,2.0799s preconditioner,1.5003s Krylov/refinement (55iterations),2.8166s line search; total36.7946s wall/35.7969s CPU. This single measured step identifies assembly as dominant in this case, not general solver performance. Peakcommit reached1,685,385,216bytes on that step.

The next iteration hit the unchanged2GiB cap while building a33.1MiB CSR copy. Prior-iteration Jacobian, block matrix and preconditioner closure were still referenced by loop locals during next assembly. They are now explicitly discarded AFTER the completed step and all diagnostics, before the next iteration, with phase memory reporting. No factorization/equation/tolerance changes; the current state and traceability remain retained. Transport Jacobian, SUPG Jacobian and scaled-block assembly receive separate timings to guide any subsequent optimization. Partial fraction0.003 fields from the failed case are labeled unqualified and not automatically reused as an accepted stage.


### Accepted fraction0.003 and reviewed contraction transition

v17 accepted auxiliary fraction0.003 at Omega200rad/s, normalized nonlinear residual2.48998766187462e-10, torque0.0011499697821727624Nm, recovered raw torque0.00015054652352658484Nm (86.9% discrepancy), Mach bound0.12870983626615165 and tip Reynolds915.49. This remains far below actual-air density/Re and is not qualified load evidence. Later-step profiling changed the bottleneck: one Newton step required8000 Krylov iterations/260.34s, compared44.68s assembly; no general assembly-only performance claim follows from the first step. The next0.009 step failed the unchanged true linear-residual gate, so v17 was controlled-stopped after its accepted0.003 field/history were retained.

After independent source review and coefficient/finite-difference tests, v18 replaces ONLY existing volume contraction reassociation with `propulsion_pod_transport_contractions.py`; boundary flux, Coriolis block and CSR assembly remain unchanged. The helper's224MiB output cap means at most26691 cells with a Jacobian, a newly explicit stronger computational resource restriction than the former40000-cell ceiling; no silent fallback or physical qualification implication. Its exact SHA is included in case snapshots. Fifteen existing inertial/MMS/forcing tests passed27.299s after integration; the actual pressure-mean observer hook plus helper tests passed6 in0.204s. This is not an end-to-end speedup claim.

A readonly observer now retains the actual assembled first-Newton bordered Jacobian/rhs/gauge at each new continuation stage BEFORE preconditioning, with source/geometry/request hashes. The purpose is exact SAME-system replay, not PDE reconstruction or result promotion. The current-Jacobian preconditioner candidate remains separate and unintegrated pending evidence on this harder system.


### Exact hard-Jacobian diagnosis and explicit v19 research route

The actual v18 fraction0.009 first Jacobian (SHA25629458593396a0dc63e6a13abfad6b344bd2363d2c500ce878ae2401733b86176; vectors SHA256f4acbb59d8facc30c65885cd8315cf712c68a56f51df8bc52d1a357591194c01) rejected both frozen-Schur and current-diagonal-Schur candidates with the original velocity ILU settings. Independent output-only diagnostics found extreme approximate inverse amplification; accurate triangular solves of the incomplete factors do not establish a good approximation of the original velocity block, nor prove original-matrix singularity. See the independently authored PROPULSION_POD_ILU_BREAKDOWN_20261024.md and PROPULSION_POD_JACOBIAN_SCHUR_20261024.md.

The explicit public helper API with velocity drop tolerance1e-6/fill factor20 passed the SAME hard system:155iterations, true full AND actually applied physical direction relative defect0.00038023949 below unchanged0.1, negative norm-merit slope-5.16507,22,441,243 native factor storage entries below30M and OS2GiB/180s enforcement. This accepts a direction only. Its source497c7721430aa27490b65f015aa65b68e67e4000ee91ac0abf3b6ca47feafaae and options hashbea30eb570ca03a129da37d60b5f837b4409e7ac63f5a4b5c02d15126d9c3dd4 are bound explicitly. Defaults remain unchanged and no automatic preconditioner fallback is added.

The restart-only adapter creates NO unused reference pressure/velocity factors, and its seed solve rejects explicitly. Current factors are frozen for each Krylov solve. After actual direction/physical/descent checks succeed, Jacobian blocks, SUPG ju, full matrix and factor closure are released BEFORE residual-only Armijo trials; delta remains available through the trial. Final residual recomputation recreates the current convection operator for final energy checks. Root independently reviewed this lifecycle; a fresh STANDARD Python test process on ACTUAL post-ju source passed9 adapter/forcing/SUPG Jacobian/nonexact-MMS checks in21.938s. Earlier staged17-test receipt is PRE-ju and is not launch evidence. The actual launch receipt is post-ju-current-schur-actual-source-tests.json.

v19 explicitly selects current_jacobian_schur_strong, binds source/options/request hashes and restarts only the accepted v18 fraction0.003 field. v18 was controlled-stopped on its unaccepted fallback; live unaccepted iterates were not persisted on OS stop and are not claimed as retained results. The new route retains original final nonlinear1e-9, energy1e-7, source, Mach, continuity diagnostics and unqualified load status. Actual full-density air, physical traction and grid/domain convergence remain open.


### v19 terminal guard and failure-state evidence limit

v19 terminated with returncode1 after313.0878s, enforcing OS2GiB/3600s. First full Newton steps at fraction0.009 and fallback0.005196152422706632 reduced residuals to0.03982029788 and0.015365719444555618 respectively. The following Jacobians violated the positive-current-velocity-diagonal preconditioner assumption; the guard was preserved. No stage above0.003 was accepted and no actual-air result exists.

The first-iteration-only export hook did NOT retain the original negative-diagonal failure matrix. Positive first-iteration matrices must not be replayed as that failure. The final exact unaccepted iterate is retained in v19/partial-unqualified-fields.npz, SHA256b74513ad670cf1a34a12889e72612a234483b585c9a0a029208992e8def6cd47, density_fraction0.005196152422706632, accepted_as_resultFalse. A single independently owned output-only diagnostic is authorized to reassemble the actual existing-owner Jacobian from those arrays with exact source/layout/density/boundary checks and residualmatch0.015365719444555618, stopping via observer BEFORE any new factor/direction/update. Such output must be labeled reassembled failure STATE, not an original retained failed matrix or bitwise identity claim. All source/field before/after hashes are required. Source edits remain frozen during the coordinated build window; this diagnostic performs no live source edits.


### Explicit signed-current preconditioner research restart (v20, 24 October)

The v19 positive-diagonal guard rejected the next Jacobian after a Newton full step; no density stage above 0.003 was accepted. Its unqualified saved iterate is diagnostic only. An output-only, source-bound reassembly reproduced its nonlinear residual 0.015365719444555618 exactly and found one negative velocity diagonal. This reassembled matrix is not claimed to be the originally retained failed matrix. The independently reviewed signed-current nonzero-diagonal Schur approximation changes only the preconditioner, not the governing residual, Jacobian, applied-direction forcing, Armijo merit, or final checks. Default `positive_current_v1` still rejects negative diagonals; signed behavior requires named `current_jacobian_schur_signed_strong`. Both complete option descriptors include the policy; historical three-key hashes are not reused.

The public helper replays and independent root algebra review cleared this explicit research route. Local actual-source verification passed 8 adapter/forcing tests (13.338 s) and 10 inertial tests including nonexact MMS/SUPG (15.364 s), plus compilation. Exact source hashes and commands are in `output/promo-propulsion-pod-20261023/inertial_cfd/air_omega200_hubcleaned_v20_signed_current/prelaunch-focused-checks.json`. The bounded v20 job restarts only the accepted v19 fraction 0.003, independently revalidates its residual, and retains first and latest nonzero-iteration matrices per stage. The OS budget remains 2048 MiB/3600 s, with internal 3540 s and BLAS/OMP one thread. Launch does not establish any new accepted density, actual-air point, or qualified traction. The existing approximately 86.9% raw/weak torque discrepancy remains open.


v20 terminal evidence: the 0.009 fraction rejected at Newton iteration 2 (normalized residual 0.02508897211920282) because the unchanged Armijo line search failed. Its latest actual matrix and RHS are retained. Existing fallback 0.005196152422706632 reached Newton iteration 6, residual 0.005193440884500574, but did not converge before adapter termination. The OS wrapper reported its 3600-second timeout; wrapper monotonic duration 32884.209 seconds is not CPU time and includes an observed host/tool wall delay. Last persisted solver record was 1052.855 elapsed seconds / 846.8125 process CPU seconds. No graceful partial field artifact was created by the OS-terminated process. Consequently the fallback is unfinished, not retrospectively classified as a nonlinear failure. Only fraction 0.003 remains accepted. `terminal-status.json` binds terminal receipts and source-end hashes. No actual-air or load qualification follows.


Prepared future orchestration (not launched): `density_growth_factor` defaults to legacy3 and accepts explicit finite values strictly above1 through3; the legacy10 multiplier below fraction0.001 is unchanged. A smaller1.5 increment changes the sequence of auxiliary parameter trials only, with no guarantee of convergence and no change to the target fluid properties or any acceptance tolerance. The matching current Newton velocity/pressure, exact mesh numbering and density now accompany each first/latest retained matrix, independently hashed and explicitly not an accepted density result. Root reviewed the frozen-v20-to-live-case diff; four focused adapter/orchestration tests passed0.103s and compilation passed. The new launch remains withheld pending the independent actual-state directional derivative audit; no extended Armijo/backtracking change is included.


Independent actual-state tangent audit completed before the next launch: the frozen v19 fallback state reproduced baseline raw residual bitwise, with the prior matrix identity retained. For the actual physical Newton direction (discarded multiplier set to zero), centered relative derivative errors at h=[0.1,0.01,0.001,1e-5,1e-7] were [7.71334e-3,7.72192e-5,7.72201e-7,2.18458e-8,2.20361e-6]; the independent boundary-fixed, pressure-gauge-balanced direction gave [2.80349e-7,2.80352e-9,2.80381e-11,3.04402e-11,3.20872e-9]. This shows truncation followed by roundoff and no detected tangent inconsistency at that state, not proof at every later state. The finite-difference raw-merit slope -0.03141417950955 agreed with analytic -0.03141417951171. The independent worker retained21 captures, source/input invariants and OS bounds (348.906s/1.044GB peak) under `v19-actual-jacobian-fd-residual-only-20261024/`.

Root then authorized v21 explicit growth1.5, accepted v20 fraction0.003 restart only, with matching matrix/state retention and unchanged signed-option, Armijo/nonlinear/energy/physical/load checks. The OS budget remains2048MiB/3600s, internal3540s/BLAS1. This launch alone establishes no new operating point or load qualification.


v21 terminal: the source-bound growth1.5 continuation accepted fraction0.003674234614174767 at Newton6, nonlinear residual8.182356710232862e-12. Weak torque0.0013864460503860174Nm, raw Cauchy torque0.00018022801582616855Nm differ87.0%; these remain unqualified loads at auxiliary density, not air. Subsequent0.005511351921262151 and fallback0.0045 trials failed the unchanged Armijo search. The OS-bounded child exited1 after2174.94s; the last failure receipt recorded2082.375 process CPU seconds. This is a numerical line-search rejection, distinct from v20 host-delay timeout. Exact current Newton velocity/pressure, mesh numbering, Jacobian/RHS and source/request hashes are retained for rejected stages; the latest unaccepted field is also diagnostic only. No actual-air target was accepted.

An output-only stage02 diagnostic has been prepared to replay the exact retained linear problem under a180s/2048MiB OS child and then capture only the original residual under a separate720s/2048MiB child. It will test the original seven Armijo alphas and seven smaller alphas1/128 through1/8192, retaining raw residuals, exact Armijo thresholds, forward directional derivative errors and merit secants. This preparation makes no solver change and is not evidence of any passing smaller step. Execution is contingent on root review and memory headroom.


The reviewed output-only v21stage02 Armijo diagnostic then executed successfully. The exact retained Jacobian/RHS direction was reconstructed with the public signed preconditioner and unchanged forcing: true bordered and actual physical direction defects0.049206297903187986 (<0.1), norm-merit slope-0.004897244314038661, gauge-direction residual-1.71e-16. This is a reconstructed direction, not claimed bitwise equal to an unretained original. The separate residual-only child reproduced baseline raw F bitwise and preserved all request/state/source/helper/mesh hashes. All original seven alphas1..1/64 failed the exact production Armijo function;1/128 also failed, whereas1/256 and all smaller predeclared alphas through1/8192 passed. The raw-merit secant approached the analytic slope (-0.00173238 at1/256,-0.00480064 at1/8192), and forward directional-vector errors decreased approximately linearly with alpha. This demonstrates a finite search-budget obstruction at this one state; it is neither a new accepted density stage nor proof of global convergence.

Both OS-bounded phases completed: linear66.42s/65.375CPU/1.134GBpeak under180s/2048MiB; residual183.35s/175.02CPU/1.030GBpeak under720s/2048MiB. Raw residual vectors, direction, exact thresholds, provenance and before/after hashes are retained under `v21-stage02-Armijo-budget-audit/`; outer enforcement receipt is `v21-stage02-Armijo-budget-bounded.json`. No live engine or Armijo acceptance formula was modified by the diagnostic.


Prepared explicit line-search budget control, pending source review before launch: `solve(maximum_line_search_trials=7)` preserves the exact legacy alpha tuple by default. It requires an exact Python integer1..14 (booleans/floats rejected) before any solve state update; the case validates before artifact work, binds the option in request/CLI, and passes it to every solve. The optional14 trials add alphas1/128 through1/8192 without modifying the merit formula, forcing/physical-direction/descent checks, final nonlinear1e-9, energy1e-7, any load check, or case maximum20 Newton updates. Profiles retain configured and attempted counts. No automatic fallback changes the configured budget.

Twenty-one focused tests passed25.467s: the analytic residualF(x)=1-x+200x^2 atx=0 has exact Newton direction1/merit slope-1; the production Armijo formula rejects all seven legacy trials and first accepts1/256 under14, while deliberately bad trials still reject. Invalid budget types/ranges fail before updates/artifacts; an actual field restart with explicit14 passes final gates/profile checks; prior MMS/SUPG/forcing tests pass. Exact source hashes and command are retained in `explicit-line-search-budget-focused-checks.json`; `future-explicit-line-search-budget.diff` compares against frozenv21. This is an explicitly increased computational search budget, not a weaker acceptance inequality or evidence that a subsequent case converges.
