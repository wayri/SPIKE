# ADR 0065: opt-in native transient recovery and reporting

Date: 2026-10-10. Status: implemented in source; numerical release review pending.

## Decision

Expose existing native adaptive BDF2/trapezoidal controls through the owned
project runner and CLI without changing fixed-step defaults or substituting a
backend. Reject contradictory controls before DLL load. Adaptive primary Newton
failure restores accepted solution state, halves the timestep, and retries within
the combined rejection budget. Histories commit only on accepted steps; singular
systems still fail closed. Unsupported OSDI adaptive callback execution remains
unsupported.

Maintain a separate sparse BE-companion factorization cache. Reuse symbolic
ordering on exact CSC pattern identity and numeric factors only on exact numeric
identity. Changed values require full numeric factorization. Do not advertise
local numeric updates under the legacy diagnostic name.

Add `spikes_transient_result_recovery_diagnostics` to ABI version 1 without
altering public structure layouts or existing entry points. ctypes discovers it
optionally, retaining compatibility with older DLLs. Project results retain their
requested output grid while measurements use original accepted samples. Record
controls and output semantics in provenance. Nonfinite LTE diagnostic ratios map
to JSON null plus an explicit finite flag.

## Consequences and limits

Reporting interpolation is not solver stepping, peak-preserving decimation or
bounded-memory capture. The BE/order-two difference is not rigorous universal LTE.
BDF source-corner restart and conservative growth limits reduce history hazards
without establishing arbitrary DAE stability. Stable ordinary C/L difference
residuals do not resolve every compact-model charge or linear-system conditioning
issue. Global excitation-scaled Newton tests remain mixed-unit.

Regression, derivation, benchmark reproduction, clean-room method provenance and
the known buck stress failure are recorded in
[adaptive switching foundation](../SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md).
No installer, competitive-parity claim or hardware qualification follows from
these source checks; knowledgeable human numerical review remains required.
