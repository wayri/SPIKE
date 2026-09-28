# SPIKE Thermal Workflow

For a step-by-step desktop and CLI tutorial with an open-source Marble board,
saved temperature plots, and a layered copper example, see the
[illustrated thermal user guide](THERMAL_USER_GUIDE.md).

SPIKE's Thermal tab has a built-in component thermal path, a separate spatial
board-plate path, and an optional CFD path. The component path runs steady-state
or transient lumped RC calculations in the local worker without OpenFOAM. It
reports approximate temperatures keyed by part reference. See
[Component thermal calculations](COMPONENT_THERMAL.md) for equations, limits,
worker contract, and numerical checks.

### Air environment scenarios

The Thermal setup provides three boundary presets for comparing a board in
still room air, in a sealed box, and under forced air. Each preset states its
assumptions and converts prescribed effective heat-transfer coefficients into
top and bottom board-to-ambient resistances using `R = 1/(h A)`. The forced-air
screen also reports the ideal bulk-air rise from `dT = P/(rho cp Q)`, using
constant standard-air properties (`rho = 1.204 kg/m3`, `cp = 1005 J/(kg K)`).

The supplied coefficients are engineering starting points: 8/5 W/(m2 K) for
the top/bottom faces in open still air, 3/2 W/(m2 K) inside a closed box, and
35/20 W/(m2 K) under nominal 0.012 m3/s forced flow. Applying a preset writes
the resulting explicit resistance, enclosure, convection, fan-flow, and
assumption inputs into the scenario. Users can edit them before running the
object or board solver. The comparison remains `approximate`; it does not solve
enclosure walls, fan pressure curves, flow bypass, recirculation, local air
velocity, component hot spots, or conjugate heat transfer. The optional
OpenFOAM path retains its separate experimental capability gates.

For a reproducible source-board run with assigned Q1/Q2/Q3 losses, thermal
paths, saved JSON, and a board-location visualization, see the
[eBrake1 object thermal example](validation/EBRAKE1_OBJECT_THERMAL_20260928.md).
Its plotted footprint colors are solved object temperatures, not a continuous
board temperature field.

The separate [board-plate gradient example](validation/EBRAKE1_BOARD_THERMAL_20260928.md)
uses imported board bounds and component locations, explicit effective sheet
conductivity/thickness, fixed board contact areas, prescribed convection, and
per-part junction-to-case and case-to-board resistances. It returns a solved
steady temperature grid and board-contact/case/junction temperatures. It is an
experimental rectangular uniform-sheet approximation, not a conforming
copper/FR-4 PCB thermal solve. The Tauri Thermal setup can display the
returned grid and temperatures when the local worker completes the request.

