# Mechanical assembly export

Status: engineering preview, source implementation. Existing archived installers
are unchanged. Requires the installed optional FreeCAD runtime; this implementation
was exercised with FreeCAD 1.1.3 and its Open Cascade STEP reader/writer.

Open **Extension Manager → MCAD Collaboration**. Use **Preview mechanical assembly**
to inspect named bodies and omissions, then **Export STEP and collaboration bundle**.
Save buttons use a native file dialog and verify decoded artifact hashes before
writing. Use **Load assembly JSON** to open the
[mixed assembly example](../examples/mcad/named-assembly.spike-mcad.json).

The existing KiCad-native STEP command remains available. The new extension accepts
explicit CAD-neutral mechanical assemblies, and can project board dielectric layers
and harness routing envelopes from the active project. When the project contains
AssemblyIR, the extension projects every board occurrence from the complete retained
`assembly_designs` set. Repeated occurrences can share one retained source design,
but each board and generated layer keeps its own occurrence-qualified ID, label,
parent-relative rigid placement and STEP/FCStd/BREP/manifest record. A missing
retained design fails projection instead of falling back to the active board. It
refuses incomplete automatic projections unless **Allow export with the omissions
listed in the preview** is selected. The omission report stays in the exported bundle.

## Export contents

- `assembly.step`: AP214 named product hierarchy, separate solid bodies and placements.
- `assembly.FCStd`: editable FreeCAD document with named objects, parent assemblies,
  source IDs, custom properties and the material table.
- `SPIKE_<identity digest>.brep`: exact local-coordinate body for each geometric object;
  multi-solid assets remain a compound. Apply the manifest's parent transforms to
  place individual BREP files in the assembly.
- `manifest.json`: object-to-product mapping, parent IDs, transforms, materials,
  source references, arbitrary properties, artifact hashes and measured validation.
- `assembly.spike-mcad.json`: validated assembly input, including embedded STEP assets.

Use the ZIP to retain all these files together. A standalone STEP file does not
carry SPIKE's full electrical or vendor property schema. Custom property/material
retention is not a qualification of material laws for electrical, thermal or
mechanical simulation. Color values are retained in JSON and FreeCAD custom
properties; STEP display-color transfer has not been qualified.

## Assembly schema

Board projection also accepts explicit `parameters.component_models` bindings
through the Python/extension context API. Preview the board first with
`assembly_from_context(context)` and `parameters.allow_partial: true`. Its
`properties.component_occurrences`, `retained_design_models` and
`retained_design_digests` provide the exact ownership and baseline identifiers.
For each model occurrence, supply:

- `occurrence_id` and one of that component's retained `model_id` values;
- `design_digest` from the preview's retained design baseline;
- `model_to_board_mm`: explicit right-handed, row-major 4x4 proper-rigid matrix;
- `geometry`: `type: "step"`, `data_base64` and the STEP byte `sha256`;
- `placement_reference`: a bounded source/review reference;
- optional `material_id`, backed by the context's explicit material table.

Preview again before export. Missing or partial model coverage stays diagnostic;
only complete coverage closes that component occurrence's missing-solid warning.
Bindings for repeated boards are separate. Reimport or regenerate the preview
after source edits; stale digests fail rather than reusing old geometry. Invalid
STEP bytes, foreign ownership, duplicate bindings, scale/shear/reflection and
unknown materials reject the handoff. No asset is fetched or inferred.

The supplied placement is board-local and the body follows the board's assembly
frame. Source KiCad vectors are retained unchanged and remain unapplied. Material
properties can be retained, but every supplied body records material qualification
and solver readiness as false. No new desktop binding editor is provided by this
increment. See [the handoff decision](adr/0078-explicit-component-solid-handoff.md)
and [native solid checks](validation/parity/WF01-S04C1.json).

[Mechanical assembly v1](../schemas/mcad-assembly-v1.schema.json) uses millimetres,
right-handed coordinates, stable string IDs and parent-relative row-major 4×4
rigid transforms. Translation occupies indices 3, 7 and 11. Scale, shear,
reflections, cycles, unknown material references and duplicate IDs are rejected.
Bottom-side parts can use an explicit proper rotation; there is no inferred
model-origin, unit, mounting-side or offset correction.

Objects can be assemblies, boards, dielectric/copper bodies, components, cells,
harness bodies, insulation or mechanical parts. Geometry can be a box, cylinder,
an extrusion with line/three-point circular-arc boundaries and cutouts, a routed
round envelope, or embedded SHA-256-checked STEP bytes. Disconnected extrusion
islands are separate objects. Cutouts must be fully contained and disjoint.
STEP geometry must consist of positive-volume solids; no mesh-to-solid conversion
is implied. Internal labels from an embedded STEP asset are not retained by the
shape reader: supply separate named objects when individual internal cell IDs matter.

