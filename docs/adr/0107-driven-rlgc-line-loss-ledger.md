<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0107: driven sampled RLGC fields and integrated electrical loss

Status: accepted for experimental implementation, 18 October 2026.

## Context

Unexcited sampled line networks do not establish local fields or heat. PI/SI
and future thermal coupling need coherent excitation, explicit power signs,
separate storage/loss and a conservative continuous spatial loss ledger.

## Decision

Add `rlgc_line_fields.py` through the existing network worker with a separate
neutral request/result. Reuse the supplied sampled RLGC network and retain its
identity. Solve positive-frequency two-ended RMS waves and evaluate named
interior V/I, model energy and local loss; integrate conductor/dielectric loss
analytically and admit only checked whole-line power balance. Do not change the
existing unexcited or transient numerical APIs. No new dependency is added.

## Consequences

The ledger supports later coupling inputs without assigning conductor/volume
ownership or depositing heat. Frequencies remain separate steady-state cases.
DC fields, thermal feedback, causal material/geometry extraction and physical
qualification remain separate. [Referenced derivation and controls](../RLGC_LINE_FIELDS.md)
distinguish RMS quantities, signed transport, storage and dissipation.
