<!-- SPDX-License-Identifier: Apache-2.0 -->
# CR/P0 Stokes constant-velocity nullspace repair - 23 October 2026

Parent integration replay: all39 Stokes/mesh/energy/CAD-transfer test methods
passed in30.492 seconds with the unchanged budgets and single BLAS/OpenMP thread.
An earlier broader run had38 passes and one default-runtime-budget rejection
in the sheared quadratic manufactured case (47.348 seconds total). That case
passed alone in15.450 seconds before the broader replay. Runtime sensitivity
is retained as a qualification observation; transient load is plausible but
not proven as the cause. No deadline, refinement level or assertion was relaxed.

## Bounded claim and retained model

This repairs the uniform-translation rejection recorded in
[the original kernel evidence](CFD_TETRA_STOKES_20261021.md). It changes
floating-point evaluation, not the governing model: steady constant-property
creeping flow, broken vector Laplacian, CR face-average velocity and P0 cell
pressure. Natural data remain pseudo-traction `(mu grad(u)-p I)n`, not
symmetric Newtonian stress. No inertial, turbulent, thermal or production
qualification is added. Knowledgeable human numerical release review remains
required under [the evidence policy](../NUMERICAL_METHOD_EVIDENCE.md).

## Reviewed primary foundation and independent scope

