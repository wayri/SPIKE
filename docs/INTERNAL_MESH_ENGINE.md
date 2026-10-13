# SPIKE internal tetra mesh engine

SPIKE now has an independently authored internal tetrahedral engine for bounded
convex point-cloud generation, solution-driven local refinement, manual edge
refinement and automatic interior quality optimization. It requires no external
mesher runtime. Its status is experimental: valid geometry is necessary for a
solver, but does not establish field accuracy, mesh convergence or production
PCB geometry support.

For normalized complete planar PCB volumes, use the separate
[focused CAD process path](PCB_FOCUSED_VOLUME_MESHING.md). It preserves layers,
cutouts, copper and via spans while refining selected nets/sources/manual boxes.
It relies on an external admitted Gmsh runtime; it does not expand the internal
convex generator's scope or promote the following adaptation limits.

## Executable operations

| Operation | Inputs and result | Scope |
| --- | --- | --- |
| `generate` | 3-D points, units, material/source ID, boundary label; tetrahedra and complete exterior triangles | Convex hull, one material, 4–128 points |
| `adapt` | Existing conforming mesh, cell indicators, target edge length and/or manual edges | One deterministic, conforming edge-star bisection pass; material/source/boundary ownership preserved |
| `optimize` | Existing conforming mesh, protected vertices, iteration limit | Backtracked interior smoothing; positive cells and nondecreasing worst mean-ratio quality |

Input meshes use `spike/solver-mesh/v1`. Coordinates are explicitly `m` or `mm`;
edge-length targets use the same units. Cell indicators are nonnegative scalar
error estimates keyed by current cell ID. The engine does not fabricate a PDE
error estimator. Bulk marking selects the smallest deterministic prefix covering
the requested fraction of squared indicators. Selected cells contribute their
longest edge. Each edge is split across all incident cells, including cells on
the other side of a material interface, to avoid hanging faces.

Manual `manual_edges` are vertex-index pairs in the input mesh. They can be
combined with automatic marking. `protected_vertices` prevents smoothing of
those vertices; it does not forbid refinement of incident edges. Exterior and
material-interface vertices are fixed during smoothing. Refinement can reduce
shape quality, so the before/after quality remains visible. A target-size request
reports remaining violations after its single pass. Solve again, refresh
indicators and repeat until the application has satisfied its physics and
resource criteria; one completed mesh operation is not an adaptive solve.

Scalar nodal P1 fields use midpoint interpolation on refinement-only passes.
Piecewise-constant cell fields inherit their parent values, preserving their
volume integrals separately in each material. Pass `optimize: false` when
supplying fields. Relocation with fields is rejected because conservative remap
is not implemented. Vector fields, H(curl)/H(div) transfer, history integration
and arbitrary moving boundaries are not covered by these scalar transfers.
Subnormal nodal constants are preserved. Integral/interpolation values whose
rounding would materially destroy the represented quantity are rejected; tiny
values cannot pass conservation merely through an absolute tolerance floor.
Full (`1.0`) bulk marking includes every positive indicator, including values
whose normalized square underflows. Lower fractions report the count of such
underflows in their marking evidence.

## Worker and Python integration

Probe `internal_mesh_capabilities` with empty parameters. Execute
`run_internal_meshing` with exactly one `request` parameter:

```json
{
  "method": "run_internal_meshing",
  "params": {
    "request": {
      "contract": "spike/internal-mesh-request/v1",
      "operation": "generate",
      "parameters": {
        "points": [[0,0,0], [2,0,0], [0.3,1,0], [0.2,0.2,1]],
        "units": "mm",
        "material_id": "dielectric",
        "source_object_id": "domain",
        "boundary_label": "exterior",
        "optimize": true
      }
    }
  }
}
```

The same request goes to
`python.spike_core.internal_meshing_engine.run_internal_meshing(request)`.
The request schema is
[`internal-mesh-request-v1`](../schemas/internal-mesh-request-v1.schema.json).
The result includes the candidate mesh, boundary triangles, quality, request
SHA-256, mesh SHA-256 and complete-candidate SHA-256. Digests use sorted-key,
compact, ASCII-escaped finite JSON. Candidate hashing includes boundaries,
transferred fields and evidence, not just connectivity. Inputs remain unchanged
even when admission fails. Unknown fields and executable/path overrides are
rejected. Requests and results each have an 8 MiB control-data limit.

Generation has 128 input points and 5,000 final cells; adaptation and optimization
have 5,000 cells and 10,000 vertices. Refinement accepts at most 256 distinct
selected edges per pass. Predicate and smoothing work have additional fixed
budgets. This is a bounded reference implementation; native large-mesh
acceleration needs profiling and separate qualification. It does not launch
external jobs. The existing `generate_tetrahedral_mesh` external CAD adapter is
unchanged; internal generation is a separate explicit method.

