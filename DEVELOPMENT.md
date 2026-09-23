# SPIKE Development

This is the setup and verification guide for the active SPIKE runtime. Read
`ARCHITECTURE.md` before changing a process boundary or shared contract. Use
`docs/DEVELOPER_GUIDE.md` for importer, solver, UI, and rendering extension
sequences, and `docs/SUBSYSTEM_INDEX.md` to find the owning module.

The supported application is the Tauri desktop host, React/TypeScript UI, and
local Python worker. The wxPython/PyVista prototype under `python/gui` is frozen
legacy code and is not a development launch path.

## Prerequisites

Install only the toolchains needed for the layer you are changing:

| Area | Required tools |
|---|---|
| Python contracts, services, CLI, tests | Python 3.11 or newer; packages from `requirements.txt` |
| Desktop UI | Node.js/npm compatible with `app/package-lock.json` |
| Native desktop host | Rust stable, Cargo, and the platform Tauri prerequisites |
| C++ kernels/bindings | CMake 3.20+, C++20 compiler, Eigen 3.4+, OpenMP, Python development files, nanobind |

Windows requires WebView2 for the Tauri renderer. Linux packages are listed in
`docs/LINUX.md`. Release artifacts use a separately qualified packaged worker;
a source environment is not evidence that the release runtime is qualified.

## Initial setup

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Set-Location app
npm.cmd ci
Set-Location ..
```

`infra/aether_boot.py` and `aether_env` belong to the frozen prototype setup.
Do not use them as the source of truth for the active desktop runtime.

## Run a development surface

Run the native desktop when testing file dialogs, the local worker, process
isolation, or packaged-resource behavior:

```powershell
Set-Location app
npm.cmd run tauri dev
```

Run the browser preview only for frontend work that does not need native
dialogs or the local worker:

```powershell
Set-Location app
npm.cmd run dev
```

Run CLI discovery from the repository root:

```powershell
.\spike.cmd --help
.\spike.cmd capabilities
.\spike.cmd solvers
```

Send a direct worker health request when isolating desktop IPC from Python:

```powershell
'{"id":"manual-health","method":"health","params":{}}' |
  python -m python.spike_core.service
```

The source-development worker can be selected with `SPIKE_PYTHON` and its
workspace with `SPIKE_WORKSPACE`. Packaged builds prefer the bundled worker;
see `docs/NATIVE_DESKTOP_RUNTIME.md` for the exact search order.

## Build the C++ kernels

The root `CMakeLists.txt` builds the PEEC and thermal static libraries, the
`test_peec` executable, and, by default, the `spike_peec_native` nanobind
module. Configure only after Eigen, OpenMP, Python development files, and
nanobind are discoverable by CMake:

```powershell
cmake -S . -B build -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=ON
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Use the same Python ABI for the native module and packaged worker. Release
worker construction and qualification are documented in
`docs/NATIVE_DESKTOP_RUNTIME.md` and
`docs/RELEASE_RUNTIME_QUALIFICATION.md`.

## Verification matrix

Start with focused checks for the changed subsystem, then run the applicable
cross-cutting gates.

| Change | Minimum focused verification |
|---|---|
| Python service or contract | Relevant module under `tests/python`; then full Python discovery |
| Error envelope or catalog | `python -m unittest tests.python.test_errors -v` |
| Frontend state or component | `npm.cmd exec tsc -- --noEmit` plus the matching `app/scripts/test-*.mjs` script |
| Parser/import UI | `npm.cmd run test:parser` and focused Python importer tests |
| Project/workspace persistence | `npm.cmd run test:project` and `npm.cmd run test:workspace` |
| Architecture or ownership | `npm.cmd run check:architecture` |
| Native host | `cargo test` from `app/src-tauri` |
| Release desktop bundle | Frontend build, Cargo release build, packaged-worker qualification, and clean-machine launch |

Core checks from a prepared environment:

```powershell
python -m unittest discover -s tests\python -v

Set-Location app
npm.cmd run check:architecture
npm.cmd exec tsc -- --noEmit
npm.cmd run test:parser
npm.cmd run test:project
npm.cmd run test:workspace
npm.cmd run build

Set-Location src-tauri
cargo test
cargo build --release
```

The architecture guard checks dependency direction, implementation-language
ownership, required documents, and recorded module-size debt. It does not
replace numerical validation, UI review, or package qualification.

## Change sequence

1. Identify ownership in `docs/SUBSYSTEM_INDEX.md` and read the subsystem doc.
2. Add or select a fixture that reproduces the behavior being changed.
3. Preserve the `spike/v1` contracts unless the change includes an explicit
   migration and architecture decision.
4. Implement within the owning language and process boundary.
5. Run focused checks, then the applicable matrix above.
6. Update user help, API/architecture notes, capability status, and validation
   evidence in the same change.
7. Add an ADR for a new process boundary, contract version, persistence
   format, renderer, implementation language, or plugin interface.

Do not make an unavailable solver appear usable with synthetic results. Do not
weaken model-status, convergence, or diagnostic reporting to make a workflow
pass.

## Documentation changes

Start at `docs/README.md`. Documentation-only changes should at least run the
architecture guard and a local-link/image check. Changes to issued errors must
also run `tests.python.test_errors`, which verifies that the runtime catalog and
`docs/ERROR_CODE_CATALOG.md` remain synchronized.

Use only repository-owned, provenance-reviewed images. The current Help Center
screenshots are under `app/public/help`; `docs/USER_TASK_SEQUENCES.md` records where
each one applies and avoids presenting a setup-only report as a solved result.

## Debugging and recovery

Use `TROUBLESHOOTING.md` for symptom-first diagnosis and
`docs/ERROR_CODE_CATALOG.md` for exact issued-code recovery. Preserve the
operation ID, exact code, application/worker versions, model status, and a
minimal reproducible input when reporting a failure. Never include
confidential design content unless it is explicitly approved for sharing.