On 23 October 2026 the primary Numdam text of M. Crouzeix and P.-A. Raviart,
*Conforming and nonconforming finite element methods for solving the stationary
Stokes equations I*, RAIRO 7(R3), 1973, 33-75,
[DOI 10.1051/m2an/197307R300331](https://doi.org/10.1051/m2an/197307R300331),
[article](https://www.numdam.org/item/M2AN_1973__7_3_33_0.pdf), was revisited:
section 2, (2.12)-(2.22), printed pages 36-38; section 5 Example 4,
(5.1)-(5.8), pages 58-60; section 7, (7.1)-(7.8), pages 72-73.
These establish the broken gradient form, affine face-centroid/average space,
divergence preservation and compatible inhomogeneous boundary data. The
constant-lift implementation, cancellation analysis, force adjoint, oracles
and fixtures below are independently authored SPIKE work, not algorithms or
code copied from that paper. No third-party implementation was inspected.
The paper does not certify this mixed-boundary implementation, its rounding
behavior, or physical predictive accuracy.

## Cause, derivation and unchanged acceptance

For one tetrahedron let `g_i = grad(phi_i)` and `sum_i g_i = 0`.
With vector face values `U_i`, define the exact linear map

```text
G(U) = sum_(i=1..3) (U_i-U_0) outer g_i.
D(U) = mu V G(U):G(U).
q_i = mu V G(U) g_i, i=1..3; q_0 = -sum_(i=1..3) q_i.
sum_i U_i.q_i = mu V G(U):G(U).
```

Thus `q = G^T (mu V) G U`, the original viscous operator applied in
factored form. The assignment of `q_0` is the transpose of the subtraction
map, not a clamped force or a zero-work special case. All gradients, stresses
and reactions are evaluated for arbitrary fields by this same map. Dimensions
are `G(U)` in 1/s, `mu` in Pa s, `V` in m3, `q` in N, and work in W.

Previously, gradients already used `U_i-U_0`, but Dirichlet reactions used
the independently rounded sparse `K U`. For `U_i=c`, the exact quantities
are both zero. Floating-point assembly and sparse multiplication can produce
`O(eps |K| |c|)` forces, whose work is first-order in roundoff. Direct gradient
dissipation of solve error is second-order. Dividing this difference by the
tiny reaction-power scale produces an order-one relative defect, despite an
accurate velocity. A larger acceptance denominator would hide this discrepancy;
the repair instead preserves the mathematical nullspace in the evaluation.

On each connected component choose `c` as the supplied velocity on its first
prescribed face. Write `U=W+c`. A constant vector has zero broken gradient
and divergence, hence `K c=0`, `B c=0` in exact arithmetic. Solve the existing
eliminated saddle system for `W`, prescribing `g-c`; keep body and natural
loads unchanged. Then restore `U=W+c` and the supplied prescribed entries.
This change of variables is applied to every solve, including nonuniform and
nonzero-load cases, with independent lifts on disconnected components.
The stiffness, pressure coupling, congruence scales, conditioning estimate,
gauges and factor/iteration budgets are unchanged. Constant data and zero
loads now give exactly zero correction RHS, rather than cancellation between
large equal terms. This is not a condition estimate for general unresolved
small perturbations riding on a large translation.

Compute reactions from assembled `q-B.T p-load` on prescribed DOFs. Compute
dissipation directly from `G(U)`, and retain the original work denominator
and `1e-9` energy threshold. The original sparse `K U-B.T p-load` free
momentum residual still runs on returned absolute `U`, using the unchanged
separate-term scale and `1e-10` threshold. Cell mass uses the original `B U`,
not a forced-zero flux. Scaled lifted-system residual remains `<=1e-10`,
inverse residual `<=1e-13`, cell mass `<=1e-10`, condition estimate `<=1e10`,
Reynolds `<=0.1` and backflow relative budget `<=1e-10`. No gate is skipped,
no load is zeroed and no artificial physical floor is introduced. Existing
overflow/underflow traps and fail-closed output behavior remain.

Both viscous representations are equivalent in exact arithmetic, but can
differ by rounding. The existing absolute-field momentum and local mass
checks remain necessary after lifting; the factorized energy check is not a
replacement for them. Nonzero work very near roundoff can still be rejected.

## Executed evidence

Windows, Python 3.12.9, NumPy 2.4.2, SciPy 1.17.0; local `.venv`;
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`. All 14 focused test methods
passed in 16.442 seconds, with unmodified default 30-second solve deadlines.
`python scripts/check_architecture.py` also passed; the numerical module is
468 lines, below the 500-line guard.
An initial run had 12/13 passing methods because the newly written forged-load
test indexed the prescribed mask instead of free DOFs. Correcting that test
index exposed the intended momentum rejection; it did not change solver code.

The original sheared 48-tetrahedron `(0.001,0,0) m/s` case was reconstructed
through the unchanged unlifted private solve and old reaction arithmetic:

| Observable | Original evaluation | Repaired solve |
| --- | ---: | ---: |
| Maximum face-velocity error, m/s | 8.67361738e-19 | 0 |
| Broken-gradient dissipation, W | 1.66531832e-35 | 0 |
| Dirichlet reaction work, W | -6.33923997e-21 | 0 |
| Relative energy defect | 0.143605582 | 0 |
| Scaled linear residual | not measured in this probe | 0 |
| Absolute-field momentum residual | not measured in this probe | 4.01838861e-16 |
| Maximum scaled cell mass residual | not measured in this probe | 8.61245737e-17 |

The expanded independent constant-field oracle checks 18 combinations of
length/viscosity pairs `(1e-3 m,1e-3 Pa s)`, `(1 m,1 Pa s)`,
`(1e3 m,1e3 Pa s)`, speeds `0`, `1e-9`, `1e-3 m/s` times direction
`(1,-0.2,0.3)`, and original versus spatially translated geometry. All use
rotated/sheared tetrahedra and density 1 kg/m3. Returned face velocities,
pressure, gradient and work are compared to the analytical constant solution,
not just completion status. A natural-outlet uniform flow and independently
translated disconnected components also pass. Across the 18 cases plus the
natural-outlet case, maximum momentum residual was `4.58870973e-16`, maximum
scaled mass residual `1.58194382e-16`, and energy defect exactly zero.

Nonzero force under uniform boundary translation produces nonzero pressure,
dissipation and body work; the force is not erased. A 1% forged inverse action
is rejected by the unchanged scaled residual, a forged free-DOF body load
by momentum, and 1% corrupted reconstruction gradients by power balance.
Existing incompatible mass, backflow, high-Re, conditioning, arithmetic,
malformed input, cancellation, runtime and no-mutation controls still pass.

The prior SI affine patch and both full continuum refinement sequences pass:

| Oracle | Cells | Relative velocity L2 | Relative pressure L2 |
| --- | ---: | ---: | ---: |
| Poiseuille | 48 | 0.2430267248 | 0.4373828146 |
| Poiseuille | 384 | 0.0893160771 | 0.1909833640 |
| Poiseuille | 3072 | 0.0266460188 | 0.0632215249 |
| Sheared quadratic | 48 | 0.0618933608 | 0.3161668190 |
| Sheared quadratic | 384 | 0.0215632597 | 0.1753390862 |
| Sheared quadratic | 3072 | 0.0066358433 | 0.0756307938 |

Finest energy defects are `1.28411160e-15` and `2.21269453e-17`, respectively.
The unchanged order, pressure and finest-error assertions all pass.

Reproduction (the receipt used a wrapper printing returned diagnostics and
independent `errors()` outputs; the same suite is run by this command):

```powershell
$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'
.venv/Scripts/python.exe -m unittest tests.python.test_cfd_tetra_stokes -v
```

Source SHA-256:

- `python/spike_core/cfd_tetra_stokes.py`:
  `627abbbdc7ed9c54df2615f86e378e80355229ba26c4b9be6e7453a443dc477c`
- `tests/python/test_cfd_tetra_stokes.py`:
  `c1880fd256fc1384157d2960a156963ec1f588af6b5589aa607ef1980d8ef8a4`

This is synthetic code verification. No experimental measurements, universal
roundoff/error certificate or broader CFD/CHT qualification is claimed.
Wider integration checks are recorded by the parent integration work.
