# SPIKE Meshing Engine

The [retained assembly field handoff](ASSEMBLY_FIELD_HANDOFF.md) consumes complete
supplied tetra volumes with occurrence/material/placement traceability. Its
experimental steady thermal kernel executes solid conduction and matched
contacts; EM/SI ports remain metadata until a general field translator exists.
Local refinement is applied before handoff and invalidates prior field results.

The [internal tetra engine](INTERNAL_MESH_ENGINE.md) adds a separate, experimental
path for convex point-cloud generation, dynamic indicator/manual refinement,
scalar refinement transfer and automatic interior quality optimization. It uses
the solver-neutral tetra mesh contract and requires no external mesher. Its
bounded geometry evidence does not qualify general PCB/CAD meshing or promote
the existing DC/PEEC preview representations described below.

The [whole-board focused volume workflow](PCB_FOCUSED_VOLUME_MESHING.md) is a
separate CAD-neutral path for planar stacks, polygon copper, cutouts and plated
via spans. It retains all geometry while applying net/source/manual refinement
boxes and a coarser background. Conforming generation uses the external admitted
Gmsh OCC development runtime, not the internal convex generator. Mesh evidence
does not automatically qualify the electrical previews or a field solve.

## Contract

`spike/mesh/v3` is the renderer- and solver-plugin-neutral mesh contract.
It is generated from `SpiDeR` and `AnalysisSpec.mesh` by
`python.spike_core.meshing.MeshingEngine`.

Supported preview dimensions:

- `surface_2_5d`: quad and clipped polygon conductor cells plus the connected hybrid electrical graph.
- `volume_3d`: extruded copper `hex8`/`prismN` cells and plated via-barrel `hex8_barrel` cells.

Every cell carries:

- Stable ID and source geometry ID.
- Source kind: track, zone, pad, or via.
- Net and physical layer.
- Material.
- Topology.
- Vertices in millimetres.

The result also contains per-net, per-layer, per-topology, and per-material
counts, mesh quality statistics, memory estimates, truncation state, and
generation provenance.

Exact predicate acceleration and real-board benchmarks are recorded in
[mesher optimization and comparison](validation/INTERNAL_MESHER_OPTIMIZATION_20261012.md).
Performance evidence does not change the mesh or solver qualification limits.

Source-filled paths with exactly retraced connectors retain physical cutouts
through validated rings and clipped conductor cells. Connector traversals are
excluded from physical boundary contact. Indexed contact observation preserves
the existing source-evidence qualification and all records. See the
[retained Marble correction](validation/MARBLE_FILLED_ZONE_FIX_20261013.md) and
[filled-path invariants](validation/FILLED_COPPER_PATH_20261013.md) for area
checks, numerical limits and verification.

Renderers must use the declared topology when constructing wire edges. A
`prismN` stores the lower face followed by the upper face; valid wires are the
two face perimeters plus matching vertical edges. Walking all `2N` vertices as
one polygon creates invalid diagonal wires outside the source conductor.

## KiCad filled planes and zero-width cuts

A KiCad `filled_polygon` can encode a hole by walking a connector twice in
opposite directions. This is a weakly simple source path, not a genuinely
self-crossing copper boundary. Rejecting every such path as non-simple omits
valid power/ground planes. Removing the hole or replacing the path with its
convex hull would introduce copper and is not a valid repair.

The corrected hybrid mesher cancels exact reverse connector edges for physical
boundary tests, validates the remaining outer/hole rings, and clips cells to the
resulting copper domain. It retains original coordinates and provenance. Cell
area and graph containment checks prevent filled voids and artificial electrical
shorts across cuts. Genuine self-crossings and over-budget geometry still fail
closed. This support does not imply every CAD polygon or arbitrary nested domain
is admitted; see the [filled-path limits](validation/FILLED_COPPER_PATH_20261013.md).

As checked on 2026-10-16, public `main` lacks this correction; the source tag
`v0.3.11-gamma.1` and the development checkout contain it. The original Gamma
installers have a separately disclosed embedded-frontend packaging fault. A
source-tag fix must not be represented as a verified working installer.

If `SPIKE-BE-MESH-W-0002` occurs on an ordinary KiCad filled plane, record the
application **and worker** versions, source zone ID/layer/net, source-file hash,
and exact issue. Check version support before asking the user to alter valid
copper. Preserve the original board; do not fill holes to silence the warning.
A failing source-specific case still needs a minimal board and diagnostic log.
A Gamma report remains a source-specific open issue even when a small filled-plane
regression passes; the version distinction alone does not explain that report.

