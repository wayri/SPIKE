<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# ADR 0025: Bounded local refinement for experimental conforming copper

Status: proposed; implementation experimental pending maintainer review.

## Context

The conforming rectangular copper partition had only a global maximum
interior edge. A board-wide reduction spends cells far from a feature of
interest and can exceed the supervised RT0 resource cap. Track-only manual
controls do not address zone, pad-adjacent, and via-adjacent interior copper.

## Decision

Admit `spike/conforming-local-refinement/v1` under `AnalysisSpec.mesh` with
at most 64 layer/net-scoped rectangular regions. Cut retained noncontact
rectangles at exact region boundaries, then subdivide only the affected
pieces to the requested maximum edge. Keep the source copper union, fixed
terminal footprints, material values, and existing global refinement unchanged.
Reject malformed, ineffective, and over-budget controls. Record application
counts in mesh admission metadata. The capability remains experimental.

## Consequences and evidence

This is a user-controlled spatial discretization, not adaptive error
estimation or production conforming 3-D meshing. It cannot turn the current
rectangle AC current bases into copper-supported affine bases. Geometry-union,
contact-invariance, deterministic replay, invalid-control, budget, and
support checks are in `tests/python/test_peec_conforming_mesh.py`.
Numerical R/L/C convergence and independent correlation remain separate gates.
