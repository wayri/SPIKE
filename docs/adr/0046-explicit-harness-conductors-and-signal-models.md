<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0046: Explicit harness conductors and supplied signal models

Status: experimental implementation; numerical human review required before release.
Date: 2026-10-09.

## Decision

Extend the existing harness contract with optional roles, explicit returns and
ordered pair metadata. Preserve legacy documents without inventing electrical
properties. Bind assembly conductor metadata to exact occurrence endpoints and
the saved pin map; validate before project persistence and analysis.

Share the diagram/inspector and analysis editor between standalone and assembly
documents. Keep 3D presentation independent of circuit validity. Use bounded
conductor sampling and existing owned scene-resource disposal. Physical twist
pitch controls displayed turns; spacing/radius remain explicitly schematic.

Reuse the native DC MNA kernel for an explicit selected wire subset, and the
existing uniform RLGC network kernel for a supplied two-conductor mode. Keep
transport, model admission and UI separate. Persist the complete SI request
snapshot and reject stale results. Expose worker, CLI and read-only MCP routes.

EM preparation is a fail-closed requirements handoff. It never claims a field
solution. Common mode, crosstalk, shield transfer, geometry extraction and
full-wave radiation require separate models and validation.

## Evidence and consequences

Independent KVL/I-squared-R and lossless transmission-line oracles protect the
bounded adapters. Tests exercise actual worker execution and `.spike` round-trip,
including preservation after rejected stale pin maps. Diagram tests exercise
parallel-wire identity, pair edits, splice branches and cascading references.
See [workflow and limits](../HARNESS_ENGINEERING.md).

No new numerical dependency or implementation language is introduced. No
external implementation, model or dataset was copied. Successful presentation
and these analytical fixtures do not establish real harness field qualification.

## Backend follow-up (2026-10-09)

Add separate `spike/harness-mtl-request/v1` and
`spike/harness-round-wire-rlgc/v1` contracts rather than changing the earlier
uniform SI model's meaning. The first uses exact sampled reciprocal matrix RLGC
and scaled-current MNA for branched/parallel networks, explicit contacts/loads,
ordered modes and terminal responses. The second is an admitted approximate
straight solid nonmagnetic round-wire/ideal-plane extraction, including internal
skin impedance; it supplies the first contract's model without implicit physical
twist/display translation. Existing SciPy/NumPy dependencies suffice.

Both remain backend APIs until supervised UI/worker integration is separately
verified. Preserve every wire and occurrence label, explicit units/reference,
condition/resource/cancellation failures and unsupported geometry status.
Analytical and independent refining-ladder/diffusion oracles are the current
evidence. Full-wave fields, real cable/connector/shield and board-copper coupling,
causality, external-solver/measured comparison and numerical human review remain
open. See the harness engineering document for derivation, sources and bounds.
