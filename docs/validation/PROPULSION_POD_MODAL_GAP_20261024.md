<!-- SPDX-License-Identifier: Apache-2.0 -->
# Modal annular action and bounded nonlinear Fourier opt-in

This is an algebraic evaluation of the existing source-free annular energy.
It adds no magnetic law, material measurements, mesh/cutoff convergence,
actual-motor qualification, or controller integration. Independent
pre-implementation review is in
[PROPULSION_POD_MODAL_GAP_REVIEW_20261024.md](PROPULSION_POD_MODAL_GAP_REVIEW_20261024.md).
The shared `AnnularGap` and linear `SeparatedMotor` implementations are unchanged.

## Mathematical derivation and references

The governing separation-of-variables foundation and primary source versions
are retained in section 18 of
[the full-loop review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md): Seto,
MATH124B notes, 5 September 2016, section 2.4; Ivrii, PDE textbook, section
6.4.1, equations 6.4.10--11 and annulus remark. The independent original
derivation, radial integral and Maxwell-stress comparison there were reused.
This change does not claim a new reading or implementation of those external
sources. The following derivative was independently derived from that
already-reviewed energy before code was written.

Let L=log(b/a), kappa=depth/mu0, u=R(n theta)r, t=tanh(nL/2),
p=u+s and v=u-s for rotor/stator real orthonormal Fourier pairs r,s.

```
E_n = kappa*n/4 * (t*|p|^2 + |v|^2/t)
grad_u E_n = kappa*n/2 * (t*p + v/t)
grad_r E_n = R.T grad_u E_n
grad_s E_n = kappa*n/2 * (t*p - v/t).
```

This gradient is linear in the coefficients and therefore is also the exact
Hessian action on a coefficient increment. It preserves the positive
sum/difference representation rather than subtracting nearly equal large
quadratic energies. With B=kappa*n*csch(nL), R'=nJR,
J=[[0,-1],[1,0]], the angle-derivative action is
`[-B*(R')^T*s,-B*R'*r]` and rotor torque is `B*n*s.T*J*u`.
The mode-zero energy is `kappa*(r0-s0)^2/(2L)`, with gradient
`[kappa*(r0-s0)/L,-kappa*(r0-s0)/L]` and exactly zero torque.
Equal constant traces remain an exact null vector. No gap jitter is added;
the inherited outer boundary fixes the full coupled gauge.

Coefficients have units Wb/m, their energy gradient A m, energy J, and
mechanical torque N m. The modal diagonal/cross entries used to construct the
reference Schur are kappa*n*coth(nL) and kappa*n*csch(nL), evaluated using
decaying exponentials and expm1. The two formulas are algebraically equivalent.
Thin-gap conditioning remains a property of the operator, not evidence of
unconditional accuracy or admissibility.

`ModalGap` snapshots one validated annulus and angle. Action, angle action,
energy and torque use O(N) storage and work. `add_to_dense` adds the same exact
entries into a caller-owned writable float64 matrix. It creates no joint dense
gap/derivative matrix internally. Scalar and array finite-range failures are
rejected. Existing linear/PM terms, supplied B-H range guards, common energy,
nonlinear tangent, actual CG residual check, and Armijo condition are unchanged.

## Integration and resource contract

The nonlinear class constructs a private Fortran-order reference matrix
`H=blockdiag(S_rotor,S_stator)+K_gap` once per evaluation angle, using modal
entry insertion, and factors it once. Its inverse remains the exact unchanged
linear-reference inverse for arbitrary RHS, as derived in
[the coupled nonlinear record](PROPULSION_POD_NONLINEAR_P2_20261023.md).
Current nonlinear domain tangents are reassembled; no nonlinear response is
frozen. No iterative inner Schur solver or changed CG assumption is introduced.

The installed SciPy **1.17.0** `cho_factor` docstring, Parameters/Notes/Returns,
was read on 24 October 2026. It specifies the selected-triangle factorization,
optional overwrite and entire-array finite check; the unused factor triangle
does not represent a second factor. The official versioned web fetch timed
out, so the installed primary dependency documentation was used directly.
`overwrite_a=True` permits reuse of the private H; it is not treated as a
guarantee of native zero-copy or peak-memory behavior. Finite checking stays on.

Constructor options are now:

```
maximum_unknowns=500000
maximum_fourier_mode=255
maximum_dense_reference_bytes=512*1024**2
```

The mode budget is an explicit integer/non-bool in 0..1024. A prepared cutoff
above the default 255 still fails unless the caller opts in. Dense allocation
is rejected before winding/load work if
`3*8*(2*(2N+1))^2 > maximum_dense_reference_bytes`; the byte option is a positive
integer/non-bool capped at 512 MiB. The three dense-equivalent arrays reserve
H, a possible factor copy, and one workspace allowance. At cutoff 1007 this is
389,781,600 B, and at 1024 it is 403,046,496 B. This is an explicit dense-array
allowance, **not a proven whole-process peak bound**. Native workspaces,
prepared factors, trace maps, quadrature caches, accepted/trial states and
assembly temporaries are additional. The reported resource plan includes
known array accounting and native reference-factor storage counts, with those
limitations stated. Views can share memory; simple accounting may overcount.
An OS-enforced whole-process bound and measured peak commit are still required
for a large resource-admission experiment.

Detached `solver_options` and their canonical sorted-JSON SHA256 identify this
policy and modal-method version. Mutating the wrapped internal option payload
invalidates subsequent evaluation. The physical constitutive identity remains
separate: changing only the permitted ceiling does not alter the actual cutoff,
material law or physical operator. Exact implementation hashes belong to the
execution receipt. The illustrative linear source case remains unqualified.

## Executed evidence and pending resource admission

On 24 October 2026, NumPy 2.4.2 / SciPy 1.17.0, BLAS/OpenMP one thread:

- Six focused/adjacent magnetic suites passed **35 tests in 0.589 s**:
  modal gap, nonlinear motor, nonlinear P2, annular gap, separated motor and P2.
- The new independent high-mode oracle integrates the separated radial
  harmonic solution with 64-point Gauss quadrature and evaluates Maxwell
  torque on a circular contour. Mixed mode 1 and cutoff modes 255/1007/1024
  agree with modal energy/torque within the predeclared 2e-11 relative plus
  2e-11 absolute bounds. Energy/action and angle/torque derivative ladders,
  small-cutoff dense action/angle/reference-insertion comparisons, exact
  common-constant gauge, symmetry and malformed-input gates pass.
- Existing nonlinear full constrained-system, arbitrary-RHS inverse,
  current/angle coenergy derivative, PM/source, range, snapshot and mutation
  checks pass. New tests verify early invalid-budget rejection, unchanged
  default-255 rejection, bitwise same small-model results under an explicit
  higher ceiling, distinct option hashes with unchanged constitutive identity,
  detached returned options, and rejection of changed internal options.
- `scripts/check_architecture.py` passed all importer/IPC/numeric/module-size/
  language-budget/legacy-UI/documentation boundaries.

The high-mode tests allocate only O(N) coefficient arrays and small radial or
contour samples. They do **not** exercise a 4,030-square dense reference factor
or the full source geometry. The bounded high-mode dense resource probe was
explicitly deferred while the host had low memory and another CFD run remained
active. No peak-memory or speedup claim is made from the algebraic tests.
Actual-geometry unchanged-linear-limit comparison additionally requires a
separate reviewed run. Actual nonlinear H070-20 torque remains blocked by
directional static curves, lamination orientation, vendor PM properties and
an admitted directional constitutive law. Synthetic data cannot close that gap.

Knowledgeable human review remains required before release.
