<!-- SPDX-License-Identifier: Apache-2.0 -->
# Conservative 3-D land fields with explicit face patches

This in-process experimental reference solves steady scalar Ohmic conduction
in one explicitly supplied rectangular prism. It does not infer an electrode,
annular geometry, arbitrary board contact, AC law or production qualification.
Distinct patch IDs retain distinct face fluxes and conjugate mean potentials;
repeated attachment labels never weld patches into an equipotential node.

## Acceptance fixed before implementation

Use explicit conforming Cartesian cell faces, including contact boundary lines.
All exterior faces remain in the system, including insulating faces. Reject
overlapping patches, incomplete mapping, nonfinite/unbalanced currents,
unsupported geometry, resource/conditioning failures and failed conservation.
Verify the removed gauge equation using recovered fluxes, not a reduced solve
residual alone. No diagonal regularization, zero-filling or current balancing.

Independent tests must include exact uniform axial conduction and harmonic
quadratic potential with all three nonzero current components; work and exact
cell Joule loss agree within 1e-9 relative. Face/cell KCL and prescribed flux
must agree within 1e-9 times the sum of absolute supplied currents. Verify zero,
sign/current-square/conductivity scaling, patch record ordering, distinct patches
with repeated attachment labels and rejected ambiguous mappings. A separate
cosine-series continuum oracle must check unequal localized face contacts over
three mesh levels, with finest resistance error <2% and improvement over coarse.
These are mathematical verification tolerances, not original-board gates.

## Independent governing derivation

