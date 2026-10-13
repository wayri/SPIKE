<!-- SPDX-License-Identifier: Apache-2.0 -->
# Internal laminar channel airflow and temperature

`python/spike_core/internal_airflow.py` implements an original, bounded,
experimental parallel-plate channel model. It computes fully developed laminar
velocity analytically and solves the air-temperature field with transverse
finite volumes and axial upwind marching. It runs inside SPIKE's Python worker
without an OpenFOAM executable.

This is a two-dimensional screening model with prescribed uniform wall heat
fluxes. It does not solve arbitrary board/enclosure geometry, solid/fluid CHT,
buoyancy, recirculation, inlet momentum development or turbulence. A schematic
channel view must retain these limits; it is not an assembly airflow overlay.
No turbulent kinetic energy, eddy viscosity or turbulence intensity is generated.

## Desktop and headless workflow

Open Thermal setup and find **Internal channel airflow** below the board thermal
section. Enter geometry, reviewed fluid properties, speed, inlet temperature,
both signed wall heat fluxes and the mesh sizes. Run the channel screen, then
switch between temperature and velocity arrows. Inspect mass/energy residuals
and repeat with finer meshes. Edits mark previous results stale until a new
solve succeeds. Worker failures retain the prior result with its stale label;
correct the setup and retry. Unsupported Reynolds/Peclet ranges are rejected.

Successful inputs/results are retained with the thermal scenario in the project
snapshot; the same strict field admission is applied when the panel opens.
The result includes its authored request snapshot; geometry, fluid properties,
operating conditions and mesh must all match before it is shown as that setup.
This presentation check does not establish independently verified physics.
The channel has no inferred placement or heat coupling to a loaded board.

The worker method is `run_internal_airflow` with `params: {request: ...}`;
the MCP tool is `spike_run_internal_airflow`. An original runnable example is
[run_internal_airflow.py](../examples/assembly_field/run_internal_airflow.py).
Run it from the repository root with the project Python environment.

## Request and returned fields

Call `run_internal_airflow(request, cancel_check=optional_callable)`. The strict
[request schema](../schemas/internal-channel-airflow-request-v1.schema.json)
describes structure; runtime admission additionally enforces physical and
combined resource limits. All fields
use SI units. The request below is an original reproducible fixture, with
assumed properties rather than a certified air-property table:

```json
{
  "contract": "spike/internal-channel-airflow-request/v1",
  "geometry": {"length_m": 0.3, "gap_m": 0.01, "span_m": 0.1},
  "fluid": {
    "density_kg_m3": 1.0,
    "specific_heat_j_kgk": 1000.0,
    "thermal_conductivity_w_mk": 0.03,
    "dynamic_viscosity_pa_s": 0.00002
  },
  "operating": {
    "mean_velocity_m_s": 0.1,
    "inlet_temperature_k": 300.0,
    "lower_wall_heat_flux_w_m2": 10.0,
    "upper_wall_heat_flux_w_m2": 10.0
  },
  "mesh": {"axial_cells": 40, "transverse_cells": 16}
}
```

Dimensions, properties, velocity and inlet Kelvin are positive finite numbers.
Wall flux is positive into the fluid; negative values prescribe cooling. Every
object has exact admitted keys. Booleans are not numerical inputs. The span
scales heat and mass flow as an ideal extrusion; there are no sidewalls or
finite-width velocity corrections. Users must review whether this idealization
represents their channel. This is prescribed velocity, not a fan P-Q solution.

The result contract is `spike/internal-channel-airflow-result/v1`:

