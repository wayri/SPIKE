# SPIKE Language Policy

SPIKE limits the number of independently evolving implementation languages so
that a conventional engineering team can build, debug, validate, and release
the product without relying on AI-generated context.

This policy reduces maintenance surfaces without rewriting validated or
partially validated numerical work merely to change its language.

## Language budget

| Language | Authoritative responsibility | Allowed production area | Growth policy |
|---|---|---|---|
| TypeScript / TSX | Desktop presentation, interaction state, 2D/3D visualization, and typed client contracts | `app/src/` | UI only; no EDA parsing or numerical physics |
| Python | Design contracts, import adapters, CLI, worker services, solver orchestration, reports, and external-process adapters | `python/core/`, `python/spike_core/`, narrow tools and adapters | Primary application-service language; no new desktop UI |
| C++ | Performance-critical numerical kernels | `src/`, `python/bindings/` | UI experiments remain outside production roots until a migration decision |
| Rust | Tauri window/process/security boundary | `app/src-tauri/` | Frozen thin host; no solver, importer, project-model, or report logic |

Rust remains a fourth compiled language because Tauri requires it. It is not a
second backend. Its maintained surface must stay small and infrastructure-only.
Removing Rust now would require replacing the desktop host; removing Python,
TypeScript, or C++ would require a high-risk service, UI, or numerical rewrite.
Those rewrites are not justified before the validated PI release.

CSS, HTML, JSON, JSON Schema, TOML, YAML, Markdown, and CMake are declarative
formats rather than additional product implementation languages.

## Mandatory rules

1. No new implementation language may enter a production source root without
   an accepted ADR that includes ownership, toolchain, security, packaging,
   test, and retirement analysis.
2. Domain rules and schemas live in the Python contract/service boundary and
   versioned JSON schemas. They are not reimplemented independently in Rust or
   TypeScript.
3. C++ is introduced only where profiling or numerical requirements justify a
   native kernel. Every binding has a Python reference or regression oracle.
4. Rust remains limited to windowing, native dialogs, process supervision,
   bounded IPC, OS integration, and packaging.
5. Cross-platform build and release orchestration belongs in Python. PowerShell,
   Batch, and POSIX shell files are platform entry shims and must not acquire
   product logic.
6. The wxPython/VTK implementation under `python/gui/`, `python/ui/`, and
   `python/viz/` is frozen legacy code. It receives no features and must not be
   imported by the supported worker or desktop runtime.
7. Adding a language to obtain one library is not acceptable. Use a process
   adapter, C ABI, or versioned file/JSON contract unless an ADR proves that a
   new in-process runtime is necessary.

## Reduction plan

### Now: stop growth

- Enforce the language allowlist in `scripts/check_architecture.py`.
- Keep one supported Tauri desktop launcher and one Python CLI/worker service.
- Reject new domain code in the Rust host and new UI code in Python. The retired `wx_desktop/` client is no longer a production root; local UI experiments require a separate review before inclusion.

### PI stabilization: remove duplicate surfaces

- Move reusable Windows/Linux packaging logic into Python commands.
- Reduce `.ps1`, `.bat`, and `.sh` files to argument-forwarding shims.
- Remove unused root-level patch/debug scripts after their behavior is either
  covered by maintained tooling or proven obsolete.
- Archive and then delete the frozen wxPython/VTK UI after project migration
  and launcher compatibility are verified.

### After the validated PI release: re-evaluate the host

Measure maintenance cost, package size, startup, GPU behavior, and workstation
performance. A proposal to remove Rust, C++, Python, or TypeScript must include
a working prototype and a migration that preserves contracts and validation
evidence. Raw language-count reduction alone is not sufficient justification.

## Review checklist

- Does the change stay inside the owning language and subsystem?
- Does it duplicate a contract, parser, or physical model in another language?
- Can an existing process/plugin contract integrate the dependency instead?
- Does a native kernel have profiling evidence and a reference test?
- Is a platform script still a thin entry shim?
- Does the architecture check pass?
