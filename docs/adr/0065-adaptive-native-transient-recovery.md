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

## Addendum — explicit linear Radau IIA3 (2026-10-18)

Owner-approved decision: add `radau_iia3` (integration code 3), retaining all
legacy defaults and methods. CLI spelling is `--method radau-iia3` (the
underscore alias is accepted). This fixed-step two-stage method admits the
linear independent-source RLC/index-one subset only; unsupported topology,
nonlinear devices and adaptive requests fail explicitly. Additive optional ABI
exports expose Radau step counters without changing existing structure layouts.
Older DLLs reject this method rather than silently substituting another one.
Physical `matrix_order` diagnostics retain their existing meaning; the coupled
stage factorization has twice that order. On-grid accepted source corners now
count in the breakpoint diagnostic as well as shortened corner steps.
The PWM result schema admits the optional nonnegative integer Radau counter
from a newer DLL, while retaining strict unknown-field rejection and its fixed
backward-Euler integration contract; this does not enable Radau PWM coupling.

Derivation, primary references, jump/sample convention, resource limits and
executed 42-case frozen-budget evidence are recorded in
[numerical method evidence](../NUMERICAL_METHOD_EVIDENCE.md#native-linear-radau-iia3--18-october-2026).
This decision does not reclassify historical failed trapezoidal reports, qualify
nonlinear switching, or remove human numerical review before release.
