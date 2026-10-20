<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR0120: supplied piecewise coupled-line propagation

Status: accepted for experimental development, 20 October 2026.

A uniform supplied coupled pair does not represent piecewise impedance or loss.
Add an ordered cascade of1..8 unchanged symmetric pair models with ideal physical
conductor connections. Solve a bounded common-reference wave connection system
rather than propagating growing transfer matrices. Recover actual section drives
and retain complete child fields, provenance and separately owned integrated heat.

The existing RF worker/CLI expose strict separate versioned request/result
contracts. No native PDE kernel, dependency or language is added. Section IDs
preserve a future explicit thermal handoff; interfaces introduce no heat and
mutual terms have no inferred conductor/cell allocation. Independent physical
spatial-chain/quadrature references and source-bound gates verify development.
General asymmetry, geometric parasitics, external terminal feedback, transient,
physical thermal mapping and board qualification remain separately gated.
See [method and source ledger](../RLGC_COUPLED_CASCADE.md).
