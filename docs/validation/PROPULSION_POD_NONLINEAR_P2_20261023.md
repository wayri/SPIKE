<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied-law nonlinear P2 magnetic reference, 23 October 2026

This independently authored derivation precedes the implementation. It follows
[the numerical evidence policy](../NUMERICAL_METHOD_EVIDENCE.md). The bounded
in-process reference adds a single-valued supplied isotropic B-H law to the
existing straight-triangle P2 field operator. It does not qualify OpenMotor
steel, magnets, winding identity, torque, or hardware. Human numerical review
remains required before release.

## Foundations actually reviewed

- Haus and Melcher, *Electromagnetic Fields and Energy* (1989), online
  [11.4 Energy Densities](https://web.mit.edu/6.013_book/www/chapter11/11.4.html)
  and [11.7 energy principle and reciprocity](https://web.mit.edu/6.013_book/www/chapter11/11.7.html),
  read 23 October 2026: single-valued magnetic energy and terminal coenergy.
- [DefElement degree-two triangle](https://defelement.org/elements/examples/triangle-lagrange-equispaced-2.html),
  nodal functionals and polynomial space, read 23 October 2026. The existing
  SPIKE P2 basis and source integration are reused without modification.
- Boyd and Vandenberghe, *Convex Optimization*, chapter 9 lecture slides,
  revised by Boyd, Vandenberghe and Parth Nobel, online
  [unconstrained minimization](https://web.stanford.edu/class/ee364a/lectures/unconstrained.pdf),
  slides 9.9 (backtracking), 9.19-9.23 (Newton direction and descent), read
  23 October 2026. Smooth convergence rates are not asserted across B-H knots.
- NIST DLMF version 1.2.8 (release 15 September 2026),
  [3.5(v), Gauss quadrature and Gauss-Legendre formula](https://dlmf.nist.gov/3.5#v),
  positive weights, polynomial exactness and equation 3.5.21, read
  23 October 2026. The square-to-triangle change of variables below is derived
  independently; no quadrature table or external implementation is copied.

No external solver implementation, examples or test data were consulted or
adapted. Implementation, derivation and analytic fixtures are original; the
existing SPIKE `MagneticMaterial` law is reused. References establish method
provenance, not qualification of a material dataset.

## Independent derivation and units

Let A=sum a_i N_i [Wb/m], C_i=(partial_y N_i,-partial_x N_i) [1/m],
B=sum C_i a_i [T], and d>0 [m] be axial depth. Each scalar material curve
contains strictly increasing pairs (b_j,h_j) [T,A/m], beginning at (0,0).
On segment j, h(b)=h_j+s_j(b-b_j), s_j>0 [m/H]. Define

```
w(b)=sum_{k<j} (b_{k+1}-b_k)(h_k+h_{k+1})/2
     +h_j(b-b_j)+s_j(b-b_j)^2/2  [J/m^3]
H=(h(b)/b) B
D=dH/dB=(h/b)I+(s_j-h/b) uu^T, u=B/b.
```

This follows by differentiating b=(B dot B)^(1/2) and its integral w. The
radial eigenvalue is s_j; the transverse eigenvalue is h/b. Both are positive.
At zero, D=s_0 I; at a knot use the right derivative (last segment at the
upper endpoint). w and H are continuous, while D can jump. No hysteresis,
anisotropic nonlinear steel, temperature dependence or losses are inferred.

Unreplaced regions retain their exact constant SPD reluctivity nu and Br:
w=.5(B-Br)^T nu(B-Br), H=nu(B-Br), D=nu. This preserves the complete
reference c=.5d integral Br^T nu Br. Nonlinear replacement of any region
with nonzero Br is forbidden; there is no hidden nonlinear magnet model.

For positive normalized triangle quadrature weights q_k summing to one,

```
U(a)=d sum_e area_e sum_k q_k w(B_ek)
Pi(a)=U(a)-fJ dot a
r_i=d sum_e area_e sum_k q_k C_eki dot H_ek-fJ_i  [A m]
K_ij=d sum_e area_e sum_k q_k C_eki^T D_ek C_ekj  [m^2/H]
Wcurrent=fJ dot a-U
Wmaterial=d sum_e area_e sum_k q_k (H_ek dot B_ek-w_ek).
```

The tangent units above are m^2/H (equivalently A m^2/Wb), because residual is
energy differentiated by a [Wb/m]. Numerical K has these depth-weighted units;
it is not a terminal inductance. All three derivatives use identical fixed
quadrature. Consequently a quadrature approximation can preserve discrete
energy exactly while still having physical integration error. Nonzero fixed
A boundaries exchange work: Wcurrent excludes boundary-source coenergy.
At equilibrium, Wmaterial-Wcurrent=a_fixed dot r_fixed. A reduced coupled
solver must retain boundary reactions and annulus energy explicitly.

Map the unit square (s,t) to barycentrics
(1-s, s(1-t), st). Its triangle Jacobian is s. Product Gauss-Legendre
weights on [0,1] become normalized q=2*s*ws*wt. They are positive; with
order at least two they exactly integrate degree-two polynomials. Nonlinear
energy is generally nonpolynomial and must be independently refined in order
and mesh. No default quadrature order constitutes an error estimate.

B is affine on every P2 triangle. For barycentric lambda,
|B(lambda)| <= sum lambda_i |B(vertex_i)| <= max_i |B(vertex_i)|.
Checking all three vertices therefore enforces the supplied B-H upper range
over the entire element, including locations missed by quadrature.

After fixing one gauge in every connected component, positive quadrature and
positive D give an SPD free tangent (subject to numerical conditioning).
Newton solves Kff delta=-r_free and backtracks on Pi with Armijo coefficient
1e-4 and reduction 1/2. Out-of-range trials are rejected, never clipped into
an admitted material state. Residual convergence is required independently
of the energy roundoff allowance. Failure returns no solved result.

## Interface, limits and verification

`NonlinearP2MagneticOperator(base, bh_curves, quadrature_order=4)` composes the
existing `P2MagneticOperator` without modifying its source. `bh_curves` maps
existing region names to supplied pairs; it replaces each named region's law
entirely. All other tensor permeability and remanence are retained. The base
must remain unmodified while the adapter is alive; operation-boundary
fingerprints now enforce that requirement, and input curve arrays are copied.
Its linear matrices are used only for initial harmonic extension of
nonzero prescribed boundary data, never as the nonlinear solution or a fixed
nonlinear Schur complement.

`assemble(a,J)` returns NumPy residual/field arrays and a CSR tangent under
`residual_a_m`, `tangent_a_m2_per_wb`, `quadrature_b_t`,
`quadrature_h_a_per_m`, `quadrature_energy_j_per_m3`, plus magnetic energy,
material coenergy, current-source coenergy, functional Pi and PM reference.
The residual already contains PM and J. Adding the base PM load again would
double-count it. Geometry and current loads remain accessible through `base`.

`solve(J, dirichlet_a_wb_per_m=..., initial_a_wb_per_m=...)` adds a bounded
Newton driver and reaction/residual history. Initial arrays are copied and
failed trials do not change caller state. With no initial array, nonzero
boundary values use the base harmonic extension; this initial guess can be
outside the supplied curve and is then rejected. It does not establish
existence or convergence for every feasible physical problem. Defaults are
relative residual tolerance 1e-9, absolute tolerance 1e-10 A m, and 60 steps;
step count is limited to 200 and backtracking to 48 trials. Every connected
component requires a gauge. No factor is reused between nonlinear iterates.

Orders 2..16 and at most 2,000,000 total quadrature points are admitted.
Cached curls alone require 96 bytes per quadrature point; fields, material
tangents and sparse assembly require additional bounded working memory. Mesh
and 30,000,000 factor-nonzero limits are inherited. The factor fill limit is
checked after factorization and is not a hard allocator cap. This reference
is synchronous and in-process, without an interruption callback; expose it
only through a worker/subprocess with an appropriate execution budget. It is
not currently a worker/API route or native performance kernel.

Conditioning depends on triangle aspect ratio, source scales and differential
permeability contrast. Sparse solve residual is checked before accepting a
Newton direction. The preserved material endpoint allowance is 1e-13 relative
for floating-point roundoff; no extension of a supplied curve is constructed.
At a knot, roundoff may select either adjacent tangent. Tests check the
one-sided derivative and its positive generalized derivative interval.

Executed 23 October 2026 with the project `.venv/Scripts/python.exe`:

```
-B -m unittest tests.python.test_propulsion_pod_nonlinear_p2 tests.python.test_propulsion_pod_magnetic_p2 tests.python.test_magnetic_fem -q
-B scripts/check_architecture.py
```

All 28 tests passed in 0.164 seconds, including 10 new tests; architecture
checks passed. Independent oracles include analytic triangle moments, tensor
PM equivalence with boundary reaction work, numerical energy/residual
derivatives, positive gauged tangent spectrum, a manufactured nonlinear
quadratic patch, two different nonlinear layers at equal H, adaptive scalar
quadrature, source reciprocity/coenergy derivatives, and rejected range,
material, gauge, budget and unconverged-state cases. The corner-range fixture
is deliberately within range at all quadrature points but outside at a vertex.
No actual material data or real motor field solve was executed.

For A=-x^2/2 and H_y=B_y below 0.5 T, H_y=3B_y-1 above 0.5 T,
the aligned-interface patch reaches maximum nodal error 5.474e-14 Wb/m in
four full Newton steps; free residual is 2.919e-13 A m. For the nonpolynomial
primitive `w=1.5*b^2-.4*b+.04`, A=.3x+.4y+.1xy and depth 0.7 m,
orders 2,4,8 have absolute energy errors 9.095e-8, 1.027e-14 and below the
displayed double-precision difference, respectively, against independent
adaptive scalar integration. These synthetic cases do not establish a general
quadrature error bound. Results explicitly retain `quadrature_converged=false`,
`material_qualified=false`, and `production_qualified=false`.

For coupled-gap integration, assemble each nonlinear domain at its current
state, add the annulus quadratic energy/residual/tangent in the same trace
coordinates, and solve the common free system. Condense a current tangent
only as a Newton linear-system operation; retain the full nonlinear energy
and PM reference for reduced coenergy. A constant L/flux table cannot capture
arbitrary current-dependent saturation. The next section implements a bounded
generic domain/annulus composition. Actual source-material admission and
mesh/quadrature/current/angle refinement remain separate work. The full
repository suite is left to
the integration owner rather than duplicated by this bounded workstream.

Actual H070-20 directional B-H curves, lamination orientation and vendor PM
properties remain absent. Supplying an invented isotropic curve would not
close those physical applicability gaps. No real motor run is part of this
increment.

## Joint nonlinear rotor, Fourier gap and stator

`python/spike_core/propulsion_pod_nonlinear_motor.py` composes the supplied-law
operators with the existing `SeparatedMotor` geometry, Fourier trace matrices,
fixed outer gauge and analytic annular energy. It adds no material dataset,
new gap law, controller step, table surrogate or public worker route. The
derivation below is original. The annular mathematics and primary separation
sources are retained in section 18 of the
[independent full-loop review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md).
The primary field-energy/Newton foundations were reviewed above. For the
installed solver dependency, the official
[SciPy 1.17.0 CG API](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.cg.html)
was read on 23 October 2026: SPD operator/inverse-preconditioner assumptions,
relative/absolute residual criterion, callback and iteration termination.
No external implementation was inspected or copied. Execution used SciPy
1.17.0 and NumPy 2.4.2.

### Independently derived common functional

For each domain d in {r,s}, let A_d=P_d z. Here z contains, in order,
the rotor interior nodal A, stator interior nodal A, rotor Fourier coefficients
c_r, and stator Fourier coefficients c_s. P_d inserts interior values, assigns
interface A_b=V_d c_d and sets fixed exterior A=0. All z entries have units
Wb/m. P is applied by index gather/scatter and small trace multiplication;
no dense global FEM transform is created.

Let F_d contain the three exact winding load vectors obtained from supplied
elementwise chi [1/m^2]. Then J=chi*i, lambda=sum F_d^T A_d [Wb-turn], and

```
U(z,theta)=U_r(P_r z)+U_s(P_s z)+.5*c^T K_gap(theta)*c
Pi(z;i,theta)=U(z,theta)-sum_d i^T F_d^T P_d z
r=sum_d P_d^T r_d + E^T K_gap c
K=sum_d P_d^T K_d P_d + E^T K_gap E.
```

E selects the two coefficient blocks. Each r_d already includes its exact PM
and current source. The full fixed PM energy reference in U_d is retained;
there is no extra PM load added to this residual. U, Pi and coenergy are J,
r is A m and K is m^2/H. The symmetric matrix-free tangent applies P, the
current sparse domain tangents, P^T, and the analytic gap block. With positive
material tangents, full-rank traces and the inherited actual exterior gauge,
the free tangent is positive definite: zero energy variation forces constant
domain fields, the gap joins the constants, and the fixed boundary removes
the remaining common constant.

At converged z*(i,theta), r=0. Differentiating the stationary functional gives

```
Wco(i,theta)=i dot lambda-U(z*,theta)=-Pi(z*;i,theta)
partial Wco/partial i = lambda
torque=partial Wco/partial theta=-.5*c^T K_gap'(theta)*c.
```

Rotor material directions and fixed remanence remain in rotor-local
coordinates; angle enters only the gap rotation. The domain fields change
with angle/current through the nonlinear solve, but their derivative terms
cancel by stationarity. Interface reaction work is retained by the common
functional and trace constraints. Fixed exterior A is zero, so there is no
omitted nonzero exterior-source work. This class does not admit arbitrary
nonzero exterior potentials. Annular energy uses the existing stable positive
sum/difference formula; derivatives use the matching exact K_gap and K_gap'.

### Linear reference as an inverse preconditioner

The prepared domain stiffness is a reference for acceleration, not a frozen
nonlinear constitutive solution. For arbitrary RHS (y_ir,y_is,y_cr,y_cs),
let B_d=K_ib,d V_d. The prepared reference Schur matrix is
S_d=V_d^T K_bb,d V_d-B_d^T K_ii,d^-1 B_d. Direct block elimination gives

```
q_d=K_ii,d^-1 y_id
g_d=y_cd-B_d^T q_d
H=blockdiag(S_r,S_s)+K_gap
c=H^-1 [g_r,g_s]
x_id=q_d-K_ii,d^-1 B_d c_d.
```

This is the exact inverse of the reference constrained linear FEM operator
for every RHS, not just the four prepared source columns. The implementation
reuses the original sparse K_ii factors and factors the small dense H once
per evaluation angle. Domain nonlinear tangents are reassembled on each
accepted Newton state; no nonlinear Schur matrix or nonlinear response is
frozen. CG applies the current tangent and the fixed SPD reference inverse.
The returned step must independently pass the actual residual check
`||K delta+r|| <= min(1e-12,.1*NewtonThreshold)+1e-9*||r||` and a negative
directional derivative. A failed CG result is rejected before line search.
Large tangent/reference contrast can make this preconditioner inefficient;
it does not change the convergence or material-range requirements.

### API and bounded failure behavior

Construct `NonlinearSeparatedMotor(base, rotor_op, stator_op, chi_by_domain)`.
Both nonlinear operators must wrap the exact domain operators of base.
`chi_by_domain` contains rotor/stator E-by-3 arrays, copied on admission.
The existing prepared `_Domain` does not retain chi, so supplying it explicitly
avoids reconstructing source data from a reduced response. Every supplied
phase is checked independently against K_ii Xf and G; a large phase cannot
hide an incorrect weak phase. Zero outer source entries do no work at fixed
A=0 and do not affect this reduced source-equivalence check.

`evaluate(currents_a, angle_rad, include_field=False, initial_unknowns=None)`
returns torque, exact integrated winding linkage, coenergy, energy, Fourier
coefficients, residual/Newton/CG diagnostics and a detached read-only potential
snapshot. With `include_field=True`, both complete local P2 potential arrays
are returned as detached read-only snapshots. A warm start is copied and
checked; no previous result is stored or modified. The zero initial field is
feasible for all admitted zero-origin B-H laws; imposed remanence drives the
subsequent solve. Out-of-range trial fields are backtracked and no failed
solve is reported as converged.

Limits are 500,000 joint unknowns, default Fourier cutoff ceiling 255 (1,022 total trace
coefficients), 200 Newton steps, 5,000 CG iterations per step, 48 backtracks,
and at most 600 seconds per evaluate call. Defaults are 60 Newton steps,
1,000 CG iterations and 60 seconds. Time uses a high-resolution monotonic
performance counter and is checked between assembly/factorization/CG
operations; it cannot interrupt an active BLAS or SuperLU call. The two
nonlinear operators retain their respective quadrature/memory budgets.
Only the trace Schur block is dense. No allocator-hard memory cap, native
kernel or large actual-motor performance qualification is claimed.

The 24 October modal extension preserves the default 255 ceiling and allows
explicit opt-in up to 1024 with a preallocation byte allowance and separately
identified solver options. Gap action, energy and torque now use exact modal
evaluation; only the reference Schur is dense. See
[the modal implementation/evidence record](PROPULSION_POD_MODAL_GAP_20261024.md).
High-mode algebraic tests do not establish whole-process resource admission or
actual-material validity; those remain separate gates.

### Executed synthetic coupled evidence

The six tests in `test_propulsion_pod_nonlinear_motor.py` passed on
23 October 2026. They check the linear limit against an independently
assembled full constrained FEM system, the preconditioner on an arbitrary
RHS, joint nonlinear current/angle coenergy derivatives, detached snapshots,
failed-step preservation, and source/operator/range/gauge/time/iteration
budget rejection. A separate test scales one phase by 1e12 and proves that a
mismatch in another phase remains rejected.

The combined nonlinear motor, nonlinear P2, linear P2, annular-gap,
separated-motor and P1 magnetic suites passed all 39 tests in 0.380 seconds;
`scripts/check_architecture.py` also passed. The full repository suite remains
the integration owner's check.

The nonlinear fixture has 12 rotor sectors, two stator radial rings,
Fourier cutoff 2, depth .01 m, original PM regions and explicitly synthetic
isotropic saturating curves in rotor steel and stator. It is deliberately
not the OpenMotor geometry or material. At i=(12000,-8000,-4000) A and
theta=.31 rad, the supplied synthetic model gives coenergy
-151.8685611511979 J and torque -6.217247580422654 Nm. Five Newton steps
use lengths (.5,1,1,1,1), CG counts (1,18,17,18,15), and final residual
7.647e-12 A m. Independently resolving theta+/-1e-4 gives a torque derivative
error 1.373e-8 Nm; independent current perturbations +/-0.1 A give phase
linkage derivative errors no larger than 4.105e-14 Wb-turn. These are
mathematical reference values, not hardware predictions.

This completes the generic nonlinear field composition only. Actual H070-20
directional static curves, lamination orientation, PM data and source-material
admission remain open. Quadrature, geometry, Fourier cutoff and actual torque
refinement, controller coupling to a current-dependent field port, physical
losses and knowledgeable human review remain separate gates. Results retain
false material, quadrature and physical/production qualification flags.

## Constitutive provenance and mutation guard correction

Independent review identified a provenance defect in the first coupled
increment: results copied the prepared linear `spec_sha256`, although changing
the supplied B-H law changed the solved physical model. Original source and
geometry identities alone do not identify the nonlinear constitutive model.
The corrected P2 and coupled interfaces now report a separate
`constitutive_sha256` and detached `constitutive_model` descriptor.

The P2 descriptor records every exact copied B-H pair, SI column names,
admitted magnitude range, forbidden extrapolation, single-valued isotropic
law status, and caller-supplied/unverified provenance. Unreplaced regions
record their exact constant tensor reluctivity, remanence and PM energy
reference convention. No measured-data attribution, source license, grade,
batch or calibration provenance is invented. Supplied material qualification
remains false. Depth, prepared operator fingerprint and the actual quadrature
rule/order/points/weights are bound into the identity.

Canonical descriptor JSON uses sorted keys, compact separators, finite
numbers and UTF-8 before SHA-256. Large operator arrays use sorted named
shape/dtype records followed by contiguous little-endian float64 or int64
bytes, without expanding meshes or sparse matrices into JSON. The prepared
operator fingerprint includes coordinates, elements, connectivity, regions,
basis geometry, all reluctivity/remanence values, gauge metadata, PM source
and reference, and CSR stiffness. The coupled descriptor binds both domain
constitutive identities, trace and exact winding/source arrays, the Fourier
gap definition, and the original prepared source/geometry/spec identities.
These hashes identify supplied numeric content; they are not authenticity
certificates or measured-material qualification.

The coupled result retains original `source_sha256` and `geometry_sha256`
separately. Original linear spec identity is explicitly nested inside
`prepared_linear_model_identity`; it is no longer returned as the nonlinear
top-level `spec_sha256`. Different supplied curves or quadrature give different
constitutive identities while the actual source/geometry identifiers can stay
the same. Returned descriptors are deep copies; editing one cannot change a
subsequent result or the model used to solve it.

Owned material and quadrature arrays are read-only. Public P2 `assemble`
checks dependencies at entry and result construction; standalone `solve` and
coupled `evaluate` check at entry and exit. Checks cover the wrapped numeric
operators, derived owned arrays, source/trace/gap data and identity metadata.
Opaque prepared SuperLU factors are retained by object identity; replacing
one is rejected. No expensive array hashing occurs inside a tangent matvec
or line-search trial: those run through a private assembly path within the
guarded operation. Dependency changes require constructing a new operator and
new identity. Concurrent mutation during a call is unsupported; endpoint
checks are consistency guards, not isolation against hostile in-process code.

Four new tests establish repeatable equal-input identities, different-law
and different-quadrature identities, exact detached law/range/unit metadata,
and read-only supplied data. They additionally verify that two models sharing
one prepared motor but using different supplied B-H curves produce different
coenergy and identities, and that wrapped material, trace, gap, source
identity and factor replacement are rejected on repeated evaluation. This
correction changes provenance/admission only, not the field equations or
material applicability gates.

After this correction all 43 adjacent magnetic/coupled tests passed in 0.573
seconds and the architecture check passed. The actual source comparison's
Fourier cutoff 1007 exceeds this bounded nonlinear reference's cutoff 255;
the limit remains unchanged. This reference is not admitted for that actual
case without separately justified memory, conditioning and convergence work,
in addition to the missing material/orientation data.

## 24 October: bounded element tangent contraction

The later modal-gap extension admits explicit high-mode generic experiments;
it does not change material qualification. The first actual-domain linear-limit
attempt at Fourier 1007, with empty supplied-law replacements and the unchanged
illustrative linear materials, failed at the 2 GiB process limit during initial
stator tangent assembly. Neither nonlinear comparison case completed. The
preserved failure and allocation proposal are under
`output/promo-propulsion-pod-20261023/real_motor/actual-domain-linear-limit-v2-20261024/`
and `nonlinear-assembly-allocation-proposal-20261024.md` in its parent directory.

The independently authored pre-implementation derivation is
[bounded assembly review](PROPULSION_POD_NONLINEAR_ASSEMBLY_MEMORY_REVIEW_20261024.md).
For each element, the same tangent is
`K[e,i,j] = sum(q,a,b) w[e,q] C[e,q,i,a] D[e,q,a,b] C[e,q,j,b]`.
The element index is not summed, so partitioning it into contiguous batches
and filling corresponding slices of the preallocated `(E,6,6)` result preserves
the real-arithmetic operator and existing COO/CSR ordering. Binary64 summation
may differ with optimizer ordering; bitwise tangent identity is not claimed.
Quadrature, constitutive values/ranges, residuals, energies, public fields,
identity/options, reference factors, solver tolerances and all other state
lifetimes remain unchanged.

Private `_tangent_batch_size(Q)` is
`min(1024,max(1,8388608//(4*Q*6*2*8+36*8)))`. This models four curl-shaped
binary64 scratch arrays plus one batch local matrix against 8 MiB, separately
from the full output, constitutive arrays, sparse conversion, fields and live
reference factors. For Q=4,16,36,256 the sizes are 1024,1024,594,85. It is an
explicit storage estimate, not a native allocator or whole-process guarantee.
No large run or actual-domain memory admission follows from this change.

Installed NumPy 2.4.2 / SciPy 1.17.0 were used. Symbolic `einsum_path` probes
at all four batch sizes record the optimizer's intermediate order in
`output/promo-propulsion-pod-20261023/real_motor/nonlinear-p2-tangent-batching-checks-20261024.json`.
The reviewed primary NumPy manual's explicit-output, `out`, and `optimize`
semantics are cited in the independent review; its served v2.5 documentation
version is not asserted to match installed v2.4.2. No external implementation
or example was copied. The governing energy/tangent derivation above is unchanged.

Three new tests independently check: scalar-index sums using `math.fsum` on
nonconstant SPD tensors for batches one/all/partial; instrumented operand and
output element extents at Q=4 and Q=256; and full assembly against the original
unbatched contraction on anisotropic remanent regions plus nonlinear supplied
B-H replacement regions. CSR indices/row pointers and all non-tangent outputs
are unchanged; tangent agreement uses `rtol=atol=2e-14`. The existing derivative,
range, solved-reference, modal-angle, stable-energy and direct-port checks were
also executed: 38 tests passed in 7.501 s. Twelve adjacent geometry-loop,
energy-step and energy-table tests passed in 21.879 s, including the short
manufactured nonlinear field loop with the compiled controller. Architecture
checks passed. These manufactured checks do not qualify actual motor material.

Reviewed source targets for this change:

* `propulsion_pod_nonlinear_p2.py`: SHA-256
  `6a6b97d4f9b4e6a9cb063d31044f71ad8091918e6aab103163c6c52fb0d305e1`.
* `test_propulsion_pod_nonlinear_p2.py`: SHA-256
  `4a02c022216d7979e00c2faf56ff057457e39310d797c26dbb614cc03394923b`.

Only after independent diff/test review and separate authorization may a fresh
actual-domain attempt use the unchanged resource and physical acceptance gates.