Materials have stable IDs, names and arbitrary properties. The export does not
guess how vendor attributes map to material constitutive laws. Component/cell/net
references and duplicate property records can be retained under `properties`.
The schema is a collaboration contract, not an implementation of IDF, IDX, JT,
Parasolid or a proprietary MCAD database.

## Automatic board and harness projection

For KiCad projects the extension reads the embedded source board through SPIKE's
KiCad importer, preserving source Edge.Cuts lines/arcs. Current automatic outline
stitching accepts one unbranched closed loop; supply `board_rings` for multiple
outer/cutout loops or unsupported drawing primitives. ODB++ uses retained exact
profile rings. Bounds alone are never substituted for a board outline.

Physical stackup thickness is required. The projection extrudes dielectric bodies,
using source XY coordinates and stackup order in positive Z, beginning at the top
of the represented stack. Copper/process layers with thickness contribute to the
stack height, but their patterned solids are omitted. Print/paste layers without
thickness are omitted and explicitly reported. Pad/via drill subtraction, copper,
automatic component-model solid placement and flex folding remain unimplemented.
Component occurrence IDs, names, declared placements and retained model references
are preserved in collaboration metadata for every board occurrence, with a separate
missing-solid diagnostic for each occurrence. AssemblyIR parts without supplied solid
geometry are likewise reported; hierarchy containers needed by placed boards retain
their IDs and transforms. Supply explicit named objects or embedded STEP bodies for
physical component and mechanical-part geometry.
This coordinate convention is recorded and must be reconciled with the receiving
system's board datum.

Harness projection requires a route for each wire and an explicit external radius
in `wire_radius_mm`, keyed by wire ID. Named route frames require explicit transforms
in `route_frames`; omitted/`assembly` frame means assembly coordinates. The result
is a union of straight cylinders with spherical internal joins. It is a routing
envelope, not a bend-radius-controlled manufactured cable, twisted pair, shield or
separate conductor/insulation model. Those can be authored as separate explicit
objects. Electrical area is never silently converted into insulated-wire diameter.
Connector bodies need explicit geometry. The original harness document stays in
the assembly properties.

## Command line

Run from the repository root with the normal SPIKE Python environment:

```powershell
.venv/Scripts/python.exe scripts/export_mcad_assembly.py examples/mcad/named-assembly.spike-mcad.json --output build/example-mcad.zip
```

The output must be a new path. `.step` and `.stp` request STEP alone; `.zip` retains
the complete collaboration package. FreeCAD is discovered using the existing
dependency registry. No runtime is downloaded by export.

## Verification and limits

Every export reopens its STEP in a fresh FreeCAD document and verifies named
assembly/object IDs, parent relationships, solid counts, per-object volume and
world-coordinate bounds. Original and reopened volumes must agree within 1e-6
relative or 1e-7 mm³ absolute; bounds within 1e-5 mm. This does not prove CAD-feature
history, topology numbering, visual appearance, vendor-tool compatibility or solver
equivalence. Exact source bodies remain available in BREP and embedded assets.

The adapter bounds the job to 300 seconds, 4 GiB memory, 1 MiB diagnostic streams,
10,000 objects, 200,000 curve/route segments and 64 MiB combined returned artifacts.
The shared adapter terminates its process tree on cancellation. The desktop's
existing Cancel operation stops the worker; source API callers can supply a
cancellation event. Interactive cancellation of the installed desktop has not been
manually qualified for this new workflow.

Tests in `tests/python/test_mcad_export.py` cover transformed nested groups,
same-name/different-ID cells, cutouts, exact arcs, embedded multi-solid STEP assets,
material/property retention, repeated AssemblyIR board occurrences sharing retained
source, independent translations/rotations, occurrence removal, missing geometry,
invalid frames/units, digest checks, limits, cancellation and the isolated extension
process. The optional FreeCAD check compares the complete projected object inventory
across source JSON, manifest, BREP members, FCStd and reimported STEP. Collaboration
session tests require every repeated occurrence ID to survive feedback and reject
occurrence removal. Rust tests cover artifact
encoding, digest and filename validation. Public ECC83 source also produced a
verified partial dielectric export with its omissions retained.

[Recorded validation, 2026-09-06](../benchmarks/mcad-export/validation-2026-09-06.json):
53 Python importer/MCAD regression tests, four packaging tests and 31 native-host
tests passed. TypeScript, architecture and generated-help checks passed. The
source release probe exercised bundled MCAD schema/planning; the isolated source
extension also performed a real FreeCAD export. A new frozen worker or installer
has not been built or installed for this change.

Implementation references: [FreeCAD STEP export API](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Import/App/AppImportPy.cpp)
and [Open Cascade XDE data exchange](https://github.com/Open-Cascade-SAS/OCCT/wiki/xde).
