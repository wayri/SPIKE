# SPIKE FreeCAD ECAD/MCAD Workbench

This directory contains an optional external FreeCAD workbench for controlled
geometry exchange with SPIKE. It does not run PI, SI, thermal, or EMI solvers
inside FreeCAD. Its current responsibility is limited to:

- importing a validated SPIKE primitive geometry exchange JSON file;
- displaying board, copper, envelope, keepout, hole-reference, mechanical,
  air-volume, and reference solids in FreeCAD;
- exporting selected or explicitly tagged FreeCAD solids as mechanical
  envelopes or keepouts for SPIKE;
- opening SPIKE assembly sessions with stable occurrence identities and STEP or
  board-outline solids;
- returning reviewed occurrence labels/placements and pairwise solid clearance
  observations to the existing SPIKE assembly.

The implementation follows the standard external-workbench layout with
`Init.py` and `InitGui.py`. It has no Python package dependencies beyond those
bundled with FreeCAD.

## Install

1. Close FreeCAD.
2. Copy the entire `SPIKEWorkbench` directory into the current user's FreeCAD
   `Mod` directory. Do not copy only its contents.
3. Restart FreeCAD and select **SPIKE ECAD/MCAD** from the workbench selector.

Typical user module locations are:

| Platform | Module directory |
| --- | --- |
| Windows | `%APPDATA%\FreeCAD\Mod\SPIKEWorkbench` |
| Linux | `~/.local/share/FreeCAD/Mod/SPIKEWorkbench` |
| macOS | `~/Library/Application Support/FreeCAD/Mod/SPIKEWorkbench` |

The authoritative location for a particular FreeCAD installation is shown by
running `App.getUserAppDataDir()` in FreeCAD's Python console, then appending
`Mod/SPIKEWorkbench`.

The scaffold targets FreeCAD 0.21 and newer. FreeCAD 1.1.3 has passed the real
headless-kernel smoke test on Windows; each packaged FreeCAD/Python/Qt
combination still requires qualification before release through Addon Manager.

## Commands

### Collaboration sessions and solid clearances (0.2.0)

In SPIKE choose **MCAD assembly > Board instances and harnesses > FreeCAD
collaboration > Export FreeCAD session**. In FreeCAD choose **Open SPIKE
Collaboration Session**, edit occurrence placements, optionally **Measure SPIKE
Solid Clearance** on two selected solids, then **Send Placement Feedback to SPIKE**.
SPIKE's **Review FreeCAD feedback** shows the proposal before applying it.
FCStd save/reopen retains the session. See the
[implemented workflow and geometry limits](../../docs/FREECAD_COLLABORATION.md).

### Export SPIKE Assembly

Select assembly roots or parts and choose **SPIKE > Export SPIKE Assembly…**.
This writes a `.spikeassembly` ZIP with local STEP geometry, occurrence names,
hierarchy and rigid placements. Optional `SPIKEBoardSource` string properties
retain a placed object's KiCad/IPC-2581 electrical source instead of a STEP proxy.
Import the file through SPIKE's **MCAD assembly → Import board / external assembly**.
See [assembly and harness workflows](../../docs/MULTIBOARD_HARNESS_ASSEMBLIES.md).

### Import SPIKE Geometry

Choose **SPIKE > Import SPIKE Geometry...** and select a UTF-8 JSON file using
the `spike/ecad-mcad-geometry/v1` contract. The workbench validates the complete
document before opening a FreeCAD transaction. Valid objects are collected in
a named document group and carry these properties:

- `SPIKEObjectId`: stable exchange identifier;
- `SPIKEContract`: source contract;
- `SPIKESourcePath`: local source file;
- `SPIKERole`: semantic geometry role;
- `SPIKEExport`: whether an unselected object is eligible for export;
- `SPIKEPrimitiveJSON`, `SPIKEPrimitiveSHA256`, and `SPIKEMetadataJSON`: inert
  source records. Primitive JSON larger than 4 KiB is represented by its SHA-256
  digest instead of being copied into a FreeCAD string property.

