# Whole board tetra meshes with local refinement

SPIKE can prepare a complete normalized planar PCB volume model and mesh it with
fine tetrahedra near selected nets, source objects or manually specified regions,
while requesting a coarser mesh elsewhere. Selection changes sizing, not geometry:
other nets, dielectric layers, reference planes, cutouts and via spans remain.
This is an experimental CAD process path, not automatic qualification of SI, EM
or thermal results.

The PCB compiler, selection policy and admission checks are independently authored
SPIKE code. Conforming volume generation uses the separately installed, hash-admitted
Gmsh OCC runtime. This path is distinct from the dependency-free
[internal tetra engine](INTERNAL_MESH_ENGINE.md), whose generator handles bounded
convex point clouds, not a complete constrained PCB. No vendor implementation is
included in these new modules.

## Supported geometry and controls

| Input | Behavior |
| --- | --- |
| Planar board outline | Simple concave or convex polygon, with explicit non-touching cutouts |
| Stack | Explicit ordered contiguous slabs, each with a background material ID |
| Copper | Polygon traces, pads and zones with explicit holes, net and layer identities |
| Vias | Analytic plated tubes with explicit through, blind or buried z spans; drills remain separate material volumes |
| Net selection | Union of independent source bounding boxes; does not crop other nets |
| Source selection | Refine only declared source IDs and their surrounding halo |
| Manual region | Axis-aligned 3-D box and local target size; can be combined with source/net selection |
| Background | Coarse target with graded transitions; geometric curves and thin features may still require smaller cells |

Copper must lie inside the actual board outline, not merely its bounding rectangle.
Layers cannot overlap or have undeclared gaps. Foreign-net copper contact and drill
intersections are rejected: provide real antipads, not an inferred return path.
Overlapping same-net volumes are fragmented into shared interfaces with material
priority copper over background and drill over copper. Net metadata on a drill
identifies its associated source; air cells are not conducting net membership.

The input is CAD-neutral `spike/pcb-volume-model/v1`, not a KiCad parser object.
Source-format import and conversion are not performed by this compiler. Board
arcs must arrive as normalized contours. Bent rigid-flex, castellations, arbitrary
curved 3-D copper, components/enclosure CAD, terminal or port creation, high-order
elements and distributed generation are not implemented by this path.

## Prepare and run

Start with the original [five-slab example](../examples/pcb_focus_mesh/whole_board.json).
It has a concave outline, board cutout, reference plane with antipads, three nets
and through, blind and buried vias. Dimensions and sizing are in millimetres.

```json
{
  "contract": "spike/pcb-focus-sizing/v1",
  "net_names": ["SIG"],
  "source_ids": [],
  "fine_size_mm": 0.35,
  "coarse_size_mm": 1.5,
  "halo_mm": 0.4,
  "growth_rate": 0.5,
  "regions": []
}
```

For a trace-only request use `net_names: []` and `source_ids: ["sig_trace"]`.
For a local connector area, include a manual region such as
`{"id":"connector-area","bounds_mm":[[5.5,1.5,-0.1],[6.5,2.5,1.7]],"target_size_mm":0.25}`.
Manual regions coexist with selected net/source regions. Unknown selectors fail;
they are not silently ignored. A large plane's bounding box can cover much of the
board: use local source/region selection when only part of it needs refinement.

The worker method `pcb_volume_mesh_capabilities` takes empty parameters and
separately reports preparation support and admitted runtime availability. Send
`prepare_pcb_volume_mesh` with `{"request": <complete request>}`. Its result
contains the `spike/gmsh-occ-mesh/v2` job, focus plan, geometry evidence and SHA-256
bindings. Send that exact `job` to the existing `generate_tetrahedral_mesh` method
with optional `timeout_s` and `memory_limit_mb`. Preparation does not execute a
mesher. No shell, script, executable or dependency-path override is accepted.

Python callers use `prepare_pcb_volume_mesh(request)` from
`python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_mesh`, then `run_occ_case(prepared['job'], new_directory)`
from `python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_runtime`. The development runtime currently needs
Windows CPython 3.11 and its admitted Gmsh 4.15.2 entry artifacts. Probe before
execution; an unavailable runtime is not replaced by a fabricated mesh.
The complete JSON-line service also needs the ordinary SPIKE worker dependencies.
The special EMerge environment used below has enough dependencies for the isolated
mesh examples, but currently lacks `jsonschema` for the full service. Preparation
and JSON-line routing were tested in the main Python 3.12 environment; native
execution was tested separately in Python 3.11. One complete admitted service
environment for both steps remains an integration/packaging requirement.

