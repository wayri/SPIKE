<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimental unstructured tetrahedral CR/P0 Stokes

## Bounded claim and physical distinction

`python/spike_core/cfd_tetra_stokes.py` solves a steady constant-property
creeping-flow problem on a supplied, admitted tetrahedral mesh. It uses
nonconforming affine velocity with three shared face-average degrees of
freedom per triangular face and one constant pressure per tetrahedron.
Every cell's integrated normal flux is constrained to zero. It is genuinely
tetrahedral: coordinates, face areas, gradients and adjacency come from the
supplied tetrahedra, not a voxel surrogate or Cartesian bounding-box solve.

The chosen governing operator is

```text
-mu*Delta(u) + grad(p) = f,       div(u)=0
```

with viscosity `mu` [Pa s], velocity `u` [m/s], pressure `p` [Pa], and body
force density `f` [N/m3]. Its broken weak bilinear form uses
`mu*integral grad(u):grad(v)`. Its natural boundary quantity is
`t_pseudo=(mu*grad(u)-p*I)n` [Pa]. This is NOT physical symmetric Newtonian
traction `(mu*(grad(u)+grad(u).T)-p*I)n`. Constant viscosity and exact
incompressibility relate the interior strong equations, but do not make
their boundary operators or discrete dissipation interchangeable.

An exactly fully developed channel with outlet normal along the streamwise
axis has `grad(u)n=0`, so prescribed pressure is the subset `t_pseudo=-p*n`.
A general sheared or curved outlet cannot be silently called a pressure-only
physical traction boundary.

The admission ceiling is `rho*U_bound*L/mu <= 0.1`, where `L` is the
three-dimensional bounding-box diagonal and `U_bound` is the maximum
reconstructed affine velocity norm over all tetrahedral vertices. It is not
the prior rectilinear inertial solver's Re=20 ceiling. No inertial, transient,
rotor, turbulence, thermal or CHT terms are implemented. Passing this ceiling
does not establish measured accuracy, geometry authenticity or production
qualification.

## Private API, topology, and boundary data

`solve_cfd_tetra_stokes(request, cancel_check=None)` accepts exactly:

```python
{
    "contract": "spike/cfd-tetra-stokes/v1",
    "mesh": numerical_mesh,
    "dynamic_viscosity_pa_s": mu,
    "density_kg_m3": rho,
    "body_force_n_m3": [[fx, fy, fz], ...],  # one constant vector per cell
    "boundary_conditions": {
        "named_patch": {
            "kind": "velocity_dirichlet",
            "face_average_velocity_m_s": [[ux, uy, uz], ...],
        },
        "outlet_patch": {
            "kind": "pseudo_traction",
            "face_average_pseudo_traction_pa": [[tx, ty, tz], ...],
            "reject_backflow": True,
        },
    },
    "controls": {"max_runtime_s": 30.0},
}
```

The only optional control is `max_runtime_s`, positive and at most 60 seconds;
the default is 30 seconds. Numerical residual, mass, conditioning, energy and
Reynolds limits cannot be loosened by request options.

The mesh is the exact `spike/cfd-tetra-mesh/v1` numerical contract, with
`units: "m"`, `vertices`, positively oriented `cells` and named
`boundary_patches`. The independently owned `cfd_tetra_mesh.py` admits geometry,
topology, overlap/resource constraints and patch coverage; this kernel does
not duplicate or bypass that admission. Numeric mesh input contains no CAD
provenance field. CAD lineage and run/source binding belong to the caller's
separate artifact evidence.

Every boundary patch must have exactly one condition. Boundary values follow
the original order of triangles within that patch, not a guessed global face
ordering. Dirichlet values mean exact supplied face averages, not point samples.
Pseudo-traction values are treated as piecewise constant over each face;
only their means are supplied, so higher traction moments are not represented.
At least one velocity-Dirichlet face per connected component is required to
anchor translational null modes. Pure natural-boundary components are rejected.

Outlets explicitly require `reject_backflow=True`. Each outlet's face-average
normal velocity must be at least `-1e-10*U_bound`. This checks the sign of its
physical integrated flux, not every point of the affine face trace. It is a
conservative experimental admission rule, not an inertial-outflow stability
theorem, and it cannot imply absence of local recirculation.

Completed output uses `spike/cfd-tetra-stokes-result/v1`, with explicit
experimental/operator/traction labels. Fields are global `face_vertices`,
`face_average_velocity_m_s`, `cell_velocity_m_s`, `cell_pressure_pa`, and
`cell_velocity_gradient_s_inv`. Global face ordering is defined by the emitted
triangles. A cell velocity is its affine field's volume average. Discrete
pressure is constant per cell. Failed/cancelled results contain no fields.
The kernel changes no worker, registry, public schema or UI.

