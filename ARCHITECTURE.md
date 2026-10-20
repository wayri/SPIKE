# SPIKE Architecture

Studio reusable component packages remain inert on import. Visual symbol/pin
editing, source capture and explicitly approved SPICE/C++/Verilog build paths
are separate services; see [ADR 0125](docs/adr/0125-reusable-component-maker.md)
and [the component maker workflow](standalone/spikes_project/studio/docs/COMPONENT_MAKER.md).

The experimental STM32F407 owned-native peripheral mode replaces selected
Renode MMIO blocks with SPIKE C++ TIM2/SPI1/I2C1/GPIO state and routes only
PA0 AF1, PA5/PA6/PA7 AF5 and open-drain PB6/PB7 AF4 through finite native pads.
Python is transport-only; timed receivers use the accepted electrical left
limit before event outputs change. See [ADR 0119](docs/adr/0119-owned-native-peripheral-mmio-and-pads.md),
the [timing evidence](docs/validation/NATIVE_PERIPHERAL_TIMING_20261020.md) and
[pin workflow](standalone/spikes_project/studio/docs/GPIO_PIN_WORKFLOW.md).

An explicit experimental instruction-boundary firmware feedback mode is
separate from interval-held timestamp capture; see
[ADR 0114](docs/adr/0114-instruction-boundary-firmware-feedback.md).

Experimental GPIO pad properties persist with controller boards. Native C++
pad-event queueing and the explicit virtual-timestamp software-GPIO capture
adapter remain separate from the CPU backend; see
[pin/edge workflow](standalone/spikes_project/studio/docs/GPIO_PIN_WORKFLOW.md)
and [event formulation and limits](docs/validation/NATIVE_GPIO_EDGE_COUPLING_20261019.md).

Manufacturer product discovery and local LTspice indexing are separate from
generic presets and executable model qualification; see
[ADR 0111](docs/adr/0111-manufacturer-discovery-and-local-model-index.md).

SPIKES Studio has an explicit experimental native Renode firmware backend for
three admitted Cortex-M board targets, separate from inert pinout templates and
sampled C/C++ callbacks. Its process, trust, ELF physical-loading and sampled
DI/DO boundaries are recorded in [ADR 0110](docs/adr/0110-explicit-native-firmware-backend.md).

The IC/ASIC target has two visible applications, SPIKES and external KLayout,
with explicitly approved managed backends. Revision-bound project preflight
and read-only KLayout batch inspection are implemented; physical closure and
PEX execution remain separate pending gates. See
[ADR 0074](docs/adr/0074-two-application-asic-flow-and-klayout-handoff.md).

Open-PDK discovery and selected-corner preparation are inert Python application
services; the explicit ngspice C backend owns PDK circuit numerical execution.
Run digests retain model dependencies and configuration. See
[ADR 0072](docs/adr/0072-inert-open-pdk-circuit-workflows.md). This does not imply
owned C++ compact-model parity or device/process TCAD.

The SPIKES C++ transient engine owns adaptive stepping, accepted-state recovery
and sparse companion-factorization reuse. Python exposes validated controls and
reporting-grid interpolation without owning numerical state. See
[ADR 0065](docs/adr/0065-adaptive-native-transient-recovery.md) for additive ABI
and result semantics.

The experimental fixed-grid scalar co-simulation master and recorded digital
twin comparison are Python application services exposed through the existing
worker, CLI and desktop script workspace. They use versioned neutral contracts
and a trusted adapter registry; specialized solver coupling remains separate.
See [ADR 0063](docs/adr/0063-offline-cosimulation-and-digital-twins.md).

This document is the canonical description of the current SPIKE runtime. It
describes implemented boundaries and names known debt explicitly. Product
plans and unimplemented solver modes are documented elsewhere and are not
presented here as current capability.

## How to use this document

- Start at `docs/README.md` for audience- and task-based documentation
  navigation.
- Use this file for runtime boundaries, dependency direction, and state
  authority.
- Use `docs/SUBSYSTEM_INDEX.md` for file ownership and
  `docs/DEVELOPER_GUIDE.md` for extension sequences.
- Use `docs/SOLVER_STATUS.md` for implemented and validated physics. An
  architecture target or registered plugin is not a capability claim.