The original import-to-solve regression is
[test_kicad_filled_plane_dc.py](../tests/python/test_kicad_filled_plane_dc.py).
It imports an 8 x 6 mm plane with a 4 x 2 mm cutout, checks 40 mm^2 retained
copper area and that every conductive graph segment and returned field face
stays out of the void, then executes the DC adapter. Its `approximate` result
status is retained: execution and geometry preservation are not independent
physical-accuracy qualification.

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_kicad_filled_plane_dc tests.python.test_filled_copper_path tests.python.test_hybrid_filled_path tests.python.test_hybrid_mesh_containment -q
```

## Electrical Use

The current DC and PEEC adapters solve the connected hybrid graph generated by
`hybrid_mesh.py`. That graph includes:

- Routed tracks subdivided by target length.
- Copper-zone finite-volume cells and connectivity.
- SMD and through-hole pad cells.
- Track-to-zone, pad-to-zone, and pad-to-track connectivity.
- Extracted or plated-cylinder via barrels across their actual copper span.

The `surface_2_5d` cells are the visual representation of that electrical
discretization. The `volume_3d` cells are currently used for inspection and
solver-plugin exchange. They are not evidence that a dielectric/air full-wave
solve has run.

## Cross-Layer Terminals

Desktop terminals default to `connected_conductor` scope. A selection carries
the stable source-geometry ID plus the copper layers occupied by the selected
pad, via, track, or zone:

```json
{
  "position_mm": [42.5, 17.25],
  "layer_scope": "connected_conductor",
  "layer_candidates": ["F.Cu", "In1.Cu", "B.Cu"],
  "geometry_anchor": { "id": "via-183", "type": "via" }
}
```

The terminal is attached to one physical mesh node on that geometry. Current
then reaches other layers through extracted via or plated-pad barrel branches.
SPIKE does not apply the same ideal source to every layer, because that would
bypass barrel resistance. Use `layer_scope: "single"` with `layer: "F.Cu"`
only when a fixture intentionally restricts the terminal to one copper layer.

## AnalysisSpec

```json
{
  "mesh": {
    "dimension": "surface_2_5d",
    "target_size_mm": 1.0,
    "zone_cell_mm": 1.0,
    "max_preview_cells": 25000,
    "max_zone_cells": 3000,
    "max_conductors": 50000,
    "via_model": "extracted",
    "via_plating_thickness_mm": 0.025
  }
}
```

Use a sequence of decreasing `target_size_mm` and `zone_cell_mm` values for
mesh-convergence testing. A result must not be promoted from `Approximate` to
`Validated` only because a finer mesh was selected.

### Experimental conforming-copper local refinement

The separate experimental conforming PEEC/DC partition accepts a versioned
`AnalysisSpec.mesh.conforming_local_refinements` control. It refines retained
*interior copper rectangles* in selected layer/net regions, without changing
their copper union or fixed pad/via terminal footprints:

```json
{
  "mesh": {
    "target_size_mm": 0.5,
    "zone_cell_mm": 0.5,
    "conforming_local_refinements": {
      "contract": "spike/conforming-local-refinement/v1",
      "regions": [{
        "layer": "F.Cu", "net": "+1V0",
        "bounds_mm": [10.0, 20.0, 12.0, 21.0],
        "maximum_edge_mm": 0.125
      }]
    }
  }
}
```

There are at most 64 rectangular regions. All coordinates and edge lengths are
in millimetres; the local edge must not exceed the effective base target.
Regions must intersect retained noncontact copper in the selected layer/net.
Malformed, ineffective, or over-budget controls fail the partition rather
than being silently ignored. The control only subdivides existing copper:
it does not repair omitted boundary slivers, annular-via physics, port
calibration, or AC basis support. `conforming_partition` reports per-region
hits and added cells. Repeat the full mesh/physics convergence checks after
changing any local rule; this control is not a validation shortcut.

## CLI

```powershell
python -m python.spike_core.cli mesh-preview request.json
python -m python.spike_core.cli mesh-preview request.json --dimension volume_3d
python -m python.spike_core.cli mesh-preview request.json --target-size-mm 0.5
```

`preflight` uses the same mesh generator and blocks empty or truncated solver
meshes.

## Current Boundary

The following remain required before calling the 3D path a full-wave production
mesher:

- Conformal dielectric and solder-mask volumes.
- Board outline, cutout, and cavity volume discretization.
- Air-box and port meshing.
- Tetrahedral or hexahedral refinement driven by wavelength and field error.
- Curved-geometry order selection.
- Element Jacobian, skew, warpage, and solver-specific quality gates.
- Mesh partitioning and out-of-core generation for workstation-scale boards.
- Convergence benchmarks against analytical fixtures and measured boards.

Solver plugins must declare which mesh contract, dimension, topology, and
quality limits they accept. A plugin must reject incompatible geometry instead
of silently changing the model.
