<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0104: causal lossless TEM line transient

Status: accepted for experimental implementation, 18 October 2026.

## Context

SI02 requires distributed delay and reflections. Finite real-pole rational
models do not represent a pure propagation delay exactly. A uniform lossless
line provides an established analytic baseline before lossy/coupled extraction.

## Decision

Add `lossless_line_transient.py` with distinct strict neutral v1 contracts and
route it through the existing network worker. Require supplied L/C per length,
length, two finite-resistive PWL boundaries and explicit named probes. Start
with zero history and sources at zero voltage. Evaluate the finite causal
traveling-wave expansion using exact retarded-time ordering, checked numerical
amplitudes and bounded work/depth/bytes; introduce no fitted delay or time mesh.
Retain source identity, end-current orientation, power and local stored energy.

## Consequences

No change to earlier numerical contracts or new dependency is required.
The model does not extract geometry or qualify realistic lossy/dispersive
channels. Stored energy, transported power and terminal resistor heat retain
different meanings for later coupling. Referenced derivation, independent
verification, numerical limits and future gates are recorded in the
[method ledger](../LOSSLESS_LINE_TRANSIENT.md).
