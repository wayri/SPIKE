<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent direct nonlinear port derivation

This integration-owner derivation precedes implementation review. It specializes
the independently reviewed energy exchange in sections 1--3 and 33 of
[the full-loop review](PROPULSION_POD_FULL_LOOP_REVIEW_20261023.md); the physical
work/coenergy and discrete-gradient primary foundations remain those recorded
there. It proposes an internal supplied-law reference port, not a public study
route, a nonlinear current table, actual-material admission or a runtime claim.

Use E=STAR, rows (1,0),(0,1),(-1,-1), i=E x and q=E^T lambda. These are dual
coordinates, not an orthonormal basis. For a fixed gauged field space let U(a,t)
be the full magnetic energy including PM reference and gap, F the three static
winding load columns, and D=E^T Le E the supplied constant end-turn contribution.
Stationarity is U_a=FE x. The current coenergy is
W=x^T E^T F^T a-U+x^T D x/2, and its gradient is q=E^T F^T a+D x.
The same static winding loads, geometry, quadrature, constitutive energy and
source identities must be used throughout.

At a converged state, K=U_aa. Two tangent solves K Y=FE give M=E^T F^T Y+D.
This is the differential flux/current Jacobian. For any v,
v^T M v=(FEv)^T K^-1(FEv)+v^T D v. K positive definite after gauge and adequate
winding rank/storage are necessary for a positive balanced inverse; monotone
material curves alone do not establish rank. Test actual symmetry, positivity,
conditioning and true tangent residuals. Do not replace a failed tangent by the
linear reference or silently repair a consequential symmetry defect.

For a requested q, solve W_x=q within the phase-current hexagon
|x1|,|x2|,|x1+x2|<=Imax and every supplied material range. Strict convexity on
an admitted branch gives uniqueness, not reachability of every q. Boundary
stagnation with nonzero inverse residual rejects. No clamping or substitute law
may convert an inadmissible current/flux/path state into success.

H=q^T x-W has derivatives H_q=x and H_t=-tau at stationarity. At finite inverse
residual e=q-E^T F^T a-Dx, the computed same-functional expression is
H=U+x^T D x/2+x^T e. Keep the residual correction, but require an independently
bounded inverse; the correction cannot qualify inaccurate field stationarity.
Only the gap depends explicitly on angle in this model. Thus one additional
tangent solve K a_t=-U_at gives all three fixed-current phase flux derivatives
F^T a_t for the controller. Angle-independent F and Le are explicit assumptions.
Balanced q alone does not determine the common-mode phase flux derivative.

Stable differences must be composed locally, before summing total energies.
For linear tensor/PM density use half the contraction of (B1-B0) with
nu(B1+B0-2Br). For isotropic supplied H(|B|), integrate the piecewise-linear
curve only between the endpoint magnitudes, splitting at actual knots; use
(B1-B0).(B1+B0)/(|B1|+|B0|) for a small magnitude increment, with both-zero
handled separately. Keep exact original range and one-sided-knot conventions.
End-turn energy difference is (x1-x0)^T D(x1+x0)/2. Difference x^T e by a
polarized product, computing flux increments from F^T(a1-a0), not subtraction
of independently rounded phase flux totals.

For each modal gap pair, compute u=R(n t)r and use the positive sum/difference
energy already derived. A stable rotated increment is
R(n t0)[(r1-r0)+(R(n(t1-t0))-I)r1], with cos(delta)-1 evaluated as
-2 sin(delta/2)^2. Polarize the plus/minus quadratic products using that
increment. This avoids subtracting large endpoint gap energies or nearly equal
trigonometric evaluations. The unchanged total discrete-gradient chain gate,
derivative/tolerance refinement and independent high-precision fixtures still
decide whether rounded differences are adequate.

Implementation must provide immutable source/tolerance-bound cached states,
explicit bytes/field-solve/iteration/wall bounds and detached outputs. A cache
warm start may improve cost but cannot alter acceptance. Every intermediate
coordinate path must be admissible. The root-owned loop should use a generic
fixed-current phase-flux angle-derivative method and identify a direct port as
a port, while preserving existing linear-table behavior and public contracts.

Required evidence: independent small full-system tangent/angle oracles;
nonquadratic convex inverse round trips, range/rank/hexagon failures; stable
tiny mixed differences with arbitrary energy offsets; source mutation and
resource failures; then a short manufactured supplied-law compiled-controller
loop with unchanged circuit, shaft, thermal and whole-energy gates and timestep
refinement. Actual H070 law/orientation, actual-domain performance and a complete
real-source run remain separate. No implementation or executed acceptance is
claimed here; knowledgeable human numerical review remains required for release.
