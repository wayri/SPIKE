<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bounded tetrahedral CFD/CHT release composition - 23 October 2026

Status: experimental one-way composition, suitable for guarded worker exposure;
not production-qualified engineering CFD or general CAD CHT. Knowledgeable
human numerical review remains required before release. No existing admission,
residual, conservation, conditioning, Reynolds, resource or cancellation gate
was changed.

Implementation and executable evidence:

- `python/spike_core/cfd_tetra_cht.py`
- `tests/python/test_cfd_tetra_cht.py`
- request contract `spike/cfd-tetra-cht/v1`
- result contract `spike/cfd-tetra-cht-result/v1`

## Exact composed boundary

The request retains one explicit `spike/cfd-tetra-mesh/v1` SI mesh and requires
an identity record with `source_id`, caller-declared `source_sha256`, and the
transport-stable canonical `mesh_sha256`. A mismatched mesh digest blocks before
execution. Results repeat those identities, add the exact request and derived
fluid-submesh digests, and explicitly report that source authenticity was not
verified. The retained mesh is re-admitted by both existing numerical kernels.

Cell material IDs and material records explicitly select `fluid` and `solid`.
The composer extracts an exact cell/vertex/facet subset for the existing
CR/P0 Stokes solver. Every retained exterior fluid patch requires explicit
flow data in retained patch order. Every fluid-solid face is placed on the
generated `__cht_stationary_solid_interface__` patch with exact zero
face-average velocity. A nonzero solid-cell body-force input is rejected rather
than silently ignored. The full retained mesh, explicit phases and all thermal
boundaries then go to the existing RT0/P0 energy solver.

The public integration surface is intentionally small:

```python
from python.spike_core.cfd_tetra_cht import (
    cfd_tetra_cht_capabilities,
    solve_cfd_tetra_cht,
)
```

`cfd_tetra_cht_capabilities()` declares inertia, turbulence, buoyancy feedback,
general CAD import and production qualification false. `solve_cfd_tetra_cht`
returns fields only after both solver stages and the coupling certificates
complete. A blocked or cancelled stage does not publish partial fields.

## Independent coupling derivation

No new differential equation or closure is introduced. Let retained face `f`
have area `A_f`, canonical unit normal `n_f` outward from its first owner, and
accepted Stokes face-average velocity `u_f`. For constant supplied density
`rho`, the energy solver's integrated oriented mass flow is

    F_f = rho A_f (u_f dot n_f).

The face maps are built from exact sorted retained vertex identities, not
coordinate proximity. Therefore every fluid-fluid face has one shared `F_f`
and opposite cell signs. The accepted Stokes local volume balance is

    sum_(f in boundary K) s_Kf A_f (u_f dot n_f) = 0,

up to its unchanged relative `1e-10` certificate. Multiplication by the one
constant density preserves this relative balance. Every face incident on a
solid is then required and assigned exactly zero mass flow. Before thermal
execution, the composer independently recomputes all cell balances; the energy
kernel repeats its own unchanged mass-flow and solid-mask checks.

The energy stage remains

    div(q) + div(rho u cp T) = source,    q = -k grad(T),

with shared RT0 conductive flux, P0 cell temperature and donor-cell enthalpy.
The flow-to-energy map is one-way: temperature never changes density,
viscosity, velocity or pressure. Perfect thermal contact is the existing shared
face conductive unknown; it does not model contact resistance.

The governing and discrete methods are not re-derived as new methods here.
The exact primary-source reviews remain:

- Crouzeix and Raviart (1973), DOI 10.1051/m2an/197307R300331, sections and
  equations recorded in `CFD_TETRA_STOKES_20261021.md` for the broken CR/P0
  Stokes formulation and compatible boundary data.
- Vohralik (2004), DOI 10.1016/j.crma.2004.08.004, equations (1)-(3), pp.
  525-526, recorded in `CFD_TETRA_ENERGY_20261021.md` for simplex RT0/P0 mixed
  fluxes.
