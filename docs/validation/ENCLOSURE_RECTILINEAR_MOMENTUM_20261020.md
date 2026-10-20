<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental obstacle-bearing rectilinear momentum

## Bounded claim

`python/spike_core/enclosure_rectilinear_momentum.py` independently assembles
and solves steady incompressible momentum on the actual supplied fine axes.
The geometry is a stationary, closed, axis-aligned voxel mask with constant
positive Newtonian viscosity and density, not fitted CAD. Disconnected fluid
regions receive separate pressure gauges. Fine-grid forcing is supplied; no
fan, rotor, turbulence, buoyancy feedback or moving-wall law is inferred.
Refinement inserts tensor planes through the box; it is not octree AMR.
This new API changes neither the old Stokes Reynolds <=0.1 gate nor the
uniform-box laminar API's obstacle rejection and Reynolds <=20 gate.

The same experimental upper Reynolds admission of 20 is retained here:
`rho*sqrt(3)*max(abs(face_u))*max(box_extent)/mu`. This bounds the reconstructed
discrete velocity, not an unresolved continuum maximum or transition onset.
The result always declares `production_qualified:false`. No physical validation,
arbitrary obstacle accuracy guarantee or human release approval is implied.

## Reviewed primary mathematics, 20 October 2026

A. E. P. Veldman, *Computational Fluid Dynamics*, University of Groningen,
lecture notes with January 2014 preface (cover academic year 2012-2013),
[author-hosted PDF](https://www.math.rug.nl/~veldman/Colleges/CFD/CFDdictaat1314.pdf).
Reviewed text: section 1.5.3-1.5.4, printed pp. 16-18, weighted energy and
nonuniform-grid symmetry; section 2.2, pp. 54-55, staggered placement;
section 2.3, pp. 56-59, continuity, central momentum transport, pressure
adjoint and integrated volume matrix, equations 2.17-2.26; section 2.5.1,
pp. 64-65, steady saddle structure and pressure nullspace.
These provide the mathematical foundations, not a ready-made obstacle
algorithm or evidence of this implementation's accuracy.

The original Harlow/Welch 1965 paper was located through the AIP/OSTI records
and its scanned PDF opened, but the available extraction did not expose its
equations as text. No claim to equation-level review of that scan is made.
The derivation below and all code are original; no external implementation,
examples, meshes or datasets were inspected, copied or translated.
The existing SPIKE analytic curl oracle is reused as a separate continuum
reference, not generated from this solver's assembled operator.

## Independently derived discrete problem

Use SI coordinates [m], velocity [m/s], pressure [Pa], force density [N/m^3],
rho [kg/m^3], mu [Pa s]. In the fluid:

```
rho div(u tensor u) - mu Laplacian(u) + grad(p) = f
div(u) = 0
u = 0 on stationary walls.
```

The constant-property Newtonian stress divergence reduces to the Laplacian
using incompressibility. Density changes, compressibility, closure stresses
and variable-viscosity gradients are outside this formulation.

For active internal face i between fluid cells c and o in direction a, let
A_i be the physical face area and V_c,V_o the cell volumes. The velocity
unknown is its normal component. Wall-normal values are exactly zero and
excluded from the unknown vector. The dual volume is the union of the
adjacent half cells split at their centers:

```
M_i = (V_c + V_o)/2
B[c,i] = +A_i, B[o,i] = -A_i
W = diag(V_c), M = diag(M_i)
D = W^-1 B
G = -M^-1 B^T
F_i = (V_c f_c,a + V_o f_o,a)/2.
```

Thus `u^T M G p = -(D u)^T W p` exactly; using unweighted `-D^T` on this
mesh would be wrong. B maps velocity to integrated outward volume flux
[m^3/s]; F and the integrated pressure term have units N. The force quadrature
treats each cell's supplied force as constant and integrates each half.

Diffusion is assembled as positive conductances `mu*dual_area/distance`.
Each active-active link contributes `g*(u_i-u_j)` with the identical g in
the opposite row, making integrated K symmetric. Along the velocity axis,
the distance between adjacent velocity faces is the shared cell width.
For tangential neighbors the dual side has two half-cell patches. If both
neighbor fluid cells are present, each patch uses the center-to-center
distance. At a missing velocity neighbor, a solid half-patch uses the
half current tangential cell width to its zero no-slip wall. A fluid
half-patch uses the center-to-center distance to a constrained zero normal
velocity node. The two patch conductances add to the diagonal.

Consequently `u^T K u` is the sum of nonnegative internal-link
`g*(u_i-u_j)^2` and constrained-wall `g*u_i^2` contributions. This is a
staircase/mixed-corner closure, not an exact curved-surface stress calculation.
Reentrant-corner singular behavior and partial half-patches need independent
accuracy evidence; symmetry and positivity alone are insufficient.

For transport, start only from shared physical primal fluxes `Q=A*u`.
At a dual interface normal to the velocity component, q is half the sum of
the two bounding primal fluxes of its shared cell. At a transverse dual
interface, q is half the sum of the two parallel primal fluxes, one from
each adjacent half cell. Missing wall-normal primal flux is zero. Each
active-active dual interface is stored once. All boundary dual interfaces,
including those adjacent to constrained velocity nodes, are retained.
Cancellation of the shared primal face proves

```
sum_outward(q)_i = ((B u)_c + (B u)_o)/2.
```

This identity holds on nonuniform cells and arbitrary Boolean obstacle
masks; it does not require uniform cell volumes. Centered momentum flux
is `rho*q*(u_i+u_j)/2`, with a zero value at constrained neighbor nodes.
For an oriented active pair, integrated C contains `C_ij=rho*q/2`,
`C_ji=-rho*q/2`. Its diagonal is `rho*sum_outward(q)/2`. Hence

```
C + C^T = rho diag(sum_outward(q))
(K+C(u))*u - B^T*p = F,       B*u=0
u^T C(u) u = 0 and u^T*(-B^T*p) = 0 for an incompressible solution
F^T*u = u^T*K*u.             [W]
```

Energy lives in the dual-volume inner product: the pointwise operator is
`M^-1 C`, not C, and kinetic energy is `rho*u^T M u/2`. Pairwise skewness in
an unweighted pointwise operator is not used as a substitute for this fact.
Finite residuals produce small diagnosed nonzero pressure/advection work.

## Solve, conditioning, representability and resources

Each connected fluid component's first pressure unknown is pinned to zero.
Connectivity follows physical fluid-fluid faces. Isolated fluid voxels have
no velocity unknowns; they cannot resolve a within-cell pressure variation.

Damped Picard/Oseen iterations start at zero. Both velocity and pressure
are relaxed with the same omega. The saddle system is diagonally equilibrated
with velocity scale `1/sqrt(K_ii)` and pressure scale equal to the inverse
row norm of the scaled B. The final lagged Oseen matrix has a deterministic
one-vector inverse one-norm estimate obtained from sparse LU. Its reported
condition estimate is a lower-bound estimator, **not a rigorous upper
condition bound**. Values above 1e10, failed factorization, nonfinite
solutions, metric width max/min above 64 and failed residuals are rejected.
Small reported estimates cannot establish accuracy without refinement.

The nonlinear residual uses the updated velocity:
`norm(M^-1/2*((K+C)*u-B^T*p-F))/norm(M^-1/2*F)`. Norms are max-scaled before
squaring to avoid dimensional overflow/underflow. There is no dimensioned
RHS floor. The exact-zero RHS branch requires exact-zero residual.
Completion also requires `max(abs(D*u)) <= 1e-9*velocity_scale/min(width)`;
velocity scale is max(face speed, abs(F_i/K_ii)), with no dimensioned floor.
Dual flux consistency has the same relative criterion. Energy defect must
be <=max(10*relative_tolerance,1e-9), against max(abs(work),abs(dissipation),
norm(F)*norm(u)). Zero energy scale occurs only with zero products.

Floating overflow, division errors, invalid arithmetic and underflow fail
closed. Work products are explicitly multiplied before summation because
BLAS dot products do not honor NumPy's underflow error mode. This policy
can reject a case whose total power is representable when an individual
component product is not. Such a case needs properly scaled equations or
greater precision; it is not silently returned as zero-power convergence.

Independent review supplied a counterexample: a 3x3x3 all-fluid grid with
h=1e-100 m, rho=mu=1, and x force [0,1e6,2e6] by y. An earlier dimensional
norm floor admitted one omega=0.5 iterate at half the omega=1 velocity and
reported zero work. The corrected exact regression rejects both relaxations.
h=1e-60 also rejects underflowing component work; h=1e-20 completes and the
two relaxations agree within 1e-8 relative tolerance after normalizing by
1e-35 m/s. The damped solve requires more than 20 iterations.

Limits are 4096 total momentum-grid cells, builder limits of 64 intervals
per fine axis, max/min physical width <=64, <=100 iterations, and inherited
finite/bounded geometry. Sparse LU fill is not hard memory-capped; a
process watchdog remains necessary. Cancellation is checked during assembly,
between iterations and before publishing, not inside LU/norm estimation.
Blocked/cancelled results never contain fields.

## API and reproducibility

Call `solve_enclosure_rectilinear_momentum(request, cancel_check=None)`.
The strict in-process request has exactly:

```
contract: "spike/enclosure-rectilinear-momentum/v1"
grid: unmodified build_enclosure_grid(...) result
fluid_mask: Boolean[fine_nx,fine_ny,fine_nz]
body_force_n_m3: real[fine_nx,fine_ny,fine_nz,3]
dynamic_viscosity_pa_s: finite positive scalar
density_kg_m3: finite positive scalar
nonlinear_controls:
  max_iterations: integer 1..100
  relaxation: real 0.1..1
  relative_tolerance: real 1e-12..1e-7
```

Grid metrics, centers, parent indices and face areas are independently
revalidated by the shared builder validator. Inputs are not mutated. The
result has contract `spike/enclosure-rectilinear-momentum-result/v1`,
status completed/blocked/cancelled, and standard three staggered
`face_velocity_m_s` arrays plus cell `pressure_pa` only on completion.
Pressure in solids is zero display fill, not a physical solid pressure.
Diagnostics report actual momentum grid shape and
`tensor_plane_rectilinear_not_octree`; the solver never prolongs a coarse flow.

```
python -m unittest tests.python.test_enclosure_rectilinear_momentum -v
```

## Executed synthetic evidence

The reused independent analytic oracle is
`u=curl((0.3,0.5,1)*product(sin(pi*x_a)^2))`,
`p=.2*product(sin(pi*x_a))`, rho=mu=1, on a one-metre cube.
Analytic derivatives give the three-component inertial forcing. Velocity
errors use physical tangential widths and trapezoidal normal dual weights,
not an unweighted stretched-grid average.

The nonuniform sequence splits every intersected coarse interval in
[.25,.5] along all three axes by two, giving 5/10/15 cells per axis from
4/8/12. Abrupt size transitions have first-order local truncation, so the
predeclared global order gate is >0.8, finest error <.08; no universal
second-order stretched-grid claim is made. Uniform gates remain >1.8
observed order and finest error <.02.

| Sequence | Base n | Actual grid | Relative weighted velocity error | Re bound |
| --- | ---: | --- | ---: | ---: |
| Uniform | 4 | 4x4x4 | .0881727461 | 5.01749 |
| Uniform | 8 | 8x8x8 | .0250159691 | 5.59515 |
| Uniform | 12 | 12x12x12 | .0114329915 | 5.71363 |
| Nonuniform | 4 | 5x5x5 | .0947560281 | 5.43575 |
| Nonuniform | 8 | 10x10x10 | .0276281411 | 5.69539 |
| Nonuniform | 12 | 15x15x15 | .0127794778 | 5.72624 |
| Solid slab/two cavities | 4 | 9x4x4 | .0881727461 | 11.28935 |
| Solid slab/two cavities | 8 | 18x8x8 | .0250159691 | 12.58910 |
| Nonuniform solid slab | 4 | 10x5x5 | .0917469330 | 12.45066 |
| Nonuniform solid slab | 8 | 20x10x10 | .0269070396 | 12.86673 |

For the slab, x in [1,1.25] is solid and two unit cavities carry translated
analytic fields with no-slip at every wall. This tests independently known
obstacle-boundary velocities and disconnected gauges. Uniform slab gates
are order >1.8 and finest error <.03; refined slab gates >.8 and <.08.
Nonuniform orders were 1.77808 and 1.90151; refined slab order 1.76968.
All table runs converged in 8 iterations, residual <=9.27e-11, maximum
divergence <=8.83e-13 /s, energy defect <=4.31e-16. Largest reported scaled
condition estimate was 20573.1. These observations are not global bounds.

Additional tests exercise an embedded cuboid with nonzero `C(u)*u`, exact
solid/exterior face zeros, arbitrary-mask half-cell flux balance, weighted
pressure adjoint, positive diffusion, zero/conservative forcing, cancellation,
malformed/mutated-grid/underflow/nonconvergence/condition/Re/metric rejection,
and isolated fluid gauges. A refined solution differs from flux prolongation
of the coarse solve by a directly asserted nonzero amount. These are
code/solution verification, not measured physical correlation.

Executed final focused command:

```
python -m unittest tests.python.test_enclosure_rectilinear_momentum tests.python.test_enclosure_obstacle_continuum -v
```

All 13 tests passed in 27.578 seconds on the development host. The separate,
independently authored obstacle continuum test uses a polynomial
streamfunction on a reentrant L-shaped fluid domain and fixed n=8,12,16
order >=.8 / finest error <.12 gates. The disconnected slab evidence above
does not substitute for that embedded-corner test. These host timings are
observations, not performance guarantees. Repository-wide verification is
reported separately by the integrating change.

Knowledgeable human numerical review before release remains mandatory.
