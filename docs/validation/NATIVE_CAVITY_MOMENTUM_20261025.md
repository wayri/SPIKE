<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent native cavity momentum admission, 25 October 2026

## Scope, ownership and preimplementation derivation

This record was started before implementation of the new checker. The existing
owned native source is `src/solvers/thermal_fluid/airflow/cavity.cpp`, SHA-256
`a8a5493c939f75d23a3b7116a57cb85be961fba21042a7eb67ab148607f8b6d5`.
The new independent Python owner is
`python/spike_core/solvers/thermal_fluid/flow/native_cavity_momentum.py`.
It inspects returned MAC faces and cell pressures; it does not call, translate
or re-run the native predictor or pressure solver.

The question is whether the returned field satisfies the native staggered
steady momentum equations to a limit derived from the requested stopping
tolerance. The geometry, assumptions and nondimensionalization remain those
in [the native CHT method](NATIVE_CHT_METHOD_20261020.md): unit square, constant
density/viscosity, incompressible Newtonian laminar fluid, prescribed tangential
lid, impermeable walls, no thermal momentum feedback or other body force.
Coordinates, velocity, pressure and residual are dimensionless. Dimensional
acceleration is residual times Uref^2/L. This is discrete solution verification,
not continuum error, uniqueness, measured validation or production qualification.

## Primary sources actually reviewed

Reviewed 2026-10-25; only mathematical documentation, not upstream code:

