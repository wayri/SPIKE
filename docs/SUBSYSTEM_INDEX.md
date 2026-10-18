# Subsystem Index

Bounded rectangular sheet/flex folding is owned by
`python/spike_core/sheet_folding.py`; read-only worker routes by
`service_sheet_folding.py`; the desktop workspace by `app/src/SheetFoldingPanel.tsx`.
See [geometry, imports and limits](SHEET_FOLDING.md). This geometric preview is
separate from flat PCB solver inputs and does not create a formed CAD solid or
qualify deformation-dependent physics.

Mixed resistor/shunt-capacitor fitted-network transients are owned by
`python/spike_core/sparameter_capacitive_terminated.py`, using the existing
rational fitter and sampled-network service. See [referenced mathematics and
API](CAPACITIVE_NETWORK_TRANSIENT.md) and
[ADR 0096](adr/0096-shunt-capacitive-network-boundaries.md). Source/network currents,
loss and storage are distinct typed observables; thermal integration is separate.

Mixed resistive/series-inductive fitted-network transients are owned by
`python/spike_core/sparameter_inductive_terminated.py`, using the existing
rational fitter and sampled-network service boundary. Read the
[referenced equations, API and limits](INDUCTIVE_NETWORK_TRANSIENT.md) and
[ADR 0095](adr/0095-series-inductive-network-boundaries.md). Typed electrical
loss/energy histories support future coupling; thermal integration is separate.

Shared thermal, electrical and mechanical material evidence is owned by
`python/spike_core/material_library.py`; catalog facts and placeholders by
`data/materials/catalog.json`. The MCAD material browser is
`app/src/MaterialLibraryPanel.tsx`. See [material records and limits](MATERIAL_LIBRARY.md)
and [assignment workflow](MCAD_MATERIAL_WORKFLOW.md). Material availability does
not establish solver support or constitutive qualification.

Planned vibration/shock, solder-joint submodels/fatigue, multibody mechanisms,
full-drone code/propulsion/flight and satellite/launch applications are tracked
in [the vehicle/mechanism plan](VIBRATION_VEHICLES_AND_MECHANISMS_PLAN.md) and
the parity backlog under GP12-GP16. These stages have no new solver ownership
yet; existing static mechanics and scalar co-simulation retain their limits.

Bounded structural mechanics is owned by `python/spike_core/assembly_tetra_structural.py`;
executed same-mesh thermal coupling by `assembly_thermomechanical.py` and worker
admission by `service_structural.py`. Read [scope and planned coupling](COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md)
and [ADR 0094](adr/0094-bounded-static-thermoelastic-coupling.md). Existing thermal
mesh ownership validation is reused; mechanical contact/dynamics and Hall
transport are separate planned stages.

Two-application IC/ASIC project preflight is owned by `python/spikes/asic_project.py`;
read-only native KLayout layout inspection by `python/spikes/klayout_bridge.py`
and `scripts/klayout/spikes_layout_probe.py`. CLI `asic-plan`/`layout-inspect`
expose these foundations. See [flow and PEX completion gates](SPIKES_ASIC_TWO_APPLICATION_FLOW.md)
and [ADR 0074](adr/0074-two-application-asic-flow-and-klayout-handoff.md).

The independent native semiconductor-field subsystem is owned by
`src/spikes/tcad_equilibrium.*`, with console transport in `tcad_console.cpp`.
See [equilibrium derivation and full TCAD completion gates](SPIKES_TCAD_EQUILIBRIUM.md).
This is not a circuit compact-model replacement or full device/process TCAD.

Open-PDK inventory is owned by `python/spikes/pdk_inventory.py`; bounded
selected-corner preparation and explicit ngspice orchestration by
`python/spikes/pdk_workflow.py` and the `pdk` CLI. See
[workflow and semiconductor scope](SPIKES_OPEN_PDK_WORKFLOW.md) and
[ADR 0072](adr/0072-inert-open-pdk-circuit-workflows.md). Discovery is not
foundry qualification, native model compatibility or TCAD.

User-defined paired current/charge equations are composed by
`python/spikes/equation_device.py` and the `device-build` CLI; arbitrary-pin
constant package parasitics by `python/spikes/device_parasitics.py`. Their emitted
B/V/C/R/L primitives run in the existing C++ engine. See
[equations, workflows and unsupported effects](SPIKES_EQUATION_DEVICES.md) and
[ADR 0071](adr/0071-user-defined-electrical-current-charge-models.md).

Original generic multi-terminal model composition is owned by
`python/spikes/lumped_physics_parts.py`; it reuses existing C++ primitives.
Studio `device_symbols.py`, `device_glyphs.py` and `physics_model_window.py`
own geometry, v1-anchor-preserving transistor drawing and inert model editing.
See [model workflow and limits](SPIKES_LUMPED_PHYSICS_PARTS.md); symbol availability
does not establish process/semiconductor qualification.

Supplied-parameter ideal CCM SMPS/control stability is owned by
`src/spikes/smps_stability.cpp`, exposed by the typed C ABI and
`python/spikes/native_smps.py`; `python/spikes/smps_stability.py` is the explicit
analytical test reference. This is not the switched transient engine. Studio
`smps_stability_window.py` and `smps_stability_view.py` own its floating background
workflow and presentation. See [derivation](SPIKES_SMPS_STABILITY.md) and
[remaining topology/stability coverage](SPIKES_SMPS_ROADMAP.md).

Reusable sampled controller libraries are owned by Studio `compiled_ic_library.py`
and the inert visual selector `compiled_ic_dialog.py`; `controller_panel.py` owns
editor loading, trust reset and existing compilation/session attachment. Exact-MPN
coverage declarations are audited by `active_library_coverage.py`; private vendor
gate reference checks use `scripts/qualify_spikes_logic_vendor.py`. Neither implies
manufacturer qualification or redistribution permission.

Configurable preferred-value passives are owned by Studio `passive_catalog.py`;
the original generic circuit/impedance equations by `python/spikes/passive_models.py`.
`standard_passive_seed.py` adds exact manufacturer catalog evidence, not vendor
compact models. See [library workflow and scope](SPIKES_STANDARD_PASSIVE_LIBRARY.md)
and [numerical equations](SPIKES_PASSIVE_MODEL_EQUATIONS.md).

Studio discovery searches reuse `fuzzy_search.py` for bounded, cached matching
and ranking. Symbol, part, net, directive, battery, command, model-library and
waveform/timing search owners preserve their exact eligibility filters. This
does not change identifier resolution, source syntax or circuit contents.

Recorded-run XY/spectral/eye/histogram/integral reductions and floating workers
are owned by Studio `analysis_plots.py` and `analysis_plot_window.py`; see
[processing and limits](SPIKES_ANALYSIS_PLOTS.md). External-ngspice domain
examples are described in [circuit examples](SPIKES_CIRCUIT_DOMAINS.md), not
promoted to native solver or hardware qualification.

Standard functional HC package descriptors and original explicit generic SPICE
exports are owned by `python/spikes/standard_logic.py`; Studio sourced extensions
by `standard_logic_seed.py` and `standard_analog_seed.py`. Their browser integration
preserves circuit-unavailable states. See [standard parts scope](SPIKES_STANDARD_PARTS.md).
`python/spikes/firmware_targets.py` owns prospective binary/board admission only,
not execution or an electrical MCU bridge; see [firmware boundary](SPIKES_FIRMWARE_EMULATION.md).

Native analytic SIN sources: `src/spikes/dc_solver.*` owns construction and
evaluation; `transient_solver.cpp` owns delay breakpoints and stepping;
`transient_session.cpp` preserves global time. `c_api.*`, `native_abi.py` and
`native_runner.py` expose the explicit owned route. See the
[verification checkpoint](validation/NATIVE_SIN_PARITY_2026-10-12.md).

Standalone Studio paired source/schematic views are owned by
`editor_canvas_split.py`; the shared floating controller editor by
`controller_code_window.py`; exact textual pin/net navigation and lexical
styling by `code_crossprobe.py`. These reuse existing editors and do not
establish compiler-level semantic analysis. See the standalone workbench guide.
`hdl_suite.py` owns the native diagnostics/synthesis/VCD UI;
`hdl_analysis.py` owns headless cell summaries and original-transition metrics.
`ide.py` remains the bounded external-tool adapter. VCD measurements are not STA.
`controller_visual.py` owns the controller block/pin preview and ordinary setup
fields; serialization stays internal to the existing controller contract.
Dashboard visual links and optional data-only DUT pin mappings are validated in
`dashboard.py`; `dashboard_panel.py` renders and edits them, and
`dashboard_dut.py` provides the mapping dialog. No hardware adapter is executed.
Native context-menu lifecycle and text-editor actions are in `context_menus.py`;
`schematic_context.py` and `dashboard_context.py` provide workspace-specific
groups. Plot and catalog owners reuse the same helper and clicked-item targeting.
`wire_visuals.py` owns source-net-aware orthogonal crossing markers;
`junction_edit.py` and Document own explicit wire splitting/branch connectivity.
`net_labels.py` validates labels against native hierarchy/global authorities;
`hierarchy_views.py` owns instance-scoped canvas navigation, not full graphical
shared-sheet definition editing.
`quick_insert.py` owns bounded canvas search/completion suggestions;
`quick_insert_popup.py` owns the native transient palette, reviewed component
placement and monitor bindings. Blank-space double-click routes here, while
existing object editors retain their own behavior.

Studio plot annotations/sweep cursor readouts are owned by `plot_annotations.py`
and `plot_interactions.py`; `monte_carlo_panel.py` routes explicitly to the
existing linear Python sweep API. Native-parser capacitor-state `.ic` lowering
is documented in [initial state and source support](SPIKES_INITIAL_DIRECTIVES.md).

SPIKES power-marker editing lives in Studio `power_symbols.py`; battery studies
in `battery_panel.py` use `python/spikes/battery.py`, a prescribed-current Python
reference model, not a native circuit device. See [workflow and scope](SPIKES_POWER_BATTERY_WORKFLOW.md).

