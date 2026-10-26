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

## Implementation review and executed integration

The integration owner subsequently reviewed the direct port, its field tangent
and angle sensitivities, local energy differences and modal increments against
the derivation above. Source binding now covers all nine physics dependencies.
The inherited run deadline also covers initial flux evaluation, cached states
and nested operations, and is restored on exceptions. The implementation and
test hashes, nine direct-port and eleven adjacent passing checks, and successful
architecture check are recorded in
`output/promo-propulsion-pod-20261023/real_motor/nonlinear-direct-port-review-fixes-20261024.json`.
These are executed reference checks, not a proof of actual material validity.

The root-owned loop now uses the fixed-current phase-flux angle derivative
interface for its controller sensor. A direct result identifies its magnetic
port and uses the internal `spike/geometry-propulsion-direct-loop-result/v1`
contract; it does not fabricate a linear field-table identity. Existing linear
results retain their contract and table identity. Public worker/native GUI
admission for the direct port is still pending.

An actual compiled fixed C controller, nonlinear supplied-law FEM, analytic
shaft drag and eleven-node thermal feedback completed a two-step manufactured
loop with the unchanged whole-energy checks. The initial twelve-sector fixture
passed in 36.702 seconds; its executed test snapshot and exact source identities
are retained in
`output/promo-propulsion-pod-20261023/verification/direct-controller-initial-12-sector/`.
A smaller four-sector fixture subsequently passed the same integration check
in 17.824 seconds. These geometries and constitutive laws are manufactured;
neither test uses the actual OpenMotor material or propeller CFD.

The first separate three-grid timestep study failed before producing its first
result with Windows quota error 1816 under its OS-enforced 512 MiB process/job
budget. Its artifacts are preserved in
`output/promo-propulsion-pod-20261023/verification/direct-nonlinear-controller-timesteps-20261024/`
and the adjacent bounded-execution receipt. No timestep order or real-source
loop success is claimed. Diagnosing that resource failure and completing a
source-bound timestep study remain open alongside actual-domain performance,
material admission, full-air load convergence and later GUI verification.

A subsequent controller-only diagnostic isolated the quota failure: a one-process
Windows job rejects the compiler `Popen` with error 1816 at only 19.4 MB peak
job memory. An explicit four-process job completes the same controller operation
in 0.969 seconds, with 111.5 MB peak job memory. Both retain aggregate and
per-process 512 MiB limits and suspended-before-assignment containment. Exact
stack traces and bounded receipts are under `verification/controller-quota-`
`{1,4}{,-bounded}-20261024.json` in the output root. This identifies an
inappropriate diagnostic harness process allowance; it does not justify
raising memory limits or relaxing numerical gates. A corrected, versioned
timestep study remains pending headroom and execution.

## Corrected three-grid study: completed

The versioned corrected harness then passed under the original 360-second /
aggregate 512 MiB limit with the explicit four-process allowance. Available
physical memory exceeded 6.5 GB at launch; peak aggregate job commit was
222,691,328 bytes. All source identities remained unchanged. The full study
took 257.016 seconds wall and 252.516 seconds CPU.

For the same 40 microsecond duration, 20 microsecond controller period and
initial state, 10, 5 and 2.5 microsecond timesteps completed 4, 8 and 16 steps
with two compiled-controller ticks each. Successive endpoint phase-current
changes were 1.0236610785e-8 A and 2.5591642082e-9 A, exceeding the predeclared
1e-11 A floor. Their ratio 3.9999820067 passes the unchanged 3..5 screen,
corresponding to observed order 1.99999351. This is a local smooth reference
screen over three grids, not a general temporal-error estimate.

The independently authored standard-library recomputation reads the retained
JSON results and uses compensated scalar energy sums and endpoint norms. It
reproduces the ratio and whole-energy defects -9.32228e-12, -1.68428e-11 and
-1.42898e-10 J, all below the unchanged 1e-9 J threshold. Exact result hashes,
compiler/controller/port identities, source checks and containment evidence
are retained in
`output/promo-propulsion-pod-20261023/verification/direct-nonlinear-controller-timesteps-v2-20261024/`
and its adjacent bounded receipt. Independent oracle SHA256 is
`abe7cbe20989e85e3f3ee803c8b471bee34df080039b06e76f70eba6f9fc5bb8`.
The original failed attempt remains unchanged as causal evidence.

This closes the small manufactured coupled timestep prerequisite only. Actual
OpenMotor material/orientation, actual-domain nonlinear performance, converged
full-air blade loads and direct-port public GUI/native admission remain open.
