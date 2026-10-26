<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review of a one-update Newton initial-guess experiment

Integration-owner review before harness implementation, 24 October 2026.
The source-pinned projected-gradient trial reduced the original residual norm
by 14.2672% and passed two vector/scalar directional checks, while worsening
scaled continuity by 6.45484%. It remains unaccepted. Root independently
recomputed the saved-vector slope, gauge, FD and Armijo decisions using only
stdlib array/ZIP parsing, `math.fsum` and `math.hypot`; this is scalar evidence,
not a second PDE computation or a convergence claim.

The proposal `NEXT_UNCHANGED_NEWTON_PROPOSAL.md` under the output experiment
directory has SHA256
`3167aaa1a625cec80e5bc13bc3bd548e9594e957de63d4a183dca992ec829d63`.
It changes only the initial guess and diagnostic update cap. Its physical and
numerical method foundations remain those reviewed for the frozen v21 owner
and in `PROPULSION_POD_PROJECTED_DESCENT_REVIEW_20261024.md`; no new governing
equation, tolerance or global convergence theorem is introduced here.

The saved q already contains its ray multiplier. Map it once through frozen
Su/Sp, updating only the exact free velocity coordinates and pressure. Require
unchanged fixed DOFs and actual boundary prescriptions, no pressure-mean repair,
and the same source, mesh, density, layout and pressure-kernel identities.
Reconstructing the initial raw F must match the saved trial bitwise before
assembling a new Jacobian. The guess is explicitly unaccepted; it must never
be wrapped in fabricated accepted-restart metadata.

The experiment uses the exact frozen v21 owner with seven original Newton
line-search steps, signed-current factors and fixed-relative forcing 0.1.
One normal Newton update is permitted. Its actual physical direction defect,
descent and original Armijo conditions remain unchanged. A callback records
progress but must not interrupt a naturally converged return before its normal
energy validation. An iteration-limit exception after one accepted update
means unsolved, not completed convergence. A final raw-residual capture may
stop a separate residual-only invocation at iteration zero; it cannot perform
another Newton update or promote the diagnostic vector to a field result.

Before any auxiliary-stage acceptance require the existing final nonlinear
1e-9, energy 1e-7, continuity/gauge, geometry, source, kernel and physical case
gates. No density advance or air-load qualification is in scope. Preserve
linear, line-search, resource and serialization failures separately. Retain
the exact system Python 3.14.2 runtime and strict checkpoint/failure-sidecar
contracts already tested by the previous experiment.

Preparation only is authorized by this review. An actual one-update experiment
requires a separately pinned harness/plan review and fresh resource evidence.
The proposed 600 s / 2 GiB bound covers measured preparation plus the recorded
44--398 s same-density Newton timing spread at other states; it is a bound,
not a prediction. No longer retry, continuation or changed default follows
automatically. Human numerical review remains required before release.
