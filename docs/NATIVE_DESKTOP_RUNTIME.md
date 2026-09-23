# Native Desktop Runtime

## Current Architecture

SPIKE is a native Tauri executable. Rust owns the window, native file dialogs, approved filesystem paths, worker process isolation, resource sampling, application metadata, installer, and future license verification. React and Three.js render inside the operating-system web component.

On Windows, Task Manager can therefore show a WebView2 child process under SPIKE. This does not mean the application is hosted online. It is the renderer used by the native process, comparable to a GPU or utility child process in other desktop software.

The numerical worker is a separate local process. The desktop host exchanges one JSON request and one JSON response with it over standard input/output; it does not invoke a shell. This makes solver crashes, timeouts, and worker output limits containable by the desktop host.

The desktop resource monitor aggregates the Tauri host and every descendant
SPIKE process, including the WebView renderer and active numerical worker.
Process-tree CPU uses the conventional per-core scale (one saturated logical
core is 100%); total-machine capacity is reported separately. Process-tree RSS,
host RSS, tracked-process count, logical CPUs, and worker activity are exposed.
GPU utilization is not currently sampled and must remain labeled unavailable;
draw calls, triangles, geometries, and textures describe renderer workload but
are not GPU-utilization measurements.

## Offline Operation

- Frontend assets are bundled with the executable.
- Release builds bundle a frozen `spike-worker` executable and its private runtime as an application resource.
- Solver execution is local and process-isolated.
- Native dialogs and reports do not require a network.
- No cloud dependency is part of the project, PI, visualization, or report path.

The release build does not install or download dependencies. Optional external engines remain separate, explicitly configured local installations and are not silently fetched or executed.

## Packaged Worker Build

The worker artifact is built by `scripts/build_packaged_worker.py`. It is deliberately offline-first: the script only uses packages already present in the active release environment and fails rather than calling a package manager.

Prerequisites:

- Build with the target Python ABI that produced `python/spike_peec_native<EXT_SUFFIX>`.
- On Windows x64, install the hash-locked build environment with `python -m pip install --require-hashes -r requirements-build-windows-x64.txt`. Other versions are rejected.
- Build the native PEEC extension with that same interpreter before packaging.

The build produces a PyInstaller `onedir` artifact at `app/src-tauri/resources/worker/spike-worker/`. Tauri maps that directory into the installed application as `bundled/`. A generated `spike-worker.manifest.json` records the platform, Python and PyInstaller versions, worker version, native-extension hash, and SHA-256 plus size for every packaged file.

The build script performs the following protocol gates against the frozen
executable before writing the manifest:

1. `health` must report `ready`.
2. `capabilities` must include a runnable `spike.peec_2_5d` plugin, proving that the ABI-matched native PEEC extension was loaded by the packaged worker.
3. The permanent solver benchmark corpus must pass with no failed or skipped cases; its summary is recorded in the manifest.
4. The normalized source and packaged worker snapshots must be identical under
   `spike/release-runtime-qualification/v1`. The comparison includes worker
   collection errors, product capabilities, plugins, capability ledger,
   accelerators, external engines, and benchmark output.

The source-versus-packaged comparison is strict: a rejected capability request
or a digest mismatch fails the worker build and prevents the manifest from
being issued as qualified release evidence. The standalone command and current
recorded failure are documented in `docs/RELEASE_RUNTIME_QUALIFICATION.md`.

These are deployment-integrity checks. They do not validate numerical accuracy for an arbitrary PCB or elevate a solver result to validated status.

## Worker Launch Policy

At runtime the native host chooses the first executable it can start in this order:

1. `bundled/spike-worker/spike-worker` (or `.exe` on Windows).
2. `bundled/spike-worker` in the flat legacy resource location.
3. A source-development Python interpreter, using `-m python.spike_core.service`.

The source-Python path is a development fallback, not a release dependency. It can be selected through `SPIKE_PYTHON`; the host otherwise checks the workspace virtual environment, an explicitly supplied runtime, and finally the platform Python command. `SPIKE_WORKSPACE` may specify the workspace or installation root for controlled development and test environments.

The host uses direct process spawning, never a command shell. On Windows it applies `CREATE_NO_WINDOW`, so a successful local worker launch must not create a visible console window. Standard input, output, and error are piped and bounded; long-running solve requests are watchdog-limited and heavy worker operations are serialized by the host.

## Integrity and Solver Status

The worker manifest is a release-artifact inventory, not a signature or a substitute for installer signing. Release automation must retain the manifest with the installer, compare its SHA-256 entries before publishing, and sign/notarize the platform package where applicable.

The manifest is only release-eligible when its paired runtime qualification
report passes all required sections. A `ready` health response by itself is not
evidence of source/package feature parity.

The native `spike.peec_2_5d` plugin can be successfully packaged and loaded while still being classified as **Approximate**. Its current validation corpus checks bounded analytical/network cases only. It does not establish validated arbitrary-board PEEC extraction, complete PDN accuracy, SI accuracy, thermal accuracy, or EMI compliance. Reports and UI must preserve that capability and validity status.

## Eliminating WebView2

Removing the WebView process requires replacing the React/Tauri application shell with a native-widget renderer such as Qt/QML, wxWidgets, or a custom Vulkan/OpenGL application. That is a full UI-shell rewrite, not a configuration switch.

A native renderer should be considered only after profiling demonstrates that the web renderer is the limiting component. Solver performance, mesh generation, geometry normalization, and numerical accuracy are independent of that decision. A credible migration must first prove parity for docking, accessibility, text rendering, 2D picking, 3D scene output, report preview, cross-platform packaging, and automated UI tests.

## Cross-Platform Requirements

- Windows: WebView2 runtime, packaged worker, no visible console windows, signed installer or portable artifact with its manifest.
- Linux: WebKitGTK runtime supplied by the distribution or installer prerequisite, native portal file dialogs, bundled worker, and an AppImage or distribution package built on a compatible target.
- macOS: system WKWebView, signed and notarized application, bundled worker.
- All platforms: fixed dependency manifest, reproducible build inputs, solver provenance, and no network requirement for core workflows.
