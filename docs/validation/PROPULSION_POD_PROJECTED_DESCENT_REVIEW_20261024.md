<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review of a proposed residual descent diagnostic

Integration-owner derivation, 24 October 2026, before implementation or an
actual-state experiment. This is a separately named experimental direction;
the existing fixed relative Newton forcing contract is unchanged. The failed
conservative velocity-mass-shift experiment remains a negative result.

Use exactly the frozen owner's scaled residual F and physical Jacobian J.
Exclude the auxiliary gauge multiplier column: changing that multiplier is
not a physical residual correction. Let h be the normalized pressure gauge
normal in these same scaled coordinates, extended by zero on velocity, and
P=I-hh^T. This requires a finite nonzero h and an already gauge-admissible
state. P is symmetric and idempotent. It preserves the pressure constraint
for increments; it does not preserve the nonlinear continuity equations.

For phi=F^T F/2, g=J^T F. With strictly positive finite column metric
D=diag(J^T J), define v=P g and q=-P D^-1 v. Then
`F^T J q = -v^T D^-1 v < 0` whenever v is nonzero. The second projection is
essential because D need not commute with P. Reject missing/zero metric
entries, nonfinite arithmetic and projected stationarity at positive residual.
Stationarity of residual norm does not prove a PDE root.

No dense normal matrix is needed: column squares, J products and projections
suffice. Let w=J q and s=F^T w. The positive linearized-ray minimizer is
`t=-s/(w^T w)` when s<0 and the denominator is positive and finite. Rescaling
q by t preserves descent in exact arithmetic. Recompute the actual scaled
direction, gauge error, w and slope; reject cancellation, overflow, underflow
or a slope whose sign is unresolved under a declared roundoff bound. A tiny
negative slope alone does not establish useful progress. No diagonal floor,
alternate metric or repeated scale search is implicitly authorized.

Scaling is part of the merit definition. Physical momentum and continuity
rows have different units; the frozen Su/Sp transformations and their source
identity must be retained. Column squaring is performed only in that declared
scaled coordinate system. The direction is mapped back through the unchanged
owner transformation. This metric is not a physical energy and does not
justify summing unscaled incompatible quantities.

The general quadratic-metric descent foundation was independently read in
Boyd and Vandenberghe, *Convex Optimization* (2004), section 9.4.1, equation
9.25, printed page 476 / PDF page index 489, from the authors'
[Stanford PDF](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf), on
24 October 2026. The projection and least-squares ray above are independently
derived here. Convex global convergence results do not transfer to this
nonlinear stabilized flow residual. No external implementation or fixtures
were inspected or copied.

Before an actual-state experiment, require independent small analytic
fixtures for the projected slope, noncommuting metric, gauge preservation,
zero-column rejection, positive-residual stationarity and nonfinite cases.
Then review a source/runtime-bound, memory/time-limited harness. Require
baseline reconstruction, candidate directional finite-difference agreement,
direct original-merit descent and the owner's unchanged Armijo inequality.
Record momentum, continuity and gauge components separately. One accepted
trial would establish only a local diagnostic step, not nonlinear convergence,
full-air loads, mesh independence, thermal closure or GUI readiness. Existing
final residual, pressure-kernel, geometry, traction and energy gates remain.
Human numerical review remains required before release.

The independently authored output-only proposal and forty small fixtures in
`output/promo-propulsion-pod-20261023/inertial_cfd/globalization-design-20261024/next-method/`
were reviewed after this derivation. The exact-rational hand oracles, omitted
outer-projection counterexample, positive-residual stationarity, finite
precision rejection, nonlinear Armijo and scalar-slope FD counterexample all
pass. The bounded receipt records 0.375 s under OS 30 s / 100 MiB containment,
with peak private commit 18,915,328 bytes. This is a stdlib-only tiny-matrix
check, not the CFD runtime or an actual-state experiment. Its source hash is
`2bf9c8ff7e5a6697916a80dfdabb7a6284a256637ff82e5db7004fdaf4f65127`;
the design hash is
`1fd187a890fcb7a2abdcb1a224cc6fb8ddb8b9734bf5d74e868d22947ecb18cb`.
Actual-state harness preparation is authorized; execution remains unrun.
