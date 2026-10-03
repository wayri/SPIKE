| `app/src/PythonWorkspace.tsx`, `PythonCodeEditor.tsx`, `PythonFileExplorer.tsx`, `PythonDebugPanel.tsx`, `PythonRecoveryPanel.tsx`, `pythonWorkspaceModel.ts` | Tabbed script editing, folder/worktree browsing, explicit save states, bounded durable backup recovery and debugger presentation | Desktop execution stays behind `workerBridge`; recovery copies have no disk path and do not modify `.spike` design state |
| `app/src/PlotlyChart.tsx`, `InteractivePlot.tsx`, `PlotlyChart.css`, `PlotAxisEditor.tsx`, `plotAxisSettings.ts`, `plotLayout.ts`, `plotInteraction.ts`, `plotClipboard.ts` | Shared axes, plot navigation, context menu and bounded presentation-only clipboard comparisons | Domain adapters retain sample/cursor/result authority; see `docs/PLOT_INTERFACES.md` |
| `app/src/CommandStrip.tsx`, `CommandStrip.css`, `WorkbenchChrome.css` | Shared command overflow, keyboard reachability, compact shell density and bounded dock layout | Command callbacks remain with their workflow; see `docs/WORKBENCH_SEGMENTS.md` |
| `app/src/DataTable.tsx`, `DataTable.css`, `tableTheme.css`, `dataTableModel.tsx`, `spreadsheetGrid.ts`, `TableIdentityInput.tsx` | Shared searchable, paged table presentation, theme palettes, keyboard navigation, and staged ID entry | Domain rows, units, validation, ordering, and writes remain with each workflow; see `docs/TABLE_INTERFACES.md` |
| `app/src/pythonWorkspaceTemplates.ts`, `PythonTemplateLibrary.tsx`, `PythonWorkspaceHelp.tsx` | Searchable analysis templates and dedicated Python help | Guarded runners use existing worker contracts and preserve solver status; see `docs/PYTHON_WORKSPACE.md` |
# Subsystem Index

This is the maintainer ownership map for the active SPIKE application. Legacy
experiments may remain in the repository but are not supported launch paths.

## Desktop UI

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
| `app/src/main.tsx` | React bootstrap | Installs the root error boundary |
| `app/src/detachedToolWindows.tsx` | Native/browser detached Results and Probe presentation bridge | Main workspace remains state authority; child does not start workers |
| `app/src/resultsToolSnapshots.ts` | Pure detached Results/Probe presentation snapshots | Reuses probe calculations and result analytics; no state authority |
| `app/src/detachedTracePayload.ts` | Bounded display-only trace-window result projection | Preserves retained sample topology; never replaces authoritative results |
| `app/src/App.tsx` | Current application composition root | Legacy oversized module; extract workflows incrementally |
| `app/src/AppErrorBoundary.tsx` | Fatal UI recovery | Must not alter saved projects |
| `app/src/workerBridge.ts` | Worker and native file IPC | Owns operation IDs and structured invoke failures |
| `app/src/resourceMonitor.ts` | Native/browser resource metrics | Allowed native IPC boundary |
| `app/src/resourceMonitorModel.ts` | CPU normalization, valid metric handling and system RAM accounting | Pure frontend model |
| `app/src/designSourceRegistry.ts` | Frontend source-adapter dispatch | EDA-specific parser use stops here |
| `app/src/boardParser.ts` | Current local KiCad parser | Compatibility path for UI/demo loading |
| `app/src/projectPackage.ts` | SPIKE package serialization | See `docs/PROJECT_FORMAT.md` |
| `app/src/spiceWorkspace.ts` | Persisted PI/SI circuit workspace contract | See `docs/SPICE_WORKSPACE.md` |
| `src/spikes/` | Owned SPIKES DC/nonlinear-diode and fixed-step RCL transient reference kernels plus stable C ABI | Separate circuit engine source |
| `python/spikes/` | Standalone hierarchical RCLVI CLI, native ABI bridge, sessions, virtual instruments, digital events, device extensions, and model-builder contracts | Separate circuit engine source |
| `python/spikes/streaming*.py` | Bounded rolling samples and trigger-driven continuous event capture | Separate circuit engine source |
| `python/spikes/waveform_store.py` | Lossless chunked waveform compression, hard byte limits, and torn-tail recovery | Separate circuit engine source |
| `standalone/spikes_project/studio/python/spikes_studio/` | Qt-free wxPython Studio engineering preview, explicit native/ngspice batch routing, data-only library store | See `standalone/spikes_project/studio/docs/QT_FREE_WORKBENCH_IMPLEMENTATION.md` and ADR 0021; not the separate C++ wxWidgets board client |
| `app/src/appSettings.ts` | Persisted UI preferences | Storage failure must be nonfatal |
| `app/src/ProjectManager.tsx` | Project/recent-project workflow | Presentation layer only |
| `app/src/UniversalSettingsModal.tsx` | Settings UI | Uses typed application settings |
| `app/src/HelpCenter.tsx` | Integrated user help | Screenshots must match released UI |
| `app/src/ExternalEngineCenter.tsx` | Optional-engine, accelerator, recommendation, registration, and tuning UI | Never installs or deletes third-party dependencies |

