<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0106: supplied uniform sampled RLGC line networks

Status: accepted for experimental implementation, 18 October 2026.

## Context

Lossless and Heaviside line transients do not cover independent conductor and
dielectric loss. General SI frequency-domain work needs explicit supplied RLGC
without silently imposing a special ratio or inventing material properties.

## Decision

Add a separate neutral sampled line request/result and `rlgc_line_network.py`
through the existing network worker. Evaluate the uniform telegrapher two-port
with scaled decaying exponentials, exact degenerate DC limits, strict bounded
admission and sampled passivity/reciprocity checks. Retain supplied constitutive
table identity and compatible named two-port output. Existing transient solver
contracts are unchanged. No new implementation language or dependency is added.

## Consequences

This is a sampled effective distributed-circuit model. It establishes neither
broadband causal material laws nor extracted geometry or thermal deposition.
Subsequent fitting/transient use must pass its own checks. Referenced physics,
original derivation, independent references and numerical limitations are in the
[method ledger](../RLGC_LINE_NETWORK.md).