The [layered eBrake1 example](validation/EBRAKE1_LAYERED_THERMAL_20260928.md)
adds imported copper coverage by layer, physical stackup thicknesses, via and
plated-pad barrel links, and pad-land case coupling. Its optional fuzzy mode
blurs copper coverage independently on each layer. This is an approximate
structured volume model of the board, not a tetrahedral package/board solve;
its assumed materials and cooling are unvalidated.
The optional [layered board transient](validation/EBRAKE1_LAYERED_TRANSIENT_20260928.md)
uses per-cell copper/dielectric heat capacity and implicit steps. The desktop
plays saved layer-temperature frames with a fixed color scale and reports a
peak curve, stored energy, and numerical balance. It assumes an initially
ambient board and constant power. Component case/junction values in this
board result remain steady resistance-chain estimates.
Adjacent physical rows are coupled by vertical conduction. The optional
**Virtual board heatsink** is an explicit top/bottom rectangular contact with
a shared isothermal node, interface K/W, and sink-to-ambient K/W. It returns
sink temperature and heat flow and is available only in layered board mode.
The [illustrated example](THERMAL_USER_GUIDE.md#virtual-heatsink-comparison-on-the-same-fixture)
compares the same board with and without it. Assembly/CFD heatsink shapes do
not automatically affect this board solve; no fin/airflow field is resolved.

### Board gradient in the desktop

1. Import a KiCad board and open **Thermal → Thermal setup** in the native
   desktop. The browser preview cannot execute the local worker. For layered
   runs, the worker reimports the retained KiCad source through SPIKE's full
   importer so custom pads and source-filled zones retain their geometry;
   display-only board polygons are not treated as proved copper.
2. In **Board thermal**, select **Uniform 2D plate** or **Layered 3D stack**.
   Layered mode needs a complete ordered physical stackup and defaults only
   when one is imported. Enter board thickness and grid step in mm,
   top/bottom convection in W/(m2 K), and ambient in C. Plate mode needs an
   effective in-plane conductivity; layered mode needs separate copper and
   dielectric conductivities and optional via plating thickness.
3. In layered mode, toggle copper, tracks, pads, zones and vias independently.
   Enter 0 mm fuzzy sigma for unsmoothed sampled copper, or a positive sigma
   to blur layer coverage; changing grid step controls the number of cells.
   Select board component references. For each, enter dissipation W,
   junction-to-case K/W, and case-to-board K/W. Choose imported pad lands or
   an explicit square contact width. The UI warns when a selected pad is
   narrower than the requested grid step.
4. For layered transient, enable **Solve transient board field** and enter
   duration, step, saved-frame stride, and volumetric heat capacities. Choose
   **Run board thermal**. Review each layer's temperature grid and
   optional copper coverage overlay, component markers, board-contact/case/
   junction table, per-pad heat paths, `approximate` status, and diagnostics.
   The display smoothing switch blends only plotted colors; hovering retains
   the original cell temperature. In a transient run, use the time slider or
   playback to see the solved frame and the peak-temperature history. Changing
   an input makes the old plot stale until rerun.
5. Save the project to retain setup and returned result. Compare at least
   several grid steps with identical physical contact dimensions and inputs
   before interpreting a hotspot. The eBrake1 refinement record remains
   incomplete, so it is exploratory evidence only.

The uniform board rectangle and prescribed convection are explicit model
approximations. A case/junction resistance chain adds `P*R` to the contact-
weighted board temperature. It does not resolve a case field or a device's
internal junction geometry.

In the GUI, sync board parts or import a BOM CSV/TSV. Match reference,
dissipation W, top resistance K/W, and bottom resistance K/W columns in the
preview before applying. For ODB++ imports, named component properties with
those same quantities can be read directly. Unmatched references, duplicate
assignments, invalid units, and missing values are flagged; no property is
inferred from package geometry. Enter positive heat capacity J/K for each
selected part in transient mode, then choose **Run steady state** or
**Run transient**. The board-level fallback is used when no powered part is
selected. Review the reference-linked temperature table and transient samples
inside the Thermal setup panel.
The component transient overlay maps actual solved lumped part-node samples
onto board locations, with per-part peak time, time to 90% of steady rise,
and final gap. It is a part map, not a continuous board field.

**Object and surface heat transfer** adds a boundary to any enabled part,
board, heatsink, enclosure, or mechanical object. Choose the whole object, an
X/Y/Z face, or enter a named CAD surface with its measured exposed area.
Conduction uses an explicit K/W resistance to the ambient
sink or another included object. Convection uses an exposed area in mm² and a
coefficient in W/m²K; radiation uses exposed area, emissivity, and a fixed
surroundings temperature. Fluid/sink temperatures can override the scenario
ambient. The GUI suggests an area from object dimensions, but the user must
review the actually exposed area. Each object remains one lumped temperature
node; a face label does not solve its spatial gradient. Top/bottom ambient
paths and added boundaries conduct heat in parallel, so avoid entering the
same physical path twice. Transient runs require heat capacity for every
included object. Completed runs list steady boundary heat flows, positive
outward from each object.

In transient mode, set duration and time step in **Component transient
controls**. The local RC solve needs no OpenFOAM installation. The time step
also controls the returned sample interval; refine it to assess time accuracy.
Saved setups retain the board fallback power and heat capacity. BOM and ODB++
power cells may specify W or mW explicitly; a cell unit takes precedence over
the column/property unit. Unterminated quoted BOM records are rejected with a
parse message.
Syncing board parts preserves entered values and existing references, then fills
available table rows up to 256. For larger boards, import a BOM for the desired
references or remove unused rows before syncing again.

Top and bottom resistances each represent a complete path from the modeled
component node to ambient. A datasheet junction-to-case resistance alone does
not supply the board/contact/convection portions. The built-in result remains
approximate and requires knowledgeable review before release. Material labels,
CAD faces, fans and thermal links do not automatically create a conduction,
convection or radiation path for this lumped run. The built-in radiation term
uses prescribed emissivity and fixed surroundings; it does not solve view
factors or enclosure exchanges.

The optional OpenFOAM workflow captures enclosure or bounding volume, board
heat sources, air channels, openings, fan placement, and ambient conditions.
The local worker validates that scenario and translates it into a solver case.
OpenFOAM dictionaries remain an implementation detail.
The current OpenFOAM adapter does not translate the object/surface boundaries
above. While any are enabled, the GUI blocks its screen, preflight, prepare,
and run actions so those conditions cannot be silently omitted.

## Optional OpenFOAM guided flow

1. Open **Thermal setup** from the ribbon.
2. In **Setup**, define the bounding volume, environment, medium, enclosure,
   ambient temperature, gravity, and a board-level heat load.
3. Choose natural or forced convection. Forced convection requires a positive
   fan flow and direction.
4. Configure the requested mesh, iteration ceiling, residual target, and
   resource limits.
5. Run **Preflight**, then **Prepare**. SPIKE creates an inspectable,
   deterministic case in an isolated temporary directory.
6. Review capability warnings and run the prepared case. Cancellation is sent
   to the process-isolated local worker; it does not block the interface thread.
7. Inspect imported temperature, velocity, and pressure fields. A result that
   reaches its iteration ceiling remains `failed_to_converge`.

Published thermal fields are rendered as GPU instances with a deterministic
9,000-sample display ceiling. The display retains actual solver extrema and
does not interpolate or invent missing values. The project snapshot retains
this bounded preview plus provenance; complete large fields stay in the
digest-bound adapter artifact or prepared case. Canonical Kelvin fields are
converted to Celsius only at the presentation boundary, and metres from the
legacy OpenFOAM result are converted once to the shared millimetre scene frame.

Reports are selected from the active PI, SI, or Thermal workspace. Thermal
reports show thermal units, retained field counts, returned extrema, solver
model status, and the explicit qualification boundary. SI and PI retain their
own channel/eye/S-parameter/TDR and rail/drop/density/PDN sections. Responsive
tables are capped without deleting the underlying evidence, and all report
geometry follows one source-top-left 2D to right-handed 3D transform; no
layer-specific horizontal or vertical mirroring is applied.

The standalone application remains useful offline. It must report whether
OpenFOAM is detected, whether a case is only prepared, and whether a result was
actually produced. It must never present a generated placeholder case as a
validated CFD result.

## Current executable boundary

SPIKE now generates and executes a deterministic OpenFOAM v2606
`buoyantBoussinesqSimpleFoam` case for a deliberately narrow model:

- steady-state, single-region air;
- an open rectangular domain;
- natural convection or a uniform forced-flow inlet derived from one fan flow;
- volumetric air heating at explicit source coordinates;
- structured `blockMesh` cells and source selection through `topoSet`;
- fixed-argument native Linux or WSL process execution with timeout, memory,
  output, and cancellation controls;
- aligned cell-centre temperature, velocity, and pressure import into
  `spike/thermal-result/v1` with scenario and case-file provenance.

Source coordinates outside the volume and empty source cell sets fail before
physics results are accepted. Heated cases are complete only when OpenFOAM
reports residual-control convergence. A zero-power ambient fixture may qualify
through exact field equilibrium. The installed v2606 runtime has executed a
real heated smoke case and imported 1,232 aligned cells; that case reached its
iteration ceiling and is retained as `failed_to_converge`, not promoted.

This is an experimental air-domain surrogate. It does **not** include PCB or
component solids, copper/FR-4 conduction, component bonds, contact resistance,
conjugate heat transfer, fan curves or fan geometry, duct/cabinet geometry,
surface radiation, potting, vacuum heat rejection, transient CFD, or
electrical-loss spatial mapping. Those options remain visible only as
capability-gated intent. The compact RC estimator is separate and remains
approximate.

The separate `spike/thermal-field-job-request/v1` route now has a real trusted
host execution boundary and normalized `spike/thermal-field-result/v1`
contract, including bounded electro-thermal iteration. That route still fails
closed until a locally registered adapter passes its runtime probe, declares
the exact requested physics, receives qualified geometry/contact evidence, and
has workflow qualification. Planning, runtime discovery, or a visually
rendered field is not by itself production qualification.

## Multi-region mesh, execution, and import boundary

SPIKE now also publishes `spike/openfoam-multiregion-request/v1` and prepares a
deterministic `spike/openfoam-multiregion-case/v1` tree. This translator
requires digest-bound qualified assembly and per-region meshes, typed
solid/fluid materials, explicit interfaces, contact resistance and area,
component power evidence, and explicit enclosure, potting, heatsink, fan,
radiation, and vacuum intent. It writes `regionProperties` plus immutable
material/interface/environment metadata and exposes the route through the
worker as `prepare_multiregion_thermal_case`.

The original neutral-only preparation route remains `prepared_not_runnable`.
A separate runnable route now accepts only a digest-bound solver-neutral volume
mesh with exact per-region patch ownership, materializes regular OpenFOAM
`polyMesh` trees, and writes deterministic v2606 `chtMultiRegionFoam`
dictionaries. Missing mesh members, symbolic links, digest mismatches,
duplicate patches, and mismatched interface ownership fail before any process
launch.

For an admitted runnable case, SPIKE uses fixed arguments in this order:
`checkMesh -allRegions -allTopology -allGeometry`, optional view-factor
preprocessing, `chtMultiRegionFoam`, then per-region `postProcess` for cell
centres, cell volumes, a case-owned safe `gradT` alias that writes `grad(T)`, and
`wallHeatFlux` on declared external sink patches. Materialized `cellZones`
bind volumetric heat sources to the intended board/component region; source
and boundary ownership are checked before process launch. The importer
requires every solid/fluid region plus aligned C/T/heat-flux arrays and fluid
U/p arrays, and returns digest-bound temperature, heat flux, velocity, and
pressure in `spike/thermal-field-result/v1`. A partial or malformed export
rejects all fields. The neutral-to-`polyMesh`, checkMesh/CHT, wall-flux and
import path is exercised through deterministic fixtures. A successful runtime
command remains experimental adapter evidence, not a correlation or signoff
claim.

On Windows/WSL the requested solver address-space, CPU-time, and file-size
budgets are enforced inside Linux with `prlimit`. The Windows Job remains the
kill-on-close containment boundary but admits the bounded helper-process count
needed for WSL to start; applying a one-process Job cap to `wsl.exe` previously
caused false "not enough quota" failures before the solver launched.

Transient controls (`end_time_s`, `delta_t_s`, write and validation intervals)
are bounded and recorded in the case manifest. Gravity is explicit; the
fixture default is zero so a constant-density CHT case is not silently turned
into an unstable buoyancy model.

Radiation has two explicit, non-interchangeable boundaries. `viewFactor`
models exchange among participating `viewFactorWall` surfaces and requires
case-owned `faceAgglomerate` and `viewFactorsGen` preprocessing. The
`externalAmbient` model uses v2606 `externalWallHeatFluxTemperature` for a solid
surface radiating to a declared background temperature with convection fixed
to zero; it is the admitted vacuum heat-rejection boundary. Vacuum requests
must use `medium=vacuum`, contain one or more solid regions, contain no fluid or
fan regions, and provide exact emissivity and surface evidence.

The installed OpenFOAM v2606 runtime has completed the bounded solid-only
vacuum fixture through SPIKE's execution/import path: one solid region, zero
fluid regions, eight cells, 0.1 W source, emissivity 0.85, a 2 s transient, and
eight aligned temperature/heat-flux samples. The retained record is
`docs/validation/openfoam-v2606-vacuum-radiation-synthetic-candidate.json`.
This closes the executable topology and importer slice only. It does not close
representative PCB geometry, vacuum energy/mesh/time convergence,
independent/measured correlation, or packaged-runtime qualification.

The installed runtime has also completed a stricter synthetic
board/package/contact/air fixture. Its FR-4 board, explicit 0.2 K/W TIM
contact, silicon package heat source, and conjugate air region produced 24
aligned temperature/heat-flux samples plus eight fluid velocity/pressure
samples. The case uses ten bounded outer coupling correctors. Because it has
zero gravity and no fan, `frozenFlow` prevents an unforced pressure solve from
destabilizing the conductive fluid region; buoyant and fan-driven cases do not
freeze flow. Three spatial levels (3/24/81 total cells at a common 0.03125 s
step) and three time steps (1/0.5/0.25 s) pass the candidate 0.2%
maximum-temperature refinement threshold. The retained record is
`docs/validation/openfoam-v2606-board-package-contact-cht-synthetic-candidate.json`.
Its independently calculated transient energy balance passes the candidate 1%
threshold: 1 J input versus 0.987712 J stored plus 0.011722 J integrated
external loss leaves a 0.0566% residual. This closes conservation and selected
refinement checks for the synthetic fixture only; it does not validate airflow,
representative PCB/package geometry, an independent solver, measurements, or
release packages.

The codebase includes deterministic analytic references for layered solid
conduction with contact resistance and energy balance, three-level mesh
convergence assessment, and electro-thermal fixed-point convergence. Candidate
adapters must execute against those references; the references do not
themselves qualify OpenFOAM, Elmer, sparseLizard, or SPIKES.

## Accuracy gates

Before publishing engineering-grade thermal results, retain exact v2606
checkMesh/CHT/post-process records for representative fixtures; complete
analytical convection and transient fixtures, solid/fluid fan-curve and
enclosure benchmarks, and comparison data from an independent solver and
measurements. Reports must include mesh size and quality, material data,
boundary conditions, solver version, residual history, energy balance,
convergence, uncertainty, and all model assumptions. Both Windows x64 and
Linux x64 package fixtures must pass for the exact adapter and runtime version.
