# Blade-boundary creeping-flow prerequisite — 23 October 2026

This is a working experimental **blade-boundary resolved incompressible Stokes
snapshot**, not BEM, actuator forcing, resolved inertial propeller CFD, or release
qualification. Actual moving no-slip triangular blade boundaries drive a
conforming P2 velocity/P1 pressure tetrahedral solve. The returned torque is a
consistent physical symmetric-stress weak boundary reaction. No imposed torque
coefficient or BEM force enters this owner. The present blade example is **not
load qualified**: its traction and load refinement gaps remain large.

## Governing problem and independently checkable derivation

SI throughout: x metres, u m/s, pressure Pa, viscosity Pa s, density kg/m3,
angular speed rad/s, force N, torque N m, power W. On the instantaneous fluid
region, solve div(sigma)=0, div(u)=0 with sigma=-p I+2 mu D(u),
D(u)=(grad(u)+grad(u)^T)/2. Body force is zero. Blade velocity is
u=omega axis cross (x-origin); the closed stationary vessel has u=0.
There is no rotating coordinate transformation and thus no omitted MRF term
being silently treated as zero. This is a zero-inertia instantaneous snapshot.

Integration by parts yields a(u,v)-(p,div(v))=<sigma n,v>, with
a(u,v)=integral 2 mu D(u):D(v). For component a of node i and component b
of node j the matrix contribution is
mu integral [delta_ab grad(Ni).grad(Nj)+d_b(Ni)d_a(Nj)].
P2 vertex shapes are lambda_i(2lambda_i-1); edge shapes 4lambda_i lambda_j.
Four degree-two tetra quadrature points exactly integrate K and P1-div(P2)
on straight tetrahedra. Continuous P1 pressure has one volume-mean gauge.
The scaled indefinite matrix is factored by SciPy SuperLU; no penalty or
artificial compressibility changes the governing equations.

Let B_ij=integral q_i div(v_j). The physical assembled boundary reaction is
r=K u-B^T p (free entries vanish). Therefore
u^T r = u^T K u-p^T B u = integral 2 mu D:D-p^T B u.
This fixes the pressure-work diagnostic sign. Rotor loads are sums of these
consistent nodal forces, and torque sums their moments; rigid rotational
boundary data are represented exactly by P2, so rotor boundary work equals
omega times its weak reaction torque. Fluid reaction is the opposite blade
force. Positive returned torque resists positive rotation; axial thrust is
minus axis dot force on fluid. A separate three-point triangular quadrature
recovers sigma n from actual cell gradients and P1 pressure. It is reported
separately and is not silently substituted for an accurate load.

P2/P1 continuity is weak, not exactly cellwise conservative. A divergence-free
continuous solution does not make the discrete divergence pointwise zero.
No total-energy, temperature, wake energy, swirl, advection, Coriolis,
centrifugal or unsteady fluid equation is solved. Shaft power becomes viscous
dissipation in this closed creeping-flow model only.

The admission Reynolds upper bound uses the whole vessel bounding-box diagonal
and the maximum norm of the continuous P2 Bernstein controls: vertex values and
edge controls 2u_mid-(u_a+u_b)/2. Convexity bounds the actual polynomial speed.
Require rho U_bound L/mu <=0.1. This conservative declared scope is not proof
that any particular geometry has <10% inertia error. Negative omega is rejected;
zero returns exact zero fields and loads. Unit-response caching exploits exact
linearity of Stokes, not an empirical fitted load polynomial.

## Primary sources and implementation lineage

