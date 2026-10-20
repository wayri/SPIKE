<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tetra RT0/P0 sensible-energy foundation - 21 October 2026

Predeclared verification gates: analytical affine and layered conduction must
recover cell means and integrated face fluxes; independently continuous
nonlinear advection/conduction refinement must have both observed orders >=.8
and finest relative temperature-rise L2 error <.05. Actual scaled mixed residual
must be <=1e-10; cell and global energy defects <=1e-9; cell mass imbalance
<=1e-10 relative to throughput. No gate will be weakened after execution.

This internal research module is steady laminar/prescribed-coefficient conjugate
sensible heat transfer, not qualified turbulence, turbulent CHT, a CAD mesher
or a public worker route. Detailed derivation and actual evidence follow.

## Model, provenance and independent derivation

The independently authored implementation is
`python/spike_core/cfd_tetra_energy.py`, contract
`spike/cfd-tetra-energy/v1`. It re-admits the numerical mesh with
`cfd_tetra_mesh.admit_cfd_tetra_mesh`; it does not trust caller-supplied derived
geometry. The caller supplies explicit per-cell material IDs, positive
conductivity k [W/(m K)], phase, fluid specific heat cp [J/(kg K)], integrated
oriented face mass flow [kg/s], cell-average volumetric source [W/m3],
positive reference temperature [K], and every exterior thermal patch.
Solid cp is unused and may be nonnegative; fluid cp must be positive.

Primary mathematical sources reviewed on 21 October 2026:

- M. Vohralik, "Equivalence between mixed finite element and multi-point finite
  volume methods", C. R. Math. 339 (2004), 525-528,
  [publisher PDF, DOI 10.1016/j.crma.2004.08.004](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2004.08.004.pdf).
  Equations (1)-(3), pp. 525-526, and section 1 give the mixed formulation,
  simplex RT0 oriented face basis, and P0 pressure/scalar space in dimensions
  two and three. The paper's algebraic elimination algorithm is not used.
