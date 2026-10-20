<!-- SPDX-License-Identifier: Apache-2.0 -->
# Prescribed-variable-viscosity symmetric stress - 20 October 2026

## Bounded status and sources

`python/spike_core/enclosure_symmetric_stress.py` executes an experimental
steady incompressible velocity/pressure solve in a full closed rectilinear
box with a supplied positive cell viscosity field. It includes the complete
Newtonian symmetric stress, not three independent scalar diffusion operators.
It is **not RANS**: there is no transported turbulent state, production or
destruction closure, wall-distance model, transition prediction or turbulent
heat-transport law. A supplied field is not a solved turbulence closure.
Obstacles, moving walls, physical discontinuous-viscosity interface accuracy
and measured validation remain unsupported. Existing Reynolds admission and
knowledgeable human numerical release review remain required.

Sources actually reviewed on 20 October 2026:

- A. E. P. Veldman, *Computational Fluid Dynamics*, University of Groningen
  lecture notes, academic-year 2012-2013 cover and January 2014 preface,
  [author-hosted PDF](https://www.math.rug.nl/~veldman/Colleges/CFD/CFDdictaat1314.pdf).
  Section 2.1, printed pp. 51-52, stress/conservation equations (2.2)-(2.4);
  section 2.2, pp. 54-55, MAC placement, pressure kernel and tangential
  no-slip mirror relation; section 1.5.3-1.5.4, pp. 16-18, volume weighting,
  symmetry and energy identities. These are foundations, not a supplied
  variable-viscosity algorithm.
- NASA/TMBWG, [Implementing Turbulence Models into the Compressible RANS
  Equations](https://tmbwg.github.io/turbmodels/implementrans.html):
  displayed momentum and molecular-stress equations, strain definition and
  distinction between molecular and modeled Reynolds stress were reviewed.
  Only the constant-density divergence-free molecular-stress reduction is
  used here. Compressibility, gas laws and closure stresses are not implemented.

The discrete factorization, quadrature, code and test controls below were
independently authored. No external solver source, implementation tests,
meshes or measurements were inspected or copied. The existing SPIKE analytic
curl-field construction is extended through continuous analytic derivatives;
the forcing is not obtained by applying the assembled discrete operator.

## Governing equations and independent energy derivation

Use SI position [m], velocity [m/s], pressure [Pa], dynamic viscosity [Pa s],
density [kg/m^3] and force density [N/m^3]. With prescribed scalar `mu(x)>0`
and constant `rho>0`, solve

```text
rho (u dot grad)u - div(2 mu S) + grad(p) = f
div(u) = 0,       S = (grad(u)+transpose(grad(u)))/2
u = 0 on all six walls.
```

The pressure is molecular mechanical pressure, not an isotropic Reynolds-
stress-adjusted quantity. No `k` field exists.

Componentwise product differentiation and `div(u)=0` give

```text
[div(2 mu S)]_i = mu laplacian(u_i)
                   + sum_j (d_j(u_i)+d_i(u_j)) d_j(mu).
```

Replacing `mu` in an old constant-coefficient Laplacian misses all viscosity
gradients. Even `div(mu grad(u_i))` misses
`sum_j d_i(u_j) d_j(mu)`. The latter can be hidden in pressure for affine
viscosity, but not generally for nonlinear viscosity.

Multiplication by `u`, integration by parts, and stationary no-slip walls give

```text
-integral u dot div(2 mu S) dV
    = integral 2 mu S:S dV
    = integral mu [2 sum_i (d_i u_i)^2
                   + sum_(i<j) (d_j u_i+d_i u_j)^2] dV >= 0.
```

Boundary work is zero, not discarded for a moving boundary. The discrete
construction starts from this quadratic form to preserve cross-component
terms and the correct energy pairing.

## Independently derived MAC strain quadrature

Reuse the existing validated full-box face ordering, integrated divergence
`B`, cell volumes `V_c`, dual face volumes `M_i`, and force integrals `F_i`
from the rectilinear momentum topology. Normal wall values are constrained
zero and are not unknowns. Keep the same integrated pressure gradient `-B^T p`.
Only the viscous stiffness is replaced.

For each cell c and direction a, one normal-strain row evaluates

```text
e_(c,a) = (u_a at upper face - u_a at lower face)/h_(c,a)
w_(c,a) = 2 mu_c V_c.
```

For each pair a<b, place an edge row at the corresponding a/b primal cuts and
the remaining direction's cell center. Let `d_a` be half the sum of adjacent
a widths, and similarly `d_b`. At an outer cut only one adjacent half width
exists. The row is

```text
e_edge = (upper-b u_a - lower-b u_a)/d_b
            + (upper-a u_b - lower-a u_b)/d_a.
```

Missing wall-normal face values are zero. Missing tangential values at an
outer wall use the wall-to-center half width. This is equivalent to odd
no-slip mirror values, without introducing ghost unknowns.

The edge dual volume contains one quarter of each adjacent cell in the a/b
plane, times that cell's full remaining-direction width. Its weight is the
sum over valid adjacent cells:

```text
w_edge = sum_adjacent mu_c * h_(c,a)*h_(c,b)*h_(c,k)/4.
```

Thus viscosity is integrated by positive quarter-cell quadrature. For constant
viscosity this is `mu*d_a*d_b*h_k`; on a wall it automatically uses a half
dual extent, not a full interior extent. This positive arithmetic quadrature
is an approximation for spatially varying sampled viscosity. It is not an
interface-exact rule for discontinuous viscosity.

Collect all normal and shear rows in E and positive weights in W:

```text
K = transpose(E) diag(W) E
u^T K u = sum_l W_l (E_l u)^2.
```

E has units 1/m, W has units Pa s m^3, K has units kg/s, and the quadratic
form has units W. The momentum pointwise operator is `M^-1 K`; its energy
inner product uses M. Euclidean symmetry is asserted for integrated K,
not for the unweighted pointwise operator.

The normal rows alone remove a velocity kernel on this full-box topology:
zero normal strain makes each velocity component constant along its own
coordinate line, and its constrained zero endpoints make that constant zero.
All weights are positive. Therefore K is positive definite, while pressure
retains its single constant gauge. This proof does not authorize obstacle,
periodic, slip or moving-wall topology.

For constant mu, cancellation of mixed differences gives the exact tensor-grid
identity, including exterior wall terms:

```text
K_stress = K_existing_scalar_laplacian + B^T diag(mu/V_c) B.
```

At an edge, its constant weight divided by `d_a*d_b` is `mu*h_k`; the same
factor results from the corresponding two face areas divided by cell volume
in the mixed divergence product. The additional same-component term is the
extra copy of each normal derivative. Consequently both formulations give
the same incompressible velocity/pressure solution when `B u=0`, even though
the stress matrix has genuine off-component entries. The constant-mu
equivalence is an invariant check, not evidence for variable-mu accuracy.

## Solve, admission and API

The helper `_stress_operator(grid, system, viscosity, cancel_check=None)`
returns `(K,E,W,normal_row_count)` for an already admitted full-box topology.
It is not an untrusted-input API. The separately named callable is
`solve_enclosure_symmetric_stress(request, cancel_check=None)`.
Its strict request has the same fields as the rectilinear momentum request,
except the contract is `spike/enclosure-symmetric-stress/v1` and
`dynamic_viscosity_pa_s` is a finite positive real array on the **actual**
fine cells. `fluid_mask` must be true everywhere and each dimension must have
at least two cells. Boolean viscosity and extra request fields are rejected.

The implementation builds the inherited B/F/M topology, replaces K, and
executes the existing damped Oseen saddle solve. It does not merely attach a
stress diagnostic to an old constant-viscosity solution. Coupled residuals use
the actual updated velocity and variable-mu K. Admission remains

```text
rho*sqrt(3)*max(abs(face_u))*max(box_extent)/min(prescribed_mu) <= 20.
```

This is not a transition criterion. If a future coupled closure supplies
`mu+mu_t`, that outer route must additionally check Reynolds admission against
the original molecular mu; effective viscosity must not weaken the gate.

Inherited limits include 4096 cells, max/min cell width <=64, <=100 iterations,
and scaled condition-estimate rejection above 1e10. The inverse norm estimate
is not a certified upper condition bound. Zero-force branches have no
dimensioned residual floor. Overflow, invalid values, division errors and
underflow fail closed; componentwise power multiplication avoids silently
underflowing BLAS dot products. Some representable-total-power cases can still
be conservatively rejected because an intermediate product is unrepresentable.

Before publication compare both `u^T K u` and independent strain quadrature
with force work, pressure work and convection work. Relative energy/strain
defects must be <=max(10*nonlinear_tolerance,1e-9), using the inherited
force/work norm scale without a dimensional floor. Diagnostics include actual
residuals, strain row counts, viscosity extrema and source meaning. Results
always remain experimental with `production_qualified:false`; rejected or
cancelled results contain no accepted fields.

Assembly and nonlinear steps poll cancellation. Sparse LU and norm estimation
are not internally cancellable or hard memory-capped; production orchestration
still needs a process watchdog. No new worker/public CHT route is registered.

## Continuum oracles, fixed gates and observed limits

On the one-metre cube use
`u=curl((.3,.5,1)*product(sin(pi*x_a)^2))`,
`p=.2*product(sin(pi*x_a))`, rho=1, and either constant mu=1,
affine `mu=1+.3x+.2y+.1z`, or quadratic `mu=1+x^2+y^2+z^2`.
Continuous derivatives through third order supply convection, Laplacian,
full symmetric viscosity-gradient force and pressure gradient. Normal-face
velocity error uses physical dual-volume quadrature. Pressure error removes
only the volume-weighted constant gauge.

Uniform constant/affine gates were fixed before observing results:
4/8/12 grids must each have order >1.8 and finest relative velocity error <.02.
The nonuniform affine case uses the existing nested tensor cuts over
[.25,.5] on all axes, giving 5/10/15 cells per axis; its fixed gate is order
>.8 and finest error <.08 because abrupt spacing transitions are not assigned
a universal second-order local consistency claim.

| Viscosity/grid | n=4 error | n=8 error | n=12 error | Orders |
| --- | ---: | ---: | ---: | --- |
| Constant/uniform | .0881727461 | .0250159691 | .0114329915 | 1.81748, 1.93114 |
| Affine/uniform | .0872864436 | .0248720843 | .0113843756 | 1.81123, 1.92743 |
| Affine/nonuniform | .0925775278 | .0271899940 | .0126051326 | 1.76759, 1.89596 |
| Quadratic/uniform coarse probe | .0871972822 | .0255978175 | .0117851226 | **1.76826 (failed >1.8)**, 1.91304 |

The quadratic 4/8/12 probe **failed** its original order gate. The first
interval is not qualified. This failure is retained, not relabeled a passed
sequence or used to tune the operator. An explicitly authorized additional
8/12/16 resolution study retained the same >1.8 and .02 thresholds and passed:
errors were .0255978175, .0117851226, .00671873252, with orders 1.91304
and 1.95333. The n=16 pressure RMS error was .128520409 Pa, Reynolds bound
5.78487 and seven nonlinear iterations. This supports only the tested n>=8
asymptotic range; it does not retrospectively qualify the coarse n=4 run.

### Negative control: scalar component diffusion

A deliberately wrong test-only substitute removes the cross-component shear
products and halves doubled normal-strain weights, giving three independent
`div(mu grad(u_i))` operators. It still has positive energy and can converge
algebraically; neither property establishes the right physics.

For affine mu, the omitted term is `grad(u dot grad(mu))`, which pressure can
absorb. A velocity-only negative control would therefore be unsound.
For quadratic mu, the omitted term is
`grad(u dot grad(mu))-2u`; its nonzero solenoidal part changes velocity too.
The n=12 quadratic control executes both pressure/velocity solves:

- Correct-stress relative velocity error: .0117851226.
- Scalar-substitute relative velocity error: .0237669686, failing the same .02
  velocity budget.
- Correct versus scalar velocity difference: .0165766026 relative norm.
- Correct pressure RMS error: .218453277 Pa; scalar error: .769944657 Pa.

The detector gates (>1e-3 changed velocity and >.05 Pa added pressure error)
were fixed before executing that control. The pressure is demonstrably
converging in the correct runs, but these finite errors are not a strong
pressure-accuracy qualification. Physical material laws and measured
viscosity/flow matching remain open.

Additional checks cover the exact constant-mu discrete identity on uniform
and nonuniform grids, off-component stiffness entries, positive strain energy,
absence of a velocity nullspace on a small full box, zero flow, invalid
viscosity, unsupported obstacles, nonconvergence and cancellation.

Reproduce with:

```text
python -m unittest tests.python.test_enclosure_symmetric_stress -v
```

The final focused run executed seven tests successfully in 64.378 s on the
development host. Python compilation and whitespace checks also passed.
The repository architecture check was executed but failed on the unrelated
`app/src/fieldVolumeModel.ts` spread-extrema rule; this record does not report
that broader check as passed.

These are mathematical/code verification experiments only. They do not
establish turbulence, a general variable-property material model, obstacle
stress accuracy, real enclosure performance, or release qualification.
