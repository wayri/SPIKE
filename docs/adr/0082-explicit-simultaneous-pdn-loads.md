# ADR 0082: Explicit simultaneous PDN loads

Status: Accepted for bounded development; numerical human review before release.

Date: 2026-10-14.

## Context

The passive PDN worker admitted one supplied PWL sink. Multiple rails sharing a
return need independent waveform identities, a common event grid and combined
source work. Summing individual stored energies would omit quadratic cross terms.

## Decision

Extend `spike/pdn-network-request/v1` additively with a mutually exclusive
`load_transient.loads` form. Each entry has a unique existing port and supplied
PWL points. Require a common explicit final time; reject implicit waveform
extension. Preserve the legacy scalar request/result. Multi-load results carry
ordered `load_port_ids` and per-point `load_current_a_by_port` only.

The existing Python worker owns request admission and descriptor MNA execution.
It combines B u forcing, all PWL corners and signed source work, reusing the
linear inductive-slope correction with multiple right-hand sides. No dependency,
language, worker endpoint or native host behavior changes. Presentation admits
load identities and plots actual returned voltage maps.

## Evidence and limits

Original asynchronous shared-return RL references, voltage superposition,
ordering and legacy checks plus schema/worker and failure/resource/cancellation
checks define PI04-S02 acceptance. See [numerical contract](../PDN_SIMULTANEOUS_LOADS.md).
Source-bound earlier receipts are rerun after shared engine changes. Model
status remains approximate for supplied linear frequency-invariant passive
networks; nonlinear regulators, general geometry extraction and physical-board
qualification remain open.
