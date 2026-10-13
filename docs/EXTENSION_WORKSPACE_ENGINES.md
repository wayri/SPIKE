# Extension engines in the SPIKE workspace

## EM display controls

EM view controls occupy the reserved viewport toolbar, outside Notifications.
Use **Minimize** to move these controls to an **EM tools** restore button in the
bottom tool shelf. Restoring returns to EM without changing the active study.
Chamber mode reserves the remaining viewport height for the WebGL scene, with
the EM controls retained above it. The chamber is a display choice; board view
and saved analysis results remain available independently.

SPIKE exposes declared extension mesh and solve routes in the normal Mesh, PI,
HF / SI, EM and Thermal setup docks. Open **External engines > Extension
workflows** to jump to a declared route, or select **Extension engine** in the
workspace dock. **Built-in workflow** restores the native setup.

## Mesh and solve

1. Load a board and trust the installed extension in Extensions.
2. Open Mesh and select EMerge tetrahedral meshing or openEMS Cartesian FDTD
   meshing. Configure exported nets, physical stackup, mesh resolution and
   engine-specific inputs. openEMS also exposes boundary and resource limits.
3. Preview the generated case, then Generate mesh. EMerge checks the exact
   generated Python SHA-256 before execution. The openEMS preview shows its
   adapter body; the executed snapshot additionally contains authenticated
   geometry and run context, so those hashes have different meanings.
4. Inspect the returned mesh over the PCB in the main 3D viewport. Full bounded
   topology remains in the result; the display samples cells/grid lines to
   control rendering cost. A completed mesh is unsolved and unvalidated.
5. Choose Configure solve with this engine. Review the solve inputs and run
   the selected engine. Its solver prepares its own case mesh. No conversion
   or cross-engine mesh reuse is implied by this action.

EMerge supports its EMerge/EMCAD geometry choices through its GUI. openEMS uses
explicit selected nets and lumped ports; only the actually excited S-parameter
column is returned. Missing columns remain gaps and cannot export as a complete
Touchstone matrix. Supported NF2FF complex fields, angular cuts and networks
appear in the main EM results manager with their actual frequencies and units.
Missing far-field frequencies produce no field overlay.

EMerge remains a separately installed optional extension engine. Its selected
interpreter must be reachable from the installed application, and packaged
SPIKE must retain the adapter's relative Python module layout. API detection,
executed-fixture evidence, sandbox constraints, and result admission are
separate gates; see [EMerge version support](EMERGE_VERSION_SUPPORT.md).

Unavailable runtimes, untrusted extensions, invalid geometry, failed jobs,
resource limits and invalid result contracts remain blocking conditions.
Changing the loaded board while a job runs prevents its returned payload from
being published against the new board. Runtime detection and mesh admission do
not establish solver validation, convergence or compliance.

## SU2 CFD and CHT

The bundled `spike.su2-suite` adapter exposes two solver routes in **Thermal >
Extension engine**: **CFD: laminar cavity** and **CHT: coupled fluid and solid**.
The SU2 executable is separately installed; see [SU2 runtime setup](SU2_AIRFLOW.md).
Select a route, review its scalar inputs, choose **Preview generated case**,
then **Run selected engine**. Preview shows geometry, physical conditions and
runtime availability. These reference routes work without a loaded board and
do not read or simulate the loaded PCB/STEP assembly.

CFD returns velocity, pressure and centreline plots. CHT solves a fluid cavity
between hot and cold solid slabs, with both thermal interfaces, temperature
maps and heat-balance diagnostics. **Lid speed = 0** runs the conduction case;
**1 m/s** adds laminar circulating flow. Returned fields require convergence
and, for CHT, temperature and heat-balance admission. Failed results show their
diagnostics instead of accepted field plots. Output paths and hashes identify
retained solver evidence. See [CHT method and numerical checks](SU2_CHT.md).

The same fixed-case workflows are available through `scripts/run_cfd.py`
(`--engine su2` or `--engine su2-cht`), worker methods `run_su2_cfd` and
`run_su2_cht`, and the corresponding MCP tools. Native Windows execution does
not require WSL. General assembly CFD/CHT, turbulence and production
qualification remain unsupported by these routes.