## Independent derivation and geometry checks

The original incremental Delaunay implementation forms an insertion cavity from
empty-sphere tests and cones its boundary to the inserted point. Orientation is
the signed determinant of three vertex differences. The in-sphere predicate is
the determinant of coordinate differences with squared norms as the fourth
column. Conservative floating filters fall back to exact binary-rational signs.
Cospherical ties use deterministic infinitesimal lifted-height ordering; input
coordinates are never jittered. Power-of-two normalization preserves represented
coordinates, and final volumes must remain positive in the original units.

Output admission checks all input vertices, positive cells, opposite-side face
ownership, supporting convex boundary planes, closed manifold edges and vertex
links, connected cells and empty spheres. A finite enclosing tetrahedron can
fail for ill-conditioned inputs; such cases are rejected with no partial mesh.
Generation evidence describes the pre-optimization mesh. Interior smoothing
does not preserve a Delaunay guarantee, so that guarantee is not asserted for a
smoothed result.

Mean-ratio quality is
`12 * (det(J)/2)^(2/3) / sum(edge_length_squared)`, equal to one for an
equilateral tetrahedron. Candidate smoothing must improve the minimum incident
quality without inversion. Fixed boundaries and volume checks preserve the
domain in the tested conforming meshes. Existing imported meshes must already
be nonoverlapping and conforming: local topology validation is not a global
intersection detector or CAD repair operation.

## Research and provenance

This code, fixtures, determinant derivations and exact-volume oracles are
independently authored. No third-party mesher implementation, comments, meshes
or training data were examined or adapted for this increment. SciPy is used
only as an independently installed black-box verification oracle; it is not a
runtime dependency of the engine. The clean-room statement covers this
increment, not an unverifiable guarantee about all historical code.

The ICML 2025 [G-Adaptivity paper](https://arxiv.org/abs/2407.04516v3) studies
learned mesh relocation driven by FE solution error. It is a candidate for a
future measured comparison; no GNN, training corpus or paper speedup is included
or claimed here. The [validity discussion in Fast Tetrahedral Meshing in the
Wild](https://doi.org/10.1145/3386569.3392385) motivates checking floating-point
validity throughout optimization. SPIKE does not implement that paper's
triangle-soup insertion method or claim its robustness/performance envelope.

## Examples and verification

```powershell
.\.venv\Scripts\python.exe examples/internal_meshing/run_examples.py --output build/internal-mesh-example
.\.venv\Scripts\python.exe -W error -m unittest tests.python.test_internal_tetra_generation tests.python.test_dynamic_tetra_adaptation tests.python.test_internal_meshing_engine tests.python.test_tetra_mesh_refinement tests.python.test_tetra_mesh_optimization -v
python scripts/check_architecture.py
```

The example creates new output directories without overwriting prior artifacts.
It runs non-cuboidal and cospherical generation, automatic quality optimization,
manual refinement with scalar field transfer, indicator marking, edge sizing
and protected-vertex optimization. It records one warm-up and five measured
corpus runs, candidate artifacts, hashes and environment information.
Independent tests compare exact rational cell/hull volumes and generic-cloud
connectivity against SciPy Delaunay. Field-transfer tests use analytical affine
fields and per-material volume integrals. Recomputed analytical quadratic
interpolation indicators test four successive refinements and decreasing exact
L2 interpolation error; this is not a FEM PDE convergence claim. See
[qualification evidence](validation/INTERNAL_MESH_ENGINE_20260930.md).

## Remaining production work

The [October 12 optimization and comparison](validation/INTERNAL_MESHER_OPTIMIZATION_20261012.md)
records predicate allocation changes, unchanged exact certification, original
before/after fixtures and black-box Gmsh/SciPy benchmarking. These performance
measurements do not change the bounded experimental scope above.

The [second allocation pass](validation/MESHER_ALLOCATION_PASS2_20261012.md)
records further exact-output speed gains and the separate retained Marble
completeness diagnostic.

Constrained nonconvex CAD, holes/antipads/vias, conforming multi-material
generation, terminal/port surface recovery, CAD projection, sliver topology
optimization, coarsening, anisotropic metric refinement, boundary layers,
high-order cells, conservative moving-mesh remap and distributed/native
large-mesh execution remain open. Their completion requires geometry and field
convergence corpora. Knowledgeable human numerical review is required before
release. No existing SI/PI/EMI solver is automatically promoted by this engine.