- Record a boundary change in `docs/adr` and update the architecture guard in
  the same change.

## Architectural goals

SPIKE is an offline-first engineering application with these constraints:

- EDA-neutral analysis contracts. KiCad, IPC-2581, ODB++, Altium, Allegro,
  and Xpedition data must enter through importer adapters.
- One analysis model shared by the desktop UI, CLI, reports, tests, and future
  remote workers.
- Solvers are replaceable modules selected by declared capabilities.
- Unsupported physics remains unavailable or approximate; the UI cannot
  promote it to validated.
- Long-running numerical work never executes on the webview event thread.
- The repository is understandable and buildable without an AI service,
  prompt history, or generated hidden state.

## Runtime architecture

Cellwise conductivity-temperature feedback composes the existing one-way
dielectric/thermal workflow in Python. It preserves original geometry/source
identity, records generated material mappings and checks raw temperature/power
residuals before convergence. See
[ADR 0086](docs/adr/0086-cellwise-dielectric-conductivity-feedback.md).

One-way dielectric AC heating reuses the Python field and retained thermal
solvers on an identical mesh. Coherent RMS excitation generates conservative
cell heat, checked against port power before thermal execution. It preserves
experimental status and does not feed temperature back into electrical laws.
See [ADR 0085](docs/adr/0085-conservative-dielectric-thermal-coupling.md).

Explicit passive sampled PDN port reduction remains in the Python numerical
boundary, with an exact port partition, conditioned Schur solve and conjugate
power identity. Its source projection does not establish a causal macromodel.
See [ADR 0084](docs/adr/0084-explicit-passive-pdn-port-reduction.md).

The separate finite-dielectric AC module owns complex P1 field execution at
supplied frequencies, reusing electrostatic geometry admission and the existing
Python worker. It returns admittance and conjugate field-power evidence without
promoting sample data to a transient macromodel. See
[ADR 0083](docs/adr/0083-finite-dielectric-ac-admittance.md).

Explicit simultaneous PDN loads use the existing Python worker and passive
descriptor engine. The additive schema preserves legacy scalar execution;
ordered load identities and combined source work remain numerical authority.
See [ADR 0082](docs/adr/0082-explicit-simultaneous-pdn-loads.md).

Optional EMerge package maintenance stays in the Python worker. The
`emerge_runtime_updates` service owns bounded background update state and
exclusion with active EMerge operations; its IO adapter validates a dedicated
solver environment and invokes fixed-index pip and fresh-process API checks.
See [ADR 0034](docs/adr/0034-local-emerge-runtime-updates.md) and the
[runtime update contract](docs/EMERGE_RUNTIME_UPDATES.md). Package installation
and detected APIs do not establish validated physics.

Large-scene resource ownership, batching, projection complexity, package
admission limits, and remaining scaling work are documented in
Large scene performance. Cached assembly
geometry/textures have shared lifetimes; occurrence materials remain independent.
The desktop admits ZIP64 project paths up to 16 GiB while preserving bounded
legacy JSON and worker transport.

OS CPU/private RAM/GPU counters remain in the Rust host; normalization and
display remain in the frontend. CPU allocation and optional CUDA sparse
execution stay in the worker numerical boundary, as documented in
[Resource monitoring and compute allocation](docs/RESOURCE_MONITOR_AND_ACCELERATION.md).

Desktop persistence separates result payloads and imported PCB visuals from
control-plane metadata. Python `service_project_persistence.py` coordinates
`project_state_artifacts.py` and `project_visual_artifacts.py`; the native host
binds targeted artifact reads to the previously opened manifest. TypeScript
`projectPersistenceArtifacts.ts` restores results and materializes saved scenes;
it does not reinterpret manufacturing geometry. See
[ADR 0018](docs/adr/0018-portable-results-and-board-visuals.md).

Multi-board authoring uses `service_assembly_import.py` for manifest-bound
imports and `harness_authoring.py` / `harness_routing.py` for reviewable wiring
proposals. `assembly_exchange.py` imports bounded neutral ZIP assemblies;
FreeCAD's workbench exports placed STEP occurrences into that format.
Model-less `subassembly` parts are hierarchy containers. Other part model
references remain mandatory. See [assembly workflows](docs/MULTIBOARD_HARNESS_ASSEMBLIES.md)
for exchange units, limits and qualification boundaries.

