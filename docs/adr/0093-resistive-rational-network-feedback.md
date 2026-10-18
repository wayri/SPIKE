# ADR 0093: Resistive feedback around fitted rational networks

Status: accepted for bounded experimental development; release qualification open.

## Context

Prescribed incident waves do not include source/load reflections. Adding
feedback can create algebraic singularities or unstable dynamics even when
the standalone fitted model is stable.

## Decision

Require a finite resistive Thevenin boundary at every port. Solve its wave
feedback algebraically, reject singular/ill-conditioned or unresolved unstable
connections, and propagate the connected state model with bounded augmented
matrix exponentials for PWL sources. Preserve fit and boundary evidence.

## Consequences

Actual resistor-driven and resistor-loaded waveforms have independent circuit
references. Reactive/nonlinear terminations, arbitrary coupling, uncertainty
and measured qualification retain separate stages. No dependency or
implementation language is added.
