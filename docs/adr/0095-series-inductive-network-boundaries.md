<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0095: Mixed resistive and series-inductive network boundaries

Status: accepted for bounded experimental development; release qualification open.

## Context

The previous fitted-network transient supports finite resistive Thevenin
boundaries. SI/PI interconnect studies also need source/load inductance and its
state, boundary voltage and energy. A stable fit need not stay stable under a
new boundary, and some direct-feedthrough constraints need a descriptor solver.

## Decision

Add a separate versioned request/result and worker method for finite nonnegative
series R/L boundaries, requiring at least one positive L. Introduce normalized
inductor-current states and solve mixed resistor/current algebraic rows, then
propagate the full admitted stable LTI model with exact PWL augmented exponentials.
Reuse established fit/wave admission without changing older contracts. Fail on
singular, marginal, unstable, unresolved or oversized systems without repair.

## Consequences

Preserve complete fit/source/boundary provenance and typed I/dI/dt, resistor
power, inductor energy and boundary residuals for future multiphysics interfaces.
No automatic thermal handoff or physical network-energy realization is claimed.
Capacitive/nonlinear/general-circuit boundaries and descriptor systems remain
separate stages. Use [referenced derivation](../INDUCTIVE_NETWORK_TRANSIENT.md)
and independent RLC/multiport/failure evidence. No new dependency is introduced.