## Visualization

| File | Responsibility | Notes |
|---|---|---|
| `app/src/BoardViewport.tsx` | Three.js 3D scene and interaction | Legacy oversized; split scene, picking, overlays, controls |
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
| `app/src/ReportPreview.tsx` | In-app report preview |
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

| File | Responsibility |
|---|---|
| `python/spike_core/contracts.py` | Versioned SpiDeR, AnalysisSpec, and AnalysisResult |
| `python/spike_core/spider_v2.py`, `harness_authoring.py`, `multiboard_analysis.py` | AssemblyIR board occurrences, distinct direct connector mates and cable harnesses, pin ownership, and four-domain graph planning |
| `app/src/MultiboardStudyEditor.tsx`, `multiboardStudyPresentation.ts` | Coupled model property editing, study/result import/export, stale-result guards, occurrence result presentation |
| `python/spike_core/multiboard_circuit.py`, `multiboard_thermal.py`, `multiboard_em.py` | Executable experimental reduced coupled circuits, shared thermal RC networks and reciprocal magnetic-loop models; general field qualification remains gated |
| `python/spike_core/multiboard_study.py`, `multiboard_identity.py` | Assembly-derived study drafts, exact model/result binding and manifest-bound persistence |
| `python/spike_core/service_assembly_import.py`, `app/src/AssemblyStructureEditor.tsx`, `ConnectorGraphEditor.tsx`, `connectorGraphModel.ts` | Atomic multi-source board import; connector graph editing, reviewed pin suggestions, direct mates, and virtual harness route proposals |
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
| `python/spike_core/models.py` | 3D model discovery and KiCad scene export |
| `python/spike_core/extensions.py` | General extension discovery and isolation |
| `python/spike_core/service_extension_packages.py` | Managed extension package browse, preview, install, update, and removal worker handlers |
| `python/spike_core/extension_analysis_results.py` | External analysis result and board-binding admission |
| `python/spike_core/extension_mesh_exchange.py` | Bounded full mesh, preview, solver geometry, and digest handoff to analysis extensions |
| `python/spike_core/automation.py` | Python scripting facade over versioned worker operations |
| `python/spike_core/script_runtime.py`, `script_child.py`, `script_debug.py`, `script_debug_child.py`, `script_workspace_files.py`, `service_script_workspace.py` | Isolated script execution, supervised debugger and root-confined script files | Token-bound local sessions, bounded values/output, command acknowledgement and original result admission |
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
| `extensions/emerge_suite/` | Optional EMerge board adapter for bounded 2-16 copper-layer geometry, dielectric loss/stackup, optional EMCAD unions, readable GUI-generated script execution, solved S-parameters, radiation patterns and complex E/H sample planes; results remain unvalidated. See [antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md) |
| `extensions/optycal_suite/`, `app/src/OptycalExtension.tsx`, `optycalStudy.ts` | Optional one-way PEC STEP structure scattering driven by a design-bound complex EMerge far-zone source; GUI setup, exact script preview, coherent pattern comparisons, sample probes and exports. Unvalidated; excludes nearby coupling, tuning, diffraction, shadowing and multiple scattering. |
| `app/src/EMergeExtension.tsx`, `EMergeNearField.tsx`, `emergeNearFieldSamples.ts`, `emergeSampleExport.ts` | GUI setup, script/feature preview, radiation/network/field review, bounded coordinate admission, explicit sample probes and CSV/Touchstone exports |
| `app/src/AnalysisGuide.tsx`, `app/src/AnalysisGuide.css` | Floating, accessible Help-menu workflow guide with navigation and control highlighting; see `docs/ANALYSIS_GUIDE.md` |
| `python/spike_core/sparselizard_adapter.py` | SpiDeR-derived PCB mesh/material/terminal case export, cancellable process-tree-contained execution, digest binding, and strict scalar/vector/multiport result import; see `docs/SPARSELIZARD_ADAPTER.md` |
| `python/spike_core/sparselizard_validation.py` | Fail-closed signed-runtime, PETSc/MUMPS, convergence, and five-class PCB qualification report used by CLI, worker, and Solver Manager |
| `python/spike_core/peec_spice_export.py` | Reviewed PEEC RLCG endpoint mapping and staged geometry-parasitic handoff to process-isolated ngspice; see `docs/PEEC_NGSPICE_HYBRID.md` |
| `python/spike_core/converter_study.py` | Versioned PWM source compilation, ngspice/PEEC staged orchestration, converter analytics, and explicit compact-thermal loss handoff; see `docs/CONVERTER_STUDY.md` |

