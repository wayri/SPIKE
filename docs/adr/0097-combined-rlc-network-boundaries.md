<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0097: Combined R/L source and shunt-C network boundaries

Status: accepted for bounded experimental development; release qualification open.

## Context

The separate RL and RC boundaries cannot represent source/package inductance and
receiver shunt capacitance together. Source current then differs from network
current and both magnetic and electric boundary energy matter for coupled work.

## Decision

Add an explicit contract and worker method for supplied series R/L followed by
shunt C at a fitted-network port. Assemble the bounded mixed R, RL, RC and RLC
rows in one regular state formulation. Retain normalized inductor-current and
capacitor-voltage states, strict closure/stability/resource admission and exact
PWL propagation using existing dependencies. Preserve older APIs unchanged.

## Consequences

Keep separate source/network currents, KVL/KCL residuals, component derivatives,
actual resistor loss and boundary storage with source identity. Use the
[referenced independent derivation](../RLC_NETWORK_TRANSIENT.md), analytic loaded
RLC and coupled physical-equation references. General DAE/topology, nonlinear
elements, nonzero initial state and thermal execution remain separately gated.
No implementation language or dependency is added.