FreeCAD collaboration uses `service_mcad_collaboration.py` for manifest-bound
session export, feedback preview and atomic placement updates. Stable occurrence
IDs survive the round trip; revised electrical/assembly baselines are rejected.
The optional workbench exchanges inert JSON and embedded STEP. Placement changes
archive old result context and clear active fields. See
[ADR 0019](docs/adr/0019-freecad-collaboration-sessions.md) and
[the collaboration workflow](docs/FREECAD_COLLABORATION.md).

Source/visual identity invariants (2026-09-05): imported KiCad text is encoded
once as UTF-8; temporary importer input and embedded source artifacts must use
the same bytes, including newlines. A new board import clears previous package
and board-bound assembly/results state. Verified visual-bundle `blob:` URLs
represent self-contained GLB scenes and must not be dispatched to VRML based on
their missing extension. Component-pick replacement is a single linear pass;
layer selectors expand against the physical copper stack before inventory counts.

```mermaid
flowchart LR
    User["Engineer"] --> Desktop["Tauri desktop host"]
    User --> CLI["Headless CLI"]
    Adapter["CAD import / selection adapters"] --> Package["SPIKE project package"]
    Desktop --> React["React/TypeScript application"]
    React --> View["2D layout and Three.js 3D viewport"]
    React --> DesktopBridge["workerBridge and native services"]
    DesktopBridge --> Rust["Rust process host"]
    Rust --> Worker["Versioned Python JSON worker"]
    CLI --> WorkerCore["Python application services"]
    Worker --> WorkerCore
    WorkerCore --> Importers["Importer registry"]
    WorkerCore --> Solvers["Solver registry"]
    WorkerCore --> Reports["Validation, reports, and exports"]
    Importers --> IR["SpiDeR"]
    Solvers --> Result["AnalysisResult"]
    Package --> IR
    IR --> Solvers
    Result --> View
    Result --> Reports
```

The Tauri host owns operating-system integration and process isolation. React
owns interaction state and visualization. Python owns normalized application
services and solver orchestration. C++ kernels can accelerate numerical work,
but they do not define UI or EDA file semantics.

### Request lifecycle

```mermaid
sequenceDiagram
    participant UI as React workflow
    participant Bridge as workerBridge
    participant Host as Tauri process host
    participant Worker as Python service
    participant Solver as Solver plugin/engine
    UI->>Bridge: method, params, operation ID
    Bridge->>Host: bounded invoke request
    Host->>Worker: one JSON request on stdin
    Worker->>Worker: validate contract and capability
    Worker->>Solver: SpiDeR plus AnalysisSpec
    Solver-->>Worker: AnalysisResult or structured failure
    Worker-->>Host: one bounded JSON response
    Host-->>Bridge: response plus timing/failure metadata
    Bridge-->>UI: install result or preserve current state
```

The UI does not install partial output as a completed result. The native host
supervises process lifetime and transport limits but does not interpret
engineering data. The worker validates contracts and capabilities before a
solver receives the request. External engines remain child processes of an
adapter and must return through the same result/error boundaries.

### State authority

| State | Authority | Persisted form | Must not own |
|---|---|---|---|
| Imported design and provenance | Python import/application services | `SpiDeR` inside the project package | Viewport-only selections or solver-private objects |
| Analysis setup and result | Versioned Python contracts | `AnalysisSpec` and `AnalysisResult` data in project/result records | UI-derived numerical claims |
| Dock, active view, and cameras | React composition and renderers | `spike/workspace-state/v1` in `workspace/state.json` | Solver validity or source geometry |
| Approved filesystem path and worker process | Tauri host | Native dialog grants and packaged resources | Domain, importer, or solver logic |
| Numerical implementation | Solver plugin or C++ kernel | Result fields plus provenance | EDA parser objects or presentation state |

When two layers cache the same information, the versioned contract remains
authoritative. Derived UI state must be reproducible from that contract or be
explicitly stored as workspace state.

## Language budget

SPIKE deliberately limits language ownership:

- TypeScript/TSX owns the desktop UI and visualization.
- Python owns contracts, importers, worker/CLI services, orchestration, and
  external-process adapters.