Run all four actual examples in an installed compatible environment:

```powershell
.\.venv-emerge3\Scripts\python.exe -Werror examples/pcb_focus_mesh/run_example.py --output build/pcb-focus-example
```

The directory must not exist. Outputs include native `mesh.msh`, neutral mesh
JSON, material-interface/exterior faces, prepared jobs, source coverage, quality,
process evidence, source/mesh hashes and comparison evidence. Low quality and
requested-size violations remain visible. Curved CAD is represented by linear
tetrahedra: inspect per-source CAD/mesh volume discrepancies and refine curves
before using them in an accuracy-sensitive calculation.

## Sizing and acceptance

The independently derived requested size at a point is the minimum across boxes
of `min(coarse, target + growth * max(0, distance_inf_to_box - halo))`. The exact
bounding-volume tree prunes boxes using conservative lower bounds; tests compare
it with direct minima. This is a conservative box-distance policy, not exact
distance to a curved conductor or an anisotropic error metric.

The CAD adapter uses fixed numeric Box fields and their minimum. It disables
boundary-size extension and point-size propagation, but retains curvature sizing.
The global minimum is 1e-6 mm, not the requested fine target, so narrow bores and
copper edges are not erased by a lower-size clamp. The transition thickness must
be finite and at most 1e6 mm. Gmsh's realized edge sizes need not equal the requested
box formula; centroid/longest-edge diagnostics are not a proof of target satisfaction.
The [Gmsh 4.15.2 sizing documentation](https://gmsh.info/doc/texinfo/gmsh.html#Specifying-mesh-element-sizes)
describes these field and geometric-size controls.

Admission checks strict keys, finite dimensions, valid polygons, source coverage,
Boolean source-volume conservation, positive tetrahedra, shared opposite-side
face owners and represented exterior/interface triangles. Every CAD fragment
must have actual positive-volume tetrahedra. The retention flag is derived from
mesh ownership, not just pre-mesh CAD ancestry. These local checks are not a
global self-intersection detector.

Prepared controls are limited to 8 MiB; geometry to 10,000 solids and 131,072
expanded polygon points; focus to 4,096 boxes; CAD to 4,096 fragments; output to
100,000 vertices/cells. Work also has contact and assessment comparison budgets.
Timeout and private memory are enforced by the existing separate-process runner.
Windows venv redirectors are bypassed without relaxing the one-process Job limit;
`-I -S` and explicit configured package paths avoid startup `.pth` execution.
There is no filesystem/network sandbox or fully admitted transitive DLL set.
Gmsh is an optional, separately installed runtime.

## Use with SI EM and thermal studies

The returned `spike/solver-mesh/v1` carries material IDs, net/layer/source metadata,
boundary faces and shared interfaces. A compatible field adapter can use those
identities for electrical conductivity, permittivity/permeability or thermal
conductivity, and assign ports, terminals, heat loads and boundary conditions.
Those physical values and conditions are separate inputs, not inferred by meshing.
Convert coordinates to SI at the consuming solver boundary when required.

For SI/EM, refine signals together with relevant return paths, aggressors, ports,
via/antipad transitions, skin-depth and wavelength requirements. For thermal,
include heat sources, copper spreading paths, contacts and steep temperature
gradients. A coarse background must still satisfy the physics being solved.
Use the [internal adaptation API](INTERNAL_MESH_ENGINE.md) on admitted meshes
within its smaller budgets to apply refreshed error indicators or manual edges.
It does not provide PDE error estimators or conservative vector/moving-mesh transfer.

The [verification record](validation/PCB_FOCUSED_VOLUME_MESHING_20261001.md)
contains the executed fixture and numerical checks. These qualify bounded geometry
behavior, not Marble accuracy, general full-board field extraction, SI/EM/thermal
convergence, commercial parity or release readiness. Knowledgeable human numerical
review and solver-specific refinement/correlation remain required.

## Provenance

The new compiler, policy, wrappers, schemas, fixtures and test doubles were
independently authored. Official API documentation supplied field semantics;
no external mesher source, example implementation or mesh was adapted. Gmsh is
an external runtime with its own license, not an independently reimplemented
algorithm. The statement covers this increment, not all historical code.
