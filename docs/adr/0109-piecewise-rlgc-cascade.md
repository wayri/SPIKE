<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0109: supplied piecewise RLGC wave connections and section loss

Status: accepted for experimental implementation, 18 October 2026.

## Context

Uniform lines cannot represent supplied impedance changes along a route.
Future coupled studies also need section identity and conservative loss
ownership, rather than treating internal transported power as dissipation.

## Decision

Add a bounded scalar series-cascade worker/CLI with neutral versioned contracts.
Use the unchanged sampled uniform network and driven field solvers. An explicit
common-reference wave connection solve determines both the external S matrix
and coherent local drives. Retain each section's complete fields/loss ledger,
raw interface V/I/power residuals and global loss balance. Aggregate admission
precedes all numerical parent calls. No dependency or language is added.

## Consequences

This is an ideal electrical junction model; physical launch/via/fringing
discontinuities, branches and geometry extraction remain open. Section heat is
preserved for later thermal mapping without executing deposition or feedback.
[Referenced derivation and numerical controls](../RLGC_LINE_CASCADE.md) delimit
the experimental claim.
