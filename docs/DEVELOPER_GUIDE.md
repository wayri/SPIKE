# SPIKE Developer Guide

This guide is for engineers working on SPIKE without relying on prior chat or
agent context. Start with `ARCHITECTURE.md` and use `docs/SUBSYSTEM_INDEX.md` to
find ownership.

`DEVELOPMENT.md` is the canonical environment, launch, build, and verification
guide. This document owns extension and debugging sequences; it intentionally
does not duplicate the complete setup matrix. The documentation entry point is
`docs/README.md`.

## Supported development paths

SPIKE has three executable surfaces:

- Desktop: Tauri host plus React/TypeScript UI.
- CLI: `spike.cmd` on Windows or `python -m python.spike_core.cli`.
- Worker protocol: `python -m python.spike_core.service` using one JSON request
  and one JSON response on standard streams.

The desktop and CLI share Python contracts and solver services. The browser
preview is useful for UI work but cannot run local workers or native dialogs.

## Repository setup

Create a Python environment and install pinned project dependencies according
to `dependencies.lock.json` and `requirements.txt`. Install frontend packages
from the lockfile:

```powershell
cd app
npm.cmd ci
```

Install Rust stable with Cargo. Native C++ kernel setup is documented in
`DEVELOPMENT.md`, `CMakeLists.txt`, and the platform-specific dependency notes.

## Running locally

Frontend preview:

```powershell
cd app
npm.cmd run dev
```

Desktop development host:

```powershell
cd app
npm.cmd run tauri dev
```

CLI discovery:

```powershell
.\spike.cmd --help
.\spike.cmd solvers
.\spike.cmd --output design.json import path\to\board.kicad_pcb
```

The desktop worker search order is an explicit `SPIKE_WORKSPACE`, packaged
Tauri resources, then the source tree for development. Python can be selected
with `SPIKE_PYTHON`. Release packaging must include a tested runtime instead of
depending silently on an arbitrary system Python.

## Required checks

Run these before merging a cross-cutting change:

```powershell
python -m unittest discover -s tests\python -v
cd app
npm.cmd run check:architecture
npm.cmd exec tsc -- --noEmit
npm.cmd run test:parser
npm.cmd run build
cd src-tauri
cargo test
cargo build --release
```

`scripts/check_architecture.py` protects dependency and module boundaries. It
does not replace code review or numerical validation.

## Worker debugging

Send a health request directly:

```powershell
'{"id":"manual-health","method":"health","params":{}}' |
  python -m python.spike_core.service
```

Responses include the operation ID, method, duration, worker version, and a
structured error type. Desktop operation activity is mirrored into SPIKE's
console. Native worker requests and output are capped at 256 MiB; stderr is
capped at 4 MiB. Heavy methods have a watchdog and one-operation admission.

When debugging a hang, record:

- operation ID and method;
- elapsed time and watchdog configuration;
- input design/result sizes;
- process CPU and memory;
- last worker console event;
- whether the worker exited, timed out, or returned malformed JSON.

## Adding an importer

1. Define a source adapter that parses one format and returns `DesignIR`.
2. Register an `ImporterDescriptor` in a composition module.
3. Add frontend source dispatch only if browser-side parsing is required.
4. Add fixtures for units, coordinates, layers, stackup, arcs/polygons, vias,
   pads, zones, components, and unsupported objects.
5. Add an import-quality report and provenance.
6. Update `docs/IMPORTER_ARCHITECTURE.md` and the support matrix.

Do not expose a parser class or source-specific object to solvers, reports, or
renderers. Use standards-first ingestion for Altium, Allegro, and Xpedition;
add native adapters only for information that interchange standards lose.

## Adding a solver

1. Implement the SDK contract in `solver_sdk` or a built-in plugin module.
2. Declare modes, geometry, formulation, frequency, and validation capability.
3. Consume only `DesignIR` and `AnalysisSpec`.
4. Return `AnalysisResult` with provenance, assumptions, model status,
   convergence, and issues.
5. Add analytical and real-board fixtures with tolerances.
6. Update `docs/SOLVER_STATUS.md` and the relevant numerical document.

The UI should discover the solver through the catalog. Do not add a fake
result path to make an unavailable button appear functional.

## Adding UI functionality

UI commands should call an application service or worker bridge and record a
status event. Every long task needs pending, progress or elapsed-time,
completed, failed, and recovery states. Preserve viewport camera state across
panel changes unless the user explicitly requests fit/reset.

Use normalized selection objects for cross-selection. The source EDA bridge
translates those objects at the edge. Context menus may vary by task, but their
commands use the same underlying services as ribbons and shortcuts.

## Rendering work

The 2D and 3D views share normalized geometry but have separate renderer
implementations. Keep source parsing and numerical calculations out of both.
Before changing geometry transforms, test:

- top and bottom layer orientation;
- screen-to-board picking coordinates;
- resize and dock transitions;
- assembled and exploded stack positions;
- vias spanning connected copper layers;
- result, mesh, probe, and model alignment;
- large-board frame time and memory.

Use instancing and spatial indexes for repeated objects. Avoid rebuilding the
entire scene for hover, selection pulse, or panel resize.

## Documentation and ADRs

Update docs in the same change as behavior. Create an ADR under `docs/adr` for
new process boundaries, contract versions, persistence changes, rendering
engines, or plugin models. Use Mermaid for maintainable diagrams and include
links to executable tests or fixtures.

## Release responsibility

A release candidate must pass the full checks, open a real project, run an
available solver from CLI and GUI with matching results, produce a report, and
launch offline on a clean supported machine. Capability text must match
`docs/SOLVER_STATUS.md`; known limitations are release notes, not hidden tribal
knowledge.
