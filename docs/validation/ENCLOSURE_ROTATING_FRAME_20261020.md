<!-- SPDX-License-Identifier: Apache-2.0 -->
# Experimental closed co-rotating enclosure momentum

## Scope and physical assumptions

`python/spike_core/enclosure_rotating_frame.py` solves steady momentum in one
whole-domain frame rotating at a supplied **constant** angular velocity.
The enclosing walls, all voxel obstacles and all force components are fixed
in that frame. Velocity is relative to that frame and is zero at the walls.
The fluid is incompressible Newtonian, with supplied constant positive rho
and mu. This is a bounded laminar rotating-frame prerequisite, **not a fan,
propeller, blade-resolved rotor, moving-mesh, sliding-interface, MRF-zone,
rotating/stationary interface, spin-up or turbulence solver**.

The API is opt-in and in-process only. No worker/CLI/UI route, production
qualification flag or existing v1/v2 capability gate is promoted by it.
It reuses the existing obstacle-bearing rectilinear geometry, diffusion,
shared face fluxes, pressure gauges and residual controls described in
[the momentum record](ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md).

Two separate experimental dimensionless gates apply:

```
Re_relative = rho*sqrt(3)*max(abs(relative_face_u))*max(box_extent)/mu <=20
rotation_number = 2*rho*norm(Omega)*max(box_extent)^2/mu <=20.
```

The first gate is unchanged. The second is an additional conservative
admission for this new API, not a physical transition threshold. Neither
guarantees that rotation-dependent viscous layers or obstacle corners are
resolved. They do not bound the inertial rigid-body speed of a remotely
located rotation axis. Constant-density behavior, pressure-dependent
properties, cavitation, wall stress/strength and compressibility are
assumptions or exclusions, not independently validated consequences.

## Primary sources actually reviewed, 20 October 2026