- C++ owns only performance-critical numerical kernels.
- Rust is a frozen thin Tauri host for OS integration, bounded IPC, process
  supervision, and packaging; it must not acquire domain or solver logic.
- PowerShell, Batch, and POSIX shell files remain thin platform shims. Shared
  build/release behavior belongs in Python.

No new implementation language is permitted without an accepted ADR and an
architecture-guard change. The legacy wxPython/VTK UI is frozen and is not a
supported runtime. See `docs/LANGUAGE_POLICY.md` and ADR 0007 for the reduction
and retirement plan. The former C++20 wxWidgets/VTK preview under
`wx_desktop/` was retired on 2026-09-28; ADR 0008 records its original
boundary. The supported desktop remains the Tauri application.

## Dependency direction

Dependencies point inward toward versioned contracts:

```mermaid
flowchart TB
    Sources["EDA files and plugin exchanges"] --> Adapters["Source adapters"]
    Adapters --> Contracts["SpiDeR / AnalysisSpec / AnalysisResult"]
    UI["Desktop UI"] --> Contracts
    CLI["CLI"] --> Contracts
    Solvers["Solver plugins"] --> Contracts
    Reports["Reports and CI"] --> Contracts
    Contracts --> Math["Numerical kernels"]
```

Rules enforced by `scripts/check_architecture.py`:

- UI modules do not import EDA parsers directly.
- Python application services do not import source parsers outside registered
  adapter modules.
- Tauri invocation is contained in desktop bridge modules.
- large-array extrema do not use JavaScript spread arguments.
- new source modules stay below the module-size guard unless debt is recorded.
- required architecture decisions and maintainer documentation exist.
- production roots do not introduce an unapproved implementation language.
- supported Python services do not depend on the frozen wxPython/VTK UI.

Run the guard with:

```powershell
cd app
npm.cmd run check:architecture
```

## Versioned contracts

The Python definitions in `python/spike_core/contracts.py` are the current
worker-side source of truth:

- `SpiDeR`: normalized layers, stackup, conductive geometry, components,
  component bonds, connectors, regions, bends, issues, and provenance. The
  component-bond handoff is documented in `docs/COMPONENT_BONDS.md`.
- `AnalysisSpec`: solver mode, nets, terminals, return path, probes, mesh,
  limits, frequency data, and transient options.
- `AnalysisResult`: status, model status, scalar/vector fields, networks,
  probes, issues, and provenance.

Contracts contain JSON-compatible values and carry `spike/v1`. New fields may
be added compatibly. Breaking semantic or unit changes require a new contract
version and migration code. UI-only state must not be inserted into solver
contracts.

## Import architecture

`python/spike_core/importers.py` defines the backend importer protocol and
registry. `app/src/designSourceRegistry.ts` provides the corresponding local
UI source dispatch. The implemented KiCad adapter is isolated in
`python/spike_core/kicad_importer.py`; downstream services receive `SpiDeR`,
not parser objects.

```mermaid
sequenceDiagram
    participant Source as Design source
    participant Registry as Importer registry
    participant Adapter as Source adapter
    participant Validator as Import validator
    participant Consumer as UI / solver / report
    Source->>Registry: path plus optional format hint
    Registry->>Adapter: select by declared format and extension
    Adapter->>Adapter: parse, normalize units and coordinates
    Adapter-->>Registry: SpiDeR plus issues and provenance
    Registry->>Validator: validate contract and import quality
    Validator-->>Consumer: normalized design
```

Current support is intentionally explicit:

| Source | Status | Preferred path |
|---|---|---|
| KiCad PCB | Implemented | Native adapter |
| IPC-2581 | Planned | Standards-first adapter |
| ODB++ | Planned | Standards-first adapter |
| Gerber/drill/BOM/netlist | Planned fallback | Coordinated adapter set |
| Altium Designer | Planned | IPC-2581/ODB++ first, native only for gaps |
| Cadence Allegro | Planned | IPC-2581/ODB++ first, native only for gaps |
| Siemens Xpedition | Planned | ODB++/IPC-2581 first, native only for gaps |

An unsupported format must fail with a useful diagnostic. It must never be
silently treated as KiCad or imported as a partial valid design.

## Solver architecture

