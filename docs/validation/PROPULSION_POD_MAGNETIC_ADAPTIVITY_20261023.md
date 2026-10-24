# Residual-guided P2 magnetic interior refinement, 23 October 2026

Independent derivation only. No adaptive solver implementation or real-motor
adaptive convergence result is claimed. This prepares bounded marking within
the existing conforming red/green geometry owner, with the annular trace held
fixed. The indicator below is not a certified error bound for the native
high-contrast, anisotropic or poorly shaped mesh.

## Governing residual and units

Let C=[[0,1],[-1,0]], B=C grad A, nu=mu^-1, H=nu(B-Br), depth d.
The exact source-functional weak equation on each polygonal subdomain is

```
d integral H·C grad v = d integral J v,
D=C^T nu C, p=C^T nu Br, q=D grad A-p=C^T H.
```

Thus the strong equation is `-div q=J`. For constant element material and
remanence, the element residual is

```
R_K=J_K+div q_K=J_K+D_K:Hess(A_h).
```

Across an interior edge with outward normals from its two adjacent elements,
the flux residual is `j_e=q_K·n_K+q_L·n_L`. There is no imposed free-current
sheet in this model, so the exact jump is zero. Br discontinuities are included
in q and must not be discarded at magnet boundaries. Do not substitute a jump
of normal B: a conforming C0 potential already gives matching tangential trace
derivatives, hence matching normal B, even for an inaccurate solution. The
relevant residual is tangential H, equivalently normal q.

A has Wb/m, B and Br have T, H and q have A/m, D has m/H, R has A/m².
Depth cancels from the strong PDE but remains in every energy measure.

## A bounded marking indicator

For actual triangle diameter h_K, actual edge length h_e, and
alpha_K=lambda_min(D_K)>0, choose the transparent weighting
alpha_e=min(alpha_K,alpha_L). Define

```
eta_K²=d [h_K²/alpha_K integral_K R_K²
         +.5 sum_interior_edges(e of K) h_e/alpha_e integral_e j_e²].
```

Every term has joules: eta has square-root-joules, as does the magnetic energy
seminorm `sqrt(d integral grad(error)^T D grad(error))`. Shared-edge halves
avoid double counting in the global sum. This minimum-eigenvalue weighting is
an explicit conservative marking choice, not a borrowed coefficient-robust
reliability theorem. High coefficient contrast, anisotropy, element aspect
ratio, non-quasi-monotone material neighborhoods and the constrained annular
trace all affect constants and possible reliability. Keep those limitations
visible. Exact constant J, Br and material make data oscillation zero inside
each fitted element; unresolved CAD/material geometry is a separate error.

Fixed outer Dirichlet edges are excluded. Annular interface edges must not be
assigned a fabricated zero pointwise physical flux residual: the actual
finite-dimensional coupling balances projected Fourier reactions, while the
FE boundary is polygonal. The interior indicator targets the fixed-trace
variational problem only. Separately retain coupled algebraic residual,
Fourier-cutoff change, trace geometry/chord error and annulus-vs-domain energy
checks. A small interior indicator cannot establish a resolved interface.

