# SPIKE Native wxWidgets Client

This is the parallel C++20 Windows client for SPIKE 0.2.5. It uses native
wxWidgets controls and wxAUI docking, VTK on a wx-owned OpenGL context for board
and field rendering, and offline Plotly for interactive engineering reports.
It does not import or modify the Tauri/React application or the frozen wxPython
UI. Numerical work remains in the existing SPIKE JSON-lines worker process.

The native shell follows the current workbench layout: domain ribbon pages,
scene navigator, central 2D/3D viewport, analysis setup, issues/probes/power-tree
output, console, and report preview. It consumes current DesignIR v2, `spike/v1`,
analysis capability, result-index, report-index, and `.spike` v3 contracts.

## Configure and build

```powershell
cd wx_desktop
cmake --preset windows-release
cmake --build --preset windows-release
ctest --preset windows-release
```

The vcpkg manifest installs wxWidgets, VTK, and nlohmann-json for this target.
The executable discovers the repository by walking upward from its executable
and working directory, so development builds can be started from any directory:

```powershell
.\wx_desktop\build\windows-release\Release\spike-wx.exe
```

Open a design or project at launch with either a positional path or `--open`:

```powershell
.\wx_desktop\build\windows-release\Release\spike-wx.exe --open .\board.kicad_pcb
.\wx_desktop\build\windows-release\Release\spike-wx.exe .\project.spike
```

Use `--worker "<path-to-spike-worker.exe>"` to select a packaged worker,
`--repository "<path>"` to override repository discovery, and `--log "<path>"`
to select a runtime trace. In a source checkout, the client prefers the pinned
repository `.venv` so the native UI and the latest 0.2.5 source contracts stay
in lockstep and Arrow/package support is present. Installed builds use the
verified bundled worker; system Python is the final source-checkout fallback.

The normal diagnostic log is under the per-user local application-data folder.
Startup, worker exit, protocol-limit, UI exception, and fatal-native events are
recorded there. Missing WebView2 no longer prevents startup; report preview
falls back to a native message while HTML export remains available.

The client embeds the reviewed Plotly runtime from
`app/node_modules/plotly.js-dist-min/plotly.min.js` into exported reports. It
never loads Plotly or report resources from the network.

Matplotlib remains a worker/report-generation dependency, not an embedded UI
runtime. This keeps Python out of the native UI process while allowing static
publication figures to be produced by worker-side report operations. Plotly is
the self-contained interactive report surface.

## 0.2.5 capability coverage

The native client has shell and workflow parity for project import/open/save,
current worker discovery, design validation, PI DC/AC/transient requests, SI
protocol-suite validation/planning/execution, compact and field thermal
workflows, EMI screening, VTK result fields, and offline Plotly reports.

The Assembly setup page consumes and preserves `spike/assembly-ir/v1` and
`spike/assembly-designs/v1`. It renders bounded board-envelope proxies in VTK,
performs workload-specific resource admission, and plans PI or SI work through
`spike/multiboard-analysis-request/v1`. A plain board can be promoted to an
explicit single-board assembly without changing the existing applications.

| Workflow | Native 0.2.5 behavior |
| --- | --- |
| Single-board PI | DC, experimental AC, and experimental transient use the current preflight and analysis contracts. |
| Multi-board PI | Independent-board graphs are admitted and planned for caller-controlled board dispatch. |
| Single-board SI | Exact uniform-channel and protocol-suite requests validate, plan, and execute through the worker. |
| Multi-board SI | Exact per-board lane jobs run sequentially through the independent SI batch contract. |
| Harness networks | Explicit conductor models compile; reviewed board ports, connectors, returns, and mutual terms can be bound into an inspectable reduced network. |
| Thermal | Scenario validation, compact estimation, field-job planning, OpenFOAM case preparation, and explicitly enabled case execution are exposed. |
| Coupled multi-board PI/SI | Fail-closed. SPIKE 0.2.5 has no qualified coupled solver; network compilation/binding does not claim solver execution. |

Advanced request editors intentionally retain exact JSON. Connector models,
lane definitions, return paths, and external-solver choices are engineering
inputs that the client cannot safely infer. Full probe authoring/picking and
visual assembly-structure editing remain future native-control work; the
capability matrix remains authoritative.

The preserved wxPython implementation remains an explicit interaction and
workflow reference. See [Original SPIKE reference](ORIGINAL_SPIKE_REFERENCE.md)
for the foundations to retain, the legacy implementation choices to avoid, and
the precedence rules used during the C++ port.
