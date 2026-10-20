<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coupled mean-flow/SA-noft2 research verification - 21 October 2026

## Fixed acceptance gates, recorded before execution

The internal full-closed-box equation experiment must solve mean momentum with
mu_eff=rho*(nu+q*fv1), solve positive-branch SA-noft2 with that velocity, then
reassemble BOTH residuals at the updated q and same velocity/pressure. An
iterate difference or a momentum residual evaluated at stale viscosity cannot
qualify success. Original molecular Reynolds upper bound remains <=20.

On independently continuous manufactured n=4/8/12 cases, finest relative
dual-volume velocity L2 error must be <.05, finest relative q L2 error <.1,
and each observed order for each field must be >=.7. Both normalized steady
residuals must be <=1e-9. The closure must have nu_t>=.1*nu somewhere and
materially affect velocity. These gates will not be weakened after execution.

This is equation verification only, not engineering turbulence or production
qualification. No worker route, capability declaration or schema is changed.

## Source scope and independent formulation

Re-reviewed on 21 October 2026:

- NASA/TMBWG [Spalart-Allmaras](https://tmbwg.github.io/turbmodels/spalart.html):
  one-equation eddy-viscosity relation, Boussinesq convention, positive-branch
  SA-noft2, and Note 1(c) modified-vorticity guard. The exact adopted constants,
  r cap and zero cases remain those specified in the
  [SA transport method record](ENCLOSURE_SA_TRANSPORT_20261020.md).
- NASA/TMBWG [implementing RANS](https://tmbwg.github.io/turbmodels/implementrans.html):
  displayed mean momentum equation, molecular stress, Boussinesq modeled stress
  and strain definition. Only its constant-density incompressible reduction is
  adopted; thermodynamic, compressible and turbulent heat-flux equations are not.

The inherited MAC topology, inertial flux and positive symmetric-strain
quadrature are documented in the
[stress derivation](ENCLOSURE_SYMMETRIC_STRESS_20261020.md). Its cited Veldman
sections were not newly read for this coupling increment. No external solver
source, meshes, examples or datasets were consulted or copied. The coupling,
continuum forcing, derivative below and tests are independently authored.

For constant density rho [kg/m3], molecular nu [m2/s], velocity u [m/s],
mean pressure p [Pa], and transported q [m2/s], the equations solved are

```text
rho (u.grad)u - div(mu_eff (grad(u)+grad(u)^T)) + grad(p) = f_m
div(u) = 0
u.grad(q) - P(q,curl(u)) + D(q,d)
  - [div((nu+q)grad(q)) + cb2 |grad(q)|^2]/sigma = f_q
mu_eff = rho (nu + q fv1(q/nu))
```

`f_m` [N/m3] and `f_q` [m2/s2] are explicitly named manufactured research
sources, not a fitted discrete right-hand side. All walls impose u=0 and q=0.
The domain is a full orthogonal rectilinear fluid box, so the inherited minimum
distance to the physical six wall planes remains applicable. The SA variant
does not solve k; no unavailable isotropic k correction or blade pressure/load
reconstruction is claimed. `pressure_pa` uses the stated one-equation mean
pressure convention.

Independently applying product and quotient differentiation, with
C=7.1^3, chi=q/nu and v=chi^3/(chi^3+C), gives

```text
dv/dchi = 3 C chi^2 / (chi^3+C)^2
d(q v)/dq = v + chi dv/dchi = v (4-3v)
grad(mu_eff) = rho v (4-3v) grad(q).
```

For any continuous divergence-free manufactured u, expansion of the symmetric
stress gives the analytic momentum source

```text
(f_m)_i = rho sum_j u_j d_j u_i + d_i p
          - mu_eff lap(u_i)
          - sum_j (d_j u_i+d_i u_j) d_j(mu_eff).
```

The final term includes the cross-component gradient contribution; replacing it
with three scalar variable-diffusion operators is not equivalent. The test
evaluates this expression from polynomial derivatives without calling a
production stress assembly or numerical differentiator.

## Actual coupling and fresh-state certificate

Each outer step solves the inherited velocity/pressure saddle system using the
old positive q-derived viscosity, then solves the nonlinear SA equation using
that same accepted velocity. Optional outer relaxation forms a convex
combination of old and solved q; negative inner q is rejected before relaxation.
The fresh viscosity is then assembled from the actual relaxed q.

At the unchanged accepted velocity/pressure and updated q, recompute

```text
R_m = [K(q_new)+C(u)] u - B^T p - F
R_q = A(u) q_new + L[nu q_new + q_new^2/2]/sigma
      - V[P-D+cb2 sum_a(G_a q_new)^2/sigma+f_q].
```

The momentum norm is weighted by inverse square-root dual volumes and divided
by the corresponding F norm. The closure maximum norm is divided by
max(abs(V*f_q)), independently of anything reported by the SA subsolver. For
zero manufactured f_q the fixed first-outer actual term/residual magnitude is
used instead. Zero references have explicit exact-zero branches; no dimensional
residual floor is introduced. Both reconstructed residuals, not a q increment,
must pass the outer tolerance at the same state.

The first outer momentum residual in the nontrivial fixture is about .12 even
though the inner mean solve has converged. This deliberately exposes why the
old-viscosity certificate is stale after updating q. It falls below 1e-9 only
after further actual mean/SA coupling.

Before publication, recompute mean kinetic work, symmetric dissipation,
strain-quadrature dissipation, advection work and pressure work with the updated
viscosity and same velocity. Both energy defects must be
<=min(1e-9,10*outer_tolerance); outer controls cannot weaken the existing 1e-9
stress certificate. Continuity checks remain inherited and are repeated during
closure assembly.

Crucially, the mean iteration receives the original molecular mu=rho*nu for
its Reynolds admission, never minimum effective viscosity. A separate direct
check also requires

```text
sqrt(3) max(abs(face_u)) max(box_extent) / nu <= 20.
```

This deliberately narrow bound is an inherited numerical admission limit, not
a physical transition criterion. The research label does not expand it.

## API, resource and failure boundaries

`solve_enclosure_rans_research(request, cancel_check=None)` accepts exactly:

- contract `spike/enclosure-rans-research/v1` and the built `grid`;
- positive `density_kg_m3`, `molecular_kinematic_viscosity_m2_s`;
- nonnegative cell `initial_nu_tilde_m2_s`;
- cell `manufactured_momentum_source_n_m3` vectors and
  `manufactured_sa_source_m2_s2` scalars, including explicit zero arrays;
- `outer_controls`, `momentum_controls`, `sa_controls`, each containing
  `max_iterations`, `relative_tolerance`, and `relaxation`.

Outer limits are 1-100 steps, tolerance 1e-11 through 1e-9 and relaxation .1-1.
Both inherited inner tolerances must be <=outer_tolerance/10 and preserve their
existing ranges/iteration bounds. Built-grid validation, at least two cells per
axis, <=4096 cells and max/min cell-width ratio <=64 apply before allocating
the full mask or solving. A forged shape is not trusted as an allocation size.
The validated mean force and closure source shapes bound all input fields.

Retained request JSON can be loaded and replayed through this private callable.
After exact built-grid validation, the boundary normalizes accepted list-valued
geometry to native arrays and tuple shapes before invoking inherited private
kernels. It preserves supplied validated metrics rather than recomputing them;
inconsistent volumes, centers, widths, face areas or parent maps still fail.
This repairs a concrete representation mismatch: the validator accepted numeric
lists, but downstream volume indexing required NumPy tuple indexing. It does
not add a worker method, public schema, or externally admitted CFD route.

Outputs retain only the final accepted face velocities, pressure, q and nu_t;
outer history is at most 100 compact entries. Fields are converted with finite
JSON validation and checked against an explicit 2 MiB field payload limit
before being installed in the result. This is an internal Python-array API,
not new JSON worker admission. All failures, exhausted inner/outer iterations,
nonfinite/unrepresentable arithmetic and cancellation return no solution fields.

Each outer history entry also retains the actual mean-inner relative residual
and scaled saddle condition estimate. The latter remains admission-checked at
<=1e10 by the inherited solve. Final diagnostics label the estimate as
`last_mean_subsolve_before_closure_update`: it is the last factored inner
matrix's estimate, not a falsely asserted condition bound on the fresh matrix.
Fresh momentum and closure residuals are separately certified as above.

Cancellation is polled during inherited assembly and inner solves, at outer
boundaries and before publication. Sparse factorization and condition estimation
remain noninterruptible within one call; the 4096-cell limit does not constitute
a hard LU-fill memory cap. No unique-solution proof or physical-model validation
is implied by block iteration. All results remain `research_only:true`,
`production_qualified:false`, and `model_status:equation_verification_only`.

## Executed continuum verification

The fixture extends the independent fixed-velocity SA polynomial on the unit
cube. Let b(t)=t(1-t), a(t)=b(t)^2:

```text
psi = 10 a(x)a(y)a(z)
u = (d_y psi,-d_x psi,0)
q = 1.92 b(x)b(y)b(z)(1+.5x+.3y)
p = .001 b(x)b(y)b(z),    rho=1, nu=.01.
```

The closure is positive inside, zero at all walls, and not constant along the
streamlines. Exact polynomial derivatives through third order give velocity,
gradient, Laplacian and curl. The inherited independently continuous SA oracle
supplies f_q; the derivative above supplies continuous f_m. Cell samples are
integrated by the existing mean-force quadrature. No source is constructed by
applying a discrete solver matrix.

On Python 3.14.2, NumPy 2.4.2, SciPy 1.17.0:

| n | Relative velocity L2 | Relative q L2 | Outer steps | Joint residual |
| --- | ---: | ---: | ---: | ---: |
| 4 | .1370932864 | .02295776266 | 3 | 9.546e-10 |
| 8 | .06073531606 | .007784501114 | 3 | 5.044e-10 |
| 12 | .02952410234 | .004024023521 | 3 | 4.244e-10 |

Velocity uses physical MAC dual-volume quadrature; cell q uses relative L2 on
these uniform grids. Velocity orders are 1.17455 and 1.77899; q orders are
1.56031 and 1.62740. Thus the predeclared finest .05/.1 and all .7 order gates
pass. The coarse 13.7% velocity error is retained, not described as accurate
engineering prediction.

Maximum nu_t/nu is .51485/.70719/.73436; the molecular Reynolds bounds are
1.09688/1.26767/1.29055. Final SA residuals are about 1e-15 and momentum
residuals determine the joint values. Energy defects are <=1.735e-11 in these
runs. At n=4 the coupled velocity differs from the same-forcing, purely
molecular-viscosity solve by .06239796 relative norm, exceeding the predeclared
.01 material-feedback detector.

The molecular-Re bypass negative control uses constant initial q=.1 and a
200-fold mean source. The standalone effective-viscosity mean solve converges
with its effective Reynolds bound 3.18681, while the original molecular bound
is 26.65531; the new coupled route correctly rejects it without fields.
An initial negative-control trial used factor 150 and produced molecular
19.99576, which was not actually over the gate and therefore could not test
rejection. Only that test input was corrected to cross the unchanged limit;
the accuracy and residual gates were not changed.

Eight focused tests passed in 9.000 s. The repository architecture check also
passed, including importer, IPC, numeric, module-size, language-budget,
legacy-UI and documentation boundaries. The focused tests include:

- fixed three-grid coupled refinement and nonzero eddy viscosity;
- material velocity feedback and stale-first-step momentum defect;
- exact zero-closure reduction to the molecular mean solver;
- alternate seed .2 versus 2, with .5 outer relaxation and actual relaxed-state
  residual checks;
- time-scale transformations 1e-8 and 1e8 without a residual floor;
- true molecular-Re bypass rejection;
- exhausted outer, mean and SA iterations; negative/NaN q, zero molecular nu,
  unknown keys, forged huge grid shape, early/late cancellation, and exhausted
  field payload budget, all without accepted fields;
- a deliberately false inner-SA success result whose nonzero fresh residual
  prevents joint acceptance.

A ninth regression was subsequently executed individually after the replay
boundary repair. Native and JSON-round-tripped requests produced bit-identical
velocity, pressure, q and nu_t, and the input JSON remained unchanged. Forged
serialized volumes, centers, widths, face areas and parent indices each failed
validation without fields. Python compilation also passed. Earlier source-bound
receipts remain historical; the integrating task reruns the complete current
source suite and benchmarks into new receipt directories.

Independent read-only numerical review additionally checked the damping
derivative against complex-step differentiation through q=1e5 (maximum
absolute discrepancy 2.22e-16), and the continuous manufactured force against
separately authored polynomial derivatives at four asymmetric interior points
(maximum discrepancy 2.13e-18). Density covariance at rho=.037 and 7.3
preserved u, q and p/rho to about 1.1e-17; time similarity at 1e-30 and 1e30
preserved scaled velocity to about 1.13e-17, while 1e-100 failed closed on
underflow without fields. Forged scalar, wrong-shape, NaN and negative inner q
outputs were rejected without fields. These extra review probes supplement,
but do not substitute for, the checked-in tests or required human release review.

Reproduce with:

```text
python -m unittest tests.python.test_enclosure_rans_research -v
```

This increment establishes only the listed coupled equations in this bounded
closed box. General turbulent regimes, external flow, inlet/outlet turbulence,
complex obstacles, boundary-layer resolution, turbulent heat transport,
rotating blades, measured validation and knowledgeable human release review
remain open.
