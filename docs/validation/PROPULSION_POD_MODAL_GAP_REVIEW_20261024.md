<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent modal-gap resource extension review

This integration-owner derivation precedes implementation of a larger nonlinear
Fourier budget. It reuses the governing source-free annulus, trace normalization,
rotation convention and reviewed primary separation-of-variables foundation in
[section 18 of the full-loop review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md).
No additional external implementation was consulted. This document is a design
review, not an executed high-mode nonlinear motor result.

Let L=log(b/a)>0, c=depth/mu0, and R(n theta) rotate the two rotor-local real
Fourier coefficients into the stator frame. For each positive mode define
A=c n coth(n L), B=c n csch(n L). With rotor/stator coefficient pairs r,s,

```
E_n = A/2 (r.r+s.s) - B s.Rr
grad_r E_n = A r - B R^T s
grad_s E_n = A s - B Rr
tau_n = -partial_theta E_n = B n s.JRr
J = [[0,-1],[1,0]].
```

Thus applying the exact symmetric gap Hessian to arbitrary trace increments
requires the same pairwise gradient formula, O(N) operations and storage.
It need not construct a dense matrix or evaluate finite differences. Its angle
derivative action is (-B R'^T s, -B R' r), with R'=n J R. This fixes both rotation
and torque signs independently of a nonlinear Newton implementation.

At mode zero, k=c/L, E_0=k(r0-s0)^2/2 and the two gradient components are
k(r0-s0), k(s0-r0). This block has the common-constant gauge null vector and no
angle dependence. A matrix-free implementation must retain that nullspace;
it must not create positive definiteness by changing the physical operator.
The existing external gauge and domain condensation provide the reference
system's gauge treatment.

For stable energy accumulation use t=tanh(n L/2):

```
E_n = c n/4 [t |Rr+s|^2 + |Rr-s|^2/t].
```

This is algebraically identical to the quadratic form and avoids subtracting
large nearly equal trace terms. Evaluate B through decaying exponentials and
expm1 as in the reviewed gap method; do not introduce overflowing sinh/cosh
or replace the stable energy by cancellation-prone dot products. Coefficients
have units Wb/m, coefficient gradients A m, energy J and mechanical torque N m, with the
existing orthonormal trace and axial-depth convention.

The nonlinear domain energy, supplied constitutive tangent, winding loads,
CG checks and Armijo merit remain unchanged. Only the unchanged linear reference
preconditioner needs a dense joint trace Schur matrix once per angle. A modal
energy/action does not remove its factorization cost or the dense domain trace
maps. Resource estimates must count simultaneous K/reference/factor copies,
domain fields, P2 quadrature caches and trace matrices before allocation. A
preallocation estimate is not a substitute for an OS-enforced memory bound.

Keep the default nonlinear cutoff ceiling at 255. Any extension must explicitly
opt in within the existing annulus ceiling 1024, reject invalid budgets before
large allocation, and retain reproducible option identities. The actual cutoff
1007 alone cannot be admitted by changing a guard: require independent action,
energy, angle/torque and gauge comparisons at multiple cutoffs, nonlinear
small-fixture parity, derivative checks and a source-bound high-mode resource
probe. Real-domain performance and actual-material torque remain separate
checks. Missing directional H070-20 B-H/orientations cannot be supplied by this
resource change or inferred from agreement with a linear reference.

The integration owner subsequently inspected the complete modal helper
SHA256 `95d753c429883ca0d7f07d4692a46427e7121cf52e5026cad2b7b9ae4f1386ac`
and nonlinear integration SHA256
`0bd2c334589959ececf691ee3886db2a221f68060b5e5de5fcbc2f0baf103b6e`.
The stable gradients, angle action and torque signs match this derivation.
The nonlinear path retains its domain residual/tangent, convergence and
constitutive/source checks, uses a private dense reference matrix for Cholesky,
and records separate solver-option hashes. The three-matrix allowance is
explicitly an array-accounting policy, not a whole-process memory bound.

A separately authored integration-owner oracle formed endpoint normal fluxes
from the separated radial harmonic solution and integrated Maxwell torque
around an interior contour. Mixed modes 7,43 and cutoff, plus unequal constant
traces, were tested at cutoffs 255,1007,1024 and angle -0.0711 rad. Relative
action errors were at most 2.51e-16, energy differences at most 7.11e-15 J,
and contour torque differences at most 1.48e-12 N m. No dense gap matrix,
domain factorization or motor solve was performed. Script and source-bound
receipt: `output/promo-propulsion-pod-20261023/real_motor/independent_modal_gap_flux_oracle_20261024.py`
and adjacent receipt ending `95d753c42988-10b52f0eb2a8.json`.

The implementation author's 35 focused/adjacent checks and architecture guard
also passed, recorded in `real_motor/modal-gap-small-oracles-20261024.json`
under the same output root. The later generic 1007-mode reference probe passed
under OS-enforced 60 s / 2 GiB containment with BLAS thread count requested as
one and unchanged source hashes. Its 4030-by-4030 private Cholesky input was
overwritten in place, setup took 0.596 s, and whole-child peak commit was
323248128 bytes. The full uncondensed residual was 4.35e-16. This used synthetic
domain Schur blocks and tiny interior factors, not the actual motor geometry.
The initial successful probe omitted peak instrumentation and is preserved
separately; the instrumented repeat is recorded in
`real_motor/modal-reference-1007-{probe,bounded}-20261024.json` under the output
root. Actual-domain performance, real-material admission and torque convergence
remain unexecuted or open. Knowledgeable human numerical review remains required
before release.