* NASA Glenn, [Navier–Stokes equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/navier-strokes-equation/): continuity, momentum, viscous-stress and Reynolds-number context; the inertial equations have more terms than this bounded owner.
* FEniCS Project, [DOLFINx 0.9.0 Taylor–Hood Stokes documentation](https://docs.fenicsproject.org/dolfinx/v0.9.0/python/demos/demo_stokes.html): conforming mixed P2/P1 method and pressure-gauge context. Its vector-Laplacian demonstration is NOT used as a physical surface-stress identity. The full symmetric-stress assembly above is independently authored here.
* Caltech, [Feynman Lectures II, chapter41](https://www.feynmanlectures.caltech.edu/II_41.html), rotating-cylinder viscous torque derivation, equation41.11. The independent Couette oracle below rederives its Stokes limit.

No source code was copied from these references. The pre-existing CR/P0
pseudo-traction owner is not used. Only its independently admitted tetra mesh
contract is reused. New code is repository Apache-2.0 authored implementation.
Independent reviewer analysis_media inspected symmetric K, quadrature,
pressure sign, and work/traction distinction; see its separately owned review.
Knowledgeable human numerical review remains required before release.

## Executed checks

Executed `python -m unittest tests.python.test_propulsion_pod_rotor_cfd -v`:
**6 tests passed**, 15.610s in this development environment.

* Exact affine shear u=(3y,0,0), mu=2 in unit cube: dissipation18W,
  nodal velocity and physical work agree to floating-point tolerance.
* Exact rigid rotation u=(-y,x,0): symmetric dissipation1.16e-29W,
  reaction norm <1e-12N. This detects a vector-Laplacian pseudo-stress error.
* Independent cylindrical Couette: u_theta=A r+B/r with
  A=-a^2/(b^2-a^2), B=a^2 b^2/(b^2-a^2), omega1rad/s,
  a=.01m,b=.03m,height=.02m,mu1Pa s. Pressure0 and analytical data are
  imposed on all boundaries, including caps. From
  sigma_rtheta=mu(du_theta/dr-u_theta/r)=-2mu B/r^2,
  required inner torque=4pi mu B height. Recovered symmetric traction error
  falls8.535%→3.220% with radial/azimuth refinement (288→1152tets).
  These are faceted-cylinder oracle meshes, not measured propeller evidence.
* Actual twisted-plate solve: zero speed exact; negative speed and
  omega100rad/s (Re gate) rejected; reversing supplied twist reverses thrust.
* Actual blade mesh refinement below is deliberately reported as unresolved.

## Original blade case and physical limitations

The portable geometry helper generates an original closed two-half smoothly
twisted rectangular plate (before deformation thickness2mm, radial span±30mm,
chord10mm) inside a stationary80x120x80mm vessel. Shaft is+x. The supplied
pitch parameter .2rad smoothly changes sign across its central neck. Geometry
is the exact exported mesh triangles; it is not a supplier airfoil, the larger
BEM demonstration rotor, a true cylindrical hub, or validated aerodynamic CAD.
A deterministic structured conforming mesh replaced an optional OCC Boolean
path after two native runtime access violations. No native failure was hidden
as successful CAD processing.

At mu1Pa s,rho1kg/m3,omega1rad/s:

| Tetrahedra | Torque N m | Axial force N | Re upper bound | Weak/recovered torque gap |
| --- | --- | --- | --- | --- |
| 204 | .0003105133787 | .0003136590606 | .005018685 | 86.604% |
| 1632 | .0001981826196 | .0004199665568 | .005018685 | 66.702% |

Shaft/dissipation relative residuals1.05e-15 and2.74e-16 demonstrate discrete
energy algebra, **not accurate loads**. Torque changes36.2% and thrust33.9%;
no mesh-independent load or stationary-vessel independence has been shown.
The API sets `load_qualified=false`, `production_qualified=false`, and
`load_status=mesh_and_outer_domain_convergence_required`. This capability is a
working bounded prerequisite, not completion of the user's full air-RPM
motor–propeller CFD/thermal coupling request. Real-RPM air needs a separately
verified inertial rotating/moving-domain owner, adequate mesh/traction/domain
convergence and authentic geometry/material/boundary validation.

## Callable API and reproducibility

`evaluate(spec,omega_rad_s)` in `propulsion_pod_rotor_cfd.py` returns actual P2
velocity nodes, P1 pressure, cell velocity/gradients, physical weak nodal surface
loads, separately recovered triangle tractions, torque/thrust/power, source
request digest and residuals. Required spec:

```python
from python.spike_core.propulsion_pod_rotor_cfd_geometry import build_blade_mesh
from python.spike_core.propulsion_pod_rotor_cfd import evaluate, CONTRACT
mesh, geometry_evidence = build_blade_mesh(pitch_rad=.2, refinement=1)
spec = dict(contract=CONTRACT, mesh=mesh, rotor_patches=['rotor'],
            axis_unit=[1,0,0], origin_m=[0,0,0],
            dynamic_viscosity_pa_s=1., density_kg_m3=1.)
result = evaluate(spec, 1.)
```

No UI registration, CHT link, thermal deposition, physical motor dataset or
production wrapper admission was added. Parent orchestration must preserve
the low-Re and unresolved-load states, not replace its air BEM provider
silently with this different experiment.

Exact reviewed source SHA256:

* solver: `54ff1948acd292610e47a393e6b7221555100e2e2ff79803aff075c225456652`
* original geometry: `ca650b494cf691870999b8bb1b7b3ea8f6bf8945c715df4096eaa5b6cab624b9`
* six-test oracle file: `f3ca53371ea914dd9f4254a997b0a54359be51637cf16904752a32a4f41409bb`