`python/spike_core/solver_plugins.py` owns solver registration, cataloging,
capability matching, and execution. Solvers consume `SpiDeR` and
`AnalysisSpec`, then return `AnalysisResult`. The public SDK lives in
`solver_sdk/`.

Each solver descriptor declares:

- supported modes and required geometry;
- approximation or validation status;
- frequency and geometry limits;
- mesh or formulation support;
- version and provenance.

The registry is the extension point. UI conditionals that identify a solver
by implementation name are a design smell; UI behavior should depend on
capabilities and result fields.

## Worker and process isolation

The desktop sends one JSON request through `app/src/workerBridge.ts`. The Rust
host in `app/src-tauri/src/lib.rs` launches the Python worker without a console
window, caps request and output sizes, drains output concurrently, applies a
watchdog, and keeps heavy work off the UI thread. One heavy operation is
admitted at a time in both the frontend and native host.

The Python worker returns structured errors and response metadata including
operation duration. It does not keep numerical state in the KiCad plugin.
Packaged worker resources are preferred, with source-tree execution retained
as a development fallback.

Cancellation is scoped to the admitted operation ID. The host polls a cancellation
flag during request writes and execution and terminates the owned worker tree.
The frontend retains the busy state until native settlement and discards late
results after Stop. This is process cancellation, not solver checkpoint/resume.
See `docs/SHARED_MESH_SOLVE_WORKSPACE.md` for the shared PI/SI control surfaces.

## Rendering architecture

The desktop has two related but independent views:

- `LayoutViewport.tsx`: deterministic 2D vector layout and selection.
- `BoardViewport.tsx`: native Three.js/WebGL 3D board, models, result fields,
  probes, mesh overlays, and selection.

Both consume normalized board data and share selection/result state through
the application composition root. Renderers must not parse source files or
derive numerical claims. Result visualization uses solver-provided scalar,
vector, and mesh envelopes; absent fields remain unavailable.

Large-result safeguards include iterative numeric range calculation rather
than spread calls, capped native messages, and renderer-side decimation. More
work remains on spatial indexing, instancing, geometry tiling, and explicit
GPU-budget policies for workstation-class boards.

## Project and result persistence

The SPIKE project package is defined in `docs/PROJECT_FORMAT.md`. A project may
embed the source board plus normalized data, analysis definitions, probes,
result references, and provenance. Opening a project must not depend on the
original EDA application being installed. Source round-tripping is adapter
specific and never changes the normalized analysis contract.

Exact desktop recall is carried by the separate
`spike/workspace-state/v1` contract in `workspace/state.json`. The React shell
owns dock layout and 2D/3D camera state; the canonical package service only
preserves the validated member. Renderers publish view state and consume an
explicit restore command. They do not read package files or infer solver
state. Malformed optional view data falls back to fit-to-design without
weakening package integrity or numerical validity.

Reports consume saved project and result data. A report is a presentation of
recorded numerical output, not an independent solver.

## Stability boundaries

- `AppErrorBoundary.tsx` provides root UI recovery and crash diagnostics.
- worker requests have operation IDs, activity events, size limits, and
  structured failures.
- the Rust host uses `spawn_blocking`, concurrent pipe readers, and watchdogs.
- parser syntax errors fail import instead of yielding a partially valid board.
- import diagnostics remain attached to `SpiDeR`.
- tests cover importer dispatch, parser failure, 32-layer ordering, rigid-flex
  metadata, and native worker limits.

See `docs/STABILITY_AND_RECOVERY.md` for operational details.

## Repository map

| Path | Responsibility |
|---|---|
| `app/src` | React application, workflows, reports, and visualization |
| `app/src-tauri` | Native window, dialogs, file permissions, worker process host |
| `python/spike_core` | Contracts, importers, orchestration, solver plugins, CLI services |
| `python/core` | Current low-level KiCad parser implementation |
| `src` | Native C++ numerical kernels and bindings |
| `solver_sdk` | Public solver plugin contract and examples |
| `extension_sdk` | General extension contract |
| `kicad_plugin` | Thin KiCad launch and exchange bridge |
| `tests/python` | Contract, numerical, importer, and workflow regression tests |
| `docs` | Indexed user, developer, validation, security, and subsystem records |

The detailed file ownership map is in `docs/SUBSYSTEM_INDEX.md`.

## Known architecture debt