Standalone SPIKES sourced-part browsing, offline NMOS table fitting, native GUI
instruments, warning glyphs and explicit leaf-wire RLC handoff are documented in
[sourced-parts workbench](SPIKES_SOURCED_PARTS_WORKBENCH.md). Ownership remains in
`standalone/spikes_project/studio/python/spikes_studio/`; numerical fitting lives
in `python/spikes/mosfet_curve_fit.py`. No universal manufacturer-model coverage.

Parity development tracking: `docs/parity-capability-backlog-v1.json` records
work and open benchmark definitions; `scripts/check_parity_backlog.py` checks
roadmap coverage/evidence paths and fixture integrity. Import corpus assurance
is owned by `scripts/benchmark_board_corpus.py` and `board_corpus_assertions.py`.
The first independent geometry fixture is [the parity coupon](../benchmarks/parity-import/README.md).
These tools do not change the runtime or release capability ledger.
The [general physics and wave-optics expansion](GENERAL_PHYSICS_AND_WAVE_OPTICS_PLAN.md)
adds non-PCB domains, scientific field scenes, optics, material/model catalogs
and scalable execution requirements. These are planned, not runtime capability
promotions; existing geometry/domain/worker owners remain authoritative.
`scripts/parity_stage_evidence.py` owns Done-stage source/manifest/result binding
and dependency checks; stage receipts live in `docs/validation/parity/`.
`arc_legacy_projection.py` owns exact Arc/chord admission and strict legacy
conversion; `board_outline_geometry.py` owns bounded straight outer/cutout
classification. `scripts/parity_geometry_gate.py` recomputes the original
fixture's Arrow/native Arc-only and retained-volume geometry observables.

KiCad schematic import/viewing: `python/spike_core/kicad_schematic_importer.py`
owns bounded native SVG/XML export, source hierarchy admission, and normalized
cross-selection metadata. `python/spike_core/connectivity_view_importer.py`
owns generated connectivity-only views for KiCad netlists and ODB++ packages.
See [KiCad schematic import](KICAD_SCHEMATIC_IMPORT.md).

Native CFD: `src/airflow/` owns the original laminar cavity numerical kernel;
`python/spike_core/native_airflow.py` owns its bounded process contract.
`su2_airflow.py` owns the separately installed SU2 cavity reference adapter.
`su2_cht.py` owns the original coupled fluid/solid reference adapter;
`extensions/su2_suite/` declares CFD and CHT workspace routes and process entry
points. `app/src/Su2ResultPanel.tsx` admits returned fields for presentation.
See [SU2 CHT](SU2_CHT.md) and [extension workflows](EXTENSION_WORKSPACE_ENGINES.md).
`service_cfd.py` exposes fixed worker entry points; `scripts/run_cfd.py` provides
the CLI. See [native CFD](NATIVE_CFD.md), [SU2 workflow](SU2_AIRFLOW.md) and
[ADR 0068](adr/0068-native-cfd-and-su2-reference.md).

Engineering review: `python/spike_core/engineering_review.py` owns BoM grouping,
coverage, contextual checks and analytical quick tools; `EngineeringReview.tsx`
owns the desktop view. See [workflow and scope](ENGINEERING_REVIEW.md).

Retained-volume EM: `python/spike_core/assembly_em.py` and
`extensions/openems_suite/retained_volume_geometry.py` / `retained_volume_driver.py`
own explicit polyhedral assembly execution. `assembly_em_study.py` admits saved
request/result bindings; `AssemblyEmWorkbench.tsx` owns execution and activation,
and `retainedAssemblyEm.ts` admits normalized embedded E/H preview samples. See [workflow](RETAINED_ASSEMBLY_EM.md).

SPIKES adaptive transient: `src/spikes/transient_solver.cpp` owns numerical
stepping/recovery/cache; `c_api.*` and `python/spikes/native_abi.py` own the ABI;
`native_runner.py`/`cli.py` own admission and output sampling. See
[workflow, derivation and validation](SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md).

EM reduced machine models: [machines and electromagnets](EM_MACHINES.md).
Geometry-based planar magnetic studies: [workflow](MAGNETIC_MACHINE_STUDIES.md).
`magnetic_machine_study.py` owns worker orchestration, `machine_geometry.py`
owns conforming planar region geometry, `magnetic_fem.py` owns nonlinear magnetics and
stationary eddy currents, and `magnetic_thermal.py` owns planar thermal coupling.
`MagneticMachineWorkbench.tsx` renders returned fields and histories.
Numerics are owned by python/spike_core/em_machines.py; worker/CLI route them,
and EmMachineWorkbench.tsx owns the EM setup controls and plots.

Experimental scalar co-simulation and recorded digital twin comparison are
owned by `python/spike_core/cosimulation.py`, `digital_twin.py` and
`service_cosimulation.py`. CLI and Python Workspace templates expose the same
worker methods. See [scope and staged plan](COSIMULATION_DIGITAL_TWIN.md).

Study navigation and retained result activation: [study navigator](STUDY_NAVIGATOR.md).
StudyNavigator.tsx owns the dockable tree; App.tsx owns domain restoration.
Loading estimates use projectLoadProgress.ts and useProjectLoad.ts; see
[project loading ETA](PROJECT_LOADING_ETA.md).

Project-open transport and cancellation: [loading performance](PROJECT_LOADING_PERFORMANCE.md).
Whole-program memory and interaction targets, undo ownership, and allocation
evidence: [performance target and evidence](WHOLE_PROGRAM_PERFORMANCE.md).
`mergedGeometryTransforms.ts` owns exact immutable-source transformed merging;
assembly copper/imported batch owners retain picking, material scope and teardown.
`normalizedSnapshotTransport.ts`, `service_project_handlers.py`, and the native
worker bridge own lossless transport and cancellable initial reads.

PALACE and Xyce optional native applications are owned by `extensions/palace_suite/`
and `extensions/xyce_suite/`. `PalaceExtension.tsx`, `XyceExtension.tsx`,
`ExternalSolverResults.tsx` and `NativeSolverFieldPreview.tsx` own their dedicated
workbenches; `externalSolverWorkspace.ts` owns portable settings/results admission.
See [native solver workbenches](PALACE_XYCE_WORKBENCHES.md).

Large-study planning: [crash recovery, adaptive resolution and segmented multiphysics feasibility](LARGE_STUDY_FEASIBILITY.md). Proposed work; not a solver capability claim.

Application menu grouping and keyboard access: [application menus](APPLICATION_MENUS.md).
`ApplicationMenu.tsx` owns popup navigation; App owns command callbacks.

Viewport PI tuning is owned by `piQuickTune.ts`, `PiQuickTuneBar.tsx`, and the
occurrence-aware viewport adapters. App reuses the admitted PI run transaction.
See [viewport load tuning](VIEWPORT_PI_TUNING.md).

Viewport orbit cadence is owned by `viewportFrameCadence.ts` and
`BoardViewport.tsx`; shaded conductor presentation by `harnessScene.ts`.
See [orbit and harness rendering policy and verification](VIEWPORT_ORBIT_AND_HARNESS.md).


Integrated desktop chat: [SPIKE Assistant](INTEGRATED_ASSISTANT.md), including provider consent, reviewed tools and assembly workflows.
`parallel_pool.py` and `parallel_child.py` own bounded independent inline jobs,
fresh child processes and result provenance. `cluster_protocol.py`,
`cluster_transport.py`, `cluster_manager.py`, `cluster_discovery.py` and
`cluster_cli.py` own mutual-TLS enrollment, inert hints, node preflight and
remote routing. `project_parallel_state.py` owns offline package admission and
request/result digest binding. `parallelWorkspace.ts` and App own portable UI
state; `ParallelWorkerPanel.tsx` presents local controls and retained batch history.
See [worker manager setup and limits](PARALLEL_WORKER_MANAGER.md).

