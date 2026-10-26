<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent scalable tetrahedral DC screens

Reviewed and executed 24 October 2026. Status: bounded experimental evidence.
The independently authored tests in `tests/python/test_dc_tetra_scaling.py`
exercise the explicit scalable request and retained-result validator. They do
not establish 50,000-cell capacity, 100,000-cell admission, board completeness,
physical validation, production qualification, or the knowledgeable human
review required before numerical code release.

## Sources actually reviewed

- SciPy online `eigsh` API reference: parameters `sigma`, `OPinv`, `which`,
  `v0`, `maxiter`, and `tol`, plus the normal shift-invert transformation in
  Notes. The unversioned page served the SciPy 1.18.0 manual during review:
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.eigsh.html>.
- SciPy online `splu` API reference: CSC input, column permutations, diagonal
  pivot threshold, options, and the returned factor object's solve operation.
  The unversioned page served the SciPy 1.18.0 manual:
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.splu.html>.
- Official SuperLU FAQ, section "Symmetric or diagonally dominant problems":
  symmetric mode, ordering, pivot threshold, the possible remaining row
  permutation, and the approximate transpose relation of the factors:
  <https://portal.nersc.gov/project/sparse/superlu/faq.html>.

The execution environment used SciPy 1.17.1 and NumPy 2.2.6. Attempts to open
the versioned SciPy 1.17.1 reference URLs were unavailable through the browser;
this review does not claim to have read those pages. The tested installed API
accepted the options used. No linked external implementation or example code
was inspected or incorporated. Equations, fixtures, tests, and prose here are
independently authored; citations establish method provenance, not imported
implementation or redistribution rights. The governing steady Ohmic model,
RT0 definition, SI units, and physical limitations remain those documented in
[the original independent oracles](DC_TETRA_RT0_ORACLES.md).

## Exact-arithmetic reasoning and its numerical boundary

Let A be the assembled, gauged, diagonally scaled trace operator. The physical
construction supplies symmetry and nonnegative local energy; component gauges
remove the constant-potential nullspaces. The scalable solve must preserve that
construction. An arbitrary matrix passed to the private sparse helper has no
such physical provenance.

For symmetric positive definite A, normal shift-invert at zero has eigenvalues
1/lambda. Its eigenvalue of largest magnitude corresponds to the smallest
positive eigenvalue of A, and a separate largest-algebraic eigenvalue gives the
other endpoint needed for the spectral condition number. Reusing the same
sparse factorization for inverse actions and the final linear solve avoids
another factorization.

Positive diagonal entries and a positive eigenvalue nearest zero do not prove
positive definiteness. To expose that gap, take the orthogonal four-by-four
Hadamard matrix H (entries +/-1/2), and form

    B = H diag(-2, 1, 4, 8) H^T.

All four diagonal entries of B equal 2.75, yet B has a negative eigenvalue.
Append 128 independent diagonal entries equal to 2 to exercise the sparse
path. A nearest-zero search returns +1 and a largest-algebraic search returns
+8, hiding -2. Before the symmetric-factor screen, this matrix was accepted
with estimated condition 8 and an eigenpair residual about 2.8e-15. Tiny Ritz
residuals alone therefore did not close the flaw.

The implemented additional screen uses a common row/column permutation,
positive finite elimination pivots, and U approximately equal to D L^T, where
D is the diagonal of U. In exact arithmetic, if

    P A P^T = L D L^T,

L is nonsingular and all d_i are positive, then for every nonzero vector x,
the vector y=L^T x is nonzero and

    x^T P A P^T x = sum_i d_i y_i^2 > 0.

This is the congruence argument underlying the positive-pivot test. The
implementation requests symmetric ordering/mode, zero pivot threshold, and
no equilibration, then verifies that the actual permutations agree rather
than assuming the requested mode guarantees that property. The negative-mode
fixture now rejects at both 4 and 132 rows.

This remains a floating-point screen. The U versus D L^T discrepancy allowance
is 1e-8 times the largest absolute U entry; no bound is proved for the complete
factorization backward error relative to the smallest eigenvalue. Positive
computed pivots and this discrepancy test are not certified inertia, especially
near the permitted condition limit of 1e12. Rejecting unexpected pivots can also
reject some otherwise solvable systems. Neither the FAQ nor the tests establish
unconditional stability for every admitted mesh.

For a normalized approximate symmetric eigenpair (theta,v), expansion in an
orthonormal eigenbasis gives

    ||A v - theta v||^2 = sum_j |c_j|^2 (lambda_j-theta)^2.