Primary foundations read directly: [Joachim Schöberl,Interactive Finite Elements,
chapter27,The residual error estimator,accessed23October2026](https://jschoeberl.github.io/iFEM/aposteriori/residualEE.html),
element residual/interior normal-flux jumps and the interpolation-based
reliability structure; [Cai and Zhang,Robust Residual- and Recovery-Based
A Posteriori Error Estimators for Interface Problems with Flux Jumps,
accepted3June2010,sectionsI–III,DOI10.1002/num.20629](https://www.dam.brown.edu/people/shzhang/fluxjump.pdf),
coefficient-jump robustness assumptions and interface residuals. Their scalar
coefficient/local-monotonicity results are not asserted to prove the present
tensor/high-contrast marking choice. Equations and proposed workflow here are
independently derived; no external implementation is copied.

## Reuse of the existing operator and four source fields

No new PDE solve is required for indicators after recovery of the four source
basis fields. The prepared P2 operator already has physical barycentric
gradients, six-node connectivity, areas, nu and Br. Vertex basis Hessian is
`4 grad(lambda_i) outer grad(lambda_i)`; edge Hessian is
`4[grad(lambda_i) outer grad(lambda_j)+grad(lambda_j) outer grad(lambda_i)]`.
Contract these with the six potential values to obtain the constant element
Hessian and R. This avoids numerically differentiating B.

`op.evaluate_b(A,barycentric_points)` or its `_curl` helper evaluates B at any
requested barycentric positions. For each of the three local edges, use the
two Gauss parameters t=.5±1/(2sqrt3) on that edge. Then H=nu(B-Br), q=C^TH,
and the jump is affine along each edge. Two-point Gauss integrates j² exactly.
R is constant, so its volume square is simply area times R². Share global
edge adjacency, but retain each material's one-sided q until after the jump;
do not smooth it across material boundaries. Compute outward normals from
signed triangle orientation, since the operator admits either orientation.

For augmented source z=(1,iA,iB,iC), use

```
A^(0)=the PM-only solution, J^(0)=0, Br^(0)=actual Br,
A^(j)=unit-current-total solution_j - A^(0),
J^(j)=chi_j, Br^(j)=0, j=1,2,3.
```

Alternatively recover the phase response directly from the prepared Schur
response columns. Reusing the full PM-plus-current field as a phase basis
without subtracting PM would double-count remanence. Residuals and jumps are
linear in z. Form an element4x4 Gram matrix Q_K of the weighted residual/jump
inner products; then `eta_K²(z)=z^T Q_K z`. Q is PSD to quadrature/roundoff.
Its entries have mixed source units, so normalize physical currents before
comparing eigenvalues or traces.

For the balanced phase box sum i=0, |ij|<=Imax, eta² is a convex quadratic in
i. Its exact maximum on this hexagon occurs at one of the six permutations
of (Imax,-Imax,0). Evaluate the six z vectors against each Q_K, with the PM
coordinate1. This supplies a current-envelope marking metric without six new
field solves. It does not bound angular variation: take the union or maximum
over a declared representative angle set, then verify its angular refinement.

## Budgeted refinement and discriminating checks

Sort nonnegative cell metrics deterministically and choose a declared bulk
fraction of their total (a marking algorithm parameter, not a physical
accuracy tolerance). Include red/green closure and material/interface
conformity before counting the predicted triangle/P2-node/factor budgets.
Reject or return unresolved if closure exceeds the cap; do not relax solver
or load gates. Preserve original boundary trace edges and circle mapping.
For the repeated rotor, close marks over complete14fold triangle orbits or
aggregate to the base sector, then replicate. Adapting one asymmetric realized
field and losing the mesh permutation would invalidate its proven period.
The stator may be marked independently while retaining its fixed sources.

The next bounded experiment should compare indicator-guided refinement with
the existing fixed-trace uniform-interior refinement at similar DOF count.
Retain source-function and per-material polygon measures, gauge, source hashes,
all mesh statistics, solve residuals and the scaled augmented-response PSD
check under genuine nesting. Torque is not monotone and needs the same
coenergy derivative/stress/angle/current-envelope convergence checks as before.

Before use, meaningful tests must include: a quadratic constant-material exact
patch with zero residual/jumps; a piecewise-material exact linear potential
with matching q-normal but discontinuous B/H components; a deliberately
perturbed P2 bubble producing nonzero constant residual and affine jumps;
orientation reversal; edge integration against independent dense quadrature;
PM-region discontinuity; equivalence of explicit current combinations and
Q_K contraction; balanced-box maximum against random interior samples;
conforming orbit/closure and source preservation. These are proposed tests,
not reported executed adaptive verification.

Knowledgeable human review and actual adaptive/native convergence evidence
remain required. A torque-specific goal-oriented or equilibrated-flux bound
would require additional mathematics and verification; it is not supplied by
this simple residual-marking derivation.

## Independent implementation review checkpoint

The root owner subsequently implemented
`python/spike_core/propulsion_pod_magnetic_indicator.py`. Independent inspection
checked D=C^TnuC, the P2 Hessian contraction, outward normals independent of
triangle orientation, global edge endpoint order for matching Gauss points,
one-sided remanence flux and half-distribution of each interior edge measure.
No consequential equation/sign/unit finding was identified. The three owner
tests were independently executed and passed in.005s: quadratic zero residual,
a continuous-potential/normal-B example with nonzero constitutive flux jump,
and cancellation when piecewise B=Br.

A separately authored anisotropic oracle used A=x on two unit-square triangles,
D0=diag(2,3), D1=diag(5,7), depth.3m, zero J and zero Br. Across the diagonal,
jump=3/sqrt2 A/m and length=sqrt2 m, giving exact total1.35J and.675J per
cell. The implementation returned1.3499999999999996J and
(.6749999999999998,.6749999999999998)J. This tests the tensor transform and
alpha weighting independently of the owner's scalar fixtures.

Source at review SHA256
`0e7e65bf082b8ffdd4eb15454aa2fb41f81a268fec6084588954ca992b3531b3`.
A minor fail-closed output request remains to bind to the next hash: finite
individual indicators do not guarantee their global sum cannot overflow, so
the returned sum must also be checked for finiteness. This is a marking-only
implementation; adaptive closure, current-envelope/angle selection and actual
native convergence are not established by these tests.

## Two-grid energy-correction candidate for anisotropic cells

The actual residual-indicator sequence reportedly increased162→1125→3448J
while refinement created very thin air triangles. Diameter-based residual
weights have shape-dependent reliability constants; replacing diameter by
minimum altitude without a derivation would not repair that evidence. The
following independently derived candidate instead measures a computed field
correction in its actual constitutive energy, without an empirical h weight.
It is still not a certified true-error or torque bound.

For the SAME polygon geometry, source functions, material laws, gauge and
Fourier trace mapping/cutoff, let V0 subset V1 be genuinely nested conforming
spaces. Let a0,a1 be their exact discrete stationary solutions to
`Pi(a)=.5 B(a,a)-F(a)+c`, where B is symmetric/coercive on the gauged space.
Set delta=a1-a0. Fine-space stationarity gives B(a1,delta)=F(delta). Expanding
the quadratic functional therefore gives

```
Wco1-Wco0=Pi(a0)-Pi(a1)=.5 B(delta,delta)>=0.
```

For field-cell localization on each fine child T of coarse parent K,

```
eta_T²=.5 d integral_T (B1-B0)^T nu_T (B1-B0).
```

These quantities are nonnegative joules and intrinsic to the SPD material
metric, including anisotropy. They contain no diameter/aspect heuristic.
Evaluate the COARSE P2 polynomial at the FINE physical quadrature locations;
subtracting unmatched cell means is incorrect. Since both fields have affine
B within a child contained in one coarse parent and nu is constant, the
existing three-point degree-two rule integrates this expression exactly.
Br cancels in the difference only because the constitutive geometry/source
reference is unchanged. Fine cell material, depth and coverage must agree
with its parent. If a fine cell crosses old parent edges, generic pointwise
comparison can still be defined, but it does not establish the nested-space
identity and must not be silently admitted as the same method.

For the coupled separated motor, holding the trace SPACE fixed does not hold
the solved trace COEFFICIENTS fixed. Global correction additionally includes

```
eta_gap²=.5 delta_coeff^T Kgap(theta) delta_coeff.
```

Only the sum of all domain-cell corrections AND this analytic gap correction
equals the coupled coenergy gain. The cell-only identity is valid if the
trace values themselves are unchanged, so delta_coeff=0. A large gap correction
is a separate warning against using cell markers as the complete global
comparison. Compare both fields at the same mechanical angle and physical
currents. There is no extra PM-reference correction when the material volume
and Br are identical; a changed reference means the experiment is not the
fixed-functional comparison above.

Primary foundations read directly: [Nochetto and Veeser,Primer of Adaptive
Finite Element Methods,section5.3,Lemma11/equation92 and Problem41](https://math.umd.edu/~rhn/lectures/cime.pdf),
the nested symmetric-Galerkin Pythagoras identity; [Bespalov,Praetorius,Ruggeri,
2021,Two-level a posteriori error estimation for adaptive multilevel stochastic
Galerkin FEM,section4.1,equations22–23](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/133890132/2006.02255.pdf),
DOI10.1137/20M1342586, the explicit relation between two-level differences and
the saturation assumption. The latter paper treats stochastic Galerkin spaces;
its implementation or problem-specific theorem is not transplanted to this
motor. The quadratic identity and localization above are independently proved.
The original Bank–Weiser1985 AMS PDF returned403 and is not claimed read.
No third-party implementation or paper file is redistributed.

Let e0,e1 be errors relative to a fixed limiting variational problem. Galerkin
orthogonality gives `||e0||B²=||e1||B²+||delta||B²`. Thus the correction
is only a lower bound on coarse error energy. An upper bound would require
an established saturation factor q<1 with `||e1||B<=q||e0||B`, giving
`.5||e0||B²<=eta_total²/(1-q²)`. No such q is known for this motor.
A tiny correction may simply mean inadequate enrichment in the relevant
region. Successive correction magnitudes need not themselves decrease at
every adaptive step. Neither positivity nor coenergy identity certifies
remaining torque accuracy, source properties or angular interpolation.

All four augmented source-basis fields can be reused as in the residual
section. Their correction Gram matrix per child replaces the residual Gram
matrix; the same six-vertex balanced-current-box maximum applies. Aggregate
to coarse parents when selecting a refined space, or explicitly identify the
fine-child correction as a heuristic guide to the next enrichment. Preserve
rotor14fold marking closure, exact source functions and resource preflight.
The uniform probe must itself fit the declared budgets; exceeding a budget
returns unresolved, not a fabricated small correction.

Efficient evaluation can use parent IDs from the refinement owner. Alternatively
one may locate the fine centroid, then verify ALL fine vertices lie inside
that parent and verify per-parent area coverage/material identity. Merely
finding the centroid is insufficient. Coarse B is affine and can also be
evaluated using its centroid value plus C times its constant Hessian times
physical displacement, avoiding repeated global basis construction. Seam
welding and area tolerances must be measured and reported; they are not a
license to relax a failed same-geometry comparison.

### Executed two-grid oracle and implementation review

An independent two-triangle unit-square oracle was red-refined into eight
children with unchanged piecewise source/material functions, mu=1.2/.8H/m,
Br=(.2,.1)/(-.1,.3)T, J=1/-.4A/m², depth.3m and zero outer potential.
The separately evaluated parent-polynomial/fine-quadrature sum was
.0011934285714285716J. Independent assembled `.5 delta_a^T Kfine delta_a`
was.0011934285714285718J and the solved coenergy gain was
.0011934285714285744J: defect2.81893e-18J. All eight child contributions
were positive. These are manufactured numerical units, not motor data.

The root owner subsequently implemented `hierarchical_magnetic_correction`
in the existing indicator module. Independent inspection checked parent
location/orientation, full-vertex containment, area/material/depth guards,
P2 parent-gradient evaluation and degree-two correction integration. It
explicitly excludes gap energy. The helper cannot verify source identity or
stationarity from potentials alone; its caller must bind these before using
the global coenergy-gain identity.

Running the independent Galerkin fixture against the actual helper gave
.0011934285714285714J versus the same coenergy gain, defect−3.03577e-18J.
The four owner indicator tests independently passed in.223s, including an
exact.4J polynomial correction and zero correction for identical quadratic
fields. Reviewed indicator source SHA256
`5433c22c37368d04279347abe18faa54f351f8950fd9e00d758ff3e6531c8860`;
test SHA256
`71b5c0f044df9ae827aa9cb2e6181effe894aea72c41b21353fac4be66143bdb`.
This version also closes the earlier global-sum overflow guard request.
No actual adaptive native-motor convergence or saturation claim is established.

### Physical nesting tolerance review

The owner subsequently replaced a dimensionless barycentric threshold by
`max(-lambda_i,0)*opposite_altitude_i`. This correctly measures outward
normal violation of each supporting edge line and avoids magnifying a tiny
physical discrepancy into a large barycentric coefficient on a thin cell.
However its maximum is not Euclidean point-to-triangle distance near an acute
corner. A discriminating geometric counterexample is the triangle
[(0,0),(1e-3,1e-6),(1e-3,-1e-6)] and point(-1e-9,0): the two normal
violations are about1e-12m, but the distance to the triangle is1e-9m.
Thus a2pm normal-violation allowance is not a2pm geometric nesting bound.

Review requested a closed-segment nearest-distance check for each outside
vertex if the intended policy is a true physical point-distance tolerance.
Outside a convex triangle, the minimum distance to its three closed segments,
using clamped projection parameters, is the distance to the triangle. If all
fine vertices are within delta of the coarse triangle, convexity also places
the whole fine child inside its delta-Minkowski enlargement. Keep the declared
default0 and bounded existing coordinate-weld allowance; do not relax it to
pass a field result. The swept-area-style `2delta*perimeter` allowance and
old area-roundoff floors must remain separately reported and do not establish
exact nested spaces. Neither a geometry tolerance nor parent area coverage
alone certifies source identity or the global coenergy-correction equality.
This requested corner-distance fix was pending at this checkpoint.

The subsequent source `f9b3d23f06c84654bcc4d1f9694adf38da24365a2e06851e1465f753815e868e`
implements the requested true Euclidean distance: for each outside fine vertex,
it computes clamped projections onto all three closed parent segments and
takes the nearest distance. Edge-normal violation is reported separately.
Independent inspection found the geometry logic correct. The four tests
passed in.249s. A separate sharper counterexample with coarse vertices
[(0,0),(1e-4,1e-7),(1e-4,-1e-7)], fine tip shifted to(-1e-9,0), and explicit
2pm allowance was independently executed: it correctly rejected the ancestor
containment before the area check. The original normal-only gate would have
understated that1nm excursion to about1pm. This closes the reported bug and
supports a non-admitting, factorization-free nesting audit with declared
tolerance and recorded diagnostics. Floating-point margins, swept-area
allowances and approximate geometry are still not an exact-inclusion theorem
or a physical field-accuracy certificate.
