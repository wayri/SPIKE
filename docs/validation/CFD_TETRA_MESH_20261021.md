<!-- SPDX-License-Identifier: Apache-2.0 -->
# Conservative tetra topology and bounded OCC-to-CFD bridge

Date: 21 October 2026. Status: experimental geometry admission, not a CAD
mesher, a complete conformity proof, or physical CFD qualification.
Implementation: `python/spike_core/cfd_tetra_mesh.py` and
`python/spike_core/cfd_tetra_intersections.py`. Original executable fixtures:
`tests/python/test_cfd_tetra_mesh.py`.

## Contract and boundary

The numerical mesh has exactly:

```text
contract: "spike/cfd-tetra-mesh/v1"
units: "m"
vertices: list of finite real [x,y,z]
cells: list of four distinct integer vertex indices
boundary_patches: {patch_id: list of three distinct integer vertex indices}
```

Indices are identities, not spatial nearest-neighbor guesses. There are no
material or provenance fields in this numerical contract. No ordering repair,
welding, boundary inference, or geometry displacement is performed. Tetrahedra
must already have positive determinant. All vertices must be used, all cells
must be unique, and all exterior facets must have exactly one explicit patch.
Boundary triangle winding is immaterial: the volume orientation determines
outward flux signs. Patch triangle order is retained in the returned face map.

`admit_cfd_tetra_mesh(mesh, cancel_check=None)` returns copied arrays or raises
`CfdTetraMeshError`. Cancellation raises `InterruptedError`. Returned keys:

| Geometry/topology | Meaning and units |
| --- | --- |
| `vertices`, `cells` | Source-frame coordinates in m and connectivity |
| `cell_volumes` / `volumes`, `cell_centroids` | m^3 and m |
| `barycentric_gradients` | `(cell, local vertex, xyz)`, 1/m |
| `face_vertices`, `face_areas`, `face_centroids` | Global oriented triangle, m^2, m |
| `face_normals` | Unit normal outward from first owner |
| `face_owners` | Two cell indices; second is -1 at exterior |
| `cell_faces` | Four face IDs, each opposite the corresponding local vertex |
| `cell_face_signs`, `cell_outward_normals` | +/- canonical orientation and cell-outward unit normal |
| `boundary_patches` | Patch to ordered face-index array |
| `components` | Face-connected cell-index arrays |
| `intersection_screening` | Bounded global positive-volume screening counters and exact scope |

The bridge `prepare_cfd_tetra_mesh(occ_result, patch_assignments)` consumes the
existing completed experimental `spike/gmsh-occ-mesh-result/v1` or `/v2`
representation. Assignments are an explicit mapping from **integer CAD surface
tag to patch ID string**, covering every exterior CAD surface exactly. Several
surfaces may share a patch. Millimetres become metres once at this boundary.
Only a single material with no CAD interface faces is admitted. This does not
perform fluid-region extraction, a CAD Boolean, or solid-to-fluid inference.

The bridge checks the neutral mesh contract and counts, unique cell IDs,
boundary-triangle redundancy, each boundary record's actual cell/material/source
membership, source-object coverage, and fragment/source volume bindings.
Multiple fragments with identical material/source membership are rejected:
the existing result does not provide per-cell fragment IDs to disambiguate them.
Reported tetrahedral volumes must match actual tetrahedral geometry to relative
1e-9. CAD volume sums must match the CAD ownership/source records, **not** the
tetrahedral volume. Curved CAD approximations may legitimately differ from the
flat-facet volume; the relative discrepancy is reported without correction.

The returned `mesh` remains the strict numerical object. Sibling `provenance`
retains original cell IDs/material/source records, object map, fragment map,
surface assignments, optional request/runtime metadata, and a SHA-256 of the
canonical JSON OCC result. This binds the supplied snapshot, not its authenticity.
`source_authenticity_verified` is false. A syntactically valid request digest
cannot independently prove correspondence to an unavailable STEP/request file.
Root-level source/runtime binding and real-CAD correlation remain separate checks.
No external engine is imported or invoked by this bridge.

## Reviewed primary mathematics and clean-room scope

Reviewed on 21 October 2026:

