<!-- SPDX-License-Identifier: Apache-2.0 -->
# Turbulence and rotating-flow prerequisites - 20 October 2026

Status: independently authored requirements and derivation review, **not an
implemented solver or completed CFD-04/05 gate**. This record does not authorize
a broader Reynolds envelope, production release, or substitution of prescribed
eddy viscosity/actuator forcing for a solved turbulence/propeller model.
Knowledgeable human numerical review remains required.

Subsequent same-day implementation: separate
[prescribed symmetric stress](ENCLOSURE_SYMMETRIC_STRESS_20261020.md),
[fixed-velocity SA-noft2 transport](ENCLOSURE_SA_TRANSPORT_20261020.md) and
[whole-frame rotation](ENCLOSURE_ROTATING_FRAME_20261020.md) now have actual
manufactured checks. This requirements record's original inspection is retained
below; it does not establish coupled RANS, blade/stator interfaces or propellers.

## Repository evidence and recommendation

At inspection, `enclosure_laminar.py` solves steady constant-property momentum
on a full uniform closed box, with a reported Reynolds upper bound limited to
20. `enclosure_energy.py` transports sensible heat on accepted shared face
velocities and rejects exterior mass flux. Neither contains a transported
turbulence state, blade boundary motion, or rotor/stator interface.
Concurrent nonuniform/obstacle momentum work does not by itself change these
facts or establish a new regime. The value 20 is an admission limit, not a
universal transition criterion.

Smallest honest next development increments:

1. Verify a variable-coefficient **symmetric stress** operator, transported
   closure state and coupled nonlinear convergence on fixed-wall geometry.
   A separately versioned SA variant is smaller than SST. A nontrivial
   closure-manufactured solution can verify equations even before an engineering
   turbulent regime is admitted; it must be labeled equation verification.
2. Independently add a whole-domain, constant-angular-velocity laminar frame,
   solving Coriolis coupling in momentum and recovering physical pressure.
   A co-rotating enclosure is a rotating-fluid benchmark, not a propeller.
3. Only after those checks, extend boundary/topology support for a rotor in a
   stationary environment, near-wall resolution, traction quadrature and
   open-domain conservation. Then execute geometry-matched propeller validation.

Completing engineering turbulence and propellers within the present closed-wall
constant-viscosity contract is impossible without these new prerequisites.
This is a scope/dependency statement, not a claim that the broader work cannot
be implemented. A module that only calculates closure coefficients or transforms
an already accepted field cannot satisfy either stage.

## Reviewed primary-source scope

Retrieved 20 October 2026. No external solver source, tests, meshes or datasets
were copied, translated, imported or redistributed. Official documentation and
published equations informed this independently authored specification.

- NASA's [TMR migration notice](https://www.nasa.gov/nasa-turbulence-modeling-resource/),
  updated 19 May 2026, identifies the official replacement host. Historical
  `turbmodels.larc.nasa.gov` equation links currently redirect to that notice.
