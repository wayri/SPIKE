<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bounded centroid tetra subdivision and initial-field restriction

## Claim and ownership

`python/spike_core/propulsion_pod_cfd_refinement.py` constructs an experimental
internal/bulk refinement candidate from explicit existing zero-based parent
cell IDs. It adds one interior centroid and three net tetrahedra per marker.
Original vertices, all original triangular facets, patch labels, patch order,
facet vertex order and the outer domain remain unchanged. It performs no
smoothing, surface remeshing, source inference, pressure stabilization or CFD.
Raw numerical meshes contain no CAD identifiers: preserve the separate CAD
ownership envelope by source hash and the emitted parent/child mapping.

The [independently authored review](PROPULSION_POD_CFD_REFINEMENT_REVIEW_20261024.md)
was written by the integrating reviewer before inspecting implementation.
This record follows [method evidence policy](../NUMERICAL_METHOD_EVIDENCE.md).
Knowledgeable human numerical review remains required before release.

## Primary sources actually reviewed on 24 October 2026

| Source and exact version | Reviewed extent and applicability | Rights/status |
| --- | --- | --- |
| [CGAL 6.2.1 Triangulation_3 reference](https://doc.cgal.org/6.2.1/Triangulation_3/classCGAL_1_1Triangulation__3.html), `insert_in_cell` | The current official 6.2.1 manual's member documentation specifies four-cell insertion for a point strictly inside a three-dimensional cell. Read member documentation only, not implementation. | Topological method foundation only; no CGAL dependency, source or assets copied. |
| [DefElement Lagrange](https://defelement.org/elements/lagrange.html) and [degree-two tetrahedron definition](https://defelement.org/elements/examples/tetrahedron-lagrange-equispaced-2.html), pages as accessed | Read polynomial space, nodal functionals, continuity and all ten basis expressions. These specify continuous total-degree polynomials with vertex/edge nodal evaluations. | Mathematical FEM foundation; no external implementation read or copied. |
| J. R. Shewchuk, [What Is a Good Linear Finite Element?](https://people.eecs.berkeley.edu/~jrs/papers/elemj.pdf), 31 December 2002 preprint | Read abstract and Section 3 opening, printed page 30. Geometry affects conditioning and interpolation differently. This motivates retaining separate quality and solution checks; no estimator from this paper is implemented. | Cautionary analysis reference, not a new qualification claim or imported algorithm. |

The construction, formulas, code, test data and prose were independently
authored. External implementations, example meshes and test fixtures were not
used. Existing SPIKE ownership and Apache-2.0 licensing apply.

## Independently derived geometry

Let a positive tetrahedron have affine vertices `v0,...,v3`, barycentric
coordinates `lambda_i`, Jacobian `J=[v1-v0,v2-v0,v3-v0]` and volume
`V=det(J)/6 > 0`. Positions have units m and volume has units m^3. Define the
centroid `g=sum(v_i)/4`. Child `i` replaces vertex `i` by `g`, leaving the
other three vertices in their original local slots. Determinant multilinearity
gives `V_i=lambda_i(g)*V=V/4`; orientation therefore stays positive without a
conditional vertex swap. No input orientation is repaired.

More generally the partition holds for any strictly interior rounded point
`g` with barycentric weights `w_i>0`, `sum(w_i)=1`. Given any parent point
with barycentric coordinates `lambda`, choose an index minimizing
`lambda_i/w_i`. Subtract that nonnegative multiple of `w`; the remaining
coefficients are nonnegative and the chosen coefficient is zero. Thus the
point lies in the cone from `g` to the opposite face. A unique minimizer
places it in one child interior; tied minima lie on shared child faces.
The children cover the parent with disjoint interiors and volumes `w_i*V`.

Every old face occurs exactly once among the children, while every new
internal face occurs twice with opposite orientation. The neighbouring cell
still meets the same original triangle. There are no hanging face nodes,
even if the neighbour is not refined. Original faces are identified by their
original vertex triples; derived validator face-array offsets can change.
Unselected cell indices survive. Child0 occupies its old parent index and
children1..3 are appended, with explicit provenance for every output cell.

Floating point is not the exact centroid proof. The implementation computes
`v0 + mean(v_i-v0)` to reduce translation cancellation, solves for its actual
barycentric coordinates and rejects nonpositive weights. Every source and
child Jacobian must have positive finite determinant, positive representable
volume and condition number at most the existing `1e6` limit. Each four-child
volume sum and each quarter-volume ratio must agree within `1e-10` relative
to the parent. These checks do not replace global manifold or SAT checks.
Repeated centroid subdivision can worsen aspect ratios and conditioning;
no shape-quality improvement or asymptotic diameter reduction is promised.

## Initial-field restriction

The optional input has the retained field keys `P2_nodes_m`, `P2_velocity_m_s`,
`P1_nodes_m`, `P1_pressure_pa`, `tetrahedra`, `cell_P2_nodes`. Coordinates and
connectivity must exactly equal the source mesh's existing Taylor-Hood
first-encounter edge layout. Nonfinite fields, wrong dimensions and stale
layouts fail. Coordinates and velocity/pressure require real integer/unsigned/
float dtypes before conversion; complex, boolean and object arrays fail without
coercion. Pressure is Pa and velocity is m/s in the unchanged frame.

For source parent barycentric coordinates, the ten P2 nodal functions are
`N_i=lambda_i*(2*lambda_i-1)` and `N_ij=4*lambda_i*lambda_j` for `i<j`.
These are cardinal at the four vertices and six edge midpoints and span
all ten total-degree-two Cartesian monomials. Thus evaluating the old
polynomial at new child vertices and edge midpoints exactly represents its
restriction in exact arithmetic. P1 pressure uses `p=sum(lambda_i*p_i)`.
Original geometric-vertex DOFs are copied. Old edge DOFs are looked up by
canonical original vertex pair and mapped to new layout indices; adding
centroids changes the P2 index offsets, so copying the old array prefix is
incorrect. New nodes lie strictly within one known parent; no nearest-node
search, mesh-location heuristic or extrapolation is used.

The same continuous function has the same exact volume pressure integral
and boundary trace. Floating-point evaluation introduces roundoff; the
Cartesian polynomial oracle tests it independently. No pressure gauge is
invented or projected. The output status is always `unsolved_initial_guess`.
New test functions, new quadrature points and mesh-dependent SUPG tau mean
the new nonlinear discrete residual can be nonzero even for exactly restricted
fields. No old convergence or energy/load acceptance is transferred.

## API, resources and workflow

Call `refine_centroid_tetrahedra(raw_mesh, [parent_ids], initial_fields=fields)`.
`initial_fields` is optional. The return contains separate `mesh`, `provenance`
and `initial_guess` entries; the raw `mesh` retains exactly the existing
`spike/cfd-tetra-mesh/v1` keys, with no appended provenance fields.

The default `validate=True` runs unchanged full source and destination
`admit_cfd_tetra_mesh` checks, including topology, boundary manifold,
opposite-side facets and the full positive-volume intersection screening
with face axes, cross-edge fallback and exact rational predicates where
needed. Nonshared zero-measure contacts remain unqualified by that owner.
An explicit `validate=False` returns a `globally_unadmitted_candidate` with
local checks only; it cannot authorize a flow run. Cancellation is passed
through both full admissions and checked while constructing children.

The maximum is 40,000 output cells, with at most `4*max_cells` vertices.
The bounded JSON snapshot has the existing 32 MiB/500,000-node cap. Marker
IDs must be distinct built-in integers in range; empty selections and bools
are rejected. Geometry/transfer storage grows linearly with the bounded
mesh, with no dense PDE matrix or factorization. Full geometry SAT retains
its existing resource bounds. The first actual diagnostic enforced 240 seconds
wall time and 300 MiB extra process RSS via cancellation checks. After its
timeout, the destination-only diagnostic used an explicitly authorized
420-second bound with the same memory limit and unchanged validation gates.

Before any refined CFD run, the owner must rerun source/geometry binding,
actual constant-pressure kernel checks, nonlinear momentum/continuity,
energy and load acceptance. A geometry pass alone establishes none of these.
The 13-marker case adds only 39 cells to 10,602 and is not a uniform-grid
refinement family, a GCI sequence, a certified error bound or a convergence
proof. Markers selected by absolute SUPG contribution are internal/bulk
support markers, not automatically near-wall markers. Tangential blade
triangles are unchanged; wall-normal and tangential resolution remain
separate convergence questions.

## Executed evidence

`python -m unittest tests.python.test_propulsion_pod_cfd_refinement -v` passed
six tests. Independent unit-volume/sheared-box checks establish the
four-child volume partition, unchanged original faces and boundary patches,
conformity with unrefined neighbours, unchanged original input, deterministic
markers and preserved unselected indices. A global Cartesian quadratic
velocity/affine pressure oracle agrees to `2e-14` absolute/relative tolerance;
an independently fitted arbitrary parent polynomial agrees at interior child
points to `2e-9`. Invalid markers, budgets, inverted/degenerate/nonfinite
geometry, invalid connectivity, missing boundary faces and stale field
layouts are rejected. Complex velocity, boolean pressure, object coordinates
and complex coordinates fail before coercion. Cancellation and unadmitted
candidate labels are tested.

`python scripts/check_architecture.py` passed. The integration owner remains
responsible for broader required repository checks and numerical release review.

The actual ENOLA source is
`output/promo-propulsion-pod-20261023/inertial_cfd/coarse_005_hubcleaned/fluid_hxt_bulk90/casalino-fluid-raw-si.npz`,
SHA-256 `c95c93da935b1c8b9114ca79be3a9f1996b9acdbc5addd7e99166a270630c6ef`.
The stage-02 initial field source has SHA-256
`cf7b9298e0465e85f1fb659169810efa7ddc927a9a0c3b91a5ad963c0c72e0cb`.
The localized markers are `[617,6499,10566,1882,8113,3832,2095,5131,2271,4833,10059,4824,4616]`.
The bounded diagnostic and its receipt live in
`output/promo-propulsion-pod-20261023/inertial_cfd/centroid13-refinement-20261024/`.
Executed actual results are deliberately separate receipts:

- `refinement-receipt.json`: strict source-plus-destination invocation cancelled
  at 240.075 seconds; sampled extra RSS 224.60 MiB. The interrupted phase was
  not captured, so this receipt does not claim either admission completed.
- `candidate-construction-receipt.json`: local construction and actual P2/P1
  transfer took 0.511 seconds. Cells increased 10,602 to 10,641; pressure nodes
  3,539 to 3,552; velocity nodes 20,931 to 20,996. Maximum parent-volume sum
  defect was `3.33e-16`; maximum cell condition stayed `9325.452323355905`.
  This receipt's original globally-unadmitted status is preserved.
- `independent-identity-audit.json`: all original vertices, exterior triangles
  and internal faces survive. Every old vertex/edge velocity and old vertex
  pressure value is copied exactly to its correctly mapped new node.
- `destination-admission-receipt.json`: unchanged full validator admitted the
  exact new candidate in 109.932 seconds wall, 108.125 seconds CPU and 222.02
  MiB sampled extra RSS. SAT screened 946,100 candidate pairs with 7,594,400
  axis tests and 722,575 exact predicates. Input and source hashes match before
  and after. This claims NEW geometry admission only, without old-source
  cached admission or completion of the helper's strict double call.

The raw candidate JSON file SHA-256 is
`7ec64acf809741989d87afc3cac7a93d04ca91afee000b9d577044125f26e5aa`;
the raw SI NPZ is
`02d61d7da0a38472c1b7556edcced232efe4c8b61a071024e4bd2043fbf407a8`;
the explicitly unsolved initial-guess NPZ is
`1345f848f55cd55c175d5466ca5e6d6d7f730360af9d99b734fbff925fe04b0c`.
The historic candidate filenames retain `globally-unadmitted` wording;
the later separate destination receipt records the actual full check.

The source used for the construction and large geometry checks is retained
under `source_snapshot/`, helper SHA-256
`b5ff47e5cdd86c12ef3ab7348d8501e088fb68e6ab9f0779ba7b2119d3f277ca`.
Independent review found silent complex/bool/object coercion at the optional
field boundary. The hardened helper SHA-256 is
`51ec9615f00814482a758ca9a754ccdd13024d31b8b0b6f5c3a4f9de88ee8919`.
`dtype-hardening-equivalence-receipt.json` binds six passing tests and confirms
the actual float-input mesh and every transferred array are exactly unchanged;
the expensive full geometry check was not repeated. No CFD operator assembly,
factorization, pressure-kernel solve, nonlinear solve or load acceptance ran.

## Later boundary-edge-star extension (24 October 2026)

The later `refine_boundary_edge_stars` entry point is distinct from the original
centroid behavior. It requires explicit complete incident-cell witnesses for
each boundary edge, rejects cell-overlapping stars and patch seams, and admits
only midpoints exactly representable as the rational average of the input
binary64 coordinates. Midpoints coincident with an existing or another proposed
vertex are rejected before result construction. The original source vertices
and exact polyhedral boundary support survive; split triangle IDs do not.
Parent/child cell and patch-face ancestry is recorded. Every operation preserves
the caller input. The strict default still performs full source and destination
geometry admission; an explicit locally checked candidate remains unadmitted.

Independent derivation and primary-reference/version details are in
`output/promo-propulsion-pod-20261023/inertial_cfd/nearwall-ladder-design-20261024/DESIGN.md`;
the root-authored preimplementation proof is in
`PROPULSION_POD_CFD_REFINEMENT_REVIEW_20261024.md`. In summary, splitting the whole
edge star partitions every incident parent at the common barycentric plane;
shared faces obtain matching cuts and boundary subtriangles preserve oriented
support. Volume and boundary area both halve, so wall-normal altitude is
unchanged by edge splitting. Subsequent centroid subdivision of a wall parent
reduces its face altitude to approximately one quarter. Nested P2/P1 fields can
be restricted, with surviving old edge DOFs mapped by vertex pairs and new DOFs
evaluated in recorded containing parents. Transferred fields remain unsolved.

References actually read for this extension are CGAL 6.1.1
[Triangulation_3 insert_in_edge/insert_in_cell](https://doc.cgal.org/6.1.1/Triangulation_3/classCGAL_1_1Triangulation__3.html)
and Gmsh 4.15.2 [manual](https://gmsh.info/doc/texinfo/) chapter 8
Distance/BoundaryLayer and section 6.6 extrudeBoundaryLayer. They guide method
selection; no external implementation or tutorial code was used as source.

Twelve focused tests passed, including six new edge-star tests of complete-star
conformity, oriented area/volume partition, unchanged neighbours, multi-star
ancestry/order, Cartesian and arbitrary continuous piecewise P2 restriction,
P1 pressure integral, wall altitude before/after centroid refinement, and
partial-star/overlap/seam/nonrepresentable/coincident-point/budget/invalid-geometry/
nonreal-field rejection. Small fixtures execute the unchanged full geometry
validator. The architecture guard passed.

The actual coarse mesh has 5,358 rotor faces and 4,979 wall-adjacent tetrahedra;
median/p90 wall-face altitude is 14.632/47.279 mm. Only 1,031 of 8,037 boundary
edges have exactly representable midpoints. A whole-surface edge split exceeds
the existing 5,000-pressure-node gate before flow, so no global wall-convergence
claim is possible from the small proposed patch.

An explicitly **globally unadmitted, unsolved** arithmetic-only candidate was
constructed under `nearwall16-refinement-20261024/` in 2.313 s. Sixteen edge stars
cover 32 original wall parents and 1.702% of rotor area. Tangential-only counts
are 10,634 cells/3,555 P1 vertices. Paired centroid refinement gives 10,826 cells,
3,619 P1 and 21,331 P2 nodes; maximum condition remains 9325.4523. Maximum local
volume-sum defects are 4.996e-15 and 3.997e-15. Sixty-four split rotor faces have
measured altitude ratios 0.25 to floating precision; stationary triangles and
all original coordinates are unchanged. Actual v12 fields were transferred as
unsolved guesses. The helper, input and output hashes and source snapshot are
retained in `candidate-receipt.json`. Full actual geometry, pressure kernel,
PDE and load qualification were deliberately not run while the live flow case
was active and available memory was limited. No uniform-grid/GCI evidence is
claimed, and unrefined blade support remains explicitly reported.
