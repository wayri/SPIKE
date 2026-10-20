# Retained assembly volume generation

`python/spike_core/assembly_thermal_meshing.py` connects retained project
geometry to `assembly_field_handoff` without manually authored tetrahedra.
The caller supplies the canonical project payload, reviewed physical
assignments, mesh resource limits, and a manifest-verified artifact reader.
Project freshness and URI permissions remain the caller's responsibility.

`prepare_assembly_thermal_mesh(payload, assignments, mesh_options,
artifact_reader=reader)` returns a ready plan or occurrence-specific blocking
diagnostics. `run_assembly_thermal_mesh` accepts the same arguments plus a new
output directory and optional process time/memory budgets. It returns an
admitted existing `spike/assembly-field-handoff-request/v1` and its handoff,
or explicit blockers. The reader accepts a `package:` URI and returns bytes.
Every source digest is checked; STEP bytes are checked again when staged.

Assignments follow
`schemas/assembly-thermal-mesh-assignments-v1.schema.json`. Board maps use
design identity; part maps use occurrence identity. Materials require explicit
conductivity and provenance; the existing handoff enforces scalar positivity
or symmetric positive-definite conductivity tensors. Mesh options are
`min_size_mm`, `max_size_mm`, `max_cells`, `max_vertices`; cells and vertices
have aggregate limits of 100,000 and may be bounded more tightly by the caller.

## Supported geometry and limits

- Boards require a retained source artifact, straight closed outline and
  cutout rings, and a complete contiguous physical stack with positive layer
  thickness. Each layer requires a reviewed effective material. The explicit
  `layer_homogenized` choice produces real conforming 3D layer tetrahedra but
  homogenizes patterned copper, drills and vias. It is an approximate board
  material representation, not conductor-resolved PCB geometry. Formed flex,
  curved outlines and missing stack data block; bounds never replace outlines.
- Parts require a retained exact STEP model containing one closed solid.
  Gmsh/OCC imports STEP units into millimetres. Multiple-solid compounds,
  unattached sheets and decorative GLB meshes are rejected. Model transforms
  and retained occurrence transforms are applied once in their respective
  frames. Components must already be represented as physical AssemblyIR part
  occurrences; board renderer component meshes are not implicitly included.
- Each body retains complete exterior triangles, material ownership, source
  digest, reference identity and (for boards) stack digest. Duplicate
  occurrences may reuse one generated local mesh but retain distinct nodes,
  face IDs and occurrence transforms in the field handoff. Contacts and
  thermal boundary conditions require a later explicit assignment.
- Meshing uses the existing separately installed, hash-admitted Gmsh 4.15.2
  development runner on Windows CPython 3.11. No engine is bundled or newly
  licensed by this bridge. Process time/memory limits are retained; dependency
  absence produces recovery diagnostics. This remains unqualified for
  production, as described in `THIRD_PARTY_NOTICES.md`.

## Acceptance evidence

### Declared isolated environment repair (13 October 2026, ACC04)

The fixed native worker still runs with `-I -S` and one-process/time/memory Job
limits. It directly adds the selected interpreter's package directories; it
does not process `.pth` files, user site directories or `PYTHONPATH`. A virtual
environment's explicit `include-system-site-packages=true` declaration now
adds that interpreter's base packages after its own packages. It never borrows
an unrelated installation to hide a missing dependency. The desktop bridge's
CPython 3.11 fallback uses the Windows known folder, not inherited
`LOCALAPPDATA`, to select the existing supported installation.

Before repository/mesher imports, the fresh isolated process imports NumPy,
SciPy and Shapely from those declared roots. `environment.json` records the
resolved interpreter, Python version, isolation flags, roots and dependency
versions/origins, or the failing dependency and diagnostic. Native process
records and returned mesh provenance preserve this evidence; extension results
also retain the bridge environment. This is not complete transitive DLL
admission, redistribution approval or installed-release qualification.

Reproduce the original retained STEP/package workflow without a package-path
override, using fresh output paths:

```powershell
build/qualification-py311/Scripts/python.exe scripts/validate_transient_thermal.py --retained-step-only --output "$env:TEMP/spike-acc04/validation.json" --artifacts "$env:TEMP/spike-acc04/artifacts"
build/qualification-py311/Scripts/python.exe -m unittest tests.python.test_gmsh_environment tests.python.test_gmsh_occ_runtime tests.python.test_assembly_thermal_meshing tests.python.test_gmsh_extension -q
```

The unbundled local `acc04-20261013/validation.json` record passed the actual
288-node, five-frame
SPIKE/CalculiX comparison (maximum difference 0.0108044 K) and project save/read
checks. Bound sources were unchanged before/after execution. The original
failed environment evidence in the unbundled local `solver-comprehensive-20261012`
run is
unchanged. The new artifacts retain the exact generated STEP, mesher inputs,
mesh, native logs, environment, thermal histories and portable project.
This rerun isolates the environment repair; it does not close the separate
capacity-rule/continuum or hardware-correlation gates.

`tests/python/test_assembly_thermal_meshing.py` checks source, material, outline,
resource, flex and render-mesh blockers. With the admitted optional runtime it
generates an original 2 x 2 x 1 mm board prism twice at separate placements,
checks 4 mm³ CAD/mesh volume and distinct occurrence ownership, and imports an
original 2 x 3 x 4 mm STEP box with model and assembly placements. The STEP
case checks 24 mm³ volume and metre coordinates after admission. A two-solid
STEP compound must block. These minimal original geometric oracles establish
the bounded bridge behavior; they are not general CAD or thermal qualification.

Source code and fixtures are original SPIKE implementation, using existing
public Gmsh OCC calls. No third-party implementation or CAD model was copied.