## Numerical modules

| File | Responsibility | Capability status source |
|---|---|---|
| `acceleration.py`, `compute_policy.py`, `gpu_acceleration.py` | NumPy multicore/Numba assembly and SuperLU/PETSc-MUMPS/optional CUDA sparse execution policy | `docs/ACCELERATION_ARCHITECTURE.md` |
| `dc_solver.py` | Resistive network solver | `docs/DC_SOLVER.md` |
| `python/spike_core/dc_result_utils.py` | Deterministic DC sampling, terminal, resistance, and percentile policies; keeps result-construction policy out of the solver module | `docs/DC_SOLVER.md` |
| `hybrid_mesh.py` | Connected trace/pad/via/zone discretization | `docs/MESHING_ENGINE.md` |
| `hybrid_dc_solver.py` | Hybrid-geometry DC solve | `docs/DC_SOLVER.md` |
| `peec_plugin.py` | Quasi-static PEEC plugin | `docs/SOLVER_STATUS.md` |
| `transient_peec.py` | Transient PEEC formulation | `docs/TRANSIENT_PI.md` |
| `quasistatic_capacitance.py` | Capacitance extraction | `docs/RLCG_EXTRACTION_VALIDITY.md` |
| `ngspice_plugin.py` | ngspice co-simulation adapter | `docs/SOLVER_STATUS.md` |
| `sparameters.py` | Network parameter calculations | `docs/SIGNAL_INTEGRITY_NETWORK_INTEGRATION.md` |
| `meshing.py` | General mesh representations | `docs/MESHING_ENGINE.md` |
| `internal_meshing_engine.py`, `service_meshing.py` | Versioned internal tetra worker boundary, bounded requests/candidates and digest provenance | `docs/INTERNAL_MESH_ENGINE.md` |
| `internal_tetra_generation.py` | Deterministic convex-hull tetra generation with exact predicate fallback | `docs/INTERNAL_MESH_ENGINE.md`; experimental |
| `pcb_volume_compiler.py`, `pcb_focus_sizing.py`, `pcb_volume_mesh.py` | Complete normalized planar PCB solids, net/source/manual sizing, bounded preparation and capability probe | `docs/PCB_FOCUSED_VOLUME_MESHING.md`; experimental external OCC generation |
| `dynamic_tetra_adaptation.py`, `tetra_mesh_refinement.py`, `tetra_mesh_optimization.py` | Error/manual/size-driven edge-star refinement, scalar refinement transfer and fixed-interface interior smoothing | `docs/INTERNAL_MESH_ENGINE.md`; experimental |
| `numerics.py` | Shared numerical safeguards | Tests define supported behavior |
| `pdn.py` | PDN target review, explicit mounting-path screening, and two-port candidate loading | `docs/PDN_SCREENING.md` |
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

## Study workspace

`app/src/StudyManager.tsx` and `studyManager.css` own navigation, simulation tables, and the responsive inspector. `simulationStudies.ts` owns the version-one study projection; `studyWorkspaceModel.ts` owns bounded dataset admission, import copying, and metadata compatibility. `App.tsx` owns project integration and admitted domain activation. See [simulation studies](SIMULATION_STUDIES.md) and ADR 0033.