1. S. Widnall and J. Peraire, MIT 16.07 Dynamics, Fall 2009, Version 2.0,
   *Lecture L8 - Relative Motion using Rotating Axes*,
   [official PDF](https://ocw.mit.edu/courses/16-07-dynamics-fall-2009/1b1825352e94d42461eb576b540b2f23_MIT16_07F09_Lec08.pdf).
   Reviewed pp. 2-6: equations (4), (5), (7), (10)-(13), including the
   velocity transform, rotating-vector derivative, acceleration terms and
   Cartesian signs. Constant Omega removes the angular-acceleration term;
   this implementation also assumes a fixed, nonaccelerating rotation origin.
2. James F. Price, Woods Hole Oceanographic Institution, *A Coriolis
   Tutorial, Part 1*, version distributed by MIT OCW Fall 2024,
   [official PDF](https://ocw.mit.edu/courses/res-12-001-topics-in-fluid-dynamics-fall-2024/mitres_12_001_f24_essay3_pt1.pdf).
   Reviewed abstract p. 2 and section 2.2.1, pp. 19-21, equations (20)-(23):
   rotating acceleration signs and velocity-orthogonality of Coriolis force.
   No planetary gravity cancellation, shallow-water approximation or
   geophysical closure from this source is implemented.

Clean-room statement: the derivation, sparse projection, validation fixtures
and prose below were independently authored. No external solver code,
numerical examples, images or datasets were inspected or copied. The
existing SPIKE analytic curl field is a continuum oracle, independent of
the discrete rotation assembly.

## Independent formulation and signs

Coordinates, Omega, force and relative velocity components are expressed
in the same rotating Cartesian axes. Let r=x-origin [m], Omega [rad/s],
u [m/s] be relative velocity and v inertial velocity expressed instantaneously
in those axes. Differentiating the rotating basis yields

```
v = u + Omega cross r
a_inertial = a_relative + 2 Omega cross u + Omega cross (Omega cross r).
```

There is no Euler acceleration because Omega is constant. Insert this
acceleration into the incompressible Newtonian momentum balance:

```
rho (u.grad)u + 2 rho Omega cross u
  + rho Omega cross (Omega cross r)
  - mu Laplacian(u) + grad(p) = f.
```

For constant Omega, the triple-product identity gives
`Omega cross (Omega cross r) = Omega*(Omega.dot(r)) - norm(Omega)^2*r`.
The negative of this vector is
`grad(norm(Omega cross r)^2/2)`. Define

```
Phi = rho*norm(Omega cross r)^2/2                 [Pa]
Pi = p - Phi                                    [Pa]
rho (u.grad)u + 2 rho Omega cross u
  - mu Laplacian(u) + grad(Pi) = f.
```

Coriolis therefore enters the **left** side with positive `2*rho*Omega cross u`.
For positive Omega_z, a positive x velocity produces a positive y
left-hand-side contribution; the apparent force on the right side has the
opposite sign. Relative u=0 and zero applied force imply constant Pi, but
physical p increases away from the rotation axis. Relative rest is rigid
co-rotation, not inertial rest.

### Weighted compatible Coriolis projection

Use the momentum record's integrated matrices K, B and dual volumes M.
E maps active MAC velocities into three components in every fluid cell.
Each component is the arithmetic mean of its own two opposite normal
faces. Constrained wall faces contribute exactly zero. This is interpolation
to the physical cell center even when adjacent cells have unequal sizes.
Let W3 repeat each physical fluid-cell volume three times, and let R be
the block-diagonal matrix representing `Omega cross (...)`.

```
R_c = [[0,-Omega_z,Omega_y],
       [Omega_z,0,-Omega_x],
       [-Omega_y,Omega_x,0]]
S = 2*rho*E^T*W3*R*E
(K+C(u)+S)*u - B^T*Pi = F,       B*u=0.
```

S has units kg/s; S*u is integrated force [N]. Since R is skew and W3
commutes with each block, `S^T=-S`. The pointwise rotation operator is
M^-1*S. Its adjoint is defined in the M-weighted inner product, so

```
u^T*M*(M^-1*S)*u = (E*u)^T*2*rho*W3*R*(E*u) = 0.
```

This is zero Coriolis work, not zero Coriolis force. The force is included
in every Oseen matrix and in every updated nonlinear residual. It is not
computed only after the ordinary stationary-frame solve.

The shared private `_iteration` function now accepts keyword-only
`linear_skew=None`. None retains the existing path exactly. A supplied
matrix must be real sparse, finite, shape-compatible and integrated-skew:
max(abs(S+S^T))/max(abs(S)) <=32*machine_epsilon. It is not silently
symmetrized. Tests independently reject non-skew, wrong-shape, nonfinite
and dense inputs. No public legacy schema or diagnostic changes.

### Physical pressure recovery without large-potential cancellation

Pi is pinned to zero at the first fluid cell of each connected component.
Physical pressure uses the same component gauge. Let g be that gauge,
delta=x_i-x_g, a_g=Omega cross (x_g-origin), a_d=Omega cross delta. Then

```
p_i = Pi_i + rho*(a_g.dot(a_d) + .5*a_d.dot(a_d)).
```

This computes Phi_i-Phi_g without subtracting two large absolute potentials.
The physical pressure at each component's gauge is exactly zero. Pressure
in solids is only zero display fill. Independent component gauges cannot
determine an absolute pressure offset between disconnected cavities.

The reported absolute maximum Phi is a diagnostic, not the pressure gauge.
Unrepresentable absolute potentials, shifts, products or recovered pressures
fail closed before publication. This intentionally rejects some requests
whose gauge differences alone might otherwise be representable.

## Solver controls, resources and unresolved accuracy

The base damped Picard solver, updated nonlinear residual, mass residual,
Re gate, scaled condition estimate and strict dimensional underflow checks
remain in force. The energy diagnostic separates applied work, viscous
dissipation, advection work, Coriolis work and reduced-pressure work.
Completion requires the full relative energy defect
<=max(10*relative_tolerance,1e-9), plus relative Coriolis power <=1e-10
against the same force/viscous work scale. A small residual does not prove
physical accuracy or nonlinear uniqueness.

The inherited bounds are 4096 total fine momentum cells, at most 64
intervals per fine axis, physical width max/min <=64, <=100 iterations,
and scaled condition estimator <=1e10. The condition estimator is not a
rigorous upper bound. Sparse LU fill is not hard memory-capped, and
cancellation is not possible inside one LU/norm-estimation call.
Process supervision remains necessary for hard time/memory bounds.
Tensor-plane refinement remains distinct from octree AMR.

The executed continuum rotation benchmark is a uniform full box. Algebraic
skew, wall-zero and equilibrium checks additionally cover nonuniform grids
with obstacles. Those invariants do not establish arbitrary obstacle
accuracy in strong rotation. Ekman-type boundary-layer thickness, mesh
convergence, independent measurements and knowledgeable human numerical
release review remain separate obligations.

## API

`solve_enclosure_rotating_frame(request, cancel_check=None)` takes exactly
the existing built-grid momentum fields plus:

```
contract: "spike/enclosure-rotating-frame/v1"
angular_velocity_rad_s: [Omega_x,Omega_y,Omega_z], finite real scalars
rotation_origin_m: [origin_x,origin_y,origin_z], finite real scalars
```

The other required fields are `grid` (direct validated builder result),
`fluid_mask`, `body_force_n_m3`, `dynamic_viscosity_pa_s`, `density_kg_m3`
and `nonlinear_controls` with the existing keys/ranges. Zero Omega is
allowed. Unknown fields, including moving-wall/rotor controls, are rejected.

The result uses `spike/enclosure-rotating-frame-result/v1`, explicitly
`production_qualified:false`, and completed/blocked/cancelled status.
Completed fields are `face_velocity_m_s` (relative/co-rotating MAC arrays),
`pressure_pa` (physical gauge p) and `reduced_pressure_pa` (gauge Pi).
Diagnostics explicitly label `velocity_reference_frame:"co_rotating_relative"`,
the rotation number, actual grid, separate power terms and conditioning.
Blocked/cancelled results contain no fields.

## Executed mathematical verification

The three-component oracle is
`u=curl((.3,.5,1)*product(sin(pi*x_a)^2))` on the unit cube, rho=mu=1.
Take `Pi=.2*product(sin(pi*x_a))`, Omega=(.4,-.7,1.1) rad/s and
origin=(.2,.3,.4) m. Independent analytic derivatives provide
`f=(u.grad)u-Laplacian(u)+grad(Pi)+2*Omega cross u`.
The velocity order >1.8 and finest relative error <.02 gates were fixed
before executing the n=4,8,12 sequence.

| n | Relative velocity L2 error | Re_relative | Rotation number | Iterations | Nonlinear residual |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | .08824582844 | 5.02164282 | 2.72763634 | 8 | 3.07077e-11 |
| 8 | .02502937422 | 5.59588182 | 2.72763634 | 8 | 7.09572e-11 |
| 12 | .01143835014 | 5.71391452 | 2.72763634 | 8 | 8.16233e-11 |

Observed orders: 1.81790586 and 1.93130884. Maximum divergence across these
runs was 3.002e-13 /s, absolute Coriolis power <=5.56e-17 W and relative
total energy defect <=4.42e-16. Largest scaled condition estimate was
13182.8. These are fixture observations, not guarantees over the envelope.

Nine tests passed in 4.112 seconds on the development host:

- Exact relative rest and scalar centrifugal pressure in two disconnected
  cavities on nonuniform cuts.
- Weighted skew/zero Coriolis work, signed positive-axis permutations and
  reversal of Omega.
- The three-component inertial-plus-Coriolis continuum refinement above.
- A nonzero change in solved velocity when rotation is removed at unchanged
  force, proving the coupling is not pressure-only postprocessing.
- Bitwise velocity and pressure equivalence to the existing solver at
  Omega=0 for the same request.
- Origin=(1e12,-2e12,0) m pressure-difference recovery, independently checked
  against a scalar expanded polynomial instead of subtracting potentials.
- Common translation of domain and rotation origin preserves relative flow
  and physical gauge pressure.
- Private matrix rejection, malformed vectors, unsupported fields,
  rotation-number excess, overflowing potential and cancellation.

Reproduce from the repository root:

```
python -m unittest tests.python.test_enclosure_rotating_frame -v
python -c "from tests.python.test_enclosure_rotating_frame import manufactured; print([(n, manufactured(n)[0]) for n in (4,8,12)])"
```

The existing v2 source-bound benchmark must be genuinely rerun after the
private momentum source change; old receipts must not have their hashes
patched. The integrating change owns those receipts and wider regression
results. This record establishes synthetic verification only, not propeller,
hardware or production qualification.