## Desktop workflow

Save and reopen the portable SPIKE project. Open the multi-board coupled study editor and expand **Generate 3D thermal volumes from this project**. Read retained geometry, assign a reviewed conductivity and source for every physical layer and mechanical occurrence, choose the mesh size, review the effective-layer approximation, then generate. Invalid or missing solids produce occurrence-specific blockers. No decorative render buffer becomes a thermal solid. Board-internal component models must first be represented as physical assembly parts; they are not automatically promoted.

Use **Assign heat to a meshed body** to select an exact occurrence and enter
reviewed dissipated watts. The worker uses its admitted SI volume to assign
uniform volumetric heating; this is a package-level assumption, not a resolved
die heat distribution. Review the uniform-volume assumption before applying.
Replacing existing sources on that body requires an explicit checkbox; zero
watts removes its sources. Sources on other bodies remain unchanged. Edited
loads clear the active result and require applying the draft before solving.
Nonuniform die sources remain available in the advanced problem definition.

Review matched thermal contact faces before assigning ambient exchange. Assign convection, ambient radiation, or both to remaining external faces using the thermal controls. These are prescribed ambient coefficients and radiation temperatures; the solver does not calculate airflow or enclosure radiosity. Run steady thermal, inspect the actual surface mesh and nodal temperatures, check conservation and mesh refinement, then save with results to the `.spike` project. Setup and retained results reopen without searching for an external result file. Changing geometry or thermal inputs requires a new solve.

The fixed project worker methods are `read_assembly_thermal_mesh_setup` and `run_assembly_thermal_mesh_in_project`. Both require the opened manifest digest. Reads are package-only, SHA verified, and bounded to 64 MiB per source/model. The project mesh output budget is 32 MiB; the downstream field handoff independently retains its 8 MiB control budget. Source files are never overwritten by generation. The optional separately admitted Gmsh runtime must be available; a missing runtime returns a recoverable blocker. This numerical addition requires knowledgeable human review before release.

## Recovery

| Code | Repair |
| --- | --- |
| `THERMAL_PROJECT_STALE` | Reopen the changed `.spike` project before generating. |
| `THERMAL_SOURCE` / `SOURCE_MISSING` | Retain the board source or STEP artifact inside the portable project. |
| `THERMAL_SOURCE_BUDGET` / `THERMAL_MESH_BUDGET` | Reduce artifact/output size or use a coarser volume mesh. |
| `GMSH_RUNTIME` | Use the separately admitted Windows CPython 3.11 Gmsh development runtime; the distributed installer does not acquire it automatically. |
| `BOARD_OUTLINE` / `BOARD_STACK` | Supply a supported closed straight outline and complete positive layer stack. |
| `PART_SOLID` / `CAD_MESH_FAILED` | Supply one valid closed STEP solid per physical part and review the bounded mesher diagnostic. |
| `ASSEMBLY_FIELD_OVERLAP` | Repair intersecting solids or placements; touching thermal interfaces require explicit contacts. |

Worker admission failures use `SPIKE-BE-THERMAL-E-0003` with the detailed repair reason. Unmatched contacts, missing anchors and malformed boundary values are rejected by the existing thermal problem validator.

## Board overlays and component coverage

A saved board thermal grid is an approximate board field. The main viewport
shows saved top and bottom layer grids on the respective physical PCB surfaces.
A uniform plate result has no separately solved bottom field. Internal layer
inspection is an explicit thermal display option; PCB layer separation alone
does not explode the thermal field. Probes retain exact saved temperatures and
physical depths. This grid does not contain package
interior temperatures or a meshed 3D component field.

After **Read retained geometry and layers**, the volume setup reports how many
component occurrences are retained as physical thermal parts, which are
excluded, and how many excluded components have STEP references available for
review. A ready reference still needs the placement/material review and closed
solid check described in [component STEP solids](THERMAL_COMPONENT_SOLIDS.md).
Only the admitted volume solve supplies nodal temperatures for those parts.

## Cooling and assembly model selection

| Physical condition | Required model inputs |
| --- | --- |
| Static air | Reviewed natural-convection coefficient and air temperature on exposed faces; no solved buoyancy field. |
| Forced air | A justified coefficient and air temperature for prescribed cooling, or a separately prepared fluid/solid CHT domain for resolved airflow. Fan speed alone does not establish either. |
| No convection / vacuum | Leave faces adiabatic, or explicitly apply ambient radiation; a positive-power steady study still needs a heat-removal path. |
| Attached heatsink | Retained closed STEP solid, material, reviewed mounting contact and exposed-face boundary conditions. |
| Potting | Explicit nonoverlapping material volumes replacing air, with reviewed contacts; a medium name does not create the geometry. |
| Conformal coating | Resolved material layer and contacts, or a separately admitted thin-layer model; contact resistance alone omits heat capacity and lateral conduction. |

The same occurrence identities and contact rules apply to multiple boards and
board-plus-STEP assemblies. Displayed component geometry is not evidence of
thermal inclusion: check the retained/excluded component inventory and the
actual volume result. Passive solids conduct heat without needing an artificial
power source.

Solid thermal admission now permits up to 100,000 tetrahedra and nodes, subject
to simultaneous memory, sparse-matrix, geometric-audit and serialized-payload
budgets. This is a ceiling, not a guarantee that every 100,000-cell project fits.
The electrical volume solver retains its separate limits. Actual larger solid
and transient reference checks, generated coating/potting geometry, and the
experimental assembly airflow adapter are described in
[assembly capability integration](ASSEMBLY_CAPABILITY_INTEGRATION.md).
