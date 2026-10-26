<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent derivation for an interior diagonal congruence experiment

Integration-owner review before implementation, 24 October 2026. The corrected
initializer experiment used 326 CG iterations; its direction interval consumed
28.544 s including bookkeeping. Its field remains unsolved. This motivates a
same-system linear experiment, not another full nonlinear solve or a new law.

The existing gauged reference Kref is positive definite, and its block inverse
Mref is applied through retained interior factors and a positive Schur factor.
At one fixed assembled nonlinear state, let d_i=sqrt(Kref_ii/Kcurrent_ii) on
the joint interior coordinates and let every trace d_i=1. Both diagonals have
the same physical units, so d_i is dimensionless. Require finite strictly
positive entries and representable ratios/scales; reject, never clip, floor or
silently fall back. Read diagonals from the existing CSR operators and gather
existing interior indices. No new quadrature or global tangent is needed.

For D=diag(d), use M=D Mref D. For any nonzero r,
`r^T M r=(D r)^T Mref(D r)>0`; symmetry follows from the same congruence.
This is an approximate inverse of the same unchanged tangent, not a replacement
PDE, permeability, factorization or right-hand side. The scale is fixed during
each CG solve. Updating it on CG iterates would change this method and is not
authorized. Check inverse-action symmetry/positivity numerically as well as
the unchanged actual linear residual; exact-arithmetic SPD alone cannot prove
floating-point suitability of the factor action.

On an isolated interior block Kcurrent=c Kref with c>0, D=c^-1/2 I gives
M=(1/c) Kref^-1=Kcurrent^-1. This exact limit does not extend automatically to
a coupled interior/trace system when trace scales remain one. General contrast
or anisotropy can make this heuristic worse. A negative timing or iteration
comparison is retained; no effectiveness claim follows from SPD.

The official SciPy 1.17.0
[CG parameter contract](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.cg.html),
parameters A, M, rtol/atol and return info, was reviewed on 24 October 2026.
It requires a positive definite operator and inverse preconditioner. The
congruence and reference-limit proofs above are independently derived from
quadratic forms. No external solver implementation is copied or adapted.

Require independent small contrast, anisotropy and coupled-block oracles,
including wrong one-sided scaling and invalid-diagonal rejection, before
reviewing an output-only actual-state harness. For that experiment, recover
the exact saved seed, assemble its state once and compare the same tangent,
RHS, zero starting correction and CG tolerances with Mref and D Mref D.
Retain source/material/runtime pins, scalar and vector agreement, actual
residual, positive descent, counts, action costs, wall/CPU and memory. Do not
perform a Newton step or accept torque from either correction. Neither speed
nor iteration count replaces the original actual-CG-defect requirement.

Use linear-size additional arrays only, explicitly account for simultaneous
matvec/inverse temporaries, and retain the 2 GiB OS bound. No extra reference
factor or dense trace matrix is admitted. The exact data-only 39-pair law and
its hard range remain unchanged. A real comparison requires separate review,
fresh resource headroom and no competing heavy job. Human numerical review
remains required before release.