| Primary source | Precise reviewed content and use |
| --- | --- |
| Long Chen, *Introduction to Finite Element Methods*, updated 17 January 2024, [author-hosted notes](https://webapps.math.uci.edu/~chenlong/226/Ch2FEM.pdf) | Section 2.1, printed pp. 2-4, equations (5)-(8): simplex affine coordinates, partition of unity, opposite faces, affine reference map and distinction between geometric conformity and connectivity. |
| MIT OpenCourseWare, *Calculus with Applications*, [22.3 Measures on Volumes and the Divergence Theorem](https://ocw.mit.edu/ans7870/18/18.013a/textbook/HTML/chapter22/section03.html) | Entire short section: outward normal flux, cancellation on shared boundaries, and volume divergence identity. |
| S. Gottschalk, M. C. Lin, D. Manocha, *OBBTree: A Hierarchical Structure for Rapid Interference Detection*, SIGGRAPH 1996, [author-hosted preprint](https://gamma.cs.unc.edu/SSV/obb.pdf) | Section 5, PDF p. 8: convex-polytope separating axes parallel to face normals or cross products of an edge from each polytope. SPIKE applies this theorem to tetrahedra; no OBB-tree implementation is adopted. |
| J. R. Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates*, 1 October 1997, DCG 18:305-363, [author-hosted paper](https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf) | Section 3.2, printed pp. 27-29 / PDF pp. 32-34: relative-error model, expression error propagation and sign filtering. SPIKE uses its own conservative determinant bound and Python binary rational fallback, not expansion arithmetic or source implementation from this work. |

All derivations, data structures, code and test coordinates were independently
authored. No external code, meshes, examples, runtime binaries or datasets were
copied. The existing optional Gmsh environment and its redistribution status are
unchanged; numerical conversion does not qualify an engine installation.

## Independent geometry derivation

For vertices `x0,x1,x2,x3`, form
`J=[x1-x0, x2-x0, x3-x0]`. Positive orientation requires `det(J)>0`, and
`V=det(J)/6`. Reference coordinates are `(lambda1,lambda2,lambda3) =
J^-1 (x-x0)` and `lambda0=1-sum(lambda1..3)`. Thus the last three barycentric
gradients are rows of `J^-1`, and the first is their negative sum.

Each triangle's oriented area vector is half its edge cross product. The four
outward local face tuples are `(123),(032),(013),(021)`, opposite local vertices
0,1,2,3 respectively. Their magnitudes are areas; dividing yields unit normals.
The first tetra to own a facet fixes its global orientation. Its other owner
must lie on the other side and receives sign -1, making any shared normal flux
cancel exactly in the assembled incidence topology.

Apply the divergence theorem to each constant Cartesian vector and to `x-o`:

```text
sum_f A_f n_f = 0
sum_f A_f (c_f-o).n_f = 3 V
```

Linear coordinates integrate exactly at triangle centroids. Calculations use
cell-local differences before scaling, not subtraction of two large global
surface moments. Each cell's local edge scale `L=max(abs(xi-x0))` produces
dimensionless `J/L`; the checked area and moment identities are dimensionless.
Only after those operations are areas, volumes and gradients restored to SI.
Source-frame centroids are provided for consumers; consumers must likewise use
local differences for sensitive integrations rather than large global moments.

Closure tolerance is relative 1e-12 against the sum of normalized face areas.
The scalar moment has relative 1e-10 tolerance against `det(J/L)/2`.
The spectral condition of `J/L` must not exceed 1e6. Underflow, overflow or
nonfinite derived arithmetic blocks admission; no dimensional absolute floor
manufactures a geometric success. Conditions and tolerances bound this numerical
representation, not CAD manufacturing accuracy.

Topology checks additionally require at most two owners per facet, two exterior
triangles per boundary edge, and a connected cyclic boundary vertex link. These
catch duplicate, nonmanifold and pinched boundary topology. They alone do not
exclude geometric overlap between tetrahedra with unrelated vertex identities.

## Positive-volume intersection exclusion

The added screen examines every tetra pair through exact comparisons of their
binary64 coordinate AABBs. An axis-aligned touching interval already excludes
positive-volume intersection. A pair sharing a fully verified opposite-sided
facet also cannot overlap in positive volume. Remaining candidates undergo
convex separating-axis tests: eight face normals and up to 36 cross-edge axes.

For an axis `n=e x f`, compare every `n.(bj-ai)`. If all differences have the
same weak sign and the axis is nonzero, the two interiors are separated; zero
differences allow exact contact. All 16 differences zero imply a zero axis,
since admitted tetrahedra are full-dimensional. If every nonzero candidate
axis has both signs, convex separation guarantees positive-volume overlap.

The six determinant monomials are evaluated explicitly. Each includes three
rounded input differences and two multiplications; summation has at most five
additional roundings. Under the usual `fl(op)=op*(1+delta)`, `|delta|<=u`,
the error is bounded by `gamma_10` times the exact positive permanent.
The computed permanent has a corresponding relative bound. The implemented
`128*eps/(1-128*eps)` multiple of the computed permanent conservatively exceeds
`gamma_10/(1-gamma_10)`, including its own rounding (`eps=2u`). IEEE inexact
underflow/overflow is rejected. Exactly representable subnormal operations have
zero rounding error; they are not used to waive an inexact underflow.

An uncertain sign is **not** treated as zero or separation. The fallback first
converts original binary64 endpoints with `Fraction.from_float`, then subtracts,
forms the rational cross product, and computes exact vertex projections.
Therefore it resolves the geometry actually represented by the input, not an
invented tolerance neighborhood. Exact face normals and their vertex projections
are cached across neighboring pairs; orientation reversal cannot affect an
interval separation. The eight face-axis filters are batched. Cross-edge tests
are retained when faces alone cannot separate the pair.

Caps remain 4096 cells, 16384 vertices/facets, 100000 candidate pairs,
2000000 axis tests and 200000 newly evaluated exact projections. Exceeding a
budget rejects, without disabling the screen or silently accepting the mesh.
Cancellation is polled per cell and candidate pair. The broad phase uses
bounded linear-size working arrays rather than a dense pair matrix. Metadata
serialization is bounded to 8 MiB, 250000 nodes, depth 24 and bounded strings.

This establishes **positive-volume exclusion**, not complete global mesh
conformity. Nonshared zero-measure contact, coincident partial surfaces, hanging
entities, a CAD boundary approximation, and original CAD/source authenticity
remain unqualified. Accordingly `positive_volume_overlap_checked` is true on
success while the broader `global_intersections_checked` remains false.

## Executed evidence

Command:

```text
python -m unittest tests.python.test_cfd_tetra_mesh -v
python -m py_compile python/spike_core/cfd_tetra_mesh.py python/spike_core/cfd_tetra_intersections.py tests/python/test_cfd_tetra_mesh.py
python scripts/check_architecture.py
```

The 14 focused tests pass. Their independently declared cases include:

- Reference simplex volume 1/6, exact barycentric gradients and opposite-face map.
- Nonorthogonal affine shear, proper rotation and million-metre translations:
  volume 3/8, affine scalar gradient reproduction, vector closure and the stronger
  tensor identity `sum (c_f-o) outer (A_f n_f) = V I`.
- Shared-face cancellation, preserved patch order, disconnected components and
  input immutability.
- Similarity scales 1e-40 and 1e40; unrepresentable 1e-120-volume computation rejects.
- Inversion, excessive condition, degeneracy, orphan vertices, duplicate
  tetrahedra/vertices, invalid indices/types/units, incomplete or surplus patches.
- Same-side shared-facet overlap, three-owner facets, and pinched boundary edges.
- Resource rejection before numeric allocation and cancellation.
- Millimetre conversion, retained provenance, explicit curved-volume discrepancy,
  forged boundary ownership/source/volume bindings and assignment coverage.
- Overlapping disconnected tetrahedra with no shared IDs reject. Exact nonshared
  contact is not rejected as overlap. Moving the touching vertex one binary64
  step into the other tetra rejects; moving it one step away passes.
- Rotated/sheared valid pairs at scales 2^-80, 1 and 2^80; unchanged candidate
  and exact-predicate cap rejection.
- Floating sign certificates checked against independently expanded rational
  determinants for 60 seeded cases, including large translated coordinates.
- An original integer-coordinate pair for which all face-axis projections overlap
  but the cross-edge axis `(-29,-10,8)` separates. This guards against accidentally
  omitting the edge-edge part of the theorem.

Before global screening, 10 focused tests passed in 0.045 s and architecture,
compilation and targeted whitespace checks passed. After screening, 14 tests
passed in 0.092 s in the focused run. An intermediate optimization reduced the
384-tetra sheared-grid admission from 4.43 s to 2.65 s, but the unchanged
200000-exact-predicate cap rejected its 3072-tetra counterpart after 21.83 s.
This failed timing/budget probe was not counted as accepted. Subsequent batching
and exact-projection reuse reduced the 384-tetra case to 1.25 s / 8467 new exact
projections. The final 3072-tetra sheared-grid admission passed in 12.442 s:
63296 candidate pairs, 506368 axis tests and 73033 new exact projections,
within the unchanged budgets. Integration evidence belongs in the root
benchmark receipt; no unrelated solver accuracy threshold was altered.

## Retained analytic STEP placement correction

The real curved-CAD fixture exposed an independent retained-import defect.
`assembly_thermal_cad.import_step_solid` formerly invoked the general OCC affine
transform even for identity. The existing input contract admits proper rigid
transforms only. It now reuses the existing `rigid_place` implementation:
native rotation about the source origin followed by translation; identity is
a no-op. Shape-count, closed-volume, ownership, transform-validation and runtime
installation gates are unchanged.

API semantics reviewed: the official **Gmsh 4.15.2 manual**, March 24, 2026,
[`occ.translate`, `occ.rotate`, and `occ.affineTransform`](https://gmsh.info/doc/texinfo/gmsh.html#index-gmsh_002fmodel_002focc_002faffineTransform)
entries. The first two specify translation and axis-angle rigid rotation;
the third accepts a general row-major affine matrix. Preservation of analytic
types below is directly executed evidence, not a guarantee inferred from the
manual. No external implementation was inspected or copied.

Original probe source and machine-readable results are retained at
`build/cfd-rigid-occ-probe-20261021/probe_rigid_occ.py` and `result.json`.
The cylinder has radius 0.5 mm, length 2 mm and analytic volume `pi/2 mm^3`.
The declared retained-import acceptance is relative volume error at most
`1e-10`, with analytic surface types retained.

| Native operation | Volume (mm^3) | Relative analytic error | Surface types |
| --- | ---: | ---: | --- |
| Untouched cylinder | 1.5707963267948963 | 1.414e-16 | Cylinder, Plane, Plane |
| General affine identity (old defect) | 1.5843293526940503 | 8.615391867e-3 | Three BSpline surfaces |
| Native rigid translation | 1.5707963267948963 | 1.414e-16 | Cylinder, Plane, Plane |
| Native rigid rotation | 1.5707963267948966 | 0 | Cylinder, Plane, Plane |
| Corrected STEP import, identity | 1.5707963267948963 | 1.414e-16 | Cylinder, Plane, Plane |
| Corrected STEP import, rotation and translation | 1.5707963267948963 | 1.414e-16 | Cylinder, Plane, Plane |

The probe verifies installation before loading the optional local-development
Gmsh runtime. SHA-256 bindings recorded in the result:

- Gmsh API: `f4b0935cebde899750293d87a643090e5ea33c9b18d249267f507db68a0e01c3`.
- Gmsh DLL: `a43b4c96644b3c7dc57f79285cd68814ecb3995e582939378a27d238533ed599`.
- Probe: `864664a54d55e07ba91161d5d04b2536646221ae97d248ef90992590735ac01a`.
- Corrected importer: `cae0af7e199aef9395d9dadead01e13198606c011dea2cd86eb4ff6db310dd4d`.
- Original STEP fixture: `2b6501d8fc70b44eca9c1e6c02fac28dfbbe254590531ab56a66972b8ee6481d`.

Four focused placement tests and the 14 tetra-admission tests passed together
(18 tests, 1.580 s). The unchanged existing assembly meshing and encapsulation
suites passed (14 tests, 52.139 s), including real STEP placement, rotated
source-frame coatings, interface ownership and conserved thermal power.
Their first run failed native worker result publication with Windows
`PermissionError` at `os.replace` in the sandbox's AppContainer temporary
directory. The successful rerun changed only the test runner's `tempfile.tempdir`
to `build/cfd-retained-cad-regression-temp-20261021`; no solver gate, fixture or
runtime behavior was relaxed.

This correction does not eliminate curved-boundary linear-tetra approximation
error: CAD mass and summed tetra volume remain distinct recorded quantities.
It does not establish transitive DLL provenance, redistribution permission,
or production qualification of the optional external engine.

No physical measurements, general-CAD completeness or engineering CFD accuracy
are established here. Required knowledgeable human numerical release review is
still open. Existing public contracts, runtime gates and optional-engine
licensing/packaging boundaries were not modified.
