# Conforming quadratic planar magnetic operator, 23 October 2026

Experimental implementation in `python/spike_core/propulsion_pod_magnetic_p2.py`.
This independent derivation precedes implementation. Knowledgeable human review
is required before release. No hardware, nonlinear steel, loss or torque
convergence qualification follows from polynomial-order verification.

For straight triangles with barycentric coordinates lambda_i, vertex basis is
Ni=lambda_i(2lambda_i-1), edge basis Nij=4lambda_i lambda_j. Vertex gradients
are (4lambda_i-1)grad(lambda_i); edge gradients are
4(lambda_i grad(lambda_j)+lambda_j grad(lambda_i)). Shared geometric edge
midpoints are single global degrees of freedom, ensuring C0 conformity.
For scalar axial potential A [Wb/m], B=(partial_y A,-partial_x A) [T].

For piecewise constant symmetric positive-definite permeability mu [H/m],
nu=mu^-1, remanence Br [T], axial depth d [m], and Jz [A/m²], minimize

```
Pi(a)=d integral .5(B-Br)^T nu(B-Br)-Jz A dS,
Kij=d integral curlNi^T nu curlNj dS,
fPM_i=d integral curlNi^T nu Br dS,
fJ_i=d integral Jz Ni dS,
K a=fPM+fJ (with explicit essential boundary values).
```

Retain the PM reference `.5d integral Br^T nu Br`; it is part of physical
magnetic energy U. In particular U=.5a^TKa-a^TfPM+c. For zero boundary values,
stationary current-source coenergy is `a^TfJ-U=.5a^T(fPM+fJ)-c`.
Nonzero prescribed boundary potentials involve boundary-source work, so this
reported current-source Legendre expression is not a total boundary-inclusive
coenergy. For a phase source J=sum chi_k i_k, linkage is
lambda_k=d integral chi_k A = source_load(chi_k)^T a. Hence differential
Lkl=load_k^T Kff^-1 load_l is reciprocal on the gauged free subspace.

Three equally weighted barycentric points, permutations of (2/3,1/6,1/6),
integrate degree-two polynomials exactly. P2 gradients are affine, so stiffness
and full PM energy are exact for the stated constant laws. PM source is affine;
constant J times Ni is quadratic. The vertex source integrals vanish, while
each edge basis integrates to area/3. B must be evaluated at quadrature or
requested barycentric positions; replacing it by one cell mean loses quadratic
stress/energy terms. No curved-geometry improvement is implied by midside
degrees of freedom on straight triangles.

Primary mathematical references: [DefElement, degree-two Lagrange triangle,
accessed 23 October 2026](https://defelement.org/elements/examples/triangle-lagrange-equispaced-2.html),
nodal element definition; [Le Dret, approximation of PDEs, chapter5.7](https://www.ljll.fr/ledret/M1English/M1ApproxPDE_Chapter5-2.pdf),
barycentric P2 construction; [Haus and Melcher, 1989, chapter11.7](https://web.mit.edu/6.013_book/www/chapter11/11.7.html),
energy/coenergy virtual work. Algebra and implementation are independently
authored; no third-party solver implementation is copied.

Expected verification: exact A=x²+y² with J=-4nu, A=x²-y² with J=0,
quadratic Dirichlet values on all boundary midsides; arbitrary triangle
orientation; SPD tensor quadratic patch; source-integral and shared-edge checks;
PM-source/current reciprocity and finite-difference coenergy virtual work;
repeated RHS factor reuse; invalid material, topology, boundary/gauge and
nonfinite rejection. Mesh validity beyond conforming combinatorial topology
remains the upstream geometry-admission owner's responsibility.

## Executed evidence and independent review

Author execution on23October2026:
`.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_magnetic_p2 -q`
passed6tests in0.014s, no skips. These cover both exact quadratic patches,
quadrature-position fields, anisotropic tensor/constant-PM patch, arbitrary
orientation, shared midside nodes and exclusion of interior boundary chords,
source integrals, reciprocal two-source L, current-coenergy virtual work,
factor reuse, full PM reference and a rotating constant-remanence oracle with
anisotropic nonzero reference derivative. The last oracle explicitly verifies
`dWco/dtheta=a^TfPM'-c'`; dropping c' cannot pass. Invalid SPD materials,
boolean permeability, duplicate triangles, missing component gauge, malformed
sources and nonfinite boundary/field inputs are rejected.

Final source SHA256:
`7b37c5712fde29c8e7bd76081406346bcda9ae4272b592a8993c42a338d58861`.
Test SHA256:
`4c886b66198caf106336ace50f96edf506be1c9822363bfcf5e6a018c681fa08`.

Independent root reviewer inspected the equations/source, reran all6tests,
and executed a separately authored anisotropic oracle: A=xy,
nu=[[2,.4],[.4,1]], C^TnuC=[[1,-.4],[-.4,2]], J=.8 on18triangles of a unit
square, with quadratic Dirichlet midside values. Reported maximum nodal error
3.8858e-16; computed energy.3999999999999999J versus independent analytic.4J.
The electrical worker independently reviewed the basis, depth factors,
constant-source loads, full PM reference and quadrature field interface and
reported no consequential mathematical finding. These are independent agent
reviews, not a replacement for the required knowledgeable human release review.

## Adapter contract and limits

Construct `P2MagneticOperator(nodes_m,triangles,region_ids,materials,stack_depth_m)`.
It exposes original vertices followed by shared midpoints in `nodes_m`, local
six-node `triangles_p2`, areas and barycentric gradients. Materials accept
`mu_r` or scalar/SPD2x2 `permeability_h_m`, with optional `remanence_t`.
`boundary_dofs(original_vertex_ids)` adds midsides of topological boundary
edges only. It must not constrain an interior chord merely because both end
vertices happen to lie on a boundary. Other internal essential DOFs must be
provided explicitly. Nonzero boundary data require evaluation at all fixed
P2 nodes, including midsides.

`solve(Jarray,dirichlet_a_wb_per_m={integer_index:float_value})` returns potential,
quadrature B, full magnetic energy, current-source coenergy and residual/factor
diagnostics. `source_load(chi_phase)^T a` is the phase linkage.
`evaluate_b(a,barycentric_Qx3)` returns one vector for every element and requested
position. Stiffness is prepared once and the sparse LU is reused while fixed
indices remain unchanged; four linear-port right-hand sides need one factor.
Every connected component needs a gauge. Explicit limits are at most200000
triangles,600000P2 nodes and30000000factor nonzeros; actual allocation/physical
mesh validity remain upstream responsibilities, and resource rejection does
not manufacture a solved result.

Straight-sided P2 improves field approximation, not source CAD chord error.
The actual motor still needs mesh/geometry/angle refinement. In particular,
local ALE virtual-work/stress agreement does not prove that independently
rebuilt angle meshes define a coherent global coenergy function. A real motor
table must resolve its independent-anchor coenergy derivative disagreement
before serving as a conservative global coupling port. No actual motor
torque, material, loss or full-speed-air convergence is established here.

The DefElement page was read directly. The Le Dret PDF search record was
available but direct retrieval timed out; no unverified equation is attributed
to that unread PDF. The displayed basis and independent algebra/tests suffice
for the implemented construction.
