<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fixed-velocity SA-noft2 transport equation verification - 20 October 2026

## Claim and exclusions

`python/spike_core/enclosure_sa_transport.py` actually iterates a steady scalar
transport equation with supplied incompressible MAC velocities. It is an internal,
research-only, full-fluid closed-box prerequisite, not a coupled RANS solver.
It does not enable engineering turbulence, alter molecular-Reynolds admission,
solve momentum, model turbulent heat transfer, handle obstacles or establish
blade/rotor capability. A nonzero computed eddy viscosity is an equation output,
not evidence of physically turbulent flow. Knowledgeable human numerical review
and independent physical validation remain mandatory before release.

## Primary source and exact variant

Reviewed 20 October 2026: NASA/TMBWG's official
[Spalart-Allmaras specification](https://tmbwg.github.io/turbmodels/spalart.html),
sections "Standard", its Note 1(c), and "SA-noft2". The precise adopted content is
the positive transport equation with ft2 absent, wall damping and destruction
functions, corrected cw1, zero wall value, physical nearest-wall distance, and
the c2=0.7/c3=0.9 modified-vorticity guard. The page identifies the 1994 Spalart
and Allmaras journal article and the 2012 Allmaras/Johnson/Spalart clarification.
Those papers' full text was not reviewed for this increment. No SA-neg branch,
trip, roughness, rotation or compressibility correction is implemented.

The implementation, derivation below, tests and synthetic fields are independently
authored from equations; no external implementation, fixture, mesh or dataset was
consulted, translated or redistributed. The numerical method is SPIKE-owned under
Apache-2.0; citation does not import any external software.

## Independently formulated mathematics

Let q be transported kinematic viscosity, nu constant molecular viscosity (both
m2/s), u the supplied velocity (m/s), d nearest physical wall distance (m),
and Omega the magnitude of curl(u) (1/s). For q>=0:

```text
u.grad(q) = P - D + [div((nu+q) grad(q)) + cb2 |grad(q)|^2]/sigma + f
P = cb1 S_hat q
D = cw1 fw (q/d)^2
nu_t = q fv1
```

The optional manufactured f has units m2/s2 and is explicitly named
`manufactured_source_m2_s2`. It is not an engineering forcing model.
Constants are cb1=.1355, cb2=.622, sigma=2/3, kappa=.41,
cw1=cb1/kappa^2+(1+cb2)/sigma, cw2=.3, cw3=2 and cv1=7.1.

For chi=q/nu, fv1=chi^3/(chi^3+cv1^3),
fv2=1-chi/(1+chi*fv1), and B=q*fv2/(kappa*d)^2:

```text
S_hat = Omega+B                         if B >= -.7 Omega
S_hat = Omega+Omega(.49 Omega+.9 B)/(-.5 Omega-B) otherwise
r = min(q/(S_hat*kappa^2*d^2), 10)       if S_hat > 0
r = 10                                 if S_hat = 0
g = .7 r + .3 r^6
fw = g [65/(g^6+64)]^(1/6)
```

At q=0 and Omega>0, r=fw=0; at both q=Omega=0 the specified r=10
still yields exactly zero production and destruction because q=0. No negative
iterate is evaluated as though it were SA-neg. On this exact rectangular domain,
minimum distance to the six planes is the physical nearest-wall distance, not
distance to a wall node. Cell-center distance is strictly positive.

Integrating over cells gives shared face advection. Each internal face uses its
single normal volume flux F=A*u_n, and an upwind q; the same contribution enters
one cell and leaves its neighbor. Exterior normal velocities must be exactly zero.
The supplied velocity must pass discrete divergence checking, making conservative
div(u*q) consistent with the stated incompressible advective form.

Introduce the diffusion potential H(q)=nu*q+q^2/2. The chain rule gives
grad(H)=(nu+q)grad(q), so the integrated diffusive flux across a center-to-center
link is A*(H_N-H_P)/distance. At a physical wall H(0)=0 and the center-to-wall
distance is half the adjacent cell width. This includes nonlinear diffusion
without dropping its grad(q)^2 part. The separate cb2 term remains explicit in
the nonlinear residual. A quadratic interpolant through neighboring centers,
using physical zero wall values at the boundary, supplies each cell derivative.
The same derivative stencil applied to cell-reconstructed velocity supplies
curl(u), not the strain invariant.

Writing L for integrated negative Laplacian, A for upwind transport, G_a for
derivatives and V for volumes, the exact assembled residual is

```text
R(q) = A q + L H(q)/sigma
       - V [P(q)-D(q)+cb2 sum_a (G_a q)^2/sigma+f].
```

Its integrated units are m5/s2. The Newton diffusion tangent is
L*diag(nu+q)/sigma; the gradient-square tangent is
-2 cb2/sigma sum_a diag(V*G_a q)*G_a. Only the local source derivative uses a
forward numerical perturbation of 1e-7*max(nu,max(q)); it does not alter the
residual or supply the oracle. A row-scaled sparse solve and up to 32 decreasing
positive step trials seek a residual-decreasing iterate. Negative states are
rejected/backtracked, never clipped. Actual rejected trials are reported.

## Admission, stopping and numerical limitations

The request requires the exact built rectilinear grid, three face-normal arrays,
positive molecular nu, nonnegative initial q and controls (1-100 iterations,
relaxation .1-1, relative tolerance 1e-12-1e-7). At least two cells per axis,
at most 4096 cells and metric ratio at most 64 bound the research solve.
No obstacles, external mass flux, unknown request keys, nonfinite values or
zero/negative wall distances are admitted.

Success checks the actual full steady residual, not an iterate increment or a
fixed iteration count. A nonzero manufactured load supplies a seed-independent
reference norm max(abs(V*f)); otherwise the reference is the maximum magnitude
of initial residual/assembled terms. A zero reference is handled exactly without
a dimensional floor. Thus a homogeneous positive seed can decay to the declared
initial-state-relative tolerance; it is not claimed to be exactly zero.
The exact zero seed with zero f has zero residual and eddy viscosity.

All dimensional NumPy arithmetic traps overflow, invalid values, divide by zero
and underflow. Sparse vector products explicitly multiply entries before
accumulation, because a library sparse/BLAS multiplication need not honor NumPy's
floating-point policy. Unsupported extreme scales fail closed; no arbitrary
maximum eddy viscosity is imposed. Sparse factorization is row-scaled and final
physical residuals are rechecked, but a global nonlinear uniqueness guarantee
or rigorous condition-number bound is not claimed.

Storage for assembled stencils is O(cells); sparse LU fill is data-dependent
and is not independently hard-capped beyond the 4096-cell admission.
Cancellation is checked before admission, per assembly axis, at every nonlinear
iteration/backtrack and before publication. One sparse factorization itself is
not interruptible. Failure/cancellation never publishes solution fields.

## Independent executable verification

The fixture is in `tests/python/test_enclosure_sa_transport.py`; no source term
calls the implementation's coefficient helper or assembler. On the unit cube,
define b(t)=t(1-t), p(t)=b(t)^2, and

```text
psi = 10 p(x)p(y)p(z)
u = (d_y psi, -d_x psi, 0)
q = .64 b(x)b(y)b(z) (1+.5x+.3y)
nu = .01
```

The modulation ensures u.grad(q) is nonzero: q is not tangent to the streamline
field. The test differentiates these polynomials analytically for q gradient,
q Laplacian and velocity curl. MAC face fluxes use differences of the analytical
streamfunction and are discretely solenoidal independently of the solver.
The manufactured source is evaluated from the continuous equation:

```text
f = u.grad(q)-P+D-[(nu+q)lap(q)+(1+cb2)|grad(q)|^2]/sigma.
```

Predeclared acceptance remains relative q L2 error <.1 on the finest n=12 grid
and both observed refinement orders >=.7, appropriate to first-order upwind
advection. Executed with Python 3.14.2, NumPy 2.4.2 and SciPy 1.17.0:

| Cubic grid | Relative q L2 error | Newton steps | Actual relative residual |
| --- | ---: | ---: | ---: |
| 4 | .01659444856 | 5 | 2.333e-15 |
| 8 | .00492512709 | 5 | 2.369e-14 |
| 12 | .00235132149 | 5 | 4.377e-15 |

Orders are 1.75247 and 1.82352. The n=12 run rejected one step and did not clip
any state. These are fixture-specific observations, not universal accuracy bounds.

A separate strong nonlinear fixture replaces .64 by 1.92 at n=8, with the
continuous source recomputed independently. It converged in five steps with
relative error .00779787490, residual 2.388e-14, maximum chi=4.17798 and maximum
nu_t=.00707213541 (0.7072 times molecular nu). Nonlinear diffusion's maximum
magnitude divided by total diffusion's maximum was .799053; the cb2 source
maximum integrated magnitude was 4.80665e-5 m5/s2. The modified-vorticity guard
was active in 216 of 512 cells. Tests require nu_t>.1*nu somewhere,
nonlinear fraction>.05, nonzero cb2 source and both guard branches.

Ten tests passed via:

```text
python -m unittest discover -s tests/python -p test_enclosure_sa_transport.py -v
```

They include the three-grid and strong fixtures, nonuniform tensor cuts,
alternate initial amplitudes .2 and 2, time-unit scaling by 1e-20 and 1e20,
positive-seed homogeneous decay, exact zero state, scalar coefficient limits,
both modified-vorticity branches, r cap/fw zero, cancellation, nonconvergence,
negative/NaN q, zero molecular nu, forged zero-center geometry, exterior flux,
non-solenoidal MAC input, unknown keys and dimensional underflow rejection.
The global architecture check was also executed but failed on the unrelated
`app/src/fieldVolumeModel.ts` spread-extrema guard; this increment did not modify
that file. Repository-wide checks and coupled momentum integration are owned by
the integrating task, not claimed as passed by this transport-only record.

No measured benchmark, wall-layer resolution study or physical turbulence
validation has been performed. The wider
[turbulence/rotor requirements](TURBULENCE_ROTOR_REQUIREMENTS_20261020.md)
remain open.
