<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# ADR 0026: Direct connector mates in multi-board assemblies

Status: implemented topology contract; coupled physics remains blocked.

## Context

AssemblyIR stores board occurrences and cable harnesses. Stacked boards can
mate through headers without a cable, and a zero-length harness would impose
the wrong cable model. Placement alone cannot identify connected pins.

## Decision

Use an AssemblyIR `connector_mappings` record with
`kind: "connector-mate"` and typed data containing two distinct
`board::connector` endpoints and a one-to-one `pin_map`. This is an additive
v1 record: existing connector mappings and harnesses remain valid. Validate
board ownership, pin identities, and pin reuse across mates and harnesses
before saving or planning. Expose mated connectors as separate graph edges in
the PI, SI, thermal, and EMI multi-board plan. Preserve selected-board scope.

## Consequences and evidence

The record is topology only. It supplies neither contact resistance nor an
SI launch model, heat-transfer coefficient, return path, or electromagnetic
coupling. Coupled plans remain blocked. Geometry placement and connector
mating fit require separate evidence. Regression coverage is in
`test_multiboard_analysis.py` and `test_assembly_designs.py`; the latter checks
manifest-bound project round-trip.