`python/spike_core/pwm_electrothermal.py` owns bounded PWM orchestration and
strict admission; `src/spikes` retains persistent switching/thermal MNA.
`python/spike_core/pwm_volume_electrothermal.py` owns the separate retained-volume
window coupling; `retained_thermal_step.py` owns prepared conservative energy
deposition and transpose temperature gathering. See [volume PWM coupling](PWM_VOLUME_ELECTROTHERMAL.md).
`tests/test_spikes_pwm_electrothermal.cpp` owns independent switching-reference
qualification. PI/Thermal transport integration must preserve its winding-only
thermal and behavioral-switch limits. See [model boundary and reproduction](SOURCED_POWER_QUALIFICATION.md#actual-native-pwm-with-winding-thermal-feedback-2026-10-09).

PI engineering tools are owned by `smps_converter.py`, `pi_return_path.py`,
and `capacitor_placement.py`, with read-only worker operations in
`service_simulation_handlers.py` and MCP allowlist entries in `mcp_server.py`.
Desktop panels are `SmpsConverterPanel.tsx`, `PiReturnPathAssistant.tsx` and
`CapacitorPlacementPanel.tsx`; App owns converter setup/result persistence.
See [workflow and limits](PI_ENGINEERING_TOOLS.md) and
[queued follow-on work](ACTIVE_ENGINEERING_QUEUE.md).

Internal channel cooling is owned by `internal_airflow.py`, worker
`service_simulation_handlers.py`, and `InternalAirflowPanel.tsx`;
see [internal airflow](INTERNAL_AIRFLOW.md). It is separate from assembly solid
field solving and OpenFOAM multiregion execution.

Solution-specific transient time refinement is owned by `thermal_accuracy.py`;
see [accuracy checks](THERMAL_ACCURACY_CHECKS.md). It does not qualify airflow or hardware accuracy.

Transient solid thermal is owned by `assembly_tetra_transient.py` and
`assembly_field_transient.py`; external comparison by `calculix_transient.py`.
`worker_progress.py`, Rust worker stderr transport and `workerBridge.ts` carry
bounded correlated live frames. `AssemblyTransientControls.tsx` authors settings;
`thermalTransientPresentation.ts` and `AssemblyThermalVolumeViewer.tsx` provide
saved-frame playback. Field-study/project admission retains settings and frames.
See [transient workflow](ASSEMBLY_THERMAL_TRANSIENT.md).

DC source capacity admission is owned by `python/spike_core/source_current_limits.py`
and `hybrid_dc_solver.py`. Desktop source fields live in `PiSiTerminalEditor.tsx`
and `TerminalTable.tsx`; `piSourceCurrentLimit.ts` validates UI values and
`SourceCapacityResults.tsx` presents retained per-source demand/headroom.
See [source capacity workflow and limits](SOURCE_CURRENT_LIMITS.md).

Native PI/SI to retained volume thermal feedback is owned by
`multiboard_volume_electrothermal.py`, its setup module and
`multiboard_volume_electrical_admission.py`. Contact authoring is owned by
`assembly_thermal_contact_model.py`; worker/project boundaries live in
`service_volume_electrothermal.py` and `service_project_volume_electrothermal.py`.
The desktop editor is `app/src/VolumeElectrothermalEditor.tsx`, with
`AssemblyThermalContacts.tsx` for retained contact resistance authoring.
See [equations, limits and checks](MULTIBOARD_VOLUME_ELECTROTHERMAL.md).

Reviewed STEP component promotion and provenance are owned by
`assembly_thermal_components.py`; circuit thermal-only declarations by
| Reviewed watts on meshed thermal bodies | `python/spike_core/assembly_thermal_body_power.py`, `app/src/AssemblyThermalBodyPower.tsx`, `assemblyThermalBodyPowerModel.ts` | `assign_assembly_thermal_body_power` conserves declared watts using admitted SI body volume; explicit replacement, occurrence ownership, stale geometry rejection and result invalidation. See [thermal presentation evidence](validation/THERMAL_3D_PRESENTATION_20261010.md). |
`multiboard_thermal_parts.py`. Joint conformal meshing lives in
`assembly_thermal_joint_mesh.py` and `gmsh_occ_mesher.py`, with exact reviewed
interface discovery in `assembly_thermal_autolink.py`. Desktop ownership:
`ThermalComponentPromotion.tsx`, `AssemblyThermalContacts.tsx` and
`AssemblyThermalVolumeViewer.tsx`. See [retained component solids](THERMAL_COMPONENT_SOLIDS.md).

Local layered thermal meshes/area transfers are owned by
`python/spike_core/thermal_grid.py` and `layered_board_thermal.py`.
Prescribed local air boundaries live in the latter; reduced parallel-passage
fan P-Q solving lives in `fan_system_operating_point.py`, exposed through
`service_assembly_field.py`. Physical-cell plot/probe admission is owned by
`app/src/boardThermalViewport.ts`. See [limits and examples](ASSEMBLY_ELECTROTHERMAL.md).

This is the maintainer ownership map for the active SPIKE application. Legacy
experiments may remain in the repository but are not supported launch paths.

## Desktop UI

Local sourced circuit qualification is owned by
`python/spikes/sourced_qualification.py` and `qualification_artifacts.py`;
`python/spike_core/transient_resistive_electrothermal.py` owns the separate
thermal-transient/quasi-static resistive feedback API. These have no new GUI
exposure. See [contracts and evidence](SOURCED_POWER_QUALIFICATION.md).

Embedded coupled results in the main Results panel are owned by
`app/src/SavedAssemblyResults.tsx`: the open assembly inventories saved studies,
and the worker validates each result on selection. `CoupledStudyResultTables.tsx`
shares numerical tables with the model editor. External file selection is only
the fallback for missing results. See the
[curated multi-board walkthroughs](../examples/multiboard/README.md).

Context-aware unsaved script drafts are owned by `app/src/contextScript.ts`,
`ActionContextMenu.tsx`, `contextMenuTrigger.ts` and `tableContext.ts`. They retain
source scope and open editor tabs without executing code; see
[SCRIPT_CONTEXT_MENUS.md](SCRIPT_CONTEXT_MENUS.md).

Coupled assembly DC/thermal execution is owned by
`python/spike_core/assembly_electrothermal.py` and `assembly_electrothermal_setup.py`;
electrical tetrahedra by `assembly_tetra_electrical.py` and its validation module,
and supplied averaged loss models by `electrical_heat_sources.py`, with stored
energy accounting in `energy_balanced_heat.py` and operating-point tensors in
`semiconductor_operating_losses.py`. `pcb_electrothermal_geometry.py` binds
already generated PCB meshes and derives exterior face/source ownership. The bounded
worker surface is `service_assembly_field.py`. See
[inputs, evidence and limitations](ASSEMBLY_ELECTROTHERMAL.md).

The retained assembly field reference is owned by
`python/spike_core/assembly_field_handoff.py` and `assembly_field_geometry.py`;
thermal binding, kernel and admission are in `assembly_field_thermal.py`,
`assembly_tetra_thermal.py`, `assembly_tetra_thermal_validation.py` and
`assembly_field_result.py`. `assembly_view_factors.py` owns geometric radiation
exchange only; `assembly_field_study.py` owns offline snapshots and
`service_assembly_field.py` the worker surface. See
[scope and contracts](ASSEMBLY_FIELD_HANDOFF.md). `app/src/AssemblyFieldStudyEditor.tsx`
owns desktop volume setup, boundary-value edits and experimental result review;
`assemblyFieldStudyPresentation.ts` owns occurrence display and execution gates.
`service_project_assembly_field.py` owns manifest-bound study persistence and
stale withholding. These do not supersede reduced multiboard studies.

The standalone fixed-excitation actuator map review is owned by
`python/spike_core/actuator_force_map.py`, with the versioned request in
`schemas/actuator-force-map-v1.schema.json`. It reviews supplied data only and
is not a registered actuator field solver; see [scope](ACTUATOR_FORCE_MAP.md).
`python/spike_core/actuator_motion.py` integrates the corresponding bounded
one-degree-of-freedom fixed-excitation mechanical model; see [motion](ACTUATOR_MOTION.md).
`python/spike_core/si_symbol_clock.py` owns continuous-time NRZ boundary/ramp
sampling for the loaded SI workflow, independently of the FFT grid.
`python/spike_core/si_clock_recovery.py` owns optional bounded transition-PI
receiver recovery; `python/spike_core/voice_coil_drive.py` owns the standalone
linear reciprocal electrical/mechanical actuator simulation.

The loaded SI workflow is owned by `app/src/SiWorkflowWorkbench.tsx` and
`app/src/SiWorkflowPlots.tsx`. Its worker orchestration is
`python/spike_core/si_workflow.py`; network edits, passive models and IBIS
inventory/reduction live in `si_network_workflow.py`, `si_passives.py` and
`si_ibis.py`. See [SI workflow](SI_WORKFLOW.md) for scope and contracts.

| File | Responsibility | Notes |
|---|---|---|
| `app/src/EMergeGerberImport.tsx`, `emergeGerberSource.ts` | Native Gerber source manager, materials, bounds, ports and portable package import/export | Original artwork is retained; copper meshing stays in EMerge. See [workflow](EMERGE_GERBER.md) |
| `app/src/EMergeRuntimeUpdater.tsx`, `useEMergeRuntimeUpdates.ts`, `emergeRuntimeUpdates.ts` | Local EMerge update controls and persistent workspace operation state | Release checks, exact target selection, status recovery and interpreter locking; see [workflow](EMERGE_RUNTIME_UPDATES.md) |
| `app/src/main.tsx` | React bootstrap | Installs the root error boundary |
| `app/src/detachedToolWindows.tsx` | Native/browser detached Results and Probe presentation bridge | Main workspace remains state authority; child does not start workers |
| `app/src/assemblyToolWindows.ts`, `assemblyToolWindowModel.ts` | Native/browser assembly tool IPC bridge and session contract | Token-bound actions, stale revision protection and main workspace state authority; saved assembly workers remain in workerBridge |
| `app/src/assemblyBoardLifecycle.ts`, `AssemblyStructureEditor.tsx` | Retained-source board addition, unique local duplication and occurrence removal | Independent frames and placements; explicit link cleanup; package transactions remain in `service_project_assembly.py` |
| `app/src/AssemblyToolHost.tsx`, `AssemblyToolWindowRoot.tsx` | Native assembly workspace, placement and manager tool contents | OS title-bar movement/resizing and dirty-draft close handling; no renderer buffers in snapshots |
| `app/src/LayerManager.tsx`, `NetCatalog.tsx`, `assemblyManagerPresentation.ts` | Shared normal/assembly layer inventory controls and net catalog presentation | Canonical board-scoped statistics, physical stack rows and atomic bulk layer updates; standalone PI roles remain in `NetManager.tsx` |
| `app/src/FlexBoardManager.tsx`, `FlexBoardManager.css` | Flex bend/region inspection, KiKakuka annotation copy and definition export | Flat fabrication reference; imported bends do not establish folded solver geometry |
| `app/src/plotInteraction.ts`, `reportPlotInteraction.ts` | Shared chart wheel/axis navigation and offline report SVG view transforms | Anchored axis coordinates, subplot identity and retained source samples; print restores full figures |
| `app/src/AssemblyConnectorLinks.tsx`, `assemblyConnectorLinks.css` | Graphical connector pin link cards, search and responsive endpoint layouts | Controlled drafts and canonical validation remain owned by `AssemblyBoardManagers.tsx` and `assemblyBoardManagerModel.ts` |
| `app/src/assemblyGizmoGesture.ts`, `assemblyGizmoNumericInput.ts`, `assemblyMovementControls.ts` | Local-axis mm/degree gesture transaction, combined arrows/rings and anchored numeric entry | Exclusive pointer owner; physical preview/commit contract; cancel restores gesture origin |
| `app/src/resultsToolSnapshots.ts` | Pure detached Results/Probe presentation snapshots | Reuses probe calculations and result analytics; no state authority |
| `app/src/detachedTracePayload.ts` | Bounded display-only trace-window result projection | Preserves retained sample topology; never replaces authoritative results |
| `app/src/App.tsx` | Current application composition root | Legacy oversized module; extract workflows incrementally |
| `app/src/AppErrorBoundary.tsx` | Fatal UI recovery | Must not alter saved projects |
| `app/src/workerBridge.ts` | Worker and native file IPC | Owns operation IDs and structured invoke failures |
| `app/src/resultScreenshot.ts` | Bounded single-frame WebP/JPEG/PNG export | [Result screenshots](RESULT_SCREENSHOTS.md); preserves numerical datasets separately |
| `app/src/resourceMonitor.ts` | Native/browser resource metrics | Allowed native IPC boundary |
| `scripts/audit_runtime_processes.ps1` | Read-only Windows process ownership snapshot | [Runtime ownership and cleanup](RUNTIME_RESOURCE_LIFECYCLE.md); no termination or command argument output |
| `app/src/resourceMonitorModel.ts` | CPU normalization, valid metric handling and system RAM accounting | Pure frontend model |
| `app/src/designSourceRegistry.ts` | Frontend source-adapter dispatch | EDA-specific parser use stops here |
| `app/src/boardParser.ts` | Current local KiCad parser | Compatibility path for UI/demo loading |
| `app/src/projectPackage.ts` | SPIKE package serialization | See `docs/PROJECT_FORMAT.md` |
| `app/src/spiceWorkspace.ts` | Persisted PI/SI circuit workspace contract | See `docs/SPICE_WORKSPACE.md` |
| `src/spikes/` | Owned SPIKES DC/nonlinear-diode and fixed-step RCL transient reference kernels plus stable C ABI | Separate circuit engine source |
| `python/spikes/` | Standalone hierarchical RCLVI CLI, native ABI bridge, sessions, virtual instruments, digital events, device extensions, and model-builder contracts | Separate circuit engine source |
| Internal SPICE and schematic development | Compatibility increments and Studio editor acceptance milestones | See [development sequence and evidence gates](INTERNAL_SPICE_DEVELOPMENT.md) |
| `python/spikes/board_library*.py`, `src/spikes/board_library*` | Bounded internal-engine compiled board packages, C/C++ objects and explicit Python loading | See [compiled board workflow](COMPILED_BOARD_LIBRARY.md), [research](BOARD_LIBRARY_RESEARCH.md) and ADR 0063; RLC, constant sources, static Shockley diode and Level-1 NMOS preview; not an arbitrary populated board or MCU emulator |
| `python/spikes/fault_injection.py`, `fault_campaign.py`, `reliability.py`, `environment_faults.py` | Explicit finite-shunt/VTO fault sites, checkpointed event scheduling, supplied FIT/Weibull scenarios and evidence-bound parameter mappings | See [fault/reliability contract](SPICE_FAULT_RELIABILITY.md), [native fault controls](INTERNAL_SPICE_FAULTS.md) and ADR 0064; no inferred hardware failure rates or environmental qualification |
| `python/spikes/transient_controls.py` | Bounded `.tran` output windows and maximum integration steps | See [transient controls](INTERNAL_SPICE_TRANSIENT_CONTROLS.md); parser admission and reference comparisons remain separate evidence |
| `python/spike_core/native_source_waveforms.py` | Reference evaluation of validated source waveforms used by MNA | See [SIN/EXP/SFFM semantics and native lowering](INTERNAL_SPICE_SOURCE_WAVEFORMS.md) |
| `python/spikes/streaming*.py` | Bounded rolling samples and trigger-driven continuous event capture | Separate circuit engine source |
| `python/spikes/waveform_store.py` | Lossless chunked waveform compression, hard byte limits, and torn-tail recovery | Separate circuit engine source |
| `standalone/spikes_project/studio/python/spikes_studio/` | Qt-free wxPython Studio engineering preview, explicit native/ngspice batch routing, data-only library store | See `standalone/spikes_project/studio/docs/QT_FREE_WORKBENCH_IMPLEMENTATION.md` and ADR 0021; not the separate C++ wxWidgets board client |
| `app/src/appSettings.ts` | Persisted UI preferences | Storage failure must be nonfatal |
| `app/src/ProjectManager.tsx` | Project/recent-project workflow | Presentation layer only |
| `app/src/UniversalSettingsModal.tsx` | Settings UI | Uses typed application settings |
| `app/src/HelpCenter.tsx` | Integrated user help | Screenshots must match released UI |
| `app/src/PythonWorkspace.tsx`, `PythonCodeEditor.tsx`, `pythonSyntax.ts`, `pythonEditorActions.ts`, `PythonFileExplorer.tsx`, `PythonDebugPanel.tsx`, `PythonRecoveryPanel.tsx`, `pythonWorkspaceModel.ts` | Tabbed script editing, incremental visible-line highlighting, bounded clipboard/edit actions, folder/worktree browsing, explicit save states, durable backup recovery and debugger presentation | Desktop execution stays behind `workerBridge`; recovery copies have no disk path and do not modify `.spike` design state |
| `app/src/pythonWorkspaceTemplates.ts`, `PythonTemplateLibrary.tsx`, `PythonWorkspaceHelp.tsx` | Searchable analysis templates and dedicated Python help | Guarded runners use existing worker contracts and preserve solver status; see `docs/PYTHON_WORKSPACE.md` |
| `app/src/pythonCompletions.ts`, `pythonWorkspaceContext.ts`, `PythonNetBrowser.tsx` | Static caret suggestions, occurrence-scoped loaded nets and admitted script interface actions | Uses shared `schemas/python-workspace-api-v1.json`; never evaluates code for completion or merges equal names |
| `app/src/buttonStandard.css`, `app/scripts/check-button-standard.mjs` | Shared control tokens, variants and preview coverage guard | See `docs/BUTTON_CONTROLS.md`; specialized controls retain accessible focus and disabled states |
| `python/spike_core/script_runtime.py`, `script_child.py`, `script_debug.py`, `script_debug_child.py`, `script_workspace_files.py`, `service_script_workspace.py` | Isolated script execution, supervised debugger and root-confined script files | Token-bound local sessions, bounded values/output, command acknowledgement and original result admission |
| `app/src/DataTable.tsx`, `DataTable.css`, `tableTheme.css`, `dataTableModel.tsx`, `spreadsheetGrid.ts`, `TableIdentityInput.tsx` | Shared searchable, paged table presentation, theme palettes, keyboard navigation, and staged ID entry | Domain rows, units, validation, ordering, and writes remain with each workflow; see `docs/TABLE_INTERFACES.md` |
| `app/src/CommandStrip.tsx`, `CommandStrip.css`, `WorkbenchChrome.css` | Shared command overflow, keyboard reachability, compact shell density and bounded dock layout | Command callbacks remain with their workflow; see `docs/WORKBENCH_SEGMENTS.md` |
| `app/src/PlotlyChart.tsx`, `InteractivePlot.tsx`, `PlotlyChart.css`, `PlotAxisEditor.tsx`, `plotAxisSettings.ts`, `plotLayout.ts`, `plotInteraction.ts`, `plotClipboard.ts`, `plotProbes.ts` | Shared axes, plot navigation, exact pinned sample pairs, context menu and bounded presentation-only clipboard comparisons | Domain adapters retain sample/cursor/result authority; see `docs/PLOT_INTERFACES.md` |
| `app/src/ExternalEngineCenter.tsx` | Optional-engine, accelerator, recommendation, registration, and tuning UI | Never installs or deletes third-party dependencies |

## Visualization

The independently buildable viewer library and development lab live in
`standalone/spike_viewer/`; see its `README.md` and ADRs 0029/0030/0031. It contains a
portable viewport extraction, board-bound virtual data layers, and an assembly
workspace with independent occurrences, local MCAD/board import and placement.
`src/assembly/` owns normalized assembly rendering and snapping; `adapters/`
and `demo/` own optional file conversion, authoring history and persistence.
`src/workspace/` owns portable floating/docked panels and compact drawers;
the demo host owns saved browser layouts independently of assembly files.
The KiCad viewer replacement target and qualification gates live in
`standalone/spike_viewer/docs/KICAD_VIEWER_TARGET.md` (ADR 0032); the native
model and KiCad refresh integrations are planned, not current parity claims.
The desktop continues to use the application files below until an explicit
package migration passes integration checks.

| File | Responsibility | Notes |
|---|---|---|
| `app/src/BoardViewport.tsx` | Three.js 3D scene and interaction | Legacy oversized; split scene, picking, overlays, controls |
| `app/src/assemblyNetIdentity.ts`, `assemblyNetHighlight.ts`, `python/spike_core/assembly_linked_nets.py` | Retained occurrence net identity, explicit pin traversal and component boundaries | Parser aliases resolve only against the owning board; ambiguous or invalid mappings stay unresolved |
| `app/src/ViewportNetViewer.tsx`, `viewportNetViewerModel.ts` | Collapsible searchable viewport net list and selected occurrence scope | Uses canonical per-board IDs and existing explicit-link selection callbacks |
| `app/src/minimizedTools.ts`, `ToolRestoreShelf.tsx`, `toolRestoreShelf.css` | Bottom dock restore registry, bounded controls and retry handling for minimized tools | Owners retain tool state; no collapsed panels or backdrops remain over the viewport |
| `app/src/assemblySceneInputs.ts`, `assemblyImportedBatches.ts`, `boardSurfaceMaterials.ts`, `importedBoardLayers.ts`, `componentSceneIndex.ts`, `webGLRecovery.ts` | Stable assembly geometry inputs, imported mesh batching, shared material policy, independently addressed imported surfaces, indexed component metadata and recoverable GPU context lifecycle | Preserve exact source picking, occurrence material isolation and cache resource ownership |
| `app/src/ViewportNotifications.tsx`, `viewportNotifications.css` | Bounded corner notice chips and requested full diagnostics in the application notification center | Import details remain available from the status bar; no automatic expanded canvas messages |
| `app/src/assemblyViewportInteraction.ts` | Assembly 2D SVG pointer-coordinate conversion, anchored zoom, pan threshold and selection framing | Honors SVG uniform scaling and letterbox margins; physical assembly transforms remain untouched |
| `app/src/AssemblyWorkspace.tsx`, `AssemblyQuickBar.tsx`, `assemblyBoardDraft.ts` | Dedicated multiboard entry, occurrence inventory, compact viewport controls and starter placement | Reuses retained assembly editor and scoped managers; preserves draft edits |
| `app/src/sceneResourceCache.ts` | Shared geometry/texture lifetime and decoded-scene LRU | Active sources are pinned; occurrence materials are independent |
| `app/src/modelSceneLoader.ts` | Bounded model preparation and load retry policy | Stops obsolete generation dispatch |
| `app/src/viewportPerformance.ts` | Linear scene indexes and list-window helpers | Source and tests |
| `app/src/LayoutViewport.tsx` | 2D vector layout and interaction | Keep coordinate transform tested |
| `app/src/layerPalette.ts` | Layer color policy | Keys and rendered colors must agree |
| `app/src/contourField.ts` | Smoothed/contour result fields | Presentation only; no inferred physics |
| `app/src/analysisResults.ts` | Result field decoding and access | Consumes solver output envelopes |
| `app/src/numericRange.ts` | Bounded large-array extrema | Avoids JavaScript argument overflow |
| `app/src/resultAnalytics.ts` | Derived report/UI analytics | Derivations need units and tests |
| `app/src/ResultVisualizationPanel.tsx` | Result controls | Capability-gates unavailable fields |
| `app/src/gifExport.ts` | Visualization animation export | Must decimate and bound memory |
| `app/src/thermalScene.ts` | Thermal scene entities | Solver input visualization only |
| `app/src/ThermalBoundaryEditor.tsx`, `app/src/thermalBoundaries.ts` | Explicit object/face conduction, convection, and radiation setup | Persisted lumped-network boundaries; no inferred spatial field |
| `app/src/ThermalInputImport.tsx`, `app/src/thermalBomParsing.ts` | BOM CSV/TSV and ODB++ property mapping to reference-linked thermal inputs | Preview and explicit application; no inferred heat path |

## Engineering workbenches and reports

| File | Responsibility |
|---|---|
| `app/src/powerTree.ts` | Normalized power topology model |
| `app/src/TopologyEditor.tsx` | Editable power-tree presentation |
| `app/src/SpiceWorkbench.tsx` | Circuit co-simulation workflow |
| `app/src/sparameters.ts` | Network-data utilities |
| `app/src/SParameterWorkbench.tsx` | S-parameter workflow UI |
| `app/src/EmiWorkbench.tsx` | EMI domain, pre-pass, excitation, solver setup, and screening dashboard |
| `app/src/emRadiationViewport.ts`, `app/src/BoardViewport.tsx` | Validated angular-grid display mesh and probe mapping for board-anchored relative far-field review; the viewport does not convert angular samples to a spatial near field |
| `app/src/siCrosstalkViewport.ts`, `app/src/BoardViewport.tsx` | Strict design/net binding for categorical SI aggressor and victim route overlays with global NEXT/FEXT readout; no inferred spatial voltage field |
| `app/src/boardThermalViewportProbe.ts`, `app/src/BoardViewport.tsx` | Saved board thermal grid/layer admission and exact cell probe mapping in the 3D board scene; display separation does not alter physical depth |
| `app/src/engineeringReport.ts` | Report data and HTML generation |
| `app/src/reportPresentation.ts`, `engineeringReportSetup.ts`, `engineeringReportFigures.ts` | Shared report sidebar, print cover/contents, saved setup and bounded static figures; preserves result validity |
| `app/src/engineeringReportRuntime.ts` | Offline report navigation, net selection and canvas redraw after visible sizing |
| `app/src/acPowerIntegrityReport.tsx`, `optycalReport.ts`, `siChannelResults.ts` | AC PI, Optycal and SI channel reports using the shared presentation |
| `app/src/ReportPreview.tsx`, `ReportPreviewWindowRoot.tsx`, `reportPreviewWindow.ts` | Separate report window, parent-owned HTML/export and sandboxed interactive preview |
| `app/src/BenchmarkCenter.tsx` | Validation benchmark presentation |

## Native desktop host

| File | Responsibility |
|---|---|
| `app/src-tauri/src/lib.rs` | Native dialogs, approved file writes, resource monitor, worker process host |
| `app/src-tauri/src/gpu_metrics.rs` | Windows PDH GPU engines and private working sets; unavailable on other platforms |
| `app/src-tauri/src/main.rs` | Desktop executable entry point |
| `app/src-tauri/tauri.conf.json` | Bundle, window, CSP, resource, and identity configuration |
| `app/src-tauri/Cargo.toml` | Rust dependency manifest |

## Python application services

`python/spike_core/headless.py` owns supervised source/frozen worker calls,
bounded sequential workflow references and cancellation. `cli.py` exposes
`worker-call` and `workflow`; `mcp_server.py` retains specific allowlisted tools.
See [headless operation and LLM skill](HEADLESS_AUTOMATION.md) and
[ADR 0038](adr/0038-supervised-headless-automation.md).

| File | Responsibility |
|---|---|
| `python/spike_core/contracts.py` | Versioned SpiDeR, AnalysisSpec, and AnalysisResult |
| `python/spike_core/spider_v2.py`, `harness_authoring.py`, `multiboard_analysis.py` | AssemblyIR board occurrences, distinct direct connector mates and cable harnesses, pin ownership, and four-domain graph planning |
| `app/src/MultiboardStudyEditor.tsx`, `multiboardStudyPresentation.ts` | Coupled model property editing, study/result import/export, stale-result guards, occurrence result presentation |
| `app/src/AssemblyLayoutViewport.tsx`, `assemblyLayout2d.ts`, `assemblyBoardScene.ts`, `useAssemblyBoardVisuals.ts` | Complete occurrence geometry and shared verified board/component assets in 2D and 3D; exact placement, overlap selection, and connector-bound canonical net picking |
| `python/spike_core/assembly_visuals.py` | Manifest-bound source and visual preparation for the exact retained design identity |
| `python/spike_core/multiboard_circuit.py`, `multiboard_thermal.py`, `multiboard_em.py` | Executable experimental reduced coupled circuits, shared thermal RC networks and reciprocal magnetic-loop models; general field qualification remains gated |
| `python/spike_core/multiboard_circuit_bonds.py`, `multiboard_thermal_scope.py`, `app/src/AssemblyMechanicalStudyModels.tsx` | Typed board/structure node ownership, passive chassis bonds and explicit casing study forms | Physical parts require models; model-less hierarchy containers are reported exclusions |
| `python/spike_core/multiboard_study.py`, `multiboard_identity.py` | Assembly-derived study drafts, exact model/result binding and manifest-bound persistence |
| `python/spike_core/service_assembly_import.py`, `app/src/AssemblyStructureEditor.tsx`, `ConnectorGraphEditor.tsx`, `connectorGraphModel.ts` | Atomic multi-source board import; connector graph editing, reviewed pin suggestions, direct mates, and virtual harness route proposals |
| `python/spike_core/harness_intent.py`, `harness_pi.py`, `harness_signal.py` | Explicit conductor/pair admission, selected-wire DC, supplied uniform-mode SI and unsupported EM requirements handoff |
| `python/spike_core/harness_mtl.py`, `harness_rlgc_geometry.py` | Bounded sampled multi-conductor/branched network backend and approximate straight round-wire ideal-plane RLGC; explicit references/models, no arbitrary shield/helix/radiation claim |
| `app/src/HarnessDocumentEditor.tsx`, `HarnessDiagram.tsx`, `HarnessDiagramModel.ts`, `AssemblyHarnessWiring.tsx`, `assemblyHarnessConductors.ts`, `HarnessSignalPanel.tsx`, `harnessVisualization.ts` | Shared wire/splice authoring, exact assembly pin-map persistence, saved SI presentation and bounded conductor 3D picking; see `docs/HARNESS_ENGINEERING.md` |
| `python/spike_core/errors.py` | Canonical FE/BE diagnostic envelopes and catalog | See `docs/ERROR_HANDLING.md` |
| `python/spike_core/spice_workspace.py` | Validated SPICE intent and deterministic netlist composition | See `docs/SPICE_WORKSPACE.md` |
| `python/spike_core/service.py` | JSON worker request dispatch and service composition |
| `python/spike_core/cli.py` | Headless command interface, including solver-manager and external-engine workflows |
| `python/spike_core/importers.py` | EDA-neutral importer protocol and registry |
| `python/spike_core/kicad_importer.py` | KiCad-to-SpiDeR adapter |
| `python/spike_core/solver_plugins.py` | Solver descriptors, catalog, selection, and execution |
| `python/spike_core/preflight.py` | Analysis validation and mesh preview orchestration |
| `python/spike_core/convergence.py` | Mesh convergence workflow |
| `python/spike_core/geometry.py` | Net geometry extraction service |
| `python/spike_core/solver_geometry.py` | Solver-facing connected geometry utilities |
| `python/spike_core/layers.py` | Physical copper-layer ordering and helpers |
| `python/spike_core/models.py`, `model_resolver_staging.py` | 3D model discovery and KiCad scene export; parser-scoped visual-only model staging |
| `python/spike_core/mcad_component_models.py`, `scripts/parity_component_model_gate.py` | Explicit occurrence/design-bound STEP body handoff and owned native solid reference gate; no inferred source placement or material/solver qualification. See [mechanical export](MCAD_EXPORT.md). |
| `python/spike_core/component_placement_review.py` | Inert, native-reference-backed placement review drafts within a bounded source/STEP/stack envelope; no automatic placement or material/solver promotion. See [review workflow](COMPONENT_PLACEMENT_REVIEW.md). |
| `python/spike_core/component_step_scale.py`, `freecad_scale_step.py` | Digest-bound positive STEP geometry scaling through the existing supervised native CAD process, with roundtrip and invariant checks; curved conversion failures remain rejected. See [workflow and limits](COMPONENT_STEP_SCALE.md). |
| `python/spike_core/scaled_component_review.py` | Snapshot-bound bake-then-rigid component review proposals within the native reference envelope; separate derived identity registration and explicit placement review remain required. See [workflow](SCALED_COMPONENT_REVIEW.md). |
| `integrations/prism/` | Opt-in source-only Prism snapshot and bound result bridge through the existing extension SDK | [Protocol, workflow and limits](PRISM_BRIDGE.md); installer qualification pending |
| `python/spike_core/extensions.py` | General extension discovery and isolation |
| `python/spike_core/emerge_runtime_updates.py`, `emerge_runtime_updates_io.py` | Explicit EMerge 3+ virtual-environment updates, fixed-index pip boundary, bounded background status and runtime-use exclusion; [contract and recovery](EMERGE_RUNTIME_UPDATES.md) |
| `python/spike_core/service_extension_packages.py` | Managed extension package browse, preview, install, update, and removal worker handlers |
| `python/spike_core/extension_analysis_results.py` | External analysis result and board-binding admission |
| `python/spike_core/extension_mesh_exchange.py` | Bounded full mesh, preview, solver geometry, and digest handoff to analysis extensions |
| `python/spike_core/automation.py` | Python scripting facade over versioned worker operations |
| `python/spike_core/script_runtime.py`, `script_child.py` | In-app Python execution, output capture, cancellation boundary, and result admission |
| `python/spike_core/script_api.py`, `script_api_context.py` | Bound `import spike` module, occurrence collections and validated interface action records | Shared Run/Debug API; actions return to presentation after successful completion; see `docs/PYTHON_SPIKE_API.md` |
| `python/spike_core/dependencies.py` | Runtime dependency status and lock verification |
| `python/spike_core/capabilities.py` | Implemented capability reporting |
| `python/spike_core/external_engines.py` | External-engine discovery, preflight, private jobs, isolated execution, quotas, and result import |
| `python/spike_core/external_engine_discovery.py` | Discovery-only metadata for adapter-pending engines, including sparseLizard |
| `python/spike_core/openfoam_runtime.py` | Bounded native/WSL OpenFOAM runtime discovery; never promotes discovery to case readiness |
| `python/spike_core/solver_manager.py` | Workload recommendations, execution gates, and EMI pre-pass screening |
| `python/spike_core/emi.py` | Versioned EMI setup validation, geometry coverage, stage gates, and screening orchestration |
| `python/spike_core/mom_surface_basis.py`, `mom_singular_source.py`, `mom_far_field.py` | Internal oriented-RWG basis, bounded singular triangular-source moments, and supplied-current far-field/RCS operators; no executable surface-MoM current solve or validated scattering claim |
| `python/spike_core/solver_state.py` | Private bounded registrations and allowlisted tuning persistence |
| `extensions/openems_suite/` | OpenEMS PI/SI extension, engine adapter, case integrity, geometry and result validation, benchmarks, and reference evidence; `python/spike_core/openems_*.py` and `external_engines.py` are compatibility import bridges |
| `extensions/emerge_suite/gerber_source.py`, `gerber_case.py` | Native Gerber package admission, neutral snapshot and current-stackup case compilation | Direct `FileBasedPCB` loading; manual unverified ports, no inferred net/pad connectivity; [contract](EMERGE_GERBER.md) |
| `extensions/emerge_suite/` | Optional EMerge board adapter for bounded 2-16 copper-layer geometry, dielectric loss/stackup, optional EMCAD unions, readable GUI-generated script execution, solved S-parameters, radiation patterns and complex E/H sample planes; results remain unvalidated. See [antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md) |
| `extensions/optycal_suite/`, `app/src/OptycalExtension.tsx`, `optycalStudy.ts` | Optional one-way PEC STEP structure scattering driven by a design-bound complex EMerge far-zone source; GUI setup, exact script preview, coherent pattern comparisons, sample probes and exports. Unvalidated; excludes nearby coupling, tuning, diffraction, shadowing and multiple scattering. |
| `app/src/EMergeExtension.tsx`, `emergeRuntimePresentation.ts`, `EMergeNearField.tsx`, `emergeNearFieldSamples.ts`, `emergeSampleExport.ts` | GUI setup, runtime API/evidence presentation, script/feature preview, radiation/network/field review, bounded coordinate admission, explicit sample probes and CSV/Touchstone exports |
| `app/src/AnalysisGuide.tsx`, `app/src/AnalysisGuide.css` | Floating, accessible Help-menu workflow guide with navigation and control highlighting; see `docs/ANALYSIS_GUIDE.md` |
| `python/spike_core/sparselizard_adapter.py` | SpiDeR-derived PCB mesh/material/terminal case export, cancellable process-tree-contained execution, digest binding, and strict scalar/vector/multiport result import; see `docs/SPARSELIZARD_ADAPTER.md` |
| `python/spike_core/sparselizard_validation.py` | Fail-closed signed-runtime, PETSc/MUMPS, convergence, and five-class PCB qualification report used by CLI, worker, and Solver Manager |
| `python/spike_core/peec_spice_export.py` | Reviewed PEEC RLCG endpoint mapping and staged geometry-parasitic handoff to process-isolated ngspice; see `docs/PEEC_NGSPICE_HYBRID.md` |
| `python/spike_core/converter_study.py` | Versioned PWM source compilation, ngspice/PEEC staged orchestration, converter analytics, and explicit compact-thermal loss handoff; see `docs/CONVERTER_STUDY.md` |

## Numerical modules

ACC01 measurement belongs to `scripts/benchmark_circuit_timestep_accuracy.py`
(historical endpoint v1 and signed/zero waveform v2), not solver tolerance
defaults. `openems_stopping.py` owns bounded retained-EM stopping interpretation;
`gmsh_environment.py` owns fixed isolated dependency preflight. Mesh environment
selection remains in `gmsh_occ_runtime.py` / `gmsh_extension_runtime.py`.

| File | Responsibility | Capability status source |
|---|---|---|
| `acceleration.py`, `compute_policy.py`, `gpu_acceleration.py` | NumPy multicore/Numba assembly and SuperLU/PETSc-MUMPS/optional CUDA sparse execution policy | `docs/ACCELERATION_ARCHITECTURE.md` |
| `dc_solver.py` | Resistive network solver | `docs/DC_SOLVER.md` |
| `python/spike_core/dc_result_utils.py` | Deterministic DC sampling, terminal, resistance, and percentile policies; keeps result-construction policy out of the solver module | `docs/DC_SOLVER.md` |
| `hybrid_mesh.py` | Connected trace/pad/via/zone discretization | `docs/MESHING_ENGINE.md` |
| `planar_polygon_topology.py`, `filled_copper_path.py` | Exact represented-coordinate topology and bounded cutout-preserving source-filled cells | `docs/validation/FILLED_COPPER_PATH_20261013.md` |
| `source_filled_boundary.py`, `boundary_spatial_index.py` | Physical source-boundary contact observation and conservative candidate indexes | `docs/validation/MARBLE_FILLED_ZONE_FIX_20261013.md` |
| `hybrid_dc_solver.py` | Hybrid-geometry DC solve | `docs/DC_SOLVER.md` |
| `peec_plugin.py` | Quasi-static PEEC plugin | `docs/SOLVER_STATUS.md` |
| `transient_peec.py` | Transient PEEC formulation | `docs/TRANSIENT_PI.md` |
| `quasistatic_capacitance.py` | Capacitance extraction | `docs/RLCG_EXTRACTION_VALIDITY.md` |
| `ngspice_plugin.py` | ngspice co-simulation adapter | `docs/SOLVER_STATUS.md` |
| `sparameters.py` | Network parameter calculations | `docs/SIGNAL_INTEGRITY_NETWORK_INTEGRATION.md` |
| `sparameter_modes.py` | Explicit real-reference mixed-mode pairing and physical port mapping | `docs/PI_SI_PARITY_EXECUTION.md` |
| `meshing.py` | General mesh representations | `docs/MESHING_ENGINE.md` |
| `internal_meshing_engine.py`, `service_meshing.py` | Versioned internal tetra worker boundary, bounded requests/candidates and digest provenance | `docs/INTERNAL_MESH_ENGINE.md` |
| `scripts/benchmark_internal_mesher.py`, `scripts/benchmark_pcb_mesher.py` | Original fixtures, before/after mesher timings, process-memory evidence and black-box comparisons | `docs/validation/INTERNAL_MESHER_OPTIMIZATION_20261012.md` |
| `scripts/benchmark_tetra_allocation_pass2.py`, `scripts/profile_retained_board_mesher.py` | Exact second-pass tetrahedral timing and retained large-PCB completeness/hotspot diagnostics | `docs/validation/MESHER_ALLOCATION_PASS2_20261012.md`; `docs/validation/LARGE_PCB_MESHER_PROFILE_20261012.md` |
| `internal_tetra_generation.py` | Deterministic convex-hull tetra generation with exact predicate fallback | `docs/INTERNAL_MESH_ENGINE.md`; experimental |
| `pcb_volume_compiler.py`, `pcb_focus_sizing.py`, `pcb_volume_mesh.py` | Complete normalized planar PCB solids, net/source/manual sizing, bounded preparation and capability probe | `docs/PCB_FOCUSED_VOLUME_MESHING.md`; experimental external OCC generation |
| `dynamic_tetra_adaptation.py`, `tetra_mesh_refinement.py`, `tetra_mesh_optimization.py` | Error/manual/size-driven edge-star refinement, scalar refinement transfer and fixed-interface interior smoothing | `docs/INTERNAL_MESH_ENGINE.md`; experimental |
| `numerics.py` | Shared numerical safeguards | Tests define supported behavior |
| `pdn.py` | PDN target review, explicit mounting-path screening, and two-port candidate loading | `docs/PDN_SCREENING.md` |
| `pdn_network.py`, `pdn_electrostatic.py`, `pdn_shunt_capacitance.py`, `pdn_series_capacitors.py` | Explicit passive AC/filter and load-spike network, finite retained dielectric C extraction, reference-bound capacitor attachment, and series sharing review | `docs/PDN_SCREENING.md#explicit-ac-pdn-and-filter-workflow` |
| `pdn_network.py`, `schemas/pdn-network-request-v1.schema.json` | Additive simultaneous PWL loads, exact event union, physical load identities and combined source work | `docs/PDN_SIMULTANEOUS_LOADS.md` |
| `pdn_dielectric_ac.py`, `service_pdn_network.py` | Supplied finite dielectric AC fields, electrode admittance, conductive/dielectric loss and power evidence | `docs/PDN_DIELECTRIC_AC.md` |
| `pdn_admittance_reduction.py`, `service_pdn_network.py` | Explicit passive auxiliary-port termination, Schur reduction and power identity | `docs/PDN_ADMITTANCE_REDUCTION.md` |
| `pdn_dielectric_thermal.py`, `service_pdn_network.py` | Coherent RMS dielectric loss to exact retained-cell thermal sources, conserved power and actual steady thermal solve | `docs/PDN_DIELECTRIC_THERMAL.md` |
| `pdn_dielectric_feedback.py`, `service_pdn_network.py` | Cellwise supplied conductivity-temperature laws, bounded fixed-point coupling and raw convergence evidence | `docs/PDN_DIELECTRIC_FEEDBACK.md` |
| `app/src/PdnNetworkPanel.tsx`, `service_pdn_network.py` | Power-tree AC setup, source/field admission, worker execution and returned-data plots; no inferred PCB models | `docs/PDN_SCREENING.md#explicit-ac-pdn-and-filter-workflow` |
| `thermal.py` | Compact thermal scenario/model | `docs/THERMAL_WORKFLOW.md` |
| `board_thermal.py`, `layered_board_thermal.py`, `thermal_copper_geometry.py` | Board plate and optional structured layered steady/transient thermal solve, imported pad contact coupling, sampled/blurred copper coverage and via links | `docs/validation/EBRAKE1_BOARD_THERMAL_20260928.md`, `docs/validation/EBRAKE1_LAYERED_THERMAL_20260928.md`, `docs/validation/EBRAKE1_LAYERED_TRANSIENT_20260928.md`; experimental, approximate geometry |
| `component_thermal.py`, `thermal_network.py` | Built-in bounded component steady/transient RC solver and worker adapter | `docs/COMPONENT_THERMAL.md`; approximate, no spatial field |
| `openfoam.py` | OpenFOAM case adapter | `docs/EXTERNAL_ENGINE_INTEROPERABILITY.md` |

## Source parsers and native kernels

| Path | Responsibility |
|---|---|
| `python/core/board_parser.py` | Current low-level KiCad S-expression parser |
| `src/peec` | Native PEEC kernel code |
| `src/peec/volume_inductance.*` | Isolated experimental finite rectangular-volume integration, not the legacy production extractor |
| `python/spike_core/peec_magnetic_geometry.py` | Strict physical cross-section descriptors separate from equivalent DC area; not yet production-wired |
| `src/thermal` | Native thermal kernel code |
| `src/math` | Native mathematical utilities |
| `CMakeLists.txt` | Native build configuration |

## SDKs and bridges

| Path | Responsibility |
|---|---|
| `solver_sdk` | Solver plugin API, manifests, and examples |
| `extension_sdk` | General application extension API |
| `python/spike_core/mcp_server.py`, `scripts/spike_mcp.py` | Allowlisted local stdio MCP tools over the existing Python automation worker |
| `python/spike_core/local_llm.py`, `scripts/spike_local_chat.py` | Loopback-only LM Studio and Ollama tool-calling client |
| `app/src-tauri/src/mcp_bridge.rs`, `app/src/McpBridgePanel.tsx` | Opt-in authenticated desktop MCP bridge and its settings panel |
| `app/src/mcpAnalysisConversation.ts` | Loaded-design conversational cases, missing inputs, exact-revision preflight, asynchronous jobs and bounded solver evidence |
| `app/src/emViewportResults.ts`, `app/src/emViewportScene.ts`, `app/src/EMViewportResultManager.tsx` | Main-viewport EM sample overlays, assembly structure, linked probes and result graphs |
| `extensions` | Built-in or example extension packages |
| `kicad_plugin` | Legacy/source-specific adapter scaffold; standalone product commands are CAD-neutral |

## Tests and governance

| Path | Responsibility |
|---|---|
| `tests/python` | Python unit, contract, workflow, and numerical regression tests |
| `tests/python/test_acceleration.py` | Optional-backend policy plus real/complex baseline-equivalence coverage |
| `tests/python/test_external_engines.py` | External-engine catalog, preflight, job-contract, path-containment, and isolated-execution coverage |
| `tests/python/test_openfoam_runtime.py` | Fixed-command WSL OpenFOAM discovery and malformed-probe rejection |
| `tests/python/test_solver_manager.py` | Recommendation, registration, tuning, removal, and EMI-screening policy coverage |
| `app/scripts/test-board-parser.mjs` | Frontend parser regression suite |
| `scripts/check_architecture.py` | Enforced dependency and documentation guardrails |
| `docs/LANGUAGE_POLICY.md` | Implementation-language ownership, budget, and retirement plan |
| `docs/validation` | Reproducible benchmark inputs and outputs |
| `docs/adr` | Architecture decision records |
| `schemas` | JSON wire-contract envelopes |
| `docs/ENGINEERING_GOVERNANCE.md` | Review and release policy |
| `LICENSE` and `LICENSING.md` | Repository license boundary and contributor provenance policy |
| `THIRD_PARTY_NOTICES.md` | Third-party software and example-source attribution |

## Documentation ownership

| Path | Responsibility |
|---|---|
| `docs/README.md` | Audience- and task-based documentation entry point |
| `docs/USER_TASK_SEQUENCES.md` | Detailed desktop task sequences using reviewed Help Center screenshots |
| `docs/LOCAL_LLM_MCP.md` | Offline LM Studio and Ollama setup, MCP scope, and desktop bridge workflow |
| `ARCHITECTURE.md` | Canonical runtime boundaries, dependency direction, and state authority |
| `DEVELOPMENT.md` | Active setup, launch paths, build commands, and verification matrix |
| `TROUBLESHOOTING.md` | Symptom-first operational diagnosis and recovery sequences |
| `docs/ERROR_HANDLING.md` | Diagnostic contract, emission policy, and contribution rules |
| `docs/ERROR_CODE_CATALOG.md` | Issued codes and canonical first recovery actions |
| `docs/SOLVER_STATUS.md` | Implemented capability and numerical-validity status |

User-facing workflow changes update the in-app Help Center and
`docs/USER_TASK_SEQUENCES.md` together. A new screenshot must be a reviewed repository
asset with provenance; documentation must not substitute a mock result for an
unavailable capability.

When ownership is unclear, add or update this index before adding another
cross-cutting dependency.

## Desktop interaction and icons

`app/src/webviewGuards.ts` owns browser-default suppression in the shared bootstrap. `app/src-tauri/src/webview_policy.rs` applies Windows WebView2 menu, status and zoom settings to each loaded window. `shortcutContext.ts` preserves form and editor keyboard ownership before application shortcuts. `icons/index.tsx` owns the semantic icon pack; `IconGallery.tsx` owns its searchable reference. See [WebView guards](WEBVIEW_GUARDS.md) and [SPIKE icon system](SPIKE_ICON_SYSTEM.md).

## Study workspace

`app/src/StudyManager.tsx` and `studyManager.css` own navigation, simulation tables, and the responsive inspector. `simulationStudies.ts` owns the version-one study projection; `studyWorkspaceModel.ts` owns bounded dataset admission, import copying, and metadata compatibility. `App.tsx` owns project integration and admitted domain activation. See [simulation studies](SIMULATION_STUDIES.md) and ADR 0033.

### Retained 3D thermal meshing

Project-bound volume generation: `python/spike_core/service_project_thermal_mesh.py`, `assembly_thermal_meshing.py`, and `assembly_thermal_cad.py`. Desktop setup: `app/src/AssemblyThermalMeshSetup.tsx`; actual mesh/temperature surfaces: `AssemblyThermalVolumeViewer.tsx`. See [3D thermal meshing](ASSEMBLY_THERMAL_MESHING.md) for effective layer and STEP-solid limits.

Generated material volumes: `assembly_thermal_encapsulation.py`,
`assembly_thermal_encapsulation_occ.py`, `service_project_encapsulation.py`,
and `AssemblyEncapsulationSetup.tsx`. Assembly CHT: `assembly_airflow.py`,
`assembly_airflow_mesh.py`, `assembly_airflow_runtime.py`,
`service_project_airflow.py`, and `AssemblyAirflowPanel.tsx`. Solid geometry
candidate budgets: `tetra_aabb_candidates.py`. Guarded package replacement:
`project_package_write_lock.py`. See
[capability integration and pending acceptance](ASSEMBLY_CAPABILITY_INTEGRATION.md).

### External volume engines

`calculix_deck.py`, `calculix_runtime.py`, and `calculix_thermal.py` own the typed
thermal deck, process runtime and independently admitted external result.
`assembly_field_thermal.py` owns shared pure occurrence binding.
`gmsh_extension_api.py`, `gmsh_extension_runtime.py`, and `gmsh_extension_mesh.py`
own typed geometry dispatch, fixed runtime bridging and complete mesh admission.
`extensions/calculix_suite/` and `extensions/gmsh_suite/` own declared routes.
`RetainedVolumeEngineSetup.tsx` and `GmshPcbMeshSetup.tsx` integrate existing
study controls into the native extension selectors.

### Detached assistant chats

- `app/src/AssistantWindowRoot.tsx`: independent in-memory chats and handoff UI.
- `app/src/assistantWindow.ts`: session-bound native window and workspace broker.
- `docs/INTEGRATED_ASSISTANT.md`: user workflow, privacy and acceptance limits.
- `spike assistant-tools`: machine-readable external assistant tool discovery.

Viewport temperature history extraction and popup presentation are owned by
`app/src/thermalProbeHistory.ts` and `ThermalHistoryPopup.tsx`; see
[viewport history workflow](THERMAL_VIEWPORT_HISTORY.md).


KiCad schematic viewing: [import and cross-selection workflow](KICAD_SCHEMATIC_IMPORT.md).
`kicad_schematic_importer.py` owns native export and sanitized portable admission;
`kicadSchematicModel.ts`, `KicadSchematicViewer.tsx`, `schematicWindow.ts` and
`SchematicHost.tsx` own read-only selection and the separate desktop window.
`traceValuePopupModel.ts` and `TraceValuePopup.tsx` own returned-value mini cards.

## Requested active-part library

Requested-library acquisition and functional coverage:
`python/spikes/manufacturer_model_catalog.py`, `logic_portfolio.py`;
native discrete execution: `src/spikes/digital_kernel.hpp`;
sampled C++ model packages: Studio `compiled_part_models.py`.
Exports and validation: `scripts/build_spikes_requested_library.py` and
`scripts/build_spikes_logic_native_test.py`. See
[requested-library campaign](library/REQUESTED_LIBRARY_CAMPAIGN.md).

## Context-aware viewport tools

`app/src/viewportSmartContext.ts` derives source membership, occurrence-specific result admission and unit-labelled context. `ViewportActionMenu.tsx` owns grouped/searchable keyboard menu presentation. `App.tsx` wires actions to existing setup workflows and result viewers. See [viewport context tools](VIEWPORT_CONTEXT_TOOLS.md).

## Native close recovery

`app/src-tauri/src/close_recovery.rs` owns main-window close generations, the native unresponsive-workspace dialog and bounded process shutdown. `workerBridge.ts` acknowledges close decisions and bounds child cleanup. See [close recovery](CLOSE_RECOVERY.md).

## Viewport keyboard suite

`shortcutCatalog.ts` owns validated bindings, KiCad/legacy presets and migration. `ShortcutManager.tsx` owns searchable chord capture and conflict review. `viewportEnvironment.ts` owns exact viewport background colors and bounded orientation-grid extent; `viewportKeyboardCamera.ts` owns display camera transforms; `App.tsx` dispatches current workspace actions. See [viewport shortcuts](VIEWPORT_SHORTCUTS.md).

Workspace panel tabs, independent size/maximize preferences and the persistent
tool taskbar: `app/src/WorkspaceDock.tsx`, composed by App.tsx and styled in
WorkbenchChrome.css. See [workspace panels](WORKSPACE_PANELS.md).

In-app update presentation and workspace save/close admission:
`app/src/AppUpdatePanel.tsx`, `appUpdateModel.ts` and workerBridge.ts.
Native cache/installer handoff: `app/src-tauri/src/app_updates.rs`;
official release discovery/download: `python/spike_core/app_updates.py`.
See [application updates](APP_UPDATES.md).

### Viewport focus and progressive board restoration

`netFocusMaterial.ts` preserves and restores single-board 3D material colors;
`assemblySceneVisibility.ts` composes occurrence-scoped focus with layer opacity.
`assemblyBoardVisualRestoration.ts` retains validated assembly geometry and visual
assets when the active board snapshot is outline-only. Focused checks are
`npm run test:net-focus` and the restoration check in `npm run test:assembly-layout`.

`assemblyNetLabels.ts` owns bounded, occurrence-scoped trace/zone labels shared by
assembly SVG and 3D sprite views. `test:assembly-net-labels` covers visible names,
canonical identities, layer visibility and boolean toggle admission.

`componentPlaceholder.ts` admits explicit unit-aware physical height metadata for
single-board and assembly stand-ins. `boardParser.ts` retains KiCad custom fields;
`assemblyBoardScene.ts` uses the shared height rule without replacing resolved CAD.

## Board-bound SPIKES Studio

`app/src/studioBoardCircuit.ts`, `BoardCircuitStudioPanel.tsx`,
`studioFeedback.ts` and `StudioFeedbackPanel.tsx` own the integrated visual
setup. Studio handoff and coupling remain worker-owned; see
[board Studio](SPIKES_BOARD_STUDIO.md).

## SpiDeR and MCP interoperability

`spider_api.py` and `spider_api_validation.py` own bounded neutral document
inspection. `service_spider.py` gates legacy-worker projections.
`mcp_protocol.py`, `mcp_protocol_catalog.py` and `mcp_resources.py` own framing,
lifecycle, pagination and installed schema resources; `mcp_server.py` remains
the tool composition root. See [interfaces](MCP_SPIDER_INTERFACES.md).

## Focus desktop shell

`FocusCommandPanel.tsx` and `focusCommands.ts` own hierarchical command discovery
and navigation. `FocusToolDeck.tsx` owns the reserved single-panel presentation,
hide/restore and resizing. `FocusWorkspace.css` owns compact chrome;
`tableTheme.css` owns palette tokens. `EmbeddedAssemblyTool.tsx` reuses existing
assembly components and App-owned actions without a native window bridge.
`App.tsx` remains the project/worker state authority. See WORKSPACE_PANELS.md.

`searchSentences.ts` owns bounded sentence-command parsing and canonical target suggestions; `UniversalSearch.tsx` owns keyboard completion and explicit execution. `App.tsx` resolves board occurrence scope and dispatches through existing selections, layer controls and PI preflight. See [search sentences](VIEWPORT_SHORTCUTS.md#search-sentences-and-commands).

`FloatingPanel.tsx` owns retained DOM portal adoption, drag-to-detach and return-to-dock lifecycle; `panelPresentation.ts` supplies the active document/window to editors; `panelWindowBridge.ts` and native `panel_popup.rs` own the presentation-only scale boundary and restricted linked native popup hosts. Blank children have no additional native permissions and panel state remains owned by the main workspace.


The context quick-tools bar is owned by `app/src/ViewportQuickTools.tsx` and
`quickToolModel.ts`. It presents existing workspace action callbacks and exact
availability reasons; it never dispatches solver or file operations directly.
`ProjectManager.tsx`/`projectManager.css` and `NetManager.tsx`/`netManager.css`
own compact manager layouts and container breakpoints. Shared first-party
chrome follows `tableTheme.css` and `buttonStandard.css`; engineering field and
plot series colors remain data semantics. See [controls](BUTTON_CONTROLS.md).

## Solver suite discovery

`app/src/solverSuiteCatalog.ts` and `SolverSuitePanel.tsx` own the presentation
index of bounded source capabilities and setup routes. `App.tsx` owns navigation
and universal search; runtime eligibility remains in the selected worker workflow.
`python/spike_core/studio_bridge.py` owns inert standalone Studio discovery and
revision-bound snapshot staging/launch. See [solver suite](SOLVER_SUITE.md).

## PI sentence setup and prescribed pin loading

`app/src/piSearchIntent.ts` owns bounded endpoint sentence planning and ambiguity
reporting. `PiSearchSetupPanel.tsx` owns missing-value review; App composes the
existing PI terminals and preflight. `piPinLoads.ts` and `PiComponentLoadPanel.tsx`
own rail-pad eligibility and editable current apportionment. This is input
preparation, not IC device inference or a new electrical solver. See
[PI search workflow](VIEWPORT_SHORTCUTS.md#pi-endpoint-sentences-and-missing-details).


## Cross-workflow sentence requests

`app/src/workspaceIntentModel.ts` owns bounded lexical workflow planning, scoped
identity, unit parsing and inert review records. `WorkspaceIntentReviewPanel.tsx`
owns missing-value and ambiguity review. `workspaceIntentAdapters.ts` translates
unique canonical SI net IDs, explicit thermal heat allocation and Studio feedback
temperature/time units without dispatching solvers. App routes reviewed requests
to existing setup editors, importers and exporters and rejects changed context.
`siSearchDraft.ts` owns reviewed SI field admission; `SParameterWorkbench.tsx`
applies each draft once and invalidates superseded results. Tests are grouped by
`npm --prefix app run test:workspace-intents`. See
[request coverage and limitations](VIEWPORT_SHORTCUTS.md#reviewed-requests-across-spike).


## Windows embedded-frontend package acceptance

`scripts/verify_windows_desktop.py` owns the bounded Windows package runtime
check, reusing the existing inert `PanelPopupQualification.tsx` / native popup
qualification route. It observes only windows belonging to its launched process,
uses a disposable WebView2 profile and requires the exact completed lifecycle
marker followed by a normal close. `scripts/build_windows_ci.ps1` invokes it
before publishing a CI artifact. Unit tests cover rejection of error dialogs,
process-only survival, partial success markers, failures and early exits. See
[acceptance scope](WINDOWS_INSTALLER.md#embedded-frontend-acceptance).

## Supplied decap operating corners

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `pdn_decap_corners.py`, `service_pdn_network.py` | Explicit corner admission, existing PDN composition, sampled target evidence and generated identity preservation | [PDN decap corners](PDN_DECAP_CORNERS.md) |

## BOM-constrained decap selection

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `pdn_decap_selection.py`, `service_pdn_network.py` | Finite population enumeration, cost/inventory admission, cumulative work bounds and deterministic corner-result ranking | [PDN decap selection](PDN_DECAP_SELECTION.md) |

Interface layout selection: `app/src/appSettings.ts`, `app/src/interfaceLayout.css`,
`App.tsx`, and `UniversalSettingsModal.tsx`; see [Interface layouts](INTERFACE_LAYOUTS.md).

## Sampled two-port fixture removal

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `sparameter_deembedding.py`, `service_sparameter_processing.py` | Explicit oriented two-fixture wave-chain solves, retained sources and per-sample conditioning/reconstruction evidence | [Two-port de-embedding](TWO_PORT_DEEMBEDDING.md) |

## Explicit sampled network preparation

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `sparameter_sampling.py`, `service_sparameter_processing.py` | Explicit bounded Cartesian-linear grid transformation, real supplied/source DC policy and per-target provenance | [S-parameter resampling](SPARAMETER_RESAMPLING.md) |

## Supplied-pole sampled network models

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `sparameter_rational.py`, `service_sparameter_processing.py` | Real proper rational coefficient fit at supplied stable real poles, sample-error admission and state-realization evidence | [Rational network fit](SPARAMETER_RATIONAL_FIT.md) |

## Rational network waveform execution

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `sparameter_transient.py`, `service_sparameter_processing.py` | Actual rational-fit composition, simultaneous prescribed-wave PWL propagation, exact event union and port V/I histories | [Network transient](RATIONAL_NETWORK_TRANSIENT.md) |

## Resistively terminated rational network execution

| Owner files | Responsibility | Reference |
| --- | --- | --- |
| `sparameter_terminated.py`, `service_sparameter_processing.py` | Finite Thevenin feedback, loop/stability admission, bounded augmented exponentials and port-boundary evidence | [Terminated network](TERMINATED_NETWORK_TRANSIENT.md) |

Live first-party control search is owned by `app/src/liveControlSearch.ts` and
`UniversalSearch.tsx`; [command access](COMMAND_ACCESS.md) describes runtime coverage.
