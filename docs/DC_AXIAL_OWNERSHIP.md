<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit annular DC land and barrel ownership

`python/spike_core/dc_axial_ownership.py` is an experimental, independent helper
for one explicitly supplied coaxial annular stack. It partitions the declared
land and barrel geometry and evaluates imposed uniform axial gap currents.
It does not infer electrodes, import a board, solve land transition fields,
or change existing RT0/production dispatch. EBrake contact definition and
full PI01-S02 qualification remain open.

## Governing references and independently authored derivation

Reviewed 2026-10-21: Haus and Melcher, MIT online *Electromagnetic Fields and
Energy*, [section 7.2, Steady Ohmic Conduction](https://web.mit.edu/6.013_book/www/chapter7/7.2.html),
steady conservation, Ohm's law, continuity, insulating boundaries, and
conductance discussions; and [section 7.3, Distributed Current Sources](https://web.mit.edu/6.013_book/www/chapter7/7.3.html),
the opening conservation discussion and the distributed-current source
definitions. These establish the constitutive and conservation laws and the
distinction between actual current continuity and a reduced distributed-source
model. Embedded equation images were not separately transcribed. No external
implementation, geometry, mesh, test data, or elimination algorithm was read
or copied. The following formulation, implementation, and tests are original
SPIKE material under Apache-2.0.

Let every supplied land be an annular prism with common center `(x,y)` and bore
radius `ri`, outer radius `rland`, and explicit slab `[zmin,zmax]`. All slabs
must be disjoint and separated by a positive gap. A segment connects exactly
two adjacent slabs, with annular outer radius `ro <= min(rland_source,
rland_target)`. Its supplied center-to-center span reaches both exact slab
midplanes. Its physical axial owner is only the interval between the facing
slab surfaces. The whole land thickness belongs to the land owner, including
the radial region occupied by plating at those z coordinates.

Therefore land interiors and gap interiors are pairwise disjoint. Shared faces
have zero volume. Requiring exactly one segment for every adjacent slab gap
rejects missing gaps, duplicate/reversed duplicates, and segments skipping an
intermediate slab. Two segments meeting a middle land do not each own any of
its thickness; the land volume is counted once. This proof is for the supplied
single coaxial stack, not arbitrary copper polygon/cylinder intersections.

For a gap of length `ell` mm and conductivity `sigma` S/m, define

```
A = pi * (ro-ri) * (ro+ri)             [mm2]
Vgap = A * ell                        [mm3]
Rgap = 1000 * ell / (sigma * A)        [ohm]
Jz = sign(z_target-z_source) * I / A   [A/mm2]
Pgap = I * Rgap * I                   [W]
```

Here `I` is the supplied signed current from source land to target land. A
uniform axial field has zero divergence inside the gap, integrates to the
specified current at each annular face, and obeys Ohm's law. Independently,
`integral(|J|^2/sigma dV)` in SI gives the same `I^2 R` dissipation. Density is
a signed vector; heat is nonnegative; volume does not depend on current.
Zero supplied current yields exact zero density and heat. Negative current
reverses the vector and contact incidence without changing heat. Endpoint
reversal with current sign reversal preserves the physical field.

Each source land receives `+I` in its `net_current_to_barrels_a` ledger and
each target receives `-I`. The helper reports the sum; it does not force it to
zero, invent external current, or adjust supplied currents. Land planar and
through-thickness fields, boundary conditions, and their work balance must
be solved independently. Land conductivity is retained, but land heat is
`null` with explicit `unresolved` status, never inferred as zero.

## Contract and fresh-solve adapter

`compile_axial_ownership(request)` accepts exactly these root fields:

| Field | Meaning |
| --- | --- |
| `contract` | `spike/dc-axial-ownership-request/v1` |
| `center_xy_mm` | Two finite coordinates; common coaxial center |
| `net` | Explicit nonempty common net identity |
| `bore_radius_mm` | Explicit positive common bore radius |
| `lands` | Two to 256 explicit land records, in any order |
| `segments` | Exactly one explicit record per adjacent land gap, in any order |

A land has exactly `id`, `layer`, `node`, `z_min_mm`, `z_max_mm`,
`outer_radius_mm`, and `conductivity_s_m`. Land IDs, layers, and nonnegative
integer node IDs must be unique. Each segment has exactly `id`, `kind`
(`via` or `pad_barrel`), `source_land`, `target_land`, `start_z_mm`, `end_z_mm`,
`outer_radius_mm`, `conductivity_s_m`, `current_a`, `source_contact`, and
`target_contact`. Each face contact has exactly `id`, `land_id`, `node`,
`inner_radius_mm`, and `outer_radius_mm`; its node/land must match the named
endpoint and its radii must equal the segment annulus exactly. Contact IDs
are unique even when two different faces meet the same middle land.

Contact area is computed from those supplied radii. No arbitrary planar
contact is resized into an annular contact, and no contact incidence is
reassigned. The returned source request and SHA-256 digest retain all inputs.
The result includes the original center span and its resistance, removed
land span, physical gap resistance, signed resistance change, gap volume,
imposed-current field/heat, and signed land incidence ledger.

`make_gap_branches(request)` validates the same request and returns fresh
`MeshBranch` instances, retaining the supplied node IDs. Their endpoints are
the slab faces and their width/thickness encode the annular area as
`pi*(ro+ri)` and `ro-ri`. Their `source_id` is the explicit segment ID and
`evidence_id` is the input digest. The function takes no existing mesh or
solution and cannot mutate one.

The old center-span resistance includes lengths now owned by the lands.
Consequently every result retains `requires_resolve=true`: corrected gap
branches must be inserted before a fresh coupled solve with explicitly
matched finite contacts. Supplied currents in this helper remain imposed
values, not authenticated outputs from that fresh solve. Existing solved
currents/heat cannot be relabeled as corrected results after clipping.

The current RT0 model distributes a barrel's endpoint incidence uniformly
over its supplied planar contact. It does not resolve the 3-D transition from
axial annular flux into planar land flux. A polygonal approximation of an
annular contact also has a different area from the exact circular annulus;
an integration fixture must retain that approximation and area discrepancy,
not silently rescale it or claim exact geometry matching. This helper does
not inspect or certify any RT0 mesh/contact adapter.

In particular, two faces attached to the same land node can have different
supplied annular radii. Their ownership descriptors remain separate. Existing
RT0 node-based contact ownership does not by itself represent two different
patch distributions on that shared node. A future compiler must explicitly
map each face's patch, current incidence, and conjugate mean potential; this
helper's branch adapter does not certify that mapping. The executed integration
fixture deliberately uses the same annular footprint for every face and land.

Every result retains `complete_physical_volume=false` and
`production_qualified=false`. Disjoint ownership of the declared geometry
does not supply the missing land transition field, a whole-board density
distribution, physical-volume percentile, or physical validation. No planar
and axial field merge, thermal-cell ownership, AC, nonlinear material, contact
resistance, manufacturing model, or release qualification is introduced.

## Numerical bounds and executed checks

Coordinates and radii are bounded by 1e6 mm in magnitude; radii, land slab
thickness, annular radial thickness, and axial gaps must be at least 1e-9 mm.
Conductivity is in `[1e-12,1e12]` S/m and imposed current magnitude at most
1e12 A. These are arithmetic admission bounds, not material-validity claims.
IDs have at most 80 characters, node IDs are below `2^31`, and serialized
input is bounded to 1 MiB. The topology/ledger work is linear except for land
sorting. No linear-system conditioning, iterative convergence, or cancellation
model is implied by these closed-form geometry and uniform-field calculations.

The factored annular area avoids subtracting squared radii. Exact supplied
binary64 endpoint, contact, and identity comparisons perform no snapping or
geometry repair. Nonfinite, collapsed, overflowed, and nonzero-current
underflowed results reject. These are ordinary binary64 evaluations, not
outward-rounded interval certificates. `pi` is the standard floating-point
constant. Small perturbations near strict admission boundaries can reject;
the helper does not choose a different geometry to obtain success.

Executed with `.venv-emerge3/Scripts/python.exe -m unittest
tests.python.test_dc_axial_ownership tests.python.test_dc_axial_resolve -v`:
nine focused tests passed. Coverage
includes independent SI cylindrical Gauss integration of volume, face current,
and Joule heat; independent resistance; shared middle-layer ownership and
nonzero signed land incidence; input ordering and endpoint reversal; zero,
sign, current-square, and conductivity scaling; fresh branch resistance and
source immutability; contact reassignment/area changes; duplicate/skipped/missing
gaps, slab overlaps/touches, endpoint underreach/overhang, and representability
rejections. The separately authored integration fixture performs actual fresh
RT0 solves with center spans and gap spans on three explicitly matched annular
land/contact footprints. It verifies the independent 1.8 mm series-gap
resistance and a 0.9 ratio to the 2 mm center-span resistance, along with
heat/work and cell/face KCL. The polygonal contact-area discrepancy is retained;
the ownership request's imposed 2/3 A heat is not reused by the actual 1 A
solve. The architecture guard also passed. No board solve or human numerical
release review was performed by this helper task.
