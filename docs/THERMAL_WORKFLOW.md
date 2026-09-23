# SPIKE Thermal Workflow

SPIKE uses an intent-first thermal workflow. The user defines the enclosure or
bounding volume, board heat sources, air channels, openings, fan placement, and
ambient conditions. The local worker validates that scenario and translates it
into a solver case. OpenFOAM dictionaries remain an implementation detail.

## Guided flow

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