Consequently some eigenvalue lies within the residual norm of theta. This
does not independently prove that the nearby eigenvalue is the global minimum
or maximum. Subtracting/adding measured Ritz residuals to estimated endpoints
is useful screening, but the reported condition remains explicitly an
estimate, not a certified enclosure. The fixed initial vector makes these
tests reproducible; it does not turn an iterative eigensolve into a proof.

The field conservation and power gates remain separate and necessary. Residual
correction reuses LU at most three times; its 1e-12 relative RHS stopping target
does not replace the component-scaled 1e-9 flux and work/heat acceptance checks
in the caller and retained-result validator.

## Independent test oracles

1. **Beyond the legacy cap:** a uniform one-metre cube split into 6,000
   tetrahedra, sigma=2 S/m and opposing full-face currents +/-3 A. Continuum
   conservation gives J=(3,0,0) A/m^2, resistance 0.5 ohm, heat 4.5 W, and
   volume 1 m^3. Every reconstructed vertex field is checked with absolute
   tolerance 1e-8 A/m^2 and zero relative tolerance; power tolerance is 4.5e-9 W.
   The retained result is independently validated and remains non-production.
2. **Elongation and material contrast:** an 8 by 0.5 by 0.25 m prism, split
   halfway into sigma=2 and 8 S/m regions, driven by 0.25 A. With area 1/8 m^2,
   series resistance is 4/(2 A)+4/(8 A)=20 ohm, J=2 A/m^2, terminal drop 5 V,
   and power 1.25 W. New and legacy traces agree within 1e-9 V absolute;
   fields use 2e-8 A/m^2 absolute tolerance. This modest contrast and aspect
   ratio do not represent extreme PCB foil or contact singularities.
3. **Component scale:** 24 disconnected unit cubes retain all 24 m^3; one is
   driven at 1 A, one at 1e-12 A, and 22 are undriven. The weak component's
   power is independently 5e-25 W, and its field checks scale to its own drive.
   All 24 gauges and all 22 m^3 of undriven volume remain present. A strong
   component cannot provide the weak component's absolute error allowance.
4. **Independent spectrum:** the tridiagonal matrix with diagonal 2 and
   adjacent entries -1 has vectors sin(i k pi/(n+1)). The sine addition formula
   gives eigenvalues 2-2 cos(k pi/(n+1)); thus both extreme eigenvalues and the
   condition number are known without another eigensolver. Sizes 12 and 256
   exercise both spectrum paths, check the solved sine mode to 1e-11 absolute,
   check relative condition error below 1e-7, and assert only one LU factorization.
5. **Adversarial admission:** the hidden negative mode and diagonal condition
   1e14 reject on both small and sparse paths. Oversized requests, oversized
   matrices, asymmetry, and pre-solve cancellation reject before the relevant
   expensive geometry audit or factorization.
6. **Thin admitted cells:** a 1 by 0.73 by 0.001 m prism, divided into six
   tetrahedra, with sigma=2 S/m and current 0.00073 A. Its exact uniform field
   is (1,0,0) A/m^2, power 0.000365 W, and volume 0.00073 m^3. The test checks
   every signed face flux against independently computed outward cross-product
   area normals, every trace against the affine potential at the face centroid,
   each cell mean against both the centroid potential and mean trace, plus
   current field, power, volume, and independent retained-result validation.
   The field tolerance is 1e-8 A/m^2 absolute and power tolerance 3.65e-13 W;
   the production symmetry, conditioning and conservation gates are unchanged.

The meshes reuse original SPIKE fixture geometry; the field, energy, spectrum,
and component-scale oracles do not call the production assembly to construct
their expected answers. No external mesh or solver implementation was used.

## Direct local Gram operator for thin cells

The six-cell thin fixture above was admitted by the existing geometry audit,
but the inverse-mass-minus-rank-one local operator produced maximum scaled
asymmetry 6.144564816595653e-14, exceeding the unchanged 128-epsilon guard of
2.8421709430404014e-14. Reducing the thickness to 1e-4 m increased the observed
asymmetry to 5.387163085895221e-13. These are reproduced numerical observations
in the stated environment, not universal floating-point lower bounds.

The scalable profile now forms an algebraically equivalent local Gram matrix,
avoiding the inverse/projection subtraction. The legacy profile is unchanged.
The following derivation uses only source-free scalar RT0 geometry and the
steady constitutive law already established in the original oracles.

For tetrahedral vertices v_i, volume V, cell centroid c, and face centroids
c_i=(sum_j v_j-v_i)/3, let N_i be the outward unit normal multiplied by face
area. With N containing these four row vectors,

    sum_i N_i = 0,        N_i = -3 V grad(b_i),

