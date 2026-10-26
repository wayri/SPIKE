<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review of a proposed algebraic velocity shift

The integration owner authored this derivation before any implementation of the
proposed regularized direction. It reviews the independently authored design at
`output/promo-propulsion-pod-20261023/inertial_cfd/globalization-design-20261024/DESIGN.md`
(SHA256 `510a211a192c02723f8d2842e7b65d5c2ff2b184ae3faae42eab91f85aeb4c4e`).
No solver change, real-state regularized solve or new convergence claim is
authorized by this record. Small discriminating fixtures are the next evidence.

Keep the current raw residual F, unshifted augmented Jacobian A, boundary values,
coordinate scalings and pressure gauge fixed. Write q=(dy,dz,dlambda), with
the last component an auxiliary compatibility multiplier discarded by the
physical update. If e_g injects that multiplier into continuity, the derivative
of the actual physical residual along the update is dF=Aq-e_g dlambda.

Let D be the diagonal of the physical consistent P2 velocity mass and let
E=diag(Su D Su,0,0). For a tetrahedron the exact barycentric integral of a
monomial with exponents a is 6V product(a!)/(3+sum(a))!. Inserting
Ni=2lambda_i^2-lambda_i gives integral Ni^2=V/70. Inserting
Nij=4lambda_i lambda_j gives integral Nij^2=8V/105. Multiply by rho and
assemble incident contributions before restricting free vector DOFs. These
entries are positive. Integrals of Ni are -V/20, so row-sum lumping would
produce negative vertex masses and is inadmissible for this metric.
The diagonal sum is 18V/35: this metric is not the full kinetic-energy mass.

With Su in inverse square-root stiffness units, E has units seconds and gamma
has units inverse seconds. For (A+gamma E)q=-F+e, direct substitution gives

```
dF + F = e - gamma E q - e_g dlambda.
```

Thus convergence of the shifted linear system proves neither the existing
unshifted forcing gate nor descent of the original merit. Evaluate all defects
separately, and compute the raw-norm slope from the unshifted operator and
actual applied direction: s=F dot dF / ||F||. Reject nonfinite or nonnegative s.
Only the unchanged original Armijo predicate can accept a trial. No shifted
residual, small step, artificial work or auxiliary multiplier can qualify a
physical load or final PDE result. A scalar negative Jacobian demonstrates why
a positive mass shift alone cannot guarantee descent or invertibility.