The current codebase is not claimed to be fully SOLID. These large composition
modules predate the current boundaries and need staged extraction:

- `app/src/App.tsx`: application composition, workflows, and substantial UI
  state are still coupled.
- `app/src/BoardViewport.tsx`: scene construction, interaction, selection, and
  result rendering remain in one module.
- `app/src/LayoutViewport.tsx`: 2D scene construction and interaction are
  still coupled.
- `python/spike_core/cli.py` and `transient_peec.py`: command/formulation
  responsibilities should be decomposed as their contracts stabilize.
- `python/spike_core/hybrid_mesh.py`: topology construction and discretization
  should separate after hybrid-geometry regression coverage is broader.

New functionality must not expand these modules without a documented reason.
Refactoring should proceed behind tests and stable contracts, not as a full
rewrite.

## Architecture decisions

- `docs/README.md` (documentation entry point)
- `docs/adr/0001-normalized-design-ir.md`
- `docs/adr/0002-worker-process-isolation.md`
- `docs/adr/0003-importer-registry.md`
- `docs/adr/0007-language-budget-and-runtime-boundaries.md`
- `docs/SOLVER_PLUGIN_ARCHITECTURE.md`
- `docs/VISUALIZATION_ARCHITECTURE.md`
- `docs/EXTENSION_ARCHITECTURE.md`

Architectural changes require an ADR when they alter a dependency direction,
public contract, process boundary, persistence format, or plugin interface.

## Documentation map

Use this page for runtime boundaries and dependency direction.
[DEVELOPMENT.md](DEVELOPMENT.md) covers setup, execution, checks, and
engineering workflows. [docs/USER_TASK_SEQUENCES.md](docs/USER_TASK_SEQUENCES.md)
contains evidence-bound user task sequences. Structured failure navigation
starts in [TROUBLESHOOTING.md](TROUBLESHOOTING.md), with immutable code metadata
in [docs/ERROR_CODE_CATALOG.md](docs/ERROR_CODE_CATALOG.md).

## Supplied capacitor corner composition

The Python `pdn_decap_corners` application service composes the existing PDN
decap stamp across explicit supplied operating corners behind a versioned
worker contract. No numerical stamps or bias/temperature laws are duplicated.
See [ADR 0087](docs/adr/0087-supplied-decap-operating-corners.md).

## Bounded supplied decap selection

The Python `pdn_decap_selection` service exhaustively enumerates a bounded
supplied BOM/site domain and composes the existing operating-corner service.
Integer cost/inventory constraints and ranking remain application logic;
electrical stamps remain in the PDN core. See
[ADR 0088](docs/adr/0088-bounded-decap-bom-selection.md).

## Explicit two-port fixture removal

`sparameter_deembedding` owns bounded sampled wave-chain transforms in Python;
`service_sparameter_processing` supplies the versioned worker boundary through
the simulation dispatcher. Original sources remain separate from derived
networks. See [ADR 0089](docs/adr/0089-explicit-two-port-fixture-removal.md).

## Explicit network grid preparation

`sparameter_sampling` owns the sampled network transformation in Python;
the existing network-processing worker boundary exposes versioned requests.
Existing channel and composition services retain their admission policies.
See [ADR 0090](docs/adr/0090-explicit-network-resampling-and-dc.md).

## Supplied-pole rational network models

`sparameter_rational` owns bounded fixed-pole least-squares model construction
in Python behind the existing network-processing worker boundary. Source
identity, real coefficients and numerical admission remain authoritative;
automatic transient integration remains separate. See
[ADR 0091](docs/adr/0091-supplied-stable-pole-network-models.md).

## Prescribed-wave rational network transients

`sparameter_transient` composes the actual rational fitter with zero-state
analytic PWL propagation in Python. The existing network worker exposes
versioned requests and returned histories. Arbitrary source/load feedback
and physical transient qualification remain separate. See
[ADR 0092](docs/adr/0092-prescribed-wave-rational-transients.md).

## Resistive feedback around rational network models

`sparameter_terminated` composes the actual fitted model and shared waveform
admission with a conditioned resistive feedback connection and bounded
augmented-exponential propagation. Worker contracts retain the source/fit and
declared boundaries. See
[ADR 0093](docs/adr/0093-resistive-rational-network-feedback.md).
