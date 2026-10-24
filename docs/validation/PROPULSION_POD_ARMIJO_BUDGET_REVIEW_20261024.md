<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent finite line-search budget review

This integration-owner derivation precedes any change to the seven-trial
backtracking budget. It concerns the existing fixed-relative-forcing method,
not a new flow model or a relaxation of nonlinear acceptance. The norm-merit
and applied-direction formulation is recorded in section 30 of the
[full-loop review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md), with its primary
inexact-Newton foundation. No external implementation was consulted.

Let F(x) be the exact raw scaled residual at the retained physical velocity
and pressure, with fixed boundary values, scaling, density and gauge. Let q
be the actually applied physical direction: the auxiliary multiplier is zero
and the velocity/pressure components use their original coordinate scaling.
At nonzero F, differentiation of phi(t)=||F(x+t q)|| gives

```
phi'(0) = F(x)^T J(x) q / ||F(x)|| = s.
```

For finite s<0 and a differentiable residual, phi(t)=phi(0)+t s+o(t).
Consequently, for the unchanged c=1e-4, sufficiently small positive t obeys
phi(t)<=phi(0)+c t s. This is a local existence statement. It supplies neither
a computable lower step bound nor a global convergence guarantee. In
particular, rejection of the finite list 1,1/2,...,1/64 does not demonstrate
that all smaller steps fail. It also does not prove the assembled derivative
or scaling correct at an untested state. Finite-precision cancellation can
eventually destroy meaningful descent at very small steps.

The proposed diagnostic replays the exact retained v21 stage-2 matrix/RHS
through the same fixed signed preconditioner and forcing method. Because the
original direction was not exported, the replay must be labeled reconstructed,
not bitwise identical to an unavailable vector. Require the original full and
applied physical defects, gauge and negative raw merit slope. Then obtain the
baseline and trial raw residuals directly from the same frozen owner code,
stopping before Jacobian assembly, with a bitwise baseline/layout check.

Predeclare the original seven steps and 1/128,...,1/8192. Save every raw vector,
its norm, the original Armijo threshold and pass/fail. Do not normalize trials
by a state-dependent denominator or replace the original slope with a measured
secant. Bind sources, options, fields, matrix, geometry, hashes and OS resource
containment. This is a diagnostic of an unaccepted state, not an accepted
density stage or load. Only actual passing trials would justify separately
reviewing an explicit larger iteration budget; tiny accepted steps may still
stagnate, and final steady residual, energy and load gates remain unchanged.

Pseudo-transient continuation remains a distinct alternative requiring its
own constrained-flow derivation. The integration owner reviewed Coffey,
Kelley and Keyes' [13-page author preprint](https://www.researchgate.net/profile/David-Keyes/publication/51991900_Pseudotransient_Continuation_and_Differential-Algebraic_Equations/links/00b4953a9ef320fcb2000000/Pseudotransient-Continuation-and-Differential-Algebraic-Equations.pdf), sections 1.2 and 2, including equation 2.3
and assumptions 2.1--2.3, associated with
[DOI 10.1137/S106482750241044X](https://doi.org/10.1137/S106482750241044X).
Its semi-explicit index-one hypotheses do not establish convergence of this
velocity/pressure constraint system: continuity has no pressure derivative.
That paper's theorem is not a substitute for a relevant SPIKE derivation and
executed checks. No pseudo-time path is implemented or qualified here.

The diagnostic subsequently completed both bounded phases: the reconstructed
direction passed the original full/physical 0.1 gates with defect 0.0492063 and
slope -0.004897244314. The baseline raw residual was bitwise equal and bound
source/input hashes were unchanged. All original seven steps failed the same
Armijo predicate; 1/128 also failed, while 1/256 and every smaller tested step
through 1/8192 passed. Linear/residual phases took 66.42/183.35 s with peak
commit 1.134/1.030 GB under their separate OS 180/720 s, 2 GiB bounds.

The integration owner's separately authored recomputation used compensated
scalar sums for norms and slopes directly from the saved vectors/matrix. It
reproduced every exact pass/fail classification without widening the physical
Armijo criterion. The first oracle run used an unnecessary absolute 1e-14
equality check against the different worker norm reduction; its 2.548 merit
differed by 1.38e-14. This observation is retained separately. The cross-method
value comparison now uses a conservative size-dependent floating-rounding
envelope, while the independently recomputed acceptance inequality is unchanged.
Script `independent_v21_armijo_recompute_20261024.py` and receipt
`v21-stage02-Armijo-budget-audit/independent-recompute-cc2b2ecba286.json`
are under `output/promo-propulsion-pod-20261023/inertial_cfd/`.

This clears an explicit experimental backtracking-budget extension, preserving
the seven-trial default and every physical acceptance threshold. It does not
prove convergence of a new stage or justify changing the residual, energy,
field/load or mesh gates. Knowledgeable human numerical review remains required
before release.
