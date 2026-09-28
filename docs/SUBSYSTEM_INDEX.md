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
| `src/spikes/` | Owned SPIKES DC/nonlinear-diode and fixed-step RCL transient reference kernels plus stable C ABI | See `docs/SOLVER_STATUS.md` and `docs/SPIKES_C_ABI.md` |
| `python/spikes/` | Standalone hierarchical RCLVI CLI, native ABI bridge, sessions, virtual instruments, digital events, device extensions, and model-builder contracts | See `docs/SPIKES_CLI.md` |
| `python/spikes/streaming*.py` | Bounded rolling samples and trigger-driven continuous event capture | See `docs/SPIKES_STREAMING_RESULTS.md` |
| `python/spikes/waveform_store.py` | Lossless chunked waveform compression, hard byte limits, and torn-tail recovery | See `docs/SPIKES_STREAMING_RESULTS.md` |
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
| `app/src/viewportPerformance.ts` | Linear scene indexes and list-window helpers | See `LARGE_SCENE_PERFORMANCE.md` |
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
| `python/spike_core/contracts.py` | Versioned DesignIR, AnalysisSpec, and AnalysisResult |
| `python/spike_core/design_ir_v2.py`, `harness_authoring.py`, `multiboard_analysis.py` | AssemblyIR board occurrences, distinct direct connector mates and cable harnesses, pin ownership, and four-domain planning; coupled physics remains gated |
| `python/spike_core/errors.py` | Canonical FE/BE diagnostic envelopes and catalog | See `docs/ERROR_HANDLING.md` |
| `python/spike_core/spice_workspace.py` | Validated SPICE intent and deterministic netlist composition | See `docs/SPICE_WORKSPACE.md` |
| `python/spike_core/service.py` | JSON worker request dispatch and service composition |
| `python/spike_core/cli.py` | Headless command interface, including solver-manager and external-engine workflows |
| `python/spike_core/importers.py` | EDA-neutral importer protocol and registry |
| `python/spike_core/kicad_importer.py` | KiCad-to-DesignIR adapter |
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
| `python/spike_core/script_runtime.py`, `script_child.py` | In-app Python execution, output capture, cancellation boundary, and result admission |
| `python/spike_core/dependencies.py` | Runtime dependency status and lock verification |
| `python/spike_core/capabilities.py` | Implemented capability reporting |
| `python/spike_core/external_engines.py` | External-engine discovery, preflight, private jobs, isolated execution, quotas, and result import |
| `python/spike_core/external_engine_discovery.py` | Discovery-only metadata for adapter-pending engines, including sparseLizard |
| `python/spike_core/openfoam_runtime.py` | Bounded native/WSL OpenFOAM runtime discovery; never promotes discovery to case readiness |
| `python/spike_core/solver_manager.py` | Workload recommendations, execution gates, and EMI pre-pass screening |
| `python/spike_core/emi.py` | Versioned EMI setup validation, geometry coverage, stage gates, and screening orchestration |
| `python/spike_core/solver_state.py` | Private bounded registrations and allowlisted tuning persistence |
| `extensions/openems_suite/` | OpenEMS PI/SI extension, engine adapter, case integrity, geometry and result validation, benchmarks, and reference evidence; `python/spike_core/openems_*.py` and `external_engines.py` are compatibility import bridges |
| `extensions/emerge_suite/` | Optional EMerge board adapter for bounded two-layer geometry, solved S-parameters, radiation cuts, and sampled 3D patterns; results remain unvalidated. See [antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md) |
| `app/src/AnalysisGuide.tsx`, `app/src/AnalysisGuide.css` | Floating, accessible Help-menu workflow guide with navigation and control highlighting; see `docs/ANALYSIS_GUIDE.md` |
| `python/spike_core/sparselizard_adapter.py` | DesignIR-derived PCB mesh/material/terminal case export, cancellable process-tree-contained execution, digest binding, and strict scalar/vector/multiport result import; see `docs/SPARSELIZARD_ADAPTER.md` |
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
| `THIRD_PARTY_NOTICES.md` | Release-blocking external software and asset provenance register |

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
