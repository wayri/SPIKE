<!-- SPDX-License-Identifier: MIT -->
# ADR 0021: Explicit SPIKES Studio backend selection

- Status: Accepted for the engineering preview; not a release qualification.
- Date: 2026-09-24

## Context

Studio previously dispatched finite circuit runs only to the owned C++ engine.
Imported SPICE models may need a compatibility engine, but automatic fallback
would change numerical behavior and model provenance without user consent.

## Decision

`spikes/run-profile/v1` gains an optional `backend` value, `native` or
`ngspice`. Missing values in existing projects mean `native`, preserving the
historical behavior. The simulation manager and saved sequences retain the
selected backend. The ngspice route invokes the existing process-isolated
adapter, never the owned solver as a fallback. It is batch-only and accepts
only self-contained netlists under the adapter's directive/resource limits.

Model-tier and parasitic selections requiring native rewriting are rejected
before dispatch. The result retains ngspice provenance and unmodified backend
vectors. Studio projects only complete, real, strictly ordered transient
voltage vectors into its existing plot contract; it does not infer element
current, power, temperature or qualification from those vectors.

## Consequences

The compatibility path is useful for reviewed self-contained decks without
asserting dialect parity or manufacturer-model validation. Existing Studio
projects continue to use the owned solver until a user explicitly changes a
profile. Broader library dependency handling, AC/DC result projection,
backend-specific control semantics and installed-package verification remain
separate release gates.
