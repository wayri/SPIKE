<!-- SPDX-License-Identifier: Apache-2.0 -->
# Propulsion CFD: separately bounded backtracking diagnostic

Status: preparation and exact scalar verification only. This record does not
authorize an actual field run or qualify a fluid load. The seven-trial run is
terminal and remains preserved; its directory must not be reused.

## Observed result and method boundary

The unchanged frozen-v21 Newton diagnostic reconstructed the saved initial
residual bit for bit, then failed its seven original line-search trials.
Parent elapsed time was 245.927 s; child peak commit was 1,730,367,488 bytes,
inside the existing 600 s / 2 GiB limits. No update, field, density stage or load
was accepted. The retained record proves the source passed into line search,
but does not preserve the direction, true forcing values or individual trial
norms. Those missing quantities must not be reconstructed as measured facts.

The proposed distinct diagnostic uses the existing v22
`maximum_line_search_trials=14` option. Independent inspection found the owner
diff limited to the explicit integer budget, dyadic step sequence and profiling.
The residual, Jacobian, signed-current factors, full/applied forcing limits,
descent check, norm Armijo predicate and final residual/energy gates remain
unchanged. Do not import an entire different v22 dependency tree without checking
every selected dependency against the prior closure.

Reviewed owners:

- v21 SHA-256: `d936ffc8ac1d235f3ca275630230a5b750f4680c3f98b57eebd9444907324def`.
- v22 SHA-256: `28cd553bae106a89fdbee21907a1ee8e452dab06cf26a4988b15146231b0c720`.
- Shared forcing helper: `7ba3cedaa17b92acea0da5b4da515ec96c3c9c9aac8686c2a3261d96b5f1751e`.

The independent preimplementation review, exact source sections, complete
artifact identities and clean-room statement are in
[REVIEW.md](../../output/promo-propulsion-pod-20261023/inertial_cfd/globalization-design-20261024/next-method/extended-backtracking-review-20261024/REVIEW.md),
SHA-256 `21a1d3c5df2e195df9fb21f399c5f54e438c33de9f432ab804d79a8eac84f081`.

## Governing argument and validity

Use the owner's raw scaled residual F and the derivative v=Jd of its actual
physical update. The full augmented-system product A*delta can differ from v;
both existing forcing gates must pass. For eta=0.1 and e=v+F,

```
||e|| <= eta ||F||
g = F^T v = -||F||^2 + F^T e <= -(1-eta)||F||^2.
s = g/||F|| <= -0.9||F|| < 0, for F != 0.
```

For a differentiable residual, phi(alpha)=||F(x+alpha*d)|| has derivative s
at zero. Thus sufficiently small positive alpha satisfies the original
`phi(alpha) <= phi(0) + 1e-4*alpha*s`. No lower bound on that alpha follows.
Seven trials stop at 1/64; fourteen stop at 1/8192. Either finite sequence can
fail. Conditioning can make d large; nonsmooth branches or an inconsistent
Jacobian invalidate the differentiability argument. The prior successful
directional checks at other states do not settle those questions here.

Alpha and the Armijo coefficient are dimensionless. Velocity and pressure
updates retain the exact Su/Sp mapping, SI m/s and Pa values, gauge and free-DOF
layout. The norm is the algebraically scaled residual, not physical fluid energy.
The state-dependent reporting divisor must not enter the raw norm Armijo test.
Do not replace the norm predicate with a squared-norm predicate or widen it using
an offline rounding envelope.

Primary foundations actually reviewed by the independent author:

- Eisenstat and Walker, *Globally Convergent Inexact Newton Methods*, SIAM J.
  Optimization 4(2), 393–422 (1994),
  [DOI 10.1137/0804022](https://doi.org/10.1137/0804022): published author-hosted
  edition, pp. 393–394 and 410–411, Algorithm IN/INB and Theorem 6.1. Its
  hypotheses and acceptance formula are not substituted for SPIKE's predicate.
- Boyd and Vandenberghe, official Stanford
  [unconstrained-minimization lectures](https://web.stanford.edu/class/ee364a/lectures/unconstrained.pdf),
  41-page edition retrieved 24 October 2026, PDF pp. 10–12, descent and
  backtracking sections. Convexity and global-rate assumptions are not asserted
  for the CFD problem.

No external implementation or numerical example was copied or adapted.

## Independent executed scalar checks

[root_exact_oracles.py](../../output/promo-propulsion-pod-20261023/inertial_cfd/globalization-design-20261024/next-method/extended-backtracking-review-20261024/root_exact_oracles.py)
uses Python rational arithmetic and the independently reduced inequality for
F(x)=1+x+C*x^2, x=0, d=-1. For alpha>0 the Armijo margin is exactly
`alpha*(9999/10000-C*alpha)`.

- C=128: seven trials fail; first acceptance is trial nine, alpha=1/256.
- C=16384: all fourteen trials fail despite exact Newton forcing and descent.
- F=1, v=-9/10 attains the forcing/descent bound exactly.
- A separate two-row witness has zero full-system defect and a rejected
  physically applied defect; passing only the former is insufficient.

The script executed successfully and wrote its source hash and exact rational
values in the adjacent JSON receipt. These are scalar verification cases, not
CFD convergence evidence. Real capture/hook/control-flow checks remain required
for the new harness.

## Required capture and stopping gates

Before line search, durably save the original matrix arrays, F, delta, A*delta,
the physically applied Jd, both true forcing defects, slope and exact identities.
Save every trial's raw residual, norm, threshold, margin and decision before it
can be discarded. Do not depend on an accepted-iteration callback. Serialize
existing arrays sequentially without sparse-format conversion or a matrix copy;
retain no frames, preconditioner contexts or old factors into line search.
Review the simultaneous-buffer ledger, including an explicit 8 MiB incremental
instrumentation allowance, against the unchanged 2 GiB whole-child cap.

Require the same initial state, residual, matrix/RHS identities, Python 3.14.2,
NumPy 2.4.2, SciPy 1.17.0 and BLAS1. Permit one Newton system and at most fourteen
trials, stopping at the first accepted trial. Preserve full/applied forcing 0.1,
Armijo coefficient 1e-4, halving factor 1/2, final nonlinear tolerance 1e-9 and
energy tolerance 1e-7. Source/identity drift, nonfinite values, either forcing
failure, non-descent, export failure or resource exhaustion stops the run.

Fresh 4 GiB physical / 8 GiB commit admission, no heavy overlap, and the existing
600 s / 2 GiB OS limits include preparation, hashing, capture and cleanup.
Fourteen failures terminate this diagnostic; no automatic retry or fifteenth
trial follows. An accepted trial remains an unaccepted diagnostic field until
the owner's final gates pass. Mesh, domain, traction/load refinement, regime,
hardware and knowledgeable human release review remain separate requirements.

Current solver-folder reorganization is preserved. Frozen-baseline execution
must identify its exact isolated source tree; it does not requalify the new
layout or alter historical receipts.
