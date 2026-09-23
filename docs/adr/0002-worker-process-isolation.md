# ADR 0002: Worker Process Isolation

- Status: Accepted
- Date: 2026-08-09

## Context

Meshing, numerical solvers, Python/native dependencies, and external engines can
run for minutes, allocate heavily, fail, or hang. Running them in the webview or
native UI event thread causes an unresponsive application and makes recovery
difficult.

## Decision

The Tauri desktop invokes a versioned Python worker in a separate process. The
Rust host performs the blocking process work on a background runtime, limits
message sizes, drains pipes concurrently, applies a request-aware watchdog, and
admits one heavy operation at a time. Requests and responses are JSON-compatible
and include operation IDs.

## Consequences

- Worker failure is isolated from the desktop process.
- CLI and future HTTP transports can reuse application services.
- Large JSON payloads have serialization cost and require decimation/bounds.
- Progress streaming and cooperative cancellation require a future protocol
  extension; the current fallback is watchdog termination.
- Release packages must provide a known Python/runtime dependency set.

## Rejected alternatives

- Solver calls in React: blocks UI and mixes presentation with computation.
- In-process Python embedded in the Tauri host initially: harder crash isolation
  and dependency packaging while contracts are evolving.
- An always-required cloud worker: violates offline and privacy requirements.