- NIST FiPy 4.0.3 mathematical documentation, equations recorded in the same
  energy note for conservative shared-face upwind transport. No FiPy code is
  used.

This composition, its maps, validation data and tests were independently
authored. No external implementation, mesh, dataset or prose was copied.

## Actual analytical, conservation and convergence benchmark

The independent benchmark tetrahedralizes the unit cube with `2n x n x n`
Cartesian subdivisions and six positively oriented tetrahedra per brick. The
left half is solid and the right half fluid. The stationary conforming interface
is `x=0.5`. Conductivities are `k_s=2 W/(m K)` and `k_f=1 W/(m K)`; fluid
`rho=1 kg/m3`, `cp=100 J/(kg K)`, and `mu=1 Pa s`.

The analytical creeping field is

    u = (0, 0.005 (x-0.5), 0) m/s,    p = 0 Pa.

It is affine, divergence-free, harmonic, and exactly zero at the fluid-solid
interface. Exact triangular face averages are imposed on every exterior fluid
face. The tests require every returned CR face average to agree within
`2e-15 m/s`; this passed at all three levels.

The analytical thermal field and source are

    T = 300 + 10 y K,
    source = rho cp u_y (10 K/m) in fluid, 0 in solid.

The temperature gradient is tangent to the material interface, so both
temperature and normal conductive flux are continuous despite the conductivity
jump. Exact exterior triangular temperature averages are imposed. This is a
nonzero-flow, two-phase coupled case; donor-cell transport is expected to be
first-order rather than analytically exact.

Executed with Python 3.12.9 from `.venv`, writable `TEMP`/`TMP`, and
`OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=1`:

```text
.venv/Scripts/python.exe -m unittest tests.python.test_cfd_tetra_cht -v

Ran 3 tests in 6.551s
OK
```

Measured volume-weighted absolute cell-temperature L2 evidence:

| n | Retained cells | Fluid cells | L2 error [K] | Order | Flow local mass relative defect | Mapped mass relative defect | Cell energy relative defect | Global energy relative defect |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12 | 6 | 5.2912825e-3 | - | 2.0102e-17 | 1.9050e-16 | 6.2899e-16 | 1.4965e-16 |
| 2 | 96 | 48 | 2.1478421e-3 | 1.301 | 3.6953e-17 | 5.6122e-16 | 2.8828e-15 | 3.8339e-16 |
| 4 | 768 | 384 | 8.4703825e-4 | 1.342 | 2.0868e-16 | 7.1824e-16 | 2.3505e-14 | 2.1477e-16 |

The predeclared test gates require each temperature order above `0.5`, strict
decrease by at least a factor `0.7`, flow and mapped local mass defects no more
than `1e-10`, and cell/global energy defects no more than `1e-9`. All passed.
The finest scaled condition estimates were 1571.56 for flow and 221.97 for
energy. Solid-incident mass flow was exactly zero at every level. The test also
checks global exterior mass cancellation, exact retained face/vertex maps,
digest mismatch, forbidden solid body force, malformed thermal coverage,
cancellation, and absence of fields on every failure.

## Release limits and unsupported claims

This evidence verifies the software coupling and one manufactured numerical
regime. It does not qualify physical heat-transfer coefficients, engineering
accuracy, turbulence, eddy diffusivity, inertial flow, physical symmetric
traction, compressibility, buoyancy, radiation, transient CHT, moving solids,
contact resistance, rotating machinery, curved-wall convergence, general CAD
fluid-volume extraction, multi-material CAD interface recovery, nonshared
zero-measure contacts or automatic boundary/material inference.

The current OCC-to-tetra bridge remains single-material. Supplying numerical
cell phase masks does not turn that bridge into validated multi-material CAD
import. The Stokes outlet remains pseudo-traction with face-average backflow
rejection. Existing cell-count, geometry, Reynolds (`<=0.1`), solver residual,
condition, sparse-factor, field-size, deadline and cancellation gates remain
authoritative and unchanged.