## Independent local derivation

Let a tetrahedron have barycentric coordinates `lambda_i`, `i=0..3`, volume
`V`, and face `F_i` opposite vertex `i`. The four scalar basis functions are

```text
phi_i = 1-3*lambda_i,    grad(phi_i) = -3*grad(lambda_i).
```

On `F_i`, `lambda_i=0`, so `phi_i=1`. On any other triangular face, the
average of `lambda_i` is `1/3`, so the average of `phi_i` is zero. Hence one
shared vector `U_F` represents all three component averages on a shared face.
The basis functions sum to one and span the full affine space. For local
face values `U_i`,

```text
u_h(x) = sum_i phi_i(x)*U_i
mean_cell(u_h) = sum_i U_i/4
grad(u_h) = sum_i U_i outer grad(phi_i)
u_h(vertex_j) = sum_i U_i - 3*U_j .
```

Affine vector-norm convexity proves that the four vertex speeds bound the
speed everywhere in the tetrahedron; a maximum of face-average speeds alone
would not provide that bound.

Broken vector-Laplacian stiffness and cellwise-constant forcing are integrated
exactly:

```text
K_(i,a),(j,b) = mu*V*(grad(phi_i).grad(phi_j))*delta_ab
F_(i,a) = V*f_a/4 .
```

For a face with area `A_i` and outward unit normal `n_i`, the divergence
theorem and face-average basis property give

```text
B_c,(i,a) = V*partial_a(phi_i) = A_i*n_i,a
(B U)_c = sum_i A_i*(U_i.n_i)
div(u_h)|cell = (B U)_c/V .
```

Thus a P0 pressure constraint enforces not merely a global mass residual but
the exact local integrated mass equation for every cell. Adjacent cells use
the same face velocity vector and opposite normals, so their integrated
interior fluxes cancel. This is average-flux conservation; nonconforming
pointwise traces, including their normal components, can differ.

Pressure enters as `-B.T*p`. The free velocity equation is
`K U - B.T*p = F + T`, with `T_F=A_F*t_pseudo,F` on natural faces.
This natural load follows from integration by parts and the constant
traction approximation. It does not implement higher-order moments of a
varying traction against the other local basis traces.

## Boundary elimination, gauges, and power

Partition velocity into free `U_f` and prescribed `g_d`:

```text
K_ff*U_f - B_f.T*p = F_f+T_f-K_fd*g_d
-B_f*U_f = B_d*g_d .
```

This yields a symmetric indefinite saddle system without a pressure penalty,
artificial compressibility, diagonal pressure regularization, or added
stabilization.

A component with only Dirichlet boundary faces requires compatible total
prescribed normal flux. Its net flux divided by boundary area times maximum
prescribed speed must not exceed `1e-10`; the exact zero state has no
dimensioned tolerance floor. All local mass rows are retained. One extra
Lagrange multiplier per closed component enforces its volume-weighted mean
pressure to be zero. With `w_c=V_c` on the component and zero elsewhere, the
additional blocks are

```text
[ K_ff   -B_f.T    0 ]
[ -B_f       0    w ] .
[    0      w.T   0 ]
```

For compatible closed data, summing the mass rows gives
`lambda*sum(w)=0`, hence the multiplier is zero; this is a gauge constraint,
not a pressure penalty or modified continuity law. After solving, each closed
component's pressure receives a constant shift so its first cell is zero in
the returned reference convention. Every original mass row is independently
checked after the solve.
Components with natural boundary faces have pressure fixed by the natural
data and receive no arbitrary pressure gauge.

Let the full momentum defect on prescribed degrees of freedom be the
Dirichlet reaction `R_d`, with zero reaction on free degrees of freedom.
Multiplying by the full velocity gives

```text
body_work + pseudo_traction_work + dirichlet_reaction_work
    = mu*sum_cells V*|grad(u_h)|^2 - U.T*B.T*p .
```

The rightmost pressure term is separately reported; it tends to zero with
the local mass residual. Broken-gradient dissipation is calculated directly
from cell gradients, not inferred as whatever external work remains. A
reference face is subtracted when reconstructing gradients so a constant
local velocity has exactly zero reconstructed gradient without cancellation
of large equal values.

This power balance is for the declared vector-Laplacian operator. It must not
be relabeled the symmetric-strain physical dissipation.

## Scaling, solver backend, and fixed gates