| Field | Meaning |
| --- | --- |
| `x_m[nx]` | Downstream marching stations `(i+1)*dx`, ending at channel length. These are not axial cell centers. |
| `y_m[ny]` | Transverse cell centers between the two walls. |
| `velocity_u_m_s[ny]` | Exact transverse cell averages of fully developed axial velocity. The transverse velocity is zero by the model. |
| `temperature_k[nx][ny]` | Solved fluid temperature, indexed axial station then transverse cell. |
| `bulk_temperature_k[nx]` | Mass-flow/heat-capacity-weighted temperature at each station. |
| `wall_temperature_k.lower/upper[nx]` | Half-cell linear wall reconstruction from solved fluid temperature and prescribed wall heat flux. |
| `mass_flow_kg_s`, `pressure_drop_pa` | Analytical momentum/mass-flow observations for the admitted channel. |
| `reynolds_hydraulic`, `peclet_length` | `rho*U*(2H)/mu` and `rho*cp*U*L/k`. |
| `heat_balance` | Wall input, coolant enthalpy gain, signed/relative defect and numerical acceptance tolerance, in W where applicable. |
| `diagnostics` | Maximum cell equation residual in W, mass-flow defect in kg/s, maximum rise/absolute change over fluid and reconstructed walls in K, omitted viscous-heating rise in K, scheme and refinement status. |

The inlet is uniform at `x=0` with the returned `inlet_temperature_k`; there is
no solved inlet row. No interpolated or fabricated field is returned. Results
retain input/result digests, resource use and model limits. `status` and
`model_status` remain `experimental`, `production_qualified=false`,
`flow_regime=laminar_prescribed`, `turbulence_model=none`, and
`mesh_convergence_verified=false` for every individual run.

## Independent formulation

Let `H` be plate gap, `L` channel length, `S` the ideal extrusion span, `U`
mean axial speed and `eta=y/H`. Constant-viscosity, fully developed plane
momentum reduces to `mu*u_yy=dp/dx`. Integrating twice with no-slip at both
walls and imposing the cross-section mean gives

`u = 6 U eta (1-eta)`,
`Delta_p = 12 mu U L/H^2`, and
`mass_flow = rho U H S`.

