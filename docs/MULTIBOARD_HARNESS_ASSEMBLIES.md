# Multi-board, harness and external CAD assemblies

Open **MCAD assembly → Board instances and harnesses** in the desktop shell.
After a second board instance is added, the **Link Manager** appears in that
panel. It owns cable harness rows, stacked board connector mates, connector
mappings, rigid/flex links, and their pin maps. Choose **Save boards and links**
to commit the draft to the `.spike` package; normal **Save project** then retains
the assembly graph with the analysis and workspace state.
Save the active board as a `.spike` project first. **Import board / external
assembly** adds a KiCad `.kicad_pcb`, IPC-2581 `.ipc2581`, or `.spikeassembly`
file to that project. Save pending structure edits before importing. Existing
boards, enclosure parts and the active electrical design are retained. Import
checks the opened manifest before committing an atomic package replacement.

Each board occurrence has its own ID and XYZ/rotation placement. Multiple
occurrences can reference one retained electrical design. The existing limits
are 30 boards, 32 copper layers per board, and 100 mechanical parts/groups.
Other board instances currently use bounded envelope proxies in the viewport;
the active board uses detailed geometry. This change does not implement
simultaneous detailed rendering or a coupled multi-board field solver.

For stacked boards, add a **Stacked board connector mate** with two explicit
`board::connector` endpoints and a one-to-one pin map. This is a direct mating
edge, distinct from a cable harness. SPIKE checks that both board instances
exist, that they differ, and that no pin is assigned to both a mate and a
harness. A board's XYZ placement does not create an electrical connection;
the mate record does not infer contact resistance, return continuity, or
connector SI behavior. Enter those models explicitly in the applicable solver
workflow. A mate can be saved and included in a PI, SI, thermal, or EMI plan
without claiming a coupled solve.

For PI, thermal, or EMI analysis in the desktop, select the intended board
instance in the assembly viewport before running a selected-board workflow.
The selected instance must reference the active detailed design. This also
disambiguates repeated occurrences of the same design. A selected proxy for a
different design cannot be solved from the active design view. Analysis scope
and results identify the selected board and list omitted boards and assembly
entities; selection alone never activates electrical or thermal coupling.
SI multi-board jobs bind board identities through their own explicit request.

The `plan_multiboard_analysis` worker accepts PI, SI, thermal, and EMI domains.
`independent_board_batch` retains selected occurrence identities and requires
caller-controlled single-board dispatch. PI/SI use `coupled_harness_network`
and thermal/EMI use `coupled_assembly` to request a coupled plan. Both coupled
modes return a blocked plan until a qualified adapter consumes the corresponding
assembly physics. Plans retain direct connector mates separately from harnesses.
Thermal plans retain contacts and parts; EMI plans retain
electrical bonds and parts. Their presence in a plan is not a solved effect.

## Harness authoring

1. Choose **Discover connectors**. J, P and CN reference prefixes are candidates;
   discovery resolves canonical pin IDs to physical pin numbers and net names.
   Connector positions default to the component origin on board-local Z=0.
2. Review or add **Connector mappings**. Their typed data uses, for example,
   `{"board_id":"board-a","connector_id":"J1","position_mm":[10,20,5],"pins":{"1":"DATA","2":"GND"}}`.
   Explicit positions and pins override discovery. Use the physical cable exit
   point, especially for bottom-side or elevated connectors.
3. Choose a connector pair, or leave both automatic. Automatic pairing accepts
   only nets with exactly two available pin occurrences on different boards.
   Shared grounds, buses and repeated same-net pins produce diagnostics. An
   explicit pair matches unique equal net names; an explicit pin map permits
   reviewed crossovers or different net names.
4. Set AWG, slack and allowance per termination. Optionally provide ordered
   waypoints and solid forbidden-volume boxes, all in assembly millimetres.
5. Generate and review the proposal. Cut length equals routed polyline length
   times `(1 + slack_percent / 100)`, plus twice the termination allowance.
   Each mapped conductor receives that cut length in the CSV wire list.
6. **Add proposal to assembly draft**, then **Save board and harness structure**.
   Existing assigned pins cannot be reused. Changed planner inputs require a
   fresh proposal before applying or exporting it.

The bounded A* router avoids the interiors of up to 24 clearance-inflated
axis-aligned boxes and supports up to 32 waypoints, with a 100000-node search
limit. Routes are rendered as exact polylines, without curve smoothing through
obstacles. Moving an endpoint invalidates the saved route visually; regenerate
it after placement changes. Keepouts are explicit user input, not inferred
from STEP meshes. An enclosure's outer bounding box includes its usable
interior and generally should not be used as one solid keepout.

