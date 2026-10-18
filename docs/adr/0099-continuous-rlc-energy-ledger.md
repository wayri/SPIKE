<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0099: Continuous RLC energy ledger

Status: accepted for bounded experimental development; release qualification open.

## Context

Instantaneous resistor watts and L/C joules do not provide integrated heating or
source/network work. Sparse output-sample quadrature can miss transient energy,
while treating all work as heat loses physical storage and ownership.

## Decision

Expose a separate ledger API observing the existing initialized propagator's
actual intervals through private instrumentation. Integrate quadratic physical
outputs with a scaled covariance block exponential and doubling. Preserve both
old public transient contracts/results; retain work/heat/storage separately and
admit raw interval/total balances, Gramian diagnostics and bounded resources.

## Consequences

Return resistor joules and signed source/network work with source-port identity,
initial/final boundary storage and residuals. Reject unsupported precision or
negative heat without clipping/repair. Use the
[referenced independent derivation](../RLC_ENERGY_LEDGER.md), analytic quadrature,
physical memory, coupled-port and split/refinement checks. Generic fit-state heat,
thermal mesh transfer and parameter feedback remain separately gated. No new
dependency, implementation language, fit cache or second trajectory is added.
