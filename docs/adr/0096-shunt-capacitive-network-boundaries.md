<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0096: Shunt-capacitive network source/load boundaries

Status: accepted for bounded experimental development; release qualification open.

## Context

Resistive and series-inductive boundaries omit receiver/load shunt capacitance.
With a capacitor across a network port, source and network current differ, so
thermal-ready resistor loss cannot use the network current indiscriminately.

## Decision

Add a separate contract/worker method for mixed pure-resistor and shunt-capacitor
boundaries, requiring R>0 on C>0 ports. Introduce normalized capacitor-voltage
states, solve mixed voltage/resistor wave rows and advance the regular resolved
stable LTI problem using the existing exact PWL exponential approach. Preserve
older contracts and fail without regularization for singular/descriptor cases.

## Consequences

Report distinct source/network currents, capacitor voltage/derivative, KCL
residual, actual resistor loss and capacitor energy with full source/port
provenance. Do not claim thermal execution, arbitrary circuit topology or measured
broadband qualification. Use the [referenced derivation](../CAPACITIVE_NETWORK_TRANSIENT.md)
and independent RC/parallel-RLC/multiport/energy/failure evidence. No dependency
or implementation language is added.
