# ADR 0063: Offline co-simulation and recorded digital twins

Status: Accepted for the experimental foundation.

## Decision

Keep specialized field/circuit and electrothermal engines intact. Introduce
a separate Python scalar participant registry and fixed-grid explicit-lag
master, exposed through the existing worker/CLI and desktop Python Workspace.
Use versioned request/results rather than parser objects or UI-derived values.
Treat recorded prediction/telemetry comparison as a separate service with exact
model, unit and timestamp admission. No new implementation language or external
dependency enters the runtime.

The current workstream stays offline: local simulation, file exchange,
recorded measurement replay and comparison. Future native solver sessions,
FMI adapters, saved studies and calibration proposals must support local
offline execution. Live acquisition, network/cloud execution, device control
and HIL are deferred outside the current scope.

## Rationale and consequences

Explicit delayed exchange gives deterministic simultaneous commits without
claiming rollback, adaptive integration or algebraic-loop convergence. Adapter
callbacks are trusted Python services; JSON requests cannot select executable
code. The worker owns process isolation; callback cancellation is cooperative.
The master is experimental regardless of supplied participant qualification.

Existing solvers need explicit session adapters and reference validation before
they can join this master. Recorded residual agreement preserves supplied model
status and does not qualify hardware. Offline FMI, project-persisted twin
studies and recorded-data calibration require later contracts and evidence
gates. Live acquisition and HIL remain deferred.
See [workflow and staged plan](../COSIMULATION_DIGITAL_TWIN.md).