where b_i is the vertex barycentric coordinate. Its gradient points from the
opposite face toward v_i, with magnitude equal to inverse altitude; the volume
identity V=area*altitude/3 establishes the sign and factor three.

There is a unique affine scalar potential whose face-centroid values are the
four trace values lambda_i. Since the mean of the four c_i equals c,
its volume mean p is the arithmetic mean of lambda. The divergence theorem,
applied componentwise to its gradient, gives

    grad(phi) = (1/V) sum_i lambda_i N_i,
    J = -(sigma/V) N^T lambda,
    q = N J = -H lambda,        H = (sigma/V) N N^T.

Here J has units A/m^2, N has units m^2, q has units A, H has units S,
and lambda and p have units V. In exact arithmetic H is symmetric positive
semidefinite of rank three for a nondegenerate tetrahedron, with the constant
trace as its nullspace, because

    z^T H z = (sigma/V) ||N^T z||^2.

The mean trace is also the mixed RT0 cell potential. The unit-flux basis is
psi_i=(x-v_i)/(3V), so for constant J,

    integral_T (J/sigma) dot psi_i dx = J dot (c-v_i)/(3 sigma).

As c_i-c=(c-v_i)/3, the affine constitutive law makes this expression equal
to p-lambda_i. Thus the direct Gram operator satisfies the original four
local mixed weak equations; it is not a different electrode or material model.
Its power is V ||J||^2/sigma, and sum q_i=0 follows from sum N_i=0.

The implementation obtains normals from independently audited geometry
gradients and subtracts one local trace before the matrix-vector product,
using the constant-trace nullspace to reduce gauge-dependent cancellation.
The retained validator still reconstructs RT0 fields from the recorded q,
checks signed cross-product face integrals, performs independent quadrature,
and checks the local weak law. Producing a constant field directly does not
waive that independent q-based verification.

This formulation removes one demonstrated cancellation mechanism; it does
not repair degenerate geometry or promise accurate arbitrarily thin cells.
Inexact gradients, normal closure, trace subtraction, global conditioning and
field reconstruction can still limit accuracy. Existing geometry admission,
symmetry, positive-pivot, condition, component-current, and power gates remain
required and may reject more demanding meshes.

## Resource interpretation

The original request contract remains limited to 5,000 cells, 10,000 nodes,
and 16 MiB encoded input. The separate
`spike/tetra-dc-rt0-scalable-request/v1` admits at most 50,000 cells, 50,000
nodes, and 64 MiB encoded input, subject to all existing geometry audits.
The shared geometry audit's own larger ceiling does not increase this request
profile's limits. Component reductions use grouped sums rather than rescanning
all cells or faces separately for every component.

The helper limits trace matrices to 200,000 rows and 800,000 stored entries,
and retained L/U factors to a combined 16 million entries. The latter is a
post-factorization rejection: it does not bound allocation peaks during LU,
factor extraction, or the transpose-discrepancy calculation. Cancellation
callbacks between phases cannot interrupt a native factorization already in
progress. Real board runs therefore need process-level memory and wall-time
limits with measured native peak memory, and output/retention limits. This
test run did not measure those peaks or verify a supervisor configuration.

No 20k, 50k, or 100k physical solve was executed by this independent suite.
The passing 6,000-cell cube proves a specific analytical case above the old
limit, not a scaling law, worst-case fill bound, or readiness of arbitrary
thin, heterogeneous board meshes. Larger acceptance needs actual bounded runs
and independently checked physics, not a cap increase alone.

## Executed verification

Ordinary imports from the published repository modules, without scratch aliases:

```powershell
.venv-emerge3/Scripts/python.exe -B -m unittest tests.python.test_dc_tetra_scaling -v
```

Initial result: **7 tests passed, 19.486 seconds**, after explicitly setting zero
relative tolerance for the analytical field, trace-equivalence, and sine-mode
comparisons. An earlier run before that tolerance tightening also passed.

After the direct local Gram change and the eighth scaling test, the ordinary
import regression command was:

```powershell
.venv-emerge3/Scripts/python.exe -B -m unittest tests.python.test_dc_tetra_scaling tests.python.test_dc_tetra_rt0 tests.python.test_dc_tetra_evidence tests.python.test_dc_board_review -v
```

Result: **28 tests passed, 44.209 seconds** (8 scaling, 14 original tetrahedral,
4 evidence, 2 composition-review tests). The thin test also passed alone in
0.017 seconds. An earlier combined invocation used a nonexistent evidence
module name, causing a loader error; the corrected complete command above
passed. These timings are observations, not controlled performance benchmarks.
Only these focused checks are reported here; full repository checks, larger
real-board runs, and human release review belong to the integration owner.
