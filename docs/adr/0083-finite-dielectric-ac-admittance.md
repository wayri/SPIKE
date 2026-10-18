# ADR 0083: Finite dielectric AC admittance

Status: Accepted for bounded experimental development; human numerical review
before release.

Date: 2026-10-14.

## Decision

Add a separate `pdn_dielectric_ac` Python numerical module and versioned request
and result contracts for supplied retained dielectric meshes. Reuse existing
electrostatic geometry/electrode admission, but solve actual complex P1 fields
with γ=σI+ω tanδ ε+jωε at each positive supplied frequency. Keep the lossless
electrostatic API and frequency-invariant PDN transient contracts unchanged.

The existing owned worker exposes `extract_pdn_dielectric_ac`; presentation or
external formats do not own material or field physics. The module retains
source/mesh/context lineage, current-conservation and conjugate field-power
evidence, bounded resource admission, conditioning rejection and cancellation.
No new runtime dependency or implementation language is introduced.

## Acceptance and consequences

Original plate, differently lossy layered-plate and multielectrode references
test admittance, complex voltage redistribution, reciprocity and passive power
at mesh refinements. Worker/schema and failure/resource checks are part of
PI02-S01. See [derivation and limits](../PDN_DIELECTRIC_AC.md).

Finite insulating boundaries and electroquasistatic assumptions remain explicit.
Supplied finite-band loss tangent is not a causal broadband fit. No transient
network automatically consumes these samples; model reduction, material
dispersion, general board geometry and measured qualification remain open.