The exact velocity average in transverse cell `j` is
`u_j = 6 U [eta_j(1-eta_j) - 1/(12 ny^2)]`.
The subtraction is the cell's second central moment. Consequently summing
`rho*u_j*dy*S` recovers the known mass flow without a posteriori normalization.
The continuum momentum assumptions are consistent with
[MIT's plane-flow reference](https://ocw.mit.edu/courses/2-25-advanced-fluid-mechanics-fall-2013/1a114d602956fa0dd328155f9b45f93d_MIT2_25F13_Couet_and_Pois.pdf).
No source code or external example was used.

The admitted fluid-energy equation is

`rho cp u T_x = k T_yy`,

with uniform inlet `T_in`, `-k*T_y(0)=q_lower` and `k*T_y(H)=q_upper`.
It neglects axial diffusion, viscous heating, radiation and pressure-work
heating, and does not include solid temperatures. Properties are constant.
The reported `Delta_p/(rho cp)` gives a scale for the omitted conversion of
pressure work to sensible heating; it is not added to the computed field.

Define `m_j = rho cp u_j dy S` in W/K and `d = k dx S/dy` in W/K. At axial
station `i`, the transverse cell equation is

`m_j*(theta_i,j-theta_i-1,j) + d*sum_neighbors(theta_i,j-theta_i,neighbor) = s_j`,

where `theta=T-T_in` and `s_0=q_lower dx S`, `s_last=q_upper dx S`; other
source entries are zero. This is backward/upwind first-order marching in `x`
with centered transverse diffusion. The tridiagonal matrix has positive
capacity-flow diagonal contributions, nonpositive off-diagonals and strict
diagonal dominance. An original elimination/back-substitution solves it.
Computing temperature rise avoids subtracting large absolute Kelvin fields in
the linear algebra and energy audit.

Summing all transverse equations cancels every interior diffusive exchange.
Summing axial stations gives

`sum_j m_j*theta_out,j = (q_lower+q_upper)*L*S`.

The implementation independently evaluates this identity and the local cell
residual. Opposed equal heating/cooling is normalized by the sum of absolute
wall powers, so a zero net source does not conceal exchange. For zero heat
input the exact computed field is uniform. A small residual or balance proves
discrete consistency, not continuum accuracy.

## Numerical evidence

Run `python -m unittest tests.python.test_internal_airflow -v`.
The five original tests passed on 2026-10-09. The architecture check also passed.

The pressure/velocity/mass test independently evaluates integrated momentum and
the linear bulk-temperature rise at every station. With the fixture above,
the computed energy defect was `-3.11e-15 W` for `0.6 W` wall input and maximum
cell residual was `1.05e-16 W`. These figures are execution evidence for this
fixture, not imposed universal error estimates.

For axial accuracy, the test independently constructs the continuous-in-x
transverse finite-volume generator and uses a dense augmented matrix exponential
from SciPy as the oracle. No production matrix, elimination or marcher is reused.
At `L=0.015 m`, seven transverse cells and the same physical properties:

| Axial intervals | Outlet temperature-vector L2 error (K) |
| ---: | ---: |
| 20 | 0.00945416 |
| 40 | 0.00475138 |
| 80 | 0.00238193 |

Each error ratio must lie between 1.8 and 2.2. This isolates first-order axial
discretization error from the transverse discretization.

For transverse accuracy, independently integrating the thermally developed
equal-flux equation gives

`T-T_bulk = (q H/k)*(2 eta^3-eta^4-eta+17/70)`.

The constant follows by setting its velocity-weighted mean to zero. The wall
excess is `(17/70)*q H/k`, giving `Nu_Dh=140/17` in this ideal fully developed
limit. With uniform inlet, the sufficiently long test channel approaches this
profile. The test uses `L=1 m`, 100 axial intervals, `q=10 W/m2` on each wall:

| Transverse cells | Outlet RMS profile error (K) | Lower-wall error (K) |
| ---: | ---: | ---: |
| 8 | 0.00474970 | 0.0000566755 |
| 16 | 0.00118841 | 0.00000342869 |
| 32 | 0.000297146 | 0.000000212521 |

RMS error ratios must lie between 3.5 and 4.5; the finest RMS error must be
below 0.003 K. Wall error must decrease and be below 0.005 K. These checks
support second-order transverse behavior for this smooth limiting case. They
do not establish the order near an arbitrary inlet or a general wall law.

Other tests cover an exactly adiabatic field, opposed heating/cooling, stable
input identity, result digest, malformed/unsupported fields, resource limits,
Re/Pe restrictions, numerical range, negative computed Kelvin and cancellation.

## Admission, resources and physical limits

The bounded reference admits `0 < Re_Dh <= 1000` and `Pe_length >= 10`.
These are conservative screening choices, not universal transition or
axial-diffusion thresholds. Low Reynolds number alone does not prove that
buoyancy is negligible, and a length Peclet number does not prove that entrance
or near-wall axial diffusion is negligible. The caller must review those
assumptions, air-property variation over the full computed fluid/wall temperature
range, span effects and the upstream velocity
development before using a result. High temperature rise must not be treated
as validated constant-property air behavior merely because Kelvin is positive.

The solver requires 2..1000 axial intervals, 3..200 transverse cells and at most
100,000 temperature samples. Coefficients, pivots and outputs must be finite;
capacity-flow terms too small relative to the diagonal fail the conditioning
gate. Temperatures at fluid cells and reconstructed walls must remain positive.
Energy/residual tolerances combine a physical power scale with a retained
floating-point arithmetic allowance. Request and result obey the existing
8 MiB serialized bound. The marching solve stores `O(nx*ny)` temperatures and
uses `O(ny)` temporary vectors; cancellation is checked before admission, at
each axial station and before result publication. No partial result is returned
as success. Worker process supervision retains responsibility for hard runtime
and operating-system memory limits.

This implementation is independently authored from the momentum and energy
equations and conservation identities above. It imports no external solver
implementation, examples, mesh or dataset. The independent SciPy exponential
is a numerical oracle for a derived reduced equation, not an established CFD
solver comparison. No OpenFOAM/other CFD comparison or measured channel test
has been completed for this new internal implementation. Such comparisons,
temperature-dependent properties and validated general CHT remain separate
work in [the thermal research roadmap](THERMAL_RESEARCH_ROADMAP.md).