- NIST FiPy 4.0.3 mathematical documentation, updated 18 June 2026:
  [discretization, convection equation (2) and source equation (4)](https://pages.nist.gov/fipy/en/stable/numerical/discret.html)
  and [upwind equation (3)](https://pages.nist.gov/fipy/en/stable/numerical/scheme.html).
  These establish conservative shared-face donor transport and its first-order
  diffusion error. The orthogonality-dependent diffusion approximation on the
  discretization page is explicitly not used.

These are equation references, not imported implementation. No external code,
external numerical dataset, dependency, or production route was added.
The following moment calculation, boundary treatment, reference-temperature
accounting and independent test sources were derived for this implementation.

Let V be a tetrahedron's volume, c its centroid, v_i the vertex opposite face
i, and s_i the sign from the globally stored face normal (outward from first
owner) to that cell's outward normal. The integrated-flux basis is

    psi_i(x) = s_i (x-v_i)/(3V),   integral_face_j psi_i.n_cell = s_i delta_ij.

Thus D_ci=s_i is the integrated divergence. With constant cell k,
M_ij=integral_cell psi_i.psi_j/k. Barycentric moments are
E[lambda_i lambda_j]=(1+delta_ij)/20; therefore

    E[(x-c)(x-c)^T] = sum_a (v_a-c)(v_a-c)^T / 20,
    M_ij = s_i s_j [(c-v_i).(c-v_j) + tr(covariance)]/(9 V k).

The code evaluates offsets relative to the first vertex to avoid unnecessary
large-coordinate subtraction. Every local M must remain finite positive
definite. No normal-distance TPFA or arithmetic/harmonic conductivity averaging
is introduced at oblique faces or material interfaces.

The continuous model is q=-k grad(T),
div(q)+div(rho u cp T)=source. Unknowns are shared integrated conductive face
flows Q [W] and cell P0 temperature differences theta [K]. The original
reference formulation uses theta=T-Tref; the stabilized implementation uses
theta=T-Tlift internally and translates outputs back to requested Tref.
Tlift is the area-weighted mean of prescribed temperature/Robin ambient
data, computed from differences to the first boundary value. Testing Fourier's
law and integrating by parts gives

    M Q - D^T theta = - integral_boundary theta_D psi.n.

Because an RT0 normal trace is constant on each triangular face, temperature
boundary inputs are exact face averages when supplied analytically.
Prescribed outward heat flux [W/m2] fixes the exterior Q to area times flux
and is eliminated from the unknown system. Robin q.n=h(T-Tambient) adds
1/(h A) to the corresponding M diagonal and -(Tambient-Tref) to its RHS.
Temperature and Robin anchors are required in every connected thermal
component; all-Neumann components are conservatively rejected.

An interior face contributes F cp theta_upwind to the first owner and its
negative to the second owner; F is supplied integrated mass flow. Exterior
outflow uses its cell temperature. Inflow requires an explicit positive
`inflow_temperature_k`, or defaults to that patch's temperature Dirichlet
value. A heat-flux or Robin inflow does not silently use ambient temperature
as incoming fluid temperature.

All faces incident on solid cells require exactly zero mass flow. Adjacent
fluid cells must have exactly equal cp, ensuring constant cp within a fluid
component. Each cell must pass |sum(sF)|/sum|F|<=1e-10 (explicit zero branch).
For the accepted small nonzero mass defect dm, the cell RHS contains
source*V-Tlift*cp*dm. It is not discarded. Cell heat-balance certification also
includes Tlift*cp*dm, avoiding cancellation of large baseline enthalpy face sums
while retaining the original absolute-temperature equation. The displayed
rise is theta+(Tlift-Tref), and relative face enthalpy adds F*cp*(Tlift-Tref).
Natural temperature and Robin RHS values likewise use Tlift internally.

After essential-flux elimination the assembled system is

    [Mfree  -Dfree^T] [Qfree] = [r1]
    [-Dfree      -H] [theta]   [-r2].

H is shared-face upwind enthalpy transport. One shared Q enforces perfect
contact/conservative normal flux across conductivity jumps. P0 temperatures
are cell means, not nodal temperatures or separate interface temperatures.
No interface resistance, radiation, latent heat or temperature-dependent
coefficient iteration is present.

## Acceptance, resources and failure behavior

Flux scaling is 1/sqrt(diag(Mfree)); temperature scaling is the inverse
Euclidean row norm of Dfree times the flux scale. SciPy sparse LU solves this
scaled saddle system. Its inverse one-norm estimate and the matrix one-norm
give a reported condition estimate, required <=1e10; this estimate is not a
rigorous condition-number upper bound. The actual lifted assembled residual
is recomputed with explicitly multiplied sparse entries and the same physical
scales; normalization uses actual scaled RHS, with an explicit exact-zero
branch and no dimensional floor. Acceptance requires <=1e-10.

For each cell independently, heat defect is normalized by the maximum of its
absolute generated heat, sum of magnitudes of its conductive and relative
advective face terms expressed relative to the requested Tref, and its
Tref*cp*dm baseline mass-defect term. These original normalization scales are
unchanged by lifting. Every cell must pass
1e-9; a large-flow cell cannot mask another cell's local defect. Global
exterior heat minus generated heat must also pass 1e-9 using actual boundary/
source/baseline scales. Reported absolute advective flows add the baseline
back; reported energy defects use stable reference-temperature arithmetic.
Absolute cell temperatures must remain finite and strictly positive.

Inherited mesh admission limits are 4,096 tetrahedra and 16,384 vertices/faces.
Energy input arrays must have exact admitted lengths and finite real values.
The matrix is assembled from 16 mass entries per cell plus bounded face/cell
terms. LU factors must contain at most 4,000,000 nonzeros. This is checked
after factorization, not a guarantee on peak allocation during factorization.
The finite serialized field payload must be <=4 MiB. All fields are installed
only after every certificate, budget check and final cancellation poll passes.

A fixed 60-second cooperative deadline is checked during mesh/element work,
before and after LU, after condition estimation and before result publication.
Caller cancellation follows the same cooperative mechanism. Neither can
interrupt an in-process SciPy factorization or condition-estimation call;
there is no claim of OS-enforced hard runtime/memory isolation. Timeout,
ill-conditioning, unrepresentability, invalid inputs and failed certificates
return `blocked` without fields; cancellation returns `cancelled` without fields.
Floating overflow/underflow/invalid arithmetic is trapped where evaluated in
NumPy, including explicit sparse residual products. Public worker isolation
and public JSON admission have not been introduced.

## Independent analytical checks and executed evidence

Executed command:

    python -m unittest tests.python.test_cfd_tetra_energy -v

Initial focused run: eight tests passed in 12.847 seconds, including both
three-level refinement families and the factor/deadline guards. The
post-CAD-feedback rerun and additional regression are recorded below.

The source functions below are authored from continuum derivatives, not fitted
by applying the assembled discrete matrix:

1. Affine T=301+(2,-1,.5).x on a sheared tetrahedral box with k=2.5:
   exact cell means and integrated Q=-k grad(T).n A agree at test tolerances
   relative 1e-11/absolute 1e-12. Uniform T=Tref=300 returns exactly zero rise
   and conductive flux.
2. Three layers in x with left solid k=2, center fluid k=1, right solid k=4,
   each width 1/3, no flow, Tleft=320 and Tright=300, insulated other faces:
   resistance is (1/3)/2+1/3+(1/3)/4 and exact heat flux is
   34.2857142857 W/m2. Piecewise linear cell means and all face flows meet
   the same exactness tolerances, testing material jumps and shared contact.
3. Left temperature plus prescribed outward right heat flux, then the
   equivalent Robin condition, each reproduce the independent affine solution.
4. All-fluid nonlinear-temperature MMS: theta=x²+y²+z², k=cp=1,
   rho u=(1,.5,.25), source=-6+2 rho u.x. Tetra/triangle averages of the
   quadratic are evaluated from independent barycentric moment formulas.
5. Two-solid/fluid nonlinear-temperature MMS: theta=y²+z², same three
   conductivities/phases as the layered case, fluid rho u=(0,1,.25),
   solid mass flow zero. Source=-4k+fluid_indicator*(2y+.5z).
   The exact interface normal thermal flux is zero, while tangential
   conduction and nonzero fluid enthalpy are retained. This complements,
   rather than replaces, the nonzero-contact-flux exact layered test.

Relative L2 errors below use cell volume and temperature rise, never the
large 300 K baseline. Levels are subdivisions per unit box axis in the
all-fluid case and subdivisions per layer (3n,n,n) in the layered case.

| Family | n | Cells | Relative L2 rise error | Order | Mixed residual | Max cell heat defect |
|---|---:|---:|---:|---:|---:|---:|
| All fluid | 2 | 48 | 0.01384710 | — | 7.17e-16 | 2.25e-15 |
| All fluid | 4 | 384 | 0.00577796 | 1.261 | 1.42e-15 | 8.99e-15 |
| All fluid | 8 | 3072 | 0.00257626 | 1.165 | 3.31e-15 | 5.39e-14 |
| Two solids/fluid | 1 | 18 | 0.01793571 | — | 3.24e-16 | 1.52e-15 |
| Two solids/fluid | 2 | 144 | 0.00775664 | 1.209 | 7.65e-16 | 5.15e-15 |
| Two solids/fluid | 4 | 1152 | 0.00263128 | 1.560 | 1.73e-15 | 1.88e-14 |

Maximum global relative energy defects were 1.85e-15 (all-fluid) and
3.73e-16 (layered). Maximum fluid mass defect was 4.17e-17. Finest scaled
condition estimates were 401.10 and 224.97. All predeclared refinement and
conservation gates passed unchanged. Minor roundoff/condition-estimator
variation across executions is expected.

Additional checks shift Tref and all imposed temperatures by 1000 K, and
scale conductivity, mass flow and source together by 1e-15 and 1e15 without
changing the temperature rise. A nonzero-reference throughflow oracle uses
T=350 K, Tref=300 K, cp=1000 and k=.6 with nonzero constant mass velocity;
it requires absolute temperature error <=1e-8 K and meaningful (>1000 W)
advective face enthalpy, not a zero-flow/zero-rise shortcut.

Rejection tests cover zero/unrepresentable conductivity, NaN source, malformed
geometry, missing/unknown boundary data, solid mass flow, fluid mass imbalance,
inconsistent connected-fluid cp, missing inflow temperature, unanchored
components, payload/factor/deadline limits, early/late cancellation and no
accepted fields on failure.

### Actual CAD feedback and constant-mode stabilization

The initial eight-test implementation did not suffice for small-SI-scale
actual CAD cases. The root benchmark retained blocked energy results for
`build/cad-cfd-open-flow-final-20261021/box-0.18/` and
`build/cad-cfd-open-flow-final-20261021/sheared_duct-0.18/`.
Those request/result files remain unchanged as failed historical evidence.

The box failure was reproduced from its exact 1,198-cell request. Its mixed
residual was 1.6224e-15, but cell 788 had heat defect -2.20898e-17 W against
the legitimate local scale 1.67116e-8 W, giving 1.3218266e-9 and failing the
unchanged 1e-9 gate. The computed 50 K rise differed from its exact constant
by only 7.11e-14 K, yet cancellation in the mixed solve generated spurious
conductive face flows around 4e-18 to 7e-18 W. This was not a physical heat
load and did not justify weakening the cell conservation scale.

The internal boundary-temperature lift described above removes that constant
mode before solution. Every original normalization scale and gate remains
unchanged; accepted nonzero mass imbalance remains in the absolute-temperature
equation. The full mixed condition estimate is still computed for exact-zero
right-hand sides; there is no condition bypass or forced-success branch.

Re-execution of the two retained requests against the stabilized source gave:

| Retained request | Cells | Maximum 350 K error | Mixed residual | Max cell relative heat defect | Global relative heat defect |
|---|---:|---:|---:|---:|---:|
| Box, 0.18 mm | 1198 | 0 K | 1.1209e-15 | 2.8604e-30 | 1.1285e-31 |
| Sheared duct, 0.18 mm | 1276 | 0 K | 1.5832e-15 | 3.6928e-30 | 7.3351e-31 |

These near-zero balance defects concern a constant-state oracle, not measured
engineering accuracy or nonuniform heated-CAD verification. The tests above
still provide the independent nonuniform conduction/advection evidence.

A ninth regression independently generates 48 sheared tetrahedra at 1 mm
scale, k=.6, cp=1000, mass velocity (1e-7,0,0), imposed 350 K and requested
reference 300 K. Disabling only the internal lift reproduces the previous
energy rejection. The stabilized solve passes, preserves the requested 50 K
rise and absolute face enthalpy, and also supports zero flow without spurious
conductive heat. Perturbing one inlet flux by 1e-11 relative produces an
accepted cell mass defect of 4.99999e-12. The measured total conductive heat
4.3741627208e-20 W matches -350*cp*sum(F)=4.3741627220e-20 W with ratio
0.999999999735; using 300 K or 50 K would fail this explicit oracle.

Final focused rerun: nine tests passed in 16.193 seconds, including both
unchanged three-level refinement gates. Architecture and owned-file whitespace
checks passed. The earlier refinement table records the initial measured
values; the stabilized rerun independently rechecks all its acceptance gates.

## Scope and remaining limitations

This proves bounded equation verification on admitted tetrahedra with prescribed
coefficients and conservative supplied mass flux. It does not validate a flow
solver, fluid properties, CAD interface extraction, global tetra intersection
detection, turbulence/eddy diffusivity, turbulent CHT, compressibility,
buoyancy feedback, transient heat, radiation or production engineering.
The separate CAD bridge's current single-material limitation is not evidence
of multi-material CAD import; material masks in these tests are explicit
numerical assignments. Any flow-to-energy benchmark must certify the same
actual mesh and mass-flux orientation and remain one-way prescribed-flow
coupling, not a monolithic thermofluid solve. Knowledgeable human numerical
review remains required before release qualification.