Reviewed 2026-10-21: Haus and Melcher, MIT online *Electromagnetic Fields and
Energy*, [7.2 steady Ohmic conduction](https://web.mit.edu/6.013_book/www/chapter7/7.2.html),
conservation/constitutive/insulating-boundary/conductance discussion;
[5.4 Cartesian separation](https://web.mit.edu/6.013_book/www/chapter5/5.4.html)
and [5.10 three-dimensional Cartesian solutions](https://web.mit.edu/6.013_book/www/chapter5/5.10.html),
separation, product solutions and orthogonal series discussion. Equation images
are not claimed as separately transcribed. The face basis and elimination below
are independently derived from these laws, not copied external code or a mesh.
The existing mixed-flux lineage is described in [DC RT0 density](DC_RT0_DENSITY.md);
its triangular basis is not asserted to be this hexahedral discretization.

In SI units J=-sigma grad(phi), div(J)=0. For a box with lengths Lx,Ly,Lz,
let q_x-,q_x+ be outward integrated currents through opposite x faces and
xi=(x-xmin)/Lx. Then Jx=[-q_x-*(1-xi)+q_x+*xi]/(Ly*Lz), with cyclic y,z.
Each basis has unit outward flux on its own face and zero on the others.
The divergence integral is the sum of all six q. The exact local Ohmic mass
is block diagonal; each axis block is

`M_axis = L_axis/(sigma*A_face) * [[1/3,-1/6],[-1/6,1/3]]` ohm.

Integrating J dot w /sigma and integration by parts gives
`Mq + lambda - p*1 = 0`, `1^Tq=0`, with cell-average potential p and
face-average trace lambda. Set v=M^-1*1, d=1^Tv and
H=M^-1-v*v^T/d. Then q=-H*lambda and p=v^T*lambda/d.
Assemble H on shared face IDs. Interior outward fluxes sum to zero; boundary
flux is prescribed. Therefore S*lambda=-q_boundary. A single trace fixes the
constant-potential gauge; all other traces, including insulating boundaries,
remain unknown. Recover all q and check the omitted gauge equation explicitly.

The bilinear form is positive on divergence-free currents; H is positive
semidefinite with constant nullspace, and the connected gauged trace operator
is positive definite. Diagonal scaling and an explicit spectral condition screen
are numerical safeguards, not rigorous forward-error bounds. No regularization
or clipping is allowed. Cell power q^TMq is the exact integral of |J|^2/sigma
for the reconstructed field, including cross terms between opposite faces.
Summing stationarity gives total power=-sum_boundary(lambda*q), exactly the
supplied current times each uniform patch's area-average potential.

Boundary current is positive into the prism; each patch distributes its supplied
current uniformly over its declared finite rectangle. The compiler requires its
edges to be existing grid planes. It assigns exterior face IDs independently of
attachment labels, and rejects overlap or uncovered support. This is a prescribed
Neumann patch, not an equipotential electrode. No conductivity or geometry is
inferred from a node ID. Heat is W; mean cell heat density is W/m3, not energy J.
All cells, including zero-current volume, remain represented for later coupling.

Normalize face area by patch area before multiplying by current; a representable
small face current must not be lost through an intermediate area product.
Nonzero currents that underflow on a positive-area face reject. Recovery uses
the declared global absolute tolerance, not a per-patch relative guarantee.
Each patch retains its requested/recovered current and absolute error; tiny
patches in a much larger drive may be unresolved at that bound. They are not
silently relabeled relatively accurate or used to change the supplied currents.

## Limits

One uniform, isotropic material; fixed axis-aligned prism and rectangular patches
on its six exterior sides. This supplies actual through-thickness and spreading
fields in that domain, not annular land transition fields or a whole-board
physical-volume percentile. Different patches can share a semantic attachment
label without sharing voltage. External barrel/circuit equations must separately
couple their conjugate potentials and currents; no imposed current is silently
treated as a solved circuit current. Production and complete-board flags stay
false. Knowledgeable human numerical review is required before release.

## Runnable interface and retained evidence

Call `solve_land_transition(request)` from `dc_land_transition.py`. The strict
in-process request has `contract="spike/dc-land-transition-request/v1"`, three
explicit increasing `axes_mm` lists, `conductivity_s_m`, and `contacts`.
Each contact has exactly `id`, `attachment_id`, `face` (`x_min` through `z_max`),
`rectangle_mm` (two tangential intervals in ascending coordinate-axis order),
and `current_a`. Patch interval endpoints must be exact supplied grid planes.
Coordinates are converted to SI after subtracting each axis origin, so global
placement does not contaminate local mass moments. Bounds are returned in mm.

Limits: 2..25 planes per axis, <=4096 cells/16000 faces, 2..64 contacts, cell
aspect <=1e4, conductivity 1e-6..1e12 S/m and |patch current|<=1e9 A. Coordinates
are within +/-1e6 mm and consecutive planes separated by at least 1e-9 mm.
These are arithmetic limits, not material or manufacturing validity claims.
Bounded input structure is checked before serialization (1 MiB maximum).
The diagonally scaled gauged trace operator must have estimated condition
<=1e12; eigenvalue screening is not a rigorous forward-error certificate.
Sparse factor fill/time remains a supervised offline risk. No cancellation
or installed desktop/native performance claim is made.

Run the checked-in three-patch example without general worker registration:

```powershell
.venv-emerge3/Scripts/python.exe examples/dc_land_transition/run_land.py --output build/my-land-result.json
```

The example rejects overwriting existing output and validates the saved witnesses.
`validate_land_result(result)` separately recomputes patch/cell support, local
Ohmic weak equations, full gauge-inclusive flux balance, vector components,
integrated heat and terminal work without another solve. Raw face and cell mean
potentials are retained to make that check possible. Diagnostics alone cannot
admit changed fields. Physical results can be compared across refinements;
reported heat is ready for explicit conservative transfer by cell identity,
but no thermal mesh association is inferred.

The independent same-face spreading oracle uses 1x1x0.2 mm and sigma=5.8e7 S/m:
on z=0, +I enters the left x half and -I leaves the right half, both full-width
in y; remaining faces are insulating. Cartesian separation gives k_m=m*pi/Lx,
g_m=8I*sin(m*pi/2)/(Lx*Ly*m*pi) and
phi_m=g_m*cos(k_m*x)*cosh(k_m*(Lz-z))/(sigma*k_m*sinh(k_m*Lz)). Thus

`R=32*Lx/(sigma*Lx*Ly*pi^3) * sum_odd_m coth(m*pi*Lz/Lx)/m^3`.

After N terms the omitted positive tail is at most
`16*Lx*coth((N+1)*pi*Lz/Lx)/(sigma*Lx*Ly*pi^3*N^2)`.
This is an analytical truncation bound, not outward-rounded floating arithmetic.
The independently authored oracle, harmonic quadratic field and SI Gauss
integration tests do not derive expected values from the solver matrix.
