<!-- SPDX-License-Identifier: Apache-2.0 -->
# Conservative retained-volume DC and explicit board contacts

Status: experimental development, 2026-10-23. Acceptance below was recorded
before implementing the new tetrahedral reference. Full PI01-S02 is not done.

## Governing mathematics and primary sources

Steady scalar Ohmic conduction uses J=-sigma grad(phi), div(J)=0 in each
conductor and prescribed outward normal current on its boundary. Conductivity
is a strictly positive, finite, cellwise scalar in S/m. Geometry converts to m;
flux degrees of freedom are A, potentials V, vector density A/m2 and heat W.
No displacement current, skin/proximity effect, AC or tensor claim is made.

Reviewed 2026-10-23: Haus and Melcher, MIT online *Electromagnetic Fields and
Energy*, [7.2](https://web.mit.edu/6.013_book/www/chapter7/7.2.html), conservation,
Ohmic law, insulating boundaries and continuity discussion; and
[7.4](https://web.mit.edu/6.013_book/www/chapter7/7.4.html), linear superposition
and uniqueness. Surrounding derivations were reviewed; embedded equation
images are not claimed as separately transcribed equations.

Vohralik, *Equivalence between mixed finite element and multi-point finite
volume methods*, C. R. Math. 339 (2004), 525–528,
[reviewed publisher paper](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.1016/j.crma.2004.08.004.pdf),
DOI [10.1016/j.crma.2004.08.004](https://doi.org/10.1016/j.crma.2004.08.004),
equations (1)–(3), printed pp.525–526 and section1's oriented simplex basis,
provides the mixed formulation and face-flux foundation in dimensions two and
three. The paper's vertex-cluster elimination algorithm is not implemented.
The [DefElement RT definition](https://defelement.org/elements/raviart-thomas.html),
definition table through continuity, was reviewed for space, facet moments,
tetrahedral support and Piola mapping only. External implementation sections
were not used as algorithm source. All following algebra, code, geometries and
test oracles are independently authored; no external implementation/data is
copied or translated. Existing NumPy/SciPy/Shapely are the only dependencies.

## Independent local and hybrid derivation

For tetrahedron T, positive volume V, vertices v_i and outward face current q_i
opposite vertex i, define f_i(x)=(x-v_i)/(3V). The altitude formula proves unit
integrated outward flux on face i, zero on its other faces, and div(f_i)=1/V.
Thus J=sum(q_i f_i), div(J)=sum(q_i)/V. Normal trace is constant on each face.
One shared trace potential per geometric triangular face enforces normal-current
continuity, including across material changes. Node labels alone do not join
separately indexed solids or impose electrical contact.

Let c be the vertex mean and C=sum((v_k-c)(v_k-c)^T)/20. Uniform tetrahedral
barycentric integration gives E(x)=c and covariance C. The exact mass is

```
M_ij = [trace(C) + (c-v_i).(c-v_j)] / (9 V sigma).
```

Use coordinates relative to a cell vertex before taking differences/moments.
No centroid heat approximation or diagonal lumping is used. Integration by
parts gives Mq + lambda = p*1, together with 1^T q=0, where p is the cell mean
potential. Put W=M^-1, a=W*1, d=1^T*a. Elimination yields
H=W-a*a^T/d, q=-H*lambda and p=a^T*lambda/d. Assemble H over all shared face
identities. The prescribed outward face-flux sum is b (negative for inward
terminal current), so Hglobal*lambda=-b. One trace gauge is fixed per connected
face component. Before solving, each component must have balanced prescribed
current; recover the redundant gauge equation afterward. All undriven components
remain in the solve and volume census: homogeneous Neumann current is zero,
while the potential gauge is arbitrary.

Patch current is distributed by physical triangular area; its conjugate voltage
is the same area-weighted trace average. Separate contacts retain separate IDs.
P=sum(q^T M q)=sum(I_in*V_patch). Conservative signed flux reconstructs all three
current components and exact integrated Joule loss in every volume element.
No special branch loss or excluded land pseudo-volume is added.

## Frozen acceptance and limitations

Require finite positive oriented, nonoverlapping conforming tetrahedra using
the existing retained-solid geometry audit. Reject hanging/unused nodes,
duplicate/nonmanifold cells/faces, invalid ownership, partial/internal/overlapping
terminal faces, unbalanced connected components and resource/conditioning
failures. Missing source/axial support must remain explicit; a supplied tetra
mesh cannot by itself prove source-board completeness.

Independent checks: uniform and rigidly rotated volume fields, layered-sigma
series R and heat, multiport conservation, harmonic continuum refinement,
physical field integration, zero/signed/conductivity scaling and disconnected
undriven volume. All face/boundary/gauge and cell KCL errors must be <=1e-9 times
the connected component's sum of absolute prescribed face currents. Heat/work
must agree separately in every component within1e-9 of its physical power scale.
Actual fields with nonzero current and zero underflowed heat reject. A strong
component cannot mask a missing weak driven component's current or dissipation.
The diagonally scaled trace operator must pass the existing1e12 condition
screen; this estimate is not a rigorous forward-error certificate.

Density statistics use each unique tetrahedron's physical volume, including
undriven volumes. The retained RT0 field is affine, so the vector norm is bounded
above by maximum vertex norm, and below by centroid norm minus maximum vertex
distance. Exact supplied binary64 weighted quantile ranks of these bounds give
an enclosure, retaining quantile jump ambiguity. Refinement and geometry/model
error remain separate from this reconstructed-field bound; a percentile is not
a conservative maximum-current or hardware-rating certificate.

The board compiler must prove coverage of each explicit layer slab and barrel
gap, reject positive-volume overlap and keep full finite polygon contacts,
including holes/disconnected supports. Barrel wall thickness, electrode area,
material and stack assumptions are supplied, never inferred from a drill-center
point. A source-pinned source/mesh coverage ledger is needed before any complete
board-volume claim. Original EBrake/Marble acceptance, installed/runtime
integration, physical validation and human numerical release review stay open.

## Reproducible offline interfaces and source handling

`dc_tetra_rt0_input.py` admits `spike/tetra-dc-rt0-request/v1`: an existing
`spike/solver-mesh/v1`, exact per-cell scalar `conductivity_s_m`, and distinct
contact IDs with whole exterior triangular faces and signed inward `current_a`.
The reference caps are 5,000 tetrahedra, 10,000 vertices, 16 MiB JSON and
2--4,096 contacts. Nonzero subnormal cell heat is rejected because its rounding
cannot support the unchanged relative energy check. Cancellation is checked
between bounded operations; sparse factorization itself is not interruptible.

`dc_board_volume.py` compiles declared disjoint layer slabs, explicit barrel
gaps and exterior full polygon patches. Global noded XY boundaries, constrained
Delaunay pieces and common vertical planes produce conforming three-tetrahedron
prisms. Authored vertical endpoints are retained exactly. Directional omitted
and excess support, symmetric difference, component/hole topology and physical
volumes are retained, including the admitted binary64 overlay tolerance.
The offline compiler admits at most 128 layer/net groups, 512 barrel gaps and
256 contacts; exceeding these or the tetrahedron cap blocks before allocation.

`dc_board_source.py` authenticates every normalized pad/via against one native
source-hash-pinned inventory before selecting full-pad electrodes. The batch
inventory has a 64 MiB / two-million-node parser budget; the existing single-pad
API retains its earlier limit. Centered circular through barrels, explicit
plating thickness and scalar conductivity are admitted. Unsupported offset,
per-layer padstack, unused-layer policy and noncircular barrel cases reject.
The source stack profile's provenance must still be inspected: its fallback
thickness/interpolation is a model assumption, not measured stack evidence.

`dc_board_filled.py` admits retraced filled paths only with authoritative
native filled-copper provenance. It recovers outer/hole rings using the existing
exact source-path boundary, triangulates their physical support and audits both
directional overlay losses. A genuine triangle below the legacy per-zone area
threshold is exactly united with an adjacent piece, never discarded or moved.
Original source IDs and all foreign/NPTH drill subtraction are retained.
The selected EBrake24V source fill has 443 points, one outer ring and three holes;
the executed native rerun retains the conversion evidence and source digests.

`dc_board_study.py` composes strict `spike/dc-board-volume-model/v1` or
`spike/source-board-volume-study/v1` requests. Retained validators reconstruct
geometry/contact coverage, source authentication and independent physical field
witnesses; they do not call a second field solve. Source wrappers retain fill
evidence and hash-check the native file again after solving. Pure declared
models explicitly report that native-source authentication was not performed.

Run `examples/dc_board_volume/run_volume.py REQUEST.json FRESH_RESULT.json`
with the project Python environment. The checked-in `holed-board.request.json`
is an original declared-volume example. Output paths must be fresh. These APIs
are offline development references without a production worker route or UI
qualification. Cell/source identities, SI fields and watts are retained for
future conservative thermal transfer; coupled thermal feedback is not enabled.

Executed tests, source-bound receipts, real-board blockers and the next scaling
gates are recorded in [the dated validation record](validation/PI01_BOARD_VOLUME_20261023.md).
