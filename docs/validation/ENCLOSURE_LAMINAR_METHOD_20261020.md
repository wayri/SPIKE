<!-- SPDX-License-Identifier: Apache-2.0 -->
# Closed-box 3-D inertial flow: experimental method evidence

## Claim and scope

`python/spike_core/enclosure_laminar.py` adds a separate opt-in steady
incompressible constant-property Newtonian flow solve. It is not a change to
`enclosure_stokes.py`, its Reynolds <=0.1 gate, or its obstacle support.
The new domain is a complete rectangular fluid box with stationary no-slip
walls. The grid is uniform along each axis; its three spacings may differ.
There are three staggered velocity components, cell pressure, and supplied
cellwise volumetric force. The experimental Reynolds upper admission is 20,
defined below; this is a numerical scope restriction, not a universal laminar
transition threshold or a demonstration of physical steady-state stability.

No obstacles, disconnected fluid components, inlet/outlet, moving lid, fans,
rotors, turbulence, compressibility, local momentum refinement, curved CAD,
or thermal feedback are supplied by this API. A separate thermal workflow
must retain these limits when consuming the velocity. Local thermal-grid
refinement does not refine the momentum solution.

## Sources actually reviewed, 20 October 2026

1. F. H. Harlow and J. E. Welch, *Numerical Calculation of Time-Dependent
   Viscous Incompressible Flow of Fluid with Free Surface*, Physics of Fluids
   8, 2182-2189 (1965), DOI
   [10.1063/1.1761178](https://doi.org/10.1063/1.1761178).
   Reviewed the original-paper text reproduced in the
   [HTML transcription](https://content-animation.org.uk/htmls/harlow_welch.htm):
   "The Finite Difference Equations" paragraphs on placement and neighboring
   averages, and "Boundary Conditions at Rigid Walls" on zero normal velocity
   and odd tangential reflection. Formula images were not available as text;
   no claim is made to having checked those images. The source supplies MAC
   placement/wall foundations, not this implementation's steady Oseen solve,
   3-D extension, or energy proof.
2. NASA Glenn, [Navier-Stokes Equations](https://www.grc.nasa.gov/www/k-12/airplane/nseqs.html),
   updated 13 May 2021: textual continuity and three momentum equations.
   Used only for conservation-law and inertial/viscous-term foundations; the
   incompressible, constant-viscosity reduction is derived below.
3. NASA NPARC V&V, [Examining Spatial (Grid) Convergence](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html),
   updated 10 February 2021: "Order of Grid Convergence" and "Asymptotic
   Range of Convergence". Used for error-versus-spacing and observed-order
   interpretation, not as evidence of this solver's physical accuracy.

Clean-room statement: implementation, notation, tests, analytic oracle and
this prose were independently authored. No external implementation, mesh,
benchmark dataset, source code, or example was copied or translated. The
elementary pairwise skew operator below is independently derived from the
conservative flux balance; it is not an implementation of an unreviewed
high-order research scheme.

## Independent formulation and units

For constant density rho [kg/m^3], dynamic viscosity mu [Pa s], velocity
u [m/s], pressure p [Pa], and force density f [N/m^3], take

```
rho (u.grad)u - mu Laplacian(u) + grad(p) = f,
div(u) = 0,                  u|walls = 0.
```

Conservation of mass reduces to zero divergence. The Newtonian stress
divergence reduces to mu*Laplacian(u) because viscosity is constant and the
velocity is divergence-free. These assumptions exclude density/viscosity
feedback and Reynolds-averaged stresses.

For a cell of volume V=h_x*h_y*h_z, D has +1/h_a at the positive internal
a-face and -1/h_a at its neighboring cell. Boundary normal velocity is zero
and removed from the unknowns. The pressure gradient is exactly -D^T since
all admitted cell/active-dual volumes equal V. Therefore
`V*u^T*(-D^T*p) = -V*(D*u)^T*p`, so a divergence-free velocity does no pressure
work. A single pressure gauge is removed for the connected full box.

The symmetric positive viscous operator A uses nearest-neighbor second
differences. At a missing normal neighbor the prescribed face velocity is
zero. At a tangential wall the ghost is the negative interior value, adding
twice the ordinary neighbor coefficient to the diagonal. The existing Stokes
assembly is reused without modification.

Consider neighboring unknowns u_i and u_j of the same velocity component a,
separated in direction b. A dual-face transporting velocity q_ij is:

- For b=a, the arithmetic mean of those two a-velocities.
- For b!=a, the arithmetic mean of the two b-velocities on either side of
  the a-face (one in each adjacent primal cell).

The conservative centered flux for the transported component is
`rho*q_ij*(u_i+u_j)/2`. Summing outgoing fluxes over a dual control volume
and dividing by V gives an off-diagonal pair
`C_ij=rho*q_ij/(2*h_b)`, `C_ji=-C_ij`.
The diagonal term is `rho*div_dual(q)/2`. For the admitted complete box,
dual divergence is the average of the two adjacent primal divergences;
thus it vanishes for every divergence-free iterate. Terms containing
prescribed zero wall velocities vanish. C is consequently assembled directly
as pairwise skew coefficients. Arbitrary obstacle and stretched-grid dual
volumes cannot be substituted into this derivation; they are rejected.

`C+C^T=0` identically, even for an imperfect iterate, so `u^T*C*u=0`.
At a converged discrete solution

```
(A+C(u))*u - D^T*p = f_face,       D*u = 0,
V*f_face^T*u = V*u^T*A*u.
```

Cell forces are arithmetically averaged onto momentum faces. Work and
dissipation are in W. A nonzero supplied force is not automatically a fan
or a buoyancy law. The pressure gauge has no effect on physical differences.

## Nonlinear solution, conditioning, and failure controls

Start with zero velocity and pressure, solve an Oseen saddle system using
the previous divergence-free velocity in C, and relax *both* velocity and
pressure with omega in [0.1,1]. Convex combinations retain zero divergence
and the pressure gauge. The LU system is scaled by alpha=mu/min(h)^2;
pressure is represented as p/(alpha*min(h)). This improves unit scaling but
does not bound the condition number. Aspect ratio, refinement, roundoff and
small viscosity still affect conditioning. No unconditional Picard
convergence or uniqueness is claimed.

Every iteration evaluates the actual nonlinear residual using C of the
updated velocity, not just the linear Oseen residual. Completion requires
`norm(momentum_residual)/max(norm(f_face),1e-30) <= relative_tolerance` and
`max(abs(D*u)) <= 1e-9*velocity_scale/min(h)`. The velocity scale is the
maximum of face speed, max force/alpha, and 1e-30. Residual history is returned.
The final work/viscous/advection/pressure identity is checked against the
forcing-work norm scale with tolerance `max(10*relative_tolerance,1e-9)`.
Zero force returns exact zero in the executed regression.

The final discrete speed bound gives
`Re_bound=rho*sqrt(3)*max_face_abs_velocity*max(box_lengths)/mu`.
This bounds the componentwise interpolated discrete vector norm, not
unresolved continuum peaks. Re_bound >20 is rejected. The manufactured
refinement evidence below reaches approximately 5.71, not the entire
admission envelope.

Resource admission inherits at most 4096 cells, at most 64 per axis, with
at least two per axis here; at most 100 nonlinear iterations. Sparse direct
LU fill is not hard memory-capped. Cancellation is checked during operator
assembly, between iterations, and before publishing fields, not inside
SciPy factorization. Process watchdog/cancellation remains necessary for
hard runtime bounds. Invalid, unsupported, nonfinite, nonconverged and
cancelled cases never contain completed fields.

## API and reproduction

Call `solve_enclosure_laminar(request, cancel_check=None)`. Required keys:

```
contract: "spike/enclosure-laminar/v1"
shape: [nx,ny,nz]
spacing_m: [hx,hy,hz]
fluid_mask: Boolean[nx,ny,nz], all true
body_force_n_m3: real[nx,ny,nz,3]
dynamic_viscosity_pa_s: positive real
density_kg_m3: positive real
nonlinear_controls:
  max_iterations: integer 1..100
  relaxation: real 0.1..1
  relative_tolerance: real 1e-12..1e-7
```

Unknown fields are rejected. The result uses
`spike/enclosure-laminar-result/v1`, explicit `production_qualified:false`,
and `completed`, `blocked` or `cancelled`. Completed velocity arrays have
shapes `(nx+1,ny,nz)`, `(nx,ny+1,nz)` and `(nx,ny,nz+1)`; pressure has cell
shape. Normal exterior faces are exactly zero. Face index i is at i*h in
its component axis and cell centers in the other two axes. Pressure is
zero in the first cell by gauge choice.

Run the regression and analytic benchmark from the repository root:

```
python -m unittest tests.python.test_enclosure_laminar tests.python.test_enclosure_stokes -v
python -c "from tests.python.test_enclosure_laminar import manufactured; print([(n, manufactured(n)[:2]) for n in (4,8,12)])"
```

## Executed numerical evidence

The independent smooth oracle takes `F(x)=sin(pi*x)^2`,
`A=(0.3,0.5,1)*F(x)*F(y)*F(z)`, `u=curl(A)` and
`p=0.2*sin(pi*x)*sin(pi*y)*sin(pi*z)` on the one-metre cube,
rho=1 kg/m^3 and mu=1 Pa s. Its three nonzero velocity components vanish
on every wall, and continuum divergence is identically zero. Analytical
first/second/third tensor-factor derivatives yield the continuum forcing
`(u.grad)u-Laplacian(u)+grad(p)`, independently of the discrete assembly.
The tests compare all three staggered components against their analytical
values. Pressure error removes both means to ignore gauge.

| Cells per axis | Relative velocity L2 error | Pressure RMS error [Pa] | Re bound | Iterations | Nonlinear residual |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 | 0.0881727461 | 0.677323125 | 5.01748800 | 8 | 3.82448e-11 |
| 8 | 0.0250159691 | 0.266438854 | 5.59515436 | 8 | 7.66651e-11 |
| 12 | 0.0114329915 | 0.131529007 | 5.71362510 | 8 | 8.80590e-11 |

Observed velocity orders were 1.81748 and 1.93114, passing the predeclared
>1.8 checks; the final velocity error passed <0.04. Pressure error decreases,
but no second-order pressure or physically accurate pressure claim is made.
Maximum divergence was <=4.39e-13 /s. Relative energy defect was <=3.29e-16.
Single-host diagnostic runtimes were approximately 0.021/0.269/2.944 seconds,
including analytic fixture generation and comparison; these are observations,
not performance guarantees.

All eight new tests and all eight unchanged Stokes tests passed (16 total).
Additional executed controls cover zero/hydrostatic force, arbitrary-vector
skew identity on anisotropic spacing, explicit x/z cross-component transport,
damped iteration plus SI similarity, nonconvergence, Reynolds-envelope
rejection, unsupported obstacle/invalid controls/resource rejection, and
cancellation immediately before field publication.

Implementation SHA-256 at this run:
`732ac80311577a43db0391f732fca51cde4f38eb1974fb8787b74418d524c23f`.
Test/oracle SHA-256:
`a8dc515f4ce6b380196af06a1217db47b4c5ad4bb7c9a068f836970c056bc832`.

This is synthetic code/solution verification, not experimental physical
validation. There are no admitted measured enclosure/fan/rotor comparisons.
Knowledgeable human numerical review remains mandatory before release.