This is an algebraic candidate, not physical transient CFD. The reviewed
[Altmann–Heiland primary abstract](https://arxiv.org/abs/1901.04002), version1,
submitted 2019-01-13, establishes the DAE/index context only; its full derivation
has not been independently reread by this owner. The worker's exact primary
sections actually reviewed are recorded in its design. Our matrix identity and
mass moments above are independently derived, and no index-one convergence
theorem is imported. In particular the existing SUPG pressure-gradient term
means G need not equal -B transpose; the existing constant-pressure kernel
screen alone does not establish invertibility of B M^-1 G on the quotient.

First require independent moment/quadrature, scaling, auxiliary-removal,
unchanged-root, ascent and singular-shift fixtures. Then review their executed
evidence before any source-bound frozen real-state diagnostic. Do not overlap
real factorizations with the active CFD continuation. A new direction contract
would require explicit method metadata, unchanged final residual/energy/source/
geometry/load gates, bounded resources and further independent review. Numerical
code remains subject to knowledgeable human review before release.

## Executed stage-one evidence reviewed

The owner reviewed the complete independently authored `tiny_fixtures.py` and
its final receipts. Twenty-five checks passed under OS-enforced 30 seconds and
100 MiB, using standard-library rational elimination/polynomial integrals and a
separate point-evaluated Gauss/Duffy quadrature. The child used 0.2391 seconds
and 19,443,712 bytes peak commit. Exact positive element-mass LDL pivots,
negative vertex row sums, both-sided scaling, nonzero shifted/inexact/auxiliary
defect terms, affine constraints, ascent rejection and singular shifts are
discriminating checks of the derivation, rather than a real flow study.

The nonadjoint pressure example additionally retains an invertible steady
border while its hidden pressure product loses rank. This substantiates the
warning against inferring a pseudo-time pressure inverse from the existing
steady kernel screen. It does not diagnose that defect on the actual mesh.

Script SHA256:
`20098e64b3fc89ce18cac6b58c847d52335038d514123c932bc08d3623726ce4`.
Final receipt SHA256:
`a74ee4dec99f82a3339489cbfe191dfc22d19d7567033a0fdc01433db2531827`.
The design directory's `STAGE1_EXECUTED.md` identifies the OS receipt and
remaining unexecuted real-state stages. No live solver implementation or
real-state diagnostic has been admitted by these small checks.

## Frozen-state harness review

The owner subsequently read the complete prepared harness and plan: exact
frozen-state/source/layout/pressure-kernel bindings, reference-stiffness Su,
positive element mass assembly, original and shifted full/applied 0.1 gates,
auxiliary removal, original slope, baseline-before-factor and candidate-before-
Armijo central differences, three fixed shifts and separate bounded phases.
This is a conservative diagnostic of existing directions, not integration of
a new method or a relaxation of any old gate. Baseline or layout mismatch
rejects the experiment. Kernel evidence reuse is explicit and conditional on
exact C, Sp, gauge and geometry identities, rather than an unrun new eigensolve.

An actual Windows virtualenv redirector failure in the independent material
check exposed a launch issue before any real CFD diagnostic. A first runtime-
only proposal pinned the motor/material Python 3.12.9 environment. That proposal
was reviewed but **not launched**; its identification as the v21 runtime was
incorrect. The flow owner subsequently confirmed that v21 and its Armijo audit
both used default PowerShell `python`, without virtualenv activation or package
path insertion. Current exact-route evidence and the v22 traceback identify
system Python 3.14.2 with its own NumPy 2.4.2 / SciPy 1.17.0. The older receipts
did not record an explicit interpreter/version, a historical provenance gap.
The diagnostic must use the corrected explicit system runtime, without an
automatic environment fallback, and still prove bitwise baseline agreement.

The superseded, unexecuted 3.12 harness SHA256 was
`18c154ddaba40b0279372d22b9a3733fe41b0a33afb89bf7b36d6db7d27bcdd6`,
with plan SHA256
`14350e231ef6e377f1ddcc04f018aa9e33b9d73d45a8ff1cb75b1e89f403fd04`.
Those identities do not authorize a launch. The correction and fresh hashes
require review before execution; the old runtime-only diff/AST evidence is
retained rather than relabelled as the actual v21 environment.

The corrected code/plan are eligible for one diagnostic only after runtime review,
terminal v22 evidence,
no other active CFD job, a fresh headroom check and an exact-hash authorization
artifact. Preserve shared preparation/residual 720 s, linear 240 s, each OS
2 GiB, BLAS1, three shifts and no automatic retry. All real-state runtime
comparisons, finite differences and original-merit progress remain unexecuted
at this review. A passing diagnostic still does not produce an accepted field,
restart density, converged load or physical time integration.

The corrected system-runtime bootstrap and its metadata/path/hash checks have
now been reviewed. The numerical child body remains identical to the original
review. Final reviewed harness SHA256 is
`b0513cfddcc6884a889614cd2b254b53c486d11f236d62ca0e1190bb636733a1`,
with plan SHA256
`ee48e13b4c2ae092797445bad5e0c3c56aec9fbfd8c1a4d89d3a367635f0b51d`.
The 3.12 proposal is retained under `superseded-runtime-312-unexecuted/` and was
never numerically executed. v22 is terminal with cooperative cancellation;
the one motor proxy probe is also terminal, without convergence. A fresh
headroom/no-overlap receipt and exact-hash authorization are still required
immediately before the single diagnostic launch.

## Executed conservative diagnostic: no eligible direction

One exact-hash-authorized run completed under the reviewed system runtime,
with v22 and the motor probe terminal and fresh memory/no-overlap evidence.
Owner layout, boundary, C/Sp/gauge and source comparisons passed, the original
raw baseline was bitwise identical, and both predeclared baseline central
differences passed. Preparation took 113.97 s OS wall, linear work 35.82 s;
peak commit was approximately 1.04 and 1.16 GB respectively, under each 2 GiB
cap. The source, runtime and phase artifact bindings remained unchanged.

All three shifted solves met their own linear gate, but all failed the original
full/applied forcing criterion. For gamma ratios 0.01, 0.1 and 1, shifted
relative defects were 0.04794, 0.03822 and 0.04466; original applied defects
were 7.03279, 1.79721 and 4.12875, all above 0.1. The final phase correctly
recorded `no_conservative_direction_passed`, without selecting a direction or
running candidate FD/Armijo trials. There is no accepted field, density stage,
improved load or convergence claim. This rejects the tested conservative
directions; it does not establish that a separately defined method would give
original-merit descent or qualify silently removing the old forcing gate.

All phase/source/vector/OS evidence is retained in the design directory's
`frozen-v21-diagnostic-run/`, with the reviewed authorization and fresh headroom
records alongside it. Any new direction-generation method requires its own
independent mathematical contract, actual original-residual descent/FD/Armijo
evidence and unchanged final PDE/energy/load checks before integration. No
automatic continuation or extended shift grid is authorized by this outcome.