- TMR [Spalart-Allmaras model](https://tmbwg.github.io/turbmodels/spalart.html):
  standard-model transport, constitutive relation, constants, wall distance,
  boundary conditions, modified-vorticity limiting, SA-neg and SA-noft2 naming
  were reviewed. The page identifies Spalart and Allmaras, *A One-Equation
  Turbulence Model for Aerodynamic Flows*, Recherche Aerospatiale 1, 1994,
  pp. 5-21 as primary journal reference. This review used the TMR specification,
  not the original paper's full text. TMR's corrected `cw1` includes
  `kappa^2`; its nearest-wall distance is not nearest wall-node distance.
- TMR [Menter SST model](https://tmbwg.github.io/turbmodels/sst.html):
  standard and SST-2003 equations, blends, production limits, constants and
  smooth-wall conditions were reviewed. Original model: Menter, AIAA Journal
  32(8), 1994, pp. 1598-1605,
  [DOI 10.2514/3.12149](https://doi.org/10.2514/3.12149).
  SST-2003 changes the viscosity invariant and applies its production limiter
  to both equations; mixing these definitions silently creates another model.
  The original articles' full texts were not reviewed.
- COMSOL 6.4 official [rotating machinery theory](https://doc.comsol.com/6.4/doc/com.comsol.help.cfd/cfd_ug_fluidflow_single.06.138.html)
  and [frozen rotor](https://doc.comsol.com/6.4/doc/com.comsol.help.cfd/cfd_ug_fluidflow_single.06.139.html):
  frame/velocity descriptions and applicability prose were reviewed.
  Image-only displayed equations were not reliably retrieved and are not
  claimed as transcribed/reviewed equations. The derivation below is independent.
  Frozen rotor's geometry remains fixed; generic rotor/stator interaction is
  not thereby time-resolved.
- COMSOL 6.4 [Rotating Channel](https://doc.comsol.com/6.4/doc/com.comsol.help.models.mfl.rotating_channel/rotating_channel.html):
  explicit centrifugal/Coriolis force expressions and clockwise-axis convention
  were reviewed, along with its warning about an inlet boundary inconsistency.
  This is an official implementation-description reference, not independent
  physical validation and not an example to copy.
- Udayan Gumaste, *Euler Flow Computations on Non-Matching Unstructured Meshes*,
  NASA/CR-1999-209155, June 1999,
  [official report](https://ntrs.nasa.gov/api/citations/19990064096/downloads/19990064096.pdf):
  sections 3.3.2 and 4.1.4, printed pp. 31-32 and 48-49, were reviewed for
  uniform-state preservation and mesh swept-volume consistency. No Euler
  discretization is adopted from this report.
- TMR [flat-plate verification](https://tmbwg.github.io/turbmodels/flatplate.html),
  [backward-step validation](https://tmbwg.github.io/turbmodels/backstep_val.html)
  and the [UIUC propeller database](https://m-selig.web.engr.illinois.edu/props/propDB.html)
  were reviewed at case-description level. No numeric dataset was ingested;
  redistribution rights, exact case files and uncertainty treatment remain
  separate admission work.

## Turbulence: non-negotiable coupled contract

For incompressible constant-density mean flow, independently collect molecular
and modeled deviatoric stresses as

```text
S = (grad(u) + transpose(grad(u)))/2
div(u) = 0
rho [dt(u) + div(u tensor u)]
    = -grad(p*) + div(2 (mu + mu_t) S) + f
```

`u` is m/s, `rho` kg/m^3, `mu` and `mu_t` Pa s, `f` N/m^3.
For a two-equation Boussinesq closure, `p* = p + 2 rho k/3`;
the physical pressure must be recovered before reporting blade/body loads.
One-equation SA does not supply an independently computed `k`.

For spatially variable viscosity, `div(2 mu_eff S)` is not generally
`mu_eff laplacian(u)` nor three uncoupled variable scalar diffusion operators.
The derivative of viscosity and cross-component strain terms matter even when
`div(u)=0`. Therefore replacing the scalar `mu` parameter or scaling the old
matrix is not a correct general RANS implementation.

Integration by parts yields, on stationary no-slip walls,

```text
integral u dot div(2 mu_eff S) dV = -integral 2 mu_eff S:S dV.
```

Use this as a discrete operator design requirement. A manufactured divergence-
free field with varying `mu_eff` must expose omitted cross terms; constant-
viscosity Poiseuille alone cannot detect that defect.

### Minimum SA implementation

Choose and name one exact variant. A bounded nonnegative `SA-noft2` research
route avoids the original `ft2` terms but still requires production,
wall destruction, variable diffusion, gradient-square source, wall damping,
modified vorticity and its singular-case handling. It must not be named
SA-neg unless the negative branch is actually implemented. Prefer the full
documented SA-neg variant if robust negative-iterate handling is required.

In project notation, let `q` be the transported viscosity-like state in m^2/s.
Its positive-branch SA-noft2 balance is

```text
dt(q) + div(u q)
  = cb1 S_hat q - cw1 fw (q/d)^2
    + [div((nu+q) grad(q)) + cb2 |grad(q)|^2] / sigma
mu_t = rho q fv1.
```

All auxiliary functions, constants and selected `S_hat` guard belong in a
versioned method specification before implementation. Do not replace `S_hat`
by strain, omit nonlinear diffusion, or add an arbitrary production source.
`d` is distance to the actual admitted wall surface, including obstacle edges.
Faces at a no-slip wall impose `q=0`; positive cell-center distance is not
replaced by zero. A positive initial seed is an explicit numerical input:
`q=0` everywhere can be an invariant trivial state and is not evidence of a
working turbulent closure.

At each outer iteration the accepted velocity supplies closure advection and
velocity gradients; the new closure supplies momentum stress. Recompute both
residuals at the same final state. Under-relaxation is a nonlinear control, not
a replacement for the transport equation. Any positivity limiter, rejected
iterate, fallback and final source imbalance must be reported. Negative states
must either use the selected published branch or fail closed; clipping them
and reporting the unclipped equation as converged is invalid.

### Minimum SST implementation, if selected instead

Transport `k` (m^2/s^2) and `omega` (1/s), including advection, molecular and
turbulent diffusion, production, destruction, coefficient blending and
cross-diffusion. Require `k>=0`, `omega>0`, finite viscosity and resolved wall
distance. Choose exactly SST, SST-2003 or a named modified variant, including
production limiter and pressure convention. Smooth-wall `k=0` does not imply
`omega=0`: the selected wall formula depends on molecular viscosity and the
first normal wall spacing. Reject an unavailable/ambiguous wall spacing.

An isolated local source ODE is a useful unit test, not a transported coupled
RANS result. Test uniform decay, nonuniform diffusion, independent manufactured
transport/source balance, near-wall behavior, positivity under severe source
stiffness, and momentum sensitivity to closure feedback. Every final result
needs actual closure fields, residual histories, wall-resolution diagnostics,
the modeled-versus-resolved distinction and model-form limitations.

### Energy and regime admission

Turbulent heat transport is a further constitutive assumption, not implied by
a momentum closure. If chosen, state and version a turbulent Prandtl number
and `conductivity_eff = conductivity + mu_t cp / Pr_t` only in fluid regions.
Preserve shared interface heat fluxes, `mu_t=0` at resolved walls, and separate
conduction and modeled mixing diagnostics. This remains sensible-energy
transport unless viscous/shaft heating and total-energy terms are implemented.

Do not bypass the existing Reynolds limit by setting a large `mu_t`: compute
the admission Reynolds number from **molecular** viscosity. Any higher-Re
route needs a separate experimental contract, accuracy envelope, boundary-
layer resolution, solver/resource controls and benchmark evidence. Manufactured
closure checks at low Re do not establish turbulent physical applicability.

## Rotation: independent frame and conservation derivation

Let `Q(t)` be an orthogonal rotation from frame coordinates `r` to inertial
coordinates, with fixed origin, and let `Omega` be angular velocity expressed
in rotating coordinates. A material point has

```text
x = origin + Q r
u_inertial = Q (v + Omega cross r)
a_inertial = Q [Dv/Dt + 2 Omega cross v
                + dOmega/dt cross r + Omega cross (Omega cross r)].
```

This follows by differentiating `Q a` as
`d(Q a)/dt = Q [da/dt + Omega cross a]` twice. For constant `Omega` and
constant density the relative-velocity equation becomes

```text
rho [dt(v) + v dot grad(v)] =
    -grad(p) + div(2 mu S(v)) + f
    -2 rho Omega cross v - rho Omega cross (Omega cross r).
```

`Omega` is rad/s, `r` m; both rotation terms are N/m^3. Define
`Phi = |Omega cross r|^2/2`, so
`grad(Phi) = -Omega cross (Omega cross r)`.
Solving with reduced pressure `p_red = p - rho Phi` removes the centrifugal
gradient for constant density. Recover `p=p_red+rho Phi` for physical loads.
With `v=0`, exact co-rotation gives `p=p0+rho Phi`. An implementation returning
constant physical pressure in that case has lost the centrifugal contribution.
Variable density needs separate treatment; changing angular velocity needs the
Euler term and a real transient state.

Since `v dot (Omega cross v)=0`, Coriolis acceleration performs no work.
On staggered nonuniform unknowns, interpolation must not destroy this property:
the weighted discrete Coriolis operator must be skew-adjoint in the kinetic-
energy inner product. Assemble it in the coupled momentum solve, not as a
one-shot velocity correction. Check arbitrary-axis and reversed-axis cases,
zero rotation, rigid co-rotation and a nonzero relative-flow case.

### Frame motion is not blade motion

A globally co-rotating closed box is geometrically stationary in its own
frame. A propeller in a stationary box is not: a nonaxisymmetric stationary
outer wall changes orientation in the rotor frame. Assigning its wall velocity
`-Omega cross r` on a frozen incompatible boundary can introduce normal wall
motion through a fixed mesh. That is not an exact rigid-frame problem.

A genuine next rotor stage needs either:

- a geometry-compatible steady rotating-frame domain with correctly transformed
  boundaries and independently justified steady approximation; or
- separate rotating/stationary regions with conservative common interface
  fluxes, followed by ALE/sliding geometry for time-dependent interaction.

Actual blade no-slip conditions are `u_wall=Omega cross (x-origin)` in the
inertial frame and zero relative velocity in its rotor frame. Stair-stepped
stationary obstacles with an arbitrary swirl force are not rotating blades.
An actuator disk/line could be a separately named lower-fidelity model, but it
needs load-law provenance and coupled force evaluation; it cannot supply
geometry-resolved blade accuracy.

For moving control volume `V(t)` and mesh velocity `w`, Reynolds transport
gives the independently formulated conservation statement

```text
d/dt integral_V U dV + integral_boundary [F(U)-U w] dot n dA
    = integral_V source dV
dV/dt = integral_boundary w dot n dA.
```

The second identity must use the same face-time geometry as the first. Discrete
swept-volume mismatch otherwise changes a uniform state even with zero physical
forcing. Passing GCL alone does not establish momentum or turbulence accuracy.

### Thrust, torque and power

Use physical pressure and complete viscous/modeled stress with an explicitly
oriented blade normal. If `n_b` points outward from the blade into the fluid,
traction on the blade is `t=(-p I+tau) n_b`.
For quadrature location `x`, derive

```text
F_blade = integral t dA
M_blade = integral (x-origin) cross t dA
T = F_blade dot axis
Q_drive = -M_blade dot axis
P_shaft_to_fluid = |Omega| Q_drive.
```

State axis/sign conventions and distinguish motor torque from fluid torque.
The current overlap operator without quadrature positions cannot establish
moment conservation. Shaft work must also agree with the fluid angular-momentum
and mechanical-energy budgets, including storage, open boundaries and
dissipation; otherwise a force plot is not an accepted rotor solution.

## Checkable staging and candidate benchmarks

| Milestone | Required evidence | Claim allowed after completion |
| --- | --- | --- |
| Variable stress | Independent polynomial/trigonometric forcing, viscosity variation, strain dissipation, wall shear, three-grid error trend | Bounded variable-viscosity operator |
| Coupled closure | Nonzero transported closure, final coupled residuals, manufactured source oracle, positivity/failure cases and seed sensitivity | Named equation-verified experimental closure |
| Turbulent regime | Exact model/case matching, wall-resolution and domain/grid convergence, measured or DNS observables with model discrepancy | Only the matched experimental envelope |
| Global rotating frame | Rigid-rotation pressure, energy-neutral Coriolis, arbitrary-axis transform and nonzero relative flow | Co-rotating laminar frame |
| Rotor topology | Geometry/BC compatibility, traction quadrature, common interface mass/momentum and angular-momentum budgets | Bounded frozen-rotor calculation |
| Sliding/ALE rotor | Uniform-state preservation, swept-volume identity, transient wall motion, time/interface refinement and rollback | Bounded unsteady rotating geometry |
| Propeller case | Exact geometry, operating point, thrust/torque/power conventions, mesh/domain/time/closure refinement and independent measurements | Only the matched propeller envelope |

For the flat plate, TMR provides nested verification grids and model-specific
reference results. Its stated Mach 0.2 case is compressible: an incompressible
implementation must not demand an identical limiting result or claim exact
case equivalence. Open inflow/outflow/far-field support is a prerequisite.
TMR's backward-facing-step case adds measured reattachment, pressure,
skin friction and profiles; matching upstream boundary layers matters.
Neither benchmark is executable through the present closed-box interface.

For rotors, first use exact rigid rotation and laminar circular Couette flow
`u_theta=A r+B/r`, with constants independently derived from wall speeds and
torque derived from `tau_rtheta=mu (du_theta/dr-u_theta/r)`.
These require admitted circular geometry or an explicitly quantified geometry
approximation. Then use a UIUC small-propeller case with matched blade geometry,
RPM, Reynolds convention and thrust/power data. The database identifies APC
geometry as a separate source; a propeller name and diameter are insufficient.
UIUC cases are candidates, not evidence already executed by SPIKE.

All milestone tolerances must be fixed before accepting results and appropriate
to the observable, units and scale; this document does not invent universal
engineering-error tolerances. Record actual input/source/code versions, grids,
timing/memory, iteration histories, rejected runs and uncertainty. No turbulence
or rotating-flow acceptance tests were executed by this requirements subtask;
the proposed milestones remain open.
