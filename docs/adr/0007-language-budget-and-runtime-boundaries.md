# ADR 0007: Language Budget and Runtime Boundaries

- Status: Accepted
- Date: 2026-08-11

## Context

SPIKE currently uses TypeScript/TSX, Python, C++, and Rust, plus platform shell
scripts. It also retains a legacy wxPython/VTK UI beside the supported
Tauri/React application. Uncontrolled growth across these surfaces would make
the project difficult for human maintainers and would duplicate contracts,
workflows, and defects.

Eliminating a core language immediately is not a low-risk mechanical change.
TypeScript owns the current UI, Python owns most application and solver
orchestration, C++ owns native numerical kernels, and Rust is required by the
Tauri host. Replacing any one before PI validation would consume the same
engineering capacity needed to establish numerical credibility.

## Decision

SPIKE adopts the language budget in `docs/LANGUAGE_POLICY.md`:

- TypeScript/TSX owns presentation and visualization.
- Python owns application services, contracts, orchestration, CLI, and
  external-process adapters.
- C++ owns only justified numerical kernels.
- Rust remains a thin Tauri host and does not become a second backend.
- Platform shell languages remain thin invocation/packaging shims.
- The wxPython/VTK UI is frozen and excluded from the supported runtime.
- A new implementation language requires a superseding ADR and architecture
  guard update.

The near-term reduction is removal of duplicate implementations and script
logic, not a solver or UI rewrite. The supported runtime continues to exchange
versioned data through the existing contracts.

## Consequences

Positive consequences:

- subsystem ownership is explicit;
- new features cannot casually introduce another runtime;
- Rust and C++ remain narrow enough for specialists to review;
- legacy Python UI code has a defined retirement path;
- numerical validation is preserved while maintainability improves.

Costs and limitations:

- the repository still contains four implementation languages until a future
  host, service, UI, or kernel migration is justified;
- maintainers need basic cross-boundary debugging skills;
- contract tests and packaging tests remain mandatory at language boundaries.

## Rejected alternatives

- **Rewrite the UI in C++/Qt or wxWidgets now:** high cost, resets interaction
  and rendering maturity, and does not advance solver validation.
- **Port Python services to Rust now:** removes scientific ecosystem leverage
  and requires a broad, risky service rewrite.
- **Port C++ kernels to Python:** reduces build complexity but sacrifices the
  intended performance boundary and invalidates existing native work.
- **Move to Electron to remove Rust:** replaces a small Rust host with a larger
  desktop runtime and does not reduce TypeScript or Python ownership.

