# ADR 0042: Transient solid thermal and correlated worker progress

Status: Accepted for experimental development; numerical human review required before release.

## Decision

Add a separate transient settings contract with duration, maximum step, output
interval, explicit density and specific heat for each retained material, initial
nodal temperatures and an optional global power scale schedule. Preserve the
steady contracts. New transient result contracts retain solved frames, original
settings and integrity bindings to assembly, mesh and problem. Study-file v1
accepts an optional transient_settings field; older readers reject unfamiliar
records rather than interpreting them as steady results.

The internal kernel uses consistent P1 capacity and backward Euler. Exact event
and output times partition steps. Volume heat sources, conduction, matched
contacts, prescribed temperature/flux, convection and nonlinear radiation use
the existing admitted physical setup. Heat storage enters energy conservation.

Worker stderr carries bounded SPIKE_PROGRESS JSON records alongside diagnostics.
The final stdout response is unchanged. Native transport validates operation
and method identity; cancellation prevents subsequent admission. Live frames
are preview data only. Saving requires a complete verified result. Playback
uses physical solved times and wall-clock elapsed time, without interpolation
claims or invented intermediate solutions.

The native JSON bridge enables exact floating-point roundtrip parsing. A
one-ULP coordinate change during decoding invalidates mesh/request digests;
the bridge must preserve numerical values rather than loosen admission checks.
Transient field wrappers bind canonical physical assembly defaults, preserving
the same identity through native save/open and excluding saved reduced studies.

## Consequences

Old steady snapshots remain readable. Invalid, oversized or stale histories
fail admission. Solvers need not run at real-time speed. CalculiX DC3D4 capacity
integration differs from the internal consistent matrix; comparison therefore
needs independent analytical checks and temporal/spatial refinement. This does
not establish production qualification, Fang equivalence, enclosure CFD or
transient electrical switching feedback.
