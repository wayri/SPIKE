<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0111: Supplied scalar RLGC star with owned fields and heat

- Status: accepted for experimental implementation; not production qualified
- Date: 2026-10-19
- Stage: SI02-S06

## Context

SI02-S03 and S04 establish bounded uniform supplied-line networks and coherent
fields/losses. S05 composes these along an ordered cascade. A multi-terminal
branch needs current conservation at one common node, rather than pairwise
current opposition. Existing harness MTL already admits supplied branching;
the new stage's distinct value is reuse of stable S03/S04 propagation with
coherent interior fields and separately owned conservative heat.

## Decision

Add a Python application-service module `rlgc_line_junction.py` with strict
`spike/rlgc-line-junction-request/v1` and result contracts. Admit only a star
with 2–8 scalar uniform legs, external left ends and a common ideal right node.
Use an explicit incident wave vector ordered by unique leg IDs. All legs share
the exact positive-frequency grid and real reference. Retain original line
requests, probe ownership and complete S04 children.

Derive the lossless junction wave matrix from common voltage and summed inward
current zero: `J=2/m*ones-I`. Compose actual S03 networks through a bounded
simultaneous wave solve. Execute actual S04 fields using solved local waves;
check child provenance, boundary agreement, node voltage/KCL/power, external
wave power and sum of owned heat. Retain raw residuals. No repairs, heat
redistribution or implicit renormalization are allowed.

Expose a worker method, CLI `rlgc-junction`, checked-in executable example and
strict JSON schemas. Do not add a GUI flow, language, native binding or external
dependency. Python owns bounded numerical composition using existing NumPy;
SciPy spatial exponentials/quadrature belong to independent tests. S03/S04/S05
numerical implementations remain unchanged.

## Alternatives and consequences

A general tree/graph would add topology admission, hidden-leaf and cycle
semantics without being needed for a useful coherent T-junction study. A
physical PCB junction model would require separate geometry/material
assumptions and validation. Both remain outside this stage.

The star supports multiport external waves and per-leg interior dissipation
with a bounded conservation contract. It requires exact shared wave reference,
rejects ill-conditioned/unrepresentable cases, and has no DC field support.
It does not certify broadband causality, map heat into thermal geometry, or
repair any board reference-zone admission issue. Existing generic harness
branch support is not recharacterized as newly implemented physics.

## Evidence

See [method derivation, reviewed primary source, units, controls and executed
verification](../RLGC_LINE_JUNCTION.md). The independent physical nodal/spatial
oracle, quadrature, analytic matched star, two-leg cascade equivalence and
failure cases are executable in `tests/python/test_rlgc_line_junction.py`.
Registered worker/CLI/schema checks are in the companion contract test module.
Synthetic verification does not establish measured physical accuracy;
knowledgeable human numerical review remains required before release.
