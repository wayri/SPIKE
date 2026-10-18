<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0098: Supplied RLC initial states and stateless continuation

Status: accepted for bounded experimental development; release qualification open.

## Context

The zero-state RLC API cannot model precharged capacitors, energized inductors or
continue fitted memory across separately specified source windows. Duplicating
the mixed solver would create two numerical implementations to maintain.

## Decision

Keep v1 zero-state semantics and expose a separate v2 initialized worker/API.
Validate exact finite, fit-request-bound state dimensions/physical port subsets
before fitting. Initialize the existing propagation through a narrow private
entry point. Return original and final state records with explicit units.

## Consequences

Continuation requires explicit source slicing and local-clock translation.
Returned state is at the source horizon, even when observations stop earlier.
The record is neither authenticated nor bound to time, boundaries or code;
changed parameters require a separately specified initial-value problem and
energy accounting. General sessions/rollback/thermal coupling stay separate.
Use [referenced mathematics and limits](../RLC_INITIAL_STATES.md), analytic
initial-value cases, physical fitted-memory and split-run verification. No
language, dependency, fit cache or generic fitted-state energy claim is added.
