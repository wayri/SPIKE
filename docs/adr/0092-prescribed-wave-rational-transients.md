# ADR 0092: Prescribed-wave rational network transients

Status: accepted for bounded experimental development; release qualification open.

## Context

The supplied-pole fitter returns a stable realization but does not execute
waveforms. SI waveform studies need simultaneous inputs with declared initial
state, corner timing and port current/voltage conventions.

## Decision

Compose the actual fit workflow with analytic exponential integration of
piecewise-linear incident waves. Use a common event union, zero initial memory
and explicit coverage of every port. Preserve fitting evidence, output maps
and final model states. Do not infer arbitrary source/load feedback.

## Consequences

The fitted model can execute auditable transient histories without FFT grid
assumptions or time-step truncation error for PWL inputs. Physical broadband
accuracy, general termination coupling and measured qualification retain
separate stages. No dependency or implementation language is added.