## Extension author API

A contribution can declare `workspace_routes` metadata with a unique `id`,
`workspace`, `operation`, `label`, `model_status`, and optional
`setup_contribution_id`, `preview_contribution_id`, `mesh_kind` and
`compatible_solver_ids`. References must name existing contributions in the
same extension. Routes require `design.read` by default. A route declaring
`requires_board: false` may instead use its own reference geometry; that
declaration does not grant board access. Metadata cannot grant a validated
physics status. See `python/spike_core/extension_workflows.py` and
`app/src/ExtensionWorkspaceRoutes.ts` for bounded validation.

Scalar schemas get a generic GUI; structured schemas hand off to the declared
extension setup. The EMerge and openEMS routes embed dedicated forms. Solves
continue through existing worker/extension result admission. Meshes use
`spike/emerge-mesh/v1` or `spike/openems-grid/v1`, with board digest, case and
script provenance, millimetres and the design top-copper coordinate frame.
`extension_mesh_results.py` admits full bounded topology separately from
physics results. Viewport previews are never solver input.

## AC power integrity effects

Open **PI > AC effects** for an explicit uniform-line diagnostic. Supply RLGC,
line length, source/load impedance and frequencies. Optional slab inputs
replace the baseline R with frequency-dependent skin and imposed-field
proximity loss. Graphs show impedance, load/sending voltage gain and phase,
resistance, skin depth and conductor losses. Singular samples stay gaps.
**AC report** creates an offline report with submitted SI-unit parameters,
plots and raw numerical evidence. Project files retain the request/result and
engine setup selections.

This diagnostic is experimental and does not infer nearby conductor fields,
PCB return paths or radiation from geometry. Its Ferranti and resonance
behavior follows a distributed passive line model. See
[AC_POWER_INTEGRITY_EFFECTS.md](AC_POWER_INTEGRITY_EFFECTS.md) for derivation,
independent numerical checks, conditioning and limits. Knowledgeable human
review remains required before numerical code is released.

## Verification

Run `npm run test:extension-workflows`, `npm run test:ac-pi-effects`, the MCP
analysis tests, and Python tests for workspace routes, EMerge/openEMS and AC
power integrity. Real installed-engine mesh evidence is separate from synthetic
viewport field fixtures. A successful mesh or UI fixture is not a radiation
solve or measured-board correlation.

## CalculiX and Gmsh volume workflows

Solver and mesher preferences are independent in each analysis dock and are
retained with the project. Only declared routes appear: CalculiX supplies the
thermal solver; Gmsh supplies Mesh, PI, SI, EM and Thermal geometry routes.
Selecting a mesher does not translate its topology into another solver's case.
The PI/SI/EM Gmsh routes require an explicit solver translator and currently
advertise no solver compatibility.

For retained multiboard thermal studies:

1. Save the `.spike` project, including uniquely identified board occurrences
   and admitted mechanical solids.
2. Select **Gmsh retained assembly volumes** in Thermal's Mesher selector.
   Assign reviewed materials and mesh limits. Generate the complete volume mesh.
3. Review explicit boundaries, heat sources and matched thermal contacts in
   the existing field-study editor. Unassigned exterior faces are adiabatic.
4. Select **CalculiX** in the thermal solver control. Prepare the case, review
   the runtime/deck evidence, then run the solver.
5. Inspect actual occurrence temperatures and the volume field. Save setup
   and results into the project; reopening admits the embedded result offline.
   Changed geometry or problem data makes the saved result stale.

For explicit PCB internals, **Gmsh complete PCB volumes** accepts a typed
normalized model containing layers, copper, plated vias, drill volumes and
materials. **Prepare PCB solids** obtains the current worker-owned design
binding; editing inputs retires the prepared case. No automatic conversion of
visual component models into physical solids is implied.

The adapter code is distributed with SPIKE; the Gmsh and CalculiX runtimes
remain separately installed dependencies. Missing runtimes produce actionable
preflight errors. See [CalculiX thermal](CALCULIX_THERMAL.md),
[Gmsh extension](../extensions/gmsh_suite/README.md), and
[retained thermal meshing](ASSEMBLY_THERMAL_MESHING.md).
