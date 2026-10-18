<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0100: sampled multi-aggressor crosstalk

Status: accepted for experimental implementation, 18 October 2026.

## Context

SI07 needs multiple aggressor attribution and noise budgets while preserving
the verified initialized RLC boundary and future multiphysics provenance.

## Decision

Add `sparameter_multi_aggressor.py` above the initialized RLC solver and route a
separate worker method through `service_sparameter_processing.py`. Require
explicit reference voltages and caller voltage limits. Baseline carries common
initial state and fixed drivers; bases are zero-state deviations. Compute exact
finite signed-family envelopes at requested times and admit two actual complete
pattern witnesses. Retain original/derived identity and direct residuals in
strict registered v1 contracts. No change to old transient public contracts.

## Consequences

N+3 actual fits/trajectories are bounded together before fitting; no cache claim
or exponential enumeration is needed. Numerical cancellation and sampled-only
coverage remain explicit. Heat must be computed on a complete selected pattern
because energy is quadratic. No implicit material/geometry/thermal mapping is
created. Referenced derivation, independent physical oracles and release review
requirements are in [the method ledger](../MULTI_AGGRESSOR_CROSSTALK.md).