These are wiring and geometric proposals. Bend radius, connector mating,
wire ratings, physical fit, EMC performance and electrical coupling are not
qualified by the planner. Same net names describe proposed connectivity and
are not proof of compatible voltage domains. Existing analysis admission and
coupled-solver restrictions continue to apply.

## Explicit-pin DC harness review

The **Solve > PI > Harness PI** editor provides a project-owned harness document,
connector/pin tables and text pin maps. See [Harness PI](HARNESS_PI.md) for the
new native lumped DC execution path. It is distinct from board-field coupling:
board placement and a harness circuit alone do not extract board copper losses.

## STEP enclosure pieces and external CAD

For reviewed updates to existing occurrence placements, use the
[FreeCAD collaboration session](FREECAD_COLLABORATION.md). The assembly import
described below is the separate path for adding new occurrences and assets.

Use **Attach part** for individual STEP/STP or self-contained glTF/GLB pieces.
After importing a STEP piece, select it and use **Tessellate STEP for viewport**.
The bounded FreeCAD adapter retains the original STEP alongside its derived
visual GLB. Numeric placement, parent-frame hierarchy, material assignment and
the existing exact-shape extraction tools remain available for imported parts.

The FreeCAD workbench now includes **SPIKE → Export SPIKE Assembly…**. Select
assembly roots or parts, export `.spikeassembly`, and import that file in SPIKE.
Nested App::Part/groups retain their hierarchy and placements. STEP geometry
is separated from occurrence placement; repeated instances remain separately
placeable. Exported shapes have no inferred solver semantics. Bake non-unit
link scales before exporting. The real-kernel regression covers nested rigid
parts; arbitrary assembly-workbench constraints and linked-document variants
are not comprehensively qualified.

To retain electrical board data from FreeCAD, add a string property named
`SPIKEBoardSource` to the corresponding placed PCB object and set it to an
existing `.kicad_pcb` or `.ipc2581` file. The object's local coordinate system
must match the electrical file. Without this property, a PCB-looking STEP
solid is imported as mechanical geometry.

For other CAD programs, export neutral STEP parts plus occurrence placements
to the documented ZIP exchange below, or open a supported neutral assembly
in FreeCAD and use the workbench exporter. Proprietary native CAD files are
not directly parsed. CAD mates, feature history, external references and
vendor-specific constraints do not become editable native SPIKE constraints.

## Portable exchange format

A `.spikeassembly` is a ZIP containing `assembly.json` and the referenced
assets. Example manifest:

```json
{
  "contract": "spike/assembly-exchange/v1",
  "name": "Controller enclosure",
  "source_cad": "External CAD exporter",
  "units": "mm",
  "occurrences": [
    {"id":"housing","kind":"group","name":"Housing"},
    {"id":"base","kind":"part","parent_id":"housing","asset":"assets/base.step"},
    {"id":"controller","kind":"board","parent_id":"housing","asset":"assets/controller.kicad_pcb",
     "transform":[1,0,0,10,0,1,0,20,0,0,1,8,0,0,0,1]}
  ]
}
```

Transforms are row-major proper rigid 4×4 matrices, relative to `parent_id`;
omission means identity. Units apply to placement translations, connector
positions and harness lengths. Geometry files retain their own format units
(glTF uses its normal metre convention); no extra geometry scaling is inferred.
Occurrence IDs must be unique. Reusing an asset deduplicates model storage,
while occurrence identities stay distinct. Groups carry placement but no model.

Board assets can also be canonical DesignIR v2 `.json` files. Part assets are
STEP/STP or self-contained glTF/GLB. Optional `connector_mappings` and `harnesses`
use the AssemblyIR fields, with source occurrence IDs in `data.board_id` and
`board::connector` endpoints. The importer remaps these IDs into the destination.
No host paths are followed. Limits are 256 archive members, 256 MiB per asset,
512 MiB total expanded data, and a 200:1 compression ratio. ZIP_STORED is useful
for highly repetitive STEP geometry. Missing assets, bad parents, cycles,
unsafe paths and identity conflicts fail before the project is replaced.

Implementation: `assembly_exchange.py`, `service_assembly_import.py`,
`harness_authoring.py`, `harness_routing.py`, and the FreeCAD workbench's
`assembly_export.py`. The exporter uses the documented FreeCAD
[TopoShape STEP export](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/TopoShape_API.md)
and [hierarchical placement API](https://freecad.github.io/API/d7/d75/classApp_1_1GeoFeature.html).