- NASA Glenn, [Navier-Stokes Equations](https://www.grc.nasa.gov/www/k-12/airplane/nseqs.html),
  page dated 2021-05-13: displayed conservative X/Y momentum equations,
  pressure-gradient signs, and Reynolds scaling. Used for the reduced
  constant-property incompressible momentum law, not a source-specific algorithm.
- NIST FiPy 4.0.3, [Finite Volume Method](https://pages.nist.gov/fipy/en/stable/numerical/discret.html),
  Convection Term equation (2), Diffusion Term equation (3) and normal-gradient
  formula: integrated face flux and orthogonal neighbor-distance foundation.
  The staggered dual volumes and interpolation below are independently derived.
- NIST DLMF 1.2.8 (2026-09-15), [section 3.1](https://dlmf.nist.gov/3.1),
  subsections (i) floating-point rounding, (ii) interval arithmetic, and (iii)
  exact rational arithmetic. Exact rational evaluation is selected to avoid
  an empirical floating-point acceptance allowance.

All new formulas, code and fixtures are independently authored. No external
implementation, benchmark data or solver source was copied or adapted.

## Independent dual-volume balance

Use zero-based U(i,j), i=0..n,j=0..n-1 at vertical faces, V(i,j),
i=0..n-1,j=0..n at horizontal faces, and P(i,j) at cell centers.
For U, the momentum dual volume has U-centered east/west midfaces, and
north/south faces shared with the V grid. Its four advected momentum fluxes are:

```
E = ((U(i,j)+U(i+1,j))/2)^2
W = ((U(i-1,j)+U(i,j))/2)^2
N = ((U(i,j)+U(i,j+1))/2) * ((V(i-1,j+1)+V(i,j+1))/2)
S = ((U(i,j-1)+U(i,j))/2) * ((V(i-1,j)+V(i,j))/2)
```

Sum outward E-W+N-S and divide by dual width h. Diffusion is the sum
of the four outward neighbor differences times nu/h^2. Pressure traction
is -(P(i,j)-P(i-1,j))/h. These give R_U=-C_U+nu*L_U-G_U P.
The V balance exchanges x/y and U/V: square fluxes north/south, mixed fluxes
east/west, and pressure difference P(i,j)-P(i,j-1). Only free momentum
faces are checked: U at i=1..n-1 and V at j=1..n-1. Fixed normal wall
faces are verified separately; there is no invented wall momentum equation.

Tangential wall values lie midway between internal and ghost samples:
U(i,-1)=-U(i,0); U(i,n)=2*lid-U(i,n-1);
V(-1,j)=-V(0,j); V(n,j)=-V(n-1,j).
These enforce the moving lid and three stationary tangential walls. Normal
faces U(0,j), U(n,j), V(i,0), V(i,n) are exactly zero. The lid corners
are excluded free unknowns, consistently with the native wall convention.

To distinguish operator-coefficient rounding from checker arithmetic, freeze
the native scalar convention h=float(1/n), nu=float(1/Re), h2=float(h*h).
Then evaluate every face expression exactly over the binary input values with
alpha=1/h and beta=nu/h2 in rational arithmetic. This includes ghost values.
For non-power-of-two n the explicit h2 convention matters. There are no
guessed extra digits or measured tolerance multipliers.

## Derived stopping target and fail-closed interpretation

Write F(q)=-C(q)+beta*neighbor_laplacian(q), G=alpha*pressure_difference.
For the ideal arithmetic incremental projection:

```
qstar = q + dt*(F(q)-G*p)
qplus = qstar - dt*G*phi
pplus = p+phi - constant_mean
d = (qplus-q)/dt
R(qplus,pplus) = d + F(qplus)-F(q)
```

Let tau be the requested steady_tolerance, not the returned claimed residual.
An ideal stopped step has ||d||inf<tau and delta=dt*tau bounds every free
velocity change. Fixed normals do not change. Each tangential ghost changes
by at most delta because its dependence has slope -1. Set
M=max(abs(final faces and final ghosts))+delta, bounding both states.
An averaged velocity changes by at most delta and has magnitude at most M.
Each square or product flux therefore changes by at most 2*M*delta.
The four signed convective faces give at most 8*alpha*M*delta.
The four-neighbor-minus-four-center diffusion row gives at most
8*beta*delta, including boundary reflection. Consequently the target is

```
B = tau * (1 + dt*(8*alpha*M + 8*beta)).
```

Before forming B, require 0<dt<=min(.15*h*h/nu,.2*h), evaluated with the
same binary scalar ordering as the native timestep ceiling. The native
speed is at least one. A forged large dt cannot authorize arbitrary slack.
The original reported steady-rate, mass, gauge and thermal checks still apply.

IMPORTANT: the identity above is an exact-arithmetic derivation. The native
predictor, projection and pressure accumulation round; their old pressure and
correction fields are not in the result schema. This checker does NOT claim
to enclose those unavailable rounding errors or guarantee that every native
stopping event passes. It imposes an ADDITIONAL independent target on returned
fields: exact ||R||inf<=exact B. A native stop outside that target is rejected,
not granted a larger tolerance. Exact arithmetic certifies this returned-field
comparison, not the internal native execution history.

The constant pressure nullspace is handled by the existing gauge admission.
Small residuals do not establish uniqueness or distance to the continuum
solution; high-Re conditioning and mesh error remain separate. Finite binary
inputs can generate unrepresentable squared fluxes: exported diagnostics must
remain finite, and an overflow cannot become an accepted zero residual.

## Predeclared verification and evidence

Required fixtures: exact resting zero state; zero moving-lid field has top
free-U residual 2*beta*lid; affine pressure gives exactly negative constant
gradient; independently integrated polynomial interior momentum; exact
Lipschitz bound on distinct admissible closed-face states; shifted/mean-zero
pressure corruption; missing/NaN/infinite/large finite fields; invalid or
inflated dt; and actual native n=8,12,16 moving-lid cases spanning Re=1,100,400.
Independent exact oracles use rational arithmetic and require exact equality;
actual native cases must pass the unmodified derived target. No fixture is a
continuum benchmark. Executed commands and results will be appended after tests.

### Executed Windows evidence

The following command completed on 2026-10-25, before the separately reserved
propulsion workload window; no tests were run during that exclusive window:

```powershell
$env:SPIKE_NATIVE_CHT_EXECUTABLE = (Resolve-Path 'build/solver-reorg/airflow-build/Release/spike_native_cht.exe').Path
python -m unittest discover -s tests/python -p test_native_cavity_momentum.py -v
```

All 11 tests passed in 1.533 seconds (unittest-reported elapsed time), with
no skips. This includes actual native (n,Re)=(8,1),(8,100),(12,100),(16,100),
(8,400), each with the same-temperature thermal branch and an independently
rejected mean-zero pressure corruption. The non-power-of-two grid exercises
the declared coefficient convention. These are five actual discrete solutions,
not a grid-convergence study. The polynomial interior oracles are independent
exact identities and are not admitted as full closed-cavity solutions.

One preceding n=8, Re=100 actual-output check measured independent residual
9.32563886400949e-8 against derived limit 2.6640000009999997e-7, with native
reported steady rate 9.441807780063982e-8. Checker-only elapsed time was
0.007414 seconds locally; this is not a portable performance guarantee.

Executed native binary SHA-256 was
`435cc2d273849b39e45653939a11543fe1ff2d8fd8bce2feddd1bf509df641c2`.
The independent checker source SHA-256 was
`2556547d09b0cba6f0cff4f4be0247a4e3aa776b17a76f50b9ff49d900d4ab23`.
The native source binding is given at the start of this record. A subsequent
test-file cleanup removed only an unused import, not an oracle or threshold.

An independent reviewer inspected both stencil components, ghost/index/sign
conventions, coefficient freezing, the Lipschitz derivation and timestep guard.
No implementation correction was required. This is agent-authored mathematical
and code-review evidence, not the required knowledgeable human release review.
Full-suite, Linux, frozen-worker and installer checks remain the integrating
owner's separately recorded evidence; none is implied by these focused tests.

Knowledgeable human numerical review before release remains required.