The sample file at
`SPIKEWorkbench/examples/example-geometry-exchange.json` can be used as a smoke
test. Supported primitives are `box`, `cylinder`, and `polygon_prism`.

### Export Envelopes and Keepouts

Select one or more three-dimensional objects and choose
**SPIKE > Export SPIKE Envelopes/Keepouts...**. If an object does not already
have a `SPIKERole` of `component_envelope` or `keepout`, the command asks for a
role. With no selection, only objects with `SPIKEExport = true` are considered.

The output uses `spike/ecad-mcad-mechanical/v1`. Each solid is exported as a
global, axis-aligned bounding box. The payload records this representation and
an explicit warning in object metadata. Files are validated and written through
an atomic replacement in the selected local directory.

## Contract Rules

The machine-readable schemas are in `SPIKEWorkbench/Resources/schemas`.
Runtime validation does not require the optional `jsonschema` package.

- Contract and `schema_version` must match exactly.
- Units are millimetres.
- Coordinates are right-handed and Z-up.
- Unknown top-level, object, primitive, and visual fields are rejected.
- Duplicate JSON keys, non-finite numbers, empty identifiers, duplicate object
  identifiers, degenerate polygons, zero-size solids, and unsupported roles are
  rejected.
- Input is capped at 50 MiB, 10,000 geometry objects, 100,000 polygon points,
  32 nesting levels, and 250,000 JSON values.

The standalone contract tests do not require FreeCAD:

```powershell
python -m unittest discover -s integrations/freecad/SPIKEWorkbench/tests -v
```

The real kernel smoke is `tests/freecad_kernel_smoke.py`. Run it from a FreeCAD
console or `FreeCADCmd` with this workbench root on `sys.path`. It imports four
solids, verifies positive volume, exports envelope/keepout records, and validates
the resulting mechanical contract. Headless mode intentionally skips GUI-only
color properties when `ViewObject` is absent.

## Security Boundary

Exchange files are data, not programs. The workbench does not use `eval`,
`exec`, dynamic imports from exchange data, macros, subprocesses, shell
commands, network requests, or automatic file-open hooks. It never follows an
instruction embedded in JSON. Primitive exchange uses fixed `Part` constructors.
Collaboration sessions additionally use fixed STEP import, outline extrusion and
solid measurement APIs; they do not open FCStd or macros from exchange payloads.

Imported source paths are retained for traceability and can contain sensitive
local path information. Remove that property before sharing a FreeCAD document
outside the organization.

## Primitive exchange limitations

- Exported envelopes and keepouts are axis-aligned bounding boxes, not exact
  B-Rep, STEP, mesh, or rotated local-coordinate geometry.
- `polygon_prism` supports one simple outer polygon. Holes, arcs, board cutouts,
  and boolean operations are not represented. A `mounting_hole` cylinder is a
  visible reference solid and is not subtracted from a board solid.
- Imported geometry is intentionally not merged, healed, meshed, or modified.
- Simulation material definitions, flex/rigid-flex bends, component STEP models,
  thermal contacts, airflow boundaries, solver meshes, and simulation results
  are outside the primitive exchange contract. Collaboration sessions can use
  physical stackup thickness for a board outline solid and retained part STEP.
- This workbench does not yet call SPIKE, keep a live link, or perform automatic
  synchronization. Exchange is explicit and file-based.
- A successful import means that the exchange contract and primitive creation
  succeeded. It is not validation of manufacturability, clearances, thermal
  behaviour, structural behaviour, PI, SI, or EMI performance.

Exact B-Rep/STEP exchange and bidirectional document linking should use a new
contract version rather than extending version 1 silently.

## Planned assembly and thermal companion

The [extension development plan](../../docs/FREECAD_ASSEMBLY_THERMAL_EXTENSION_PLAN.md)
extends this foundation toward interactive assembly updates, harness round trips,
user-selectable equivalent PCB thermal models, FreeCAD-hosted solver preparation
and execution, and mapped result import into SPIKE. Version 0.2.0 implements
placement sessions and pairwise solid clearances; structural synchronization,
harness route editing and thermal execution remain planned.