Velocity congruence scaling is `S_u=diag(K_ff)^(-1/2)`.
Pressure scaling makes each row of `S_p*B_f*S_u` have Euclidean norm one.
For components with natural boundaries, the transformed symmetric saddle matrix is

```text
[ S_u*K_ff*S_u       -(S_p*B_f*S_u).T ]
[ -S_p*B_f*S_u                   0   ] .
```

For closed components the additional mean-pressure coupling column is
`S_p*w/||S_p*w||`, with its exact transpose row and zero diagonal. Normalizing
this gauge column is another congruence scale, not a penalty parameter.

Systems up to 4000 unknowns use sparse LU. Larger systems use SciPy MINRES
on this same matrix, with no altered PDE. Every approximate inverse
application used in condition estimation and the main solve has its actual
right-hand-side-relative residual recomputed. It must be at most `1e-13`,
with up to three residual-correction passes of 5000 iterations each.
MINRES's own stopping status is not substituted for this measurement.

The MINRES block preconditioner approximates the inverse of
`diag(S_u*K_ff*S_u, S_p^2*V/mu, I_gauge)`. The broken vector Laplacian has
three identical, uncoupled scalar stiffness blocks because each Dirichlet
face prescribes all three components. Its scalar block is positive definite
when each connected component is anchored. One sparse LU factor of that
scalar SPD operator is applied independently to the three right-hand-side
components; this is an LU-applied SPD-operator inverse approximation, not a
Cholesky factorization. The positive pressure-mass diagonal follows the
Schur-complement scale `B*K^-1*B.T ~ V/mu` and receives the same pressure
congruence as the actual matrix. Gauge entries use identity. This affects
iteration only: no mass row, PDE coefficient, or residual gate is changed.
Finite positive pressure entries, scalar symmetry, and positive unpivoted
factor pivots are checked. Independent tests compare the applied blocks to
dense solves and check positive quadratic forms and bilinear symmetry.
The one scalar factor counts against the same eight-million stored-nonzero
budget; it is not duplicated for each velocity component.

The one-norm condition estimate uses `onenormest` on the inverse action.
For large systems that action is an individually residual-checked approximate
MINRES solve. It is an estimate, not a rigorous certified condition bound.
An estimate above `1e10`, an unresolved inverse, or a singular/unanchored
system is rejected.

Completed results additionally require:

- Actual scaled saddle residual divided by scaled RHS norm at most `1e-10`.
- Free momentum residual at most `1e-10` relative to the maximum norm of
  its separate original terms `K_ff U_f`, `K_fd g_d`, `B_f.T p`, and external
  load. Combining `K_ff U_f+K_fd g_d` first is incorrect for this scale:
  an exactly affine harmonic flow can make that sum zero.
- Every cell flux imbalance divided by `U_bound*sum_cell_face_areas` at most
  `1e-10`, with exact-zero handling and no artificial nonzero speed floor.
- Broken-gradient power defect at most `1e-9`, relative to the maximum of
  the sum of absolute work terms, dissipation, and the velocity norm times
  total load/reaction norm.
- `Re_bound <= 0.1` and the face-average outlet backflow budget above.

NumPy overflow, underflow, invalid and division traps are enabled for
geometry/assembly/scaling/diagnostic arithmetic. Scaled norms avoid unnecessary
squaring of dimensionally tiny unscaled values. Required arithmetic that
cannot be represented is rejected, not regularized or interpreted as zero.

Admission bounds the mesh to 4096 tetrahedra before global assembly. Assembly
uses sparse local contributions: at most 48 stiffness and 12 divergence
entries per cell before duplicate reduction. No dense global matrix is
formed. Small-system LU factors are limited to eight million stored nonzeros;
the factor-size check occurs after factorization, so it is not a hard
peak-memory guarantee. Large-system MINRES uses sparse products and bounded
vector storage. Cancellation/deadline polling covers mesh admission, assembly,
inverse iterations and output checks. Sparse LU and the library calls between
polls remain cooperative rather than an operating-system hard deadline.

## Primary methods actually reviewed

Reviewed on 21 October 2026:

- M. Crouzeix and P.-A. Raviart, *Conforming and nonconforming finite element
  methods for solving the stationary Stokes equations I*, RAIRO Analyse
  Numerique 7(R3), 1973, 33-75,
  [DOI 10.1051/m2an/197307R300331](https://doi.org/10.1051/m2an/197307R300331),
  [primary Numdam article](https://www.numdam.org/item/M2AN_1973__7_3_33_0.pdf).
  Reviewed section 2, equations (2.12)-(2.22), the broken weak form; section 5,
  Example 4, equations (5.1)-(5.12), printed pages 58-61, the simplex
  face-centroid/average affine space and divergence preservation; and section
  7, equations (7.3), (7.7)-(7.12), printed pages 72-74, compatible
  inhomogeneous boundary data. The original homogeneous-boundary error
  results are not claimed as a general mixed-boundary accuracy certificate.
- C. C. Paige and M. A. Saunders, Stanford SOL,
  [MINRES: Sparse Symmetric Equations](https://web.stanford.edu/group/SOL/software/minres/),
  method description and the 2020 stopping-rule discussion; and the
  [SciPy 1.18.0 MINRES API manual](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.minres.html),
  symmetry/indefiniteness, callback, iteration limits and stopping parameters.
  The SOL page identifies Paige and Saunders, SIAM J. Numerical Analysis 12
  (1975), 617-629; that full paper is not represented here as read.

Local equations, mixed-boundary interpretation, sparse assembly, scaling,
regressions and fixtures are independently authored. No external source
implementation, mesh, example, test data or prose was copied or adapted.
SciPy is an existing separately licensed dependency called through its API.

## Verification record and retained failed attempts

Before executing the accuracy cases, the fixed sequence was declared as
`n=2,4,8` cube subdivisions, yielding 48, 384 and 3072 tetrahedra. Both
continuum fixtures must have successive relative velocity L2 orders at least
0.8 and finest velocity error below 0.05. Pressure is independently measured
and must decrease; finest relative cell-pressure error gates are 0.15 for
Poiseuille and 0.2 for the sheared quadratic MMS. These are code-verification
gates for these fixtures, not universal error estimates.

The independent Poiseuille oracle is
`u=(0.01*y*(1-y),0,0)`, `p=0.02*(1-x)`, `f=0`, `mu=rho=1` on the unit box.
The inlet and all non-outlet faces receive exact triangular velocity averages;
the streamwise outlet receives zero pseudo-traction. The z-end faces prescribe
the analytical extrusion profile, not no-slip sidewalls of a finite-width duct.
The second oracle uses an affine-sheared mesh and
`u=0.001*(y^2,z^2,x^2)`, `p=0.001*(x+2y-3z)`,
`f=0.001*(-1,0,-5)`, with exact averages on all boundary faces.
Both have zero divergence. Error integration uses an independently authored
Duffy-transformed 4-by-4-by-4 Gaussian rule, not the production stiffness
assembly. Pressure comparison removes the common volume-weighted constant
only in the all-Dirichlet case.

The initial direct-LU run passed six rejection/identity tests but both finest
meshes exceeded the unchanged eight-million factor-nonzero cap (19.005 s
suite). A symmetric MMD ordering probe was worse: the sheared finest mesh
exceeded the cooperative runtime limit and Poiseuille still exceeded the
factor cap (128.866 s suite). Neither failure was hidden by larger caps,
smaller meshes, pressure penalties or looser numerical gates. The subsequent
bounded MINRES route passed the complete Poiseuille sequence; the then-current
global mesh-overlap audit still made the sheared finest case exceed runtime.
That incomplete run had seven passing tests and one failure (80.611 s).
After optimizing the independent mesh-overlap audit, the unpreconditioned
closed finest solve reached actual inverse residual `1.58197e-13`, exceeding
the unchanged `1e-13` inverse gate. Keeping all mass rows and imposing a
volume-mean multiplier improved small-mesh condition estimates, but the
unpreconditioned finest solve still exceeded the default 30-second budget
(nine passing tests, one failure; 63.764 s suite). The SPD block
preconditioner then reduced the finest sheared solve to 956 total inverse
iterations over five applications, with 622646 scalar-factor nonzeros.
A concurrent-workload diagnostic used the already-supported 60-second
request: mesh admission took 22.953 s and the linear stage 9.266 s. It
passed all numerical gates, but that diagnostic is not a passing default
30-second regression. The final serial, single-BLAS-thread run is reported
separately below.

A real CAD cylinder supplied by the parent integration task exposed a
normalization defect in the unscaled residual diagnostic. On its nonzero
affine harmonic SI-scale field, the actual free residual norm was
`7.014110845095776e-22 N`. The former denominator combined cancelling free
and prescribed stiffness terms, yielding `8.133181702877964e-22 N` and a false
relative residual of `0.8624067556`. Keeping the original eliminated-system
terms separate gives scale `4.986742717322211e-7 N` and relative residual
`1.4065515793969465e-15`. The independently measured scaled residual was
`8.96051920059599e-16`. This repaired the normalization, not the fixed
`1e-10` gate. An added rotated, sheared 1 mm affine harmonic regression passes
the unchanged residual and energy gates and verifies exact velocity/pressure.

### Final focused verification

The frozen source SHA-256 is
`fa6762881b27ae37037d61fa71bc9db74863b3381cbb4610e5a1e03ccea08bcf`.
On Windows, Python 3.11.9, NumPy 2.2.6 and SciPy 1.17.1, all 11 tests passed
in 38.919 seconds, with every continuum request using the unchanged default
30-second deadline. No concurrent CAD numerical workload was running.
`OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1` were set in the launching
PowerShell process before Python started. These settings bound library
thread contention; they do not alter the equations or numerical gates.

The executed command used this diagnostic wrapper around the unchanged
unittest suite (it prints measured continuum errors and diagnostics):

```powershell
$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'
.venv-emerge3/Scripts/python.exe -c @'
import json,unittest
from tests.python import test_cfd_tetra_stokes as t
original=t.TetraStokesTests.completed
def logged(self,q):
 r=original(self,q)
 if self._testMethodName in ('test_affine_sheared_quadratic_manufactured_solution','test_poiseuille_three_meshes_fixed_accuracy_mass_and_energy_gates'):
  quadratic=self._testMethodName.startswith('test_affine')
  ve,pe=t.errors(q,r,quadratic=quadratic)
  print(json.dumps({'case':'sheared_quadratic' if quadratic else 'poiseuille','velocity_relative_l2':ve,'pressure_relative_l2':pe,'diagnostics':r['diagnostics']}),flush=True)
 return r
t.TetraStokesTests.completed=logged
unittest.main(module=t,verbosity=2)
'@
```

| Oracle | Tetrahedra | Relative velocity L2 | Relative pressure L2 |
| --- | ---: | ---: | ---: |
| Poiseuille | 48 | 0.243026725 | 0.437382815 |
| Poiseuille | 384 | 0.089316077 | 0.190983364 |
| Poiseuille | 3072 | 0.026646019 | 0.063221525 |
| Sheared quadratic | 48 | 0.061893361 | 0.316166819 |
| Sheared quadratic | 384 | 0.021563260 | 0.175339086 |
| Sheared quadratic | 3072 | 0.006635843 | 0.075630794 |

Successive velocity orders are `1.444123, 1.745000` for Poiseuille and
`1.521209, 1.700224` for the sheared quadratic fixture. Both exceed the
predeclared `0.8` gate and both finest errors are below `0.05`.
All pressure gates pass without changing the gauge used for comparisons.

| Finest diagnostic | Poiseuille | Sheared quadratic |
| --- | ---: | ---: |
| Scaled saddle relative residual | 1.1174e-15 | 8.2449e-16 |
| Physical momentum relative residual | 1.7304e-15 | 1.0624e-15 |
| Maximum local scaled mass residual | 1.0141e-16 | 8.2087e-17 |
| Relative broken-gradient energy defect | 1.6528e-15 | 2.2917e-16 |
| Scaled one-norm condition estimate | 1200.524 | 9120.968 |
| Reynolds upper bound | 0.00462596 | 0.00472871 |
| Total inverse iterations / applications | 1330 / 7 | 956 / 5 |
| Stored scalar-factor nonzeros | 264670 | 622646 |

The other tests cover independently reconstructed cell fluxes and gradients,
constant natural-pressure offset/sign, exact rotated/sheared SI-scale affine
flow, independent disconnected gauges, incompatible prescribed flux,
face-average backflow, malformed mesh/BC inputs, no mutation, cancellation,
runtime/condition/Re rejection without fields, and the unresolved zero-work
case below. The block-preconditioner test independently checks exact scalar
solves, positive quadratic forms and symmetric bilinear products.
`python scripts/check_architecture.py` also passed. Wider integration and
second-runtime checks belong to the parent integration record, not this
focused test receipt.

### Unresolved zero-work normalization

A nonzero uniform translation on the sheared box, with zero body force and
all boundary velocities equal to `(0.001,0,0) m/s`, has exact zero strain and
work. Small solved-velocity/reaction roundoff makes its retained relative
physical-power criterion ill-conditioned, and the request is blocked without
fields. This is an admitted unresolved numerical limitation, not a physical
prohibition on uniform flow. A regression preserves that fail-closed behavior.
Unlike the independently repaired free-equation residual normalization, no
larger energy normalization, artificial absolute floor, or zero-work waiver
was introduced here. A separately derived roundoff-limited energy contract
remains future work.
