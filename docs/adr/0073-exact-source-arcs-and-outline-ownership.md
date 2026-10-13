# Exact source arcs and outline ownership

Status: Accepted for bounded import and transport; no solver accuracy promotion.

## Context

KiCad copper arcs were imported only as eight straight chords. Canonical v2
could not recover the exact source arc, and adding both forms would duplicate
copper in Arrow and native geometry handoffs. Multiple straight Edge.Cuts loops
were retained only as drawings and could not safely reach volume consumers.

## Decision

Retain exact nondegenerate source arcs in the existing Arc collection. Each
canonical conductor has one active representation: legacy chord children are
removed from canonical tracks after validating net/layer/width, continuity,
source-circle membership and ordered sweep. Anonymous occurrences receive
deterministic separate source IDs. Imported legacy chord rows and their order
are bound to the Arc extension with geometry basis and content digest.

Canonical-to-v1 numerical projection restores admitted unchanged chords in
original order and remains explicitly approximate. Changed arcs or chord
records fail with a stale-projection error. Arcs without an admitted surrogate
fail solver projection rather than disappear. Nonnumerical presentation and
persistence may explicitly request `allow_unprojected_arcs=True`; numerical
legacy boundaries independently reject omitted arc geometry. Exact Arrow/layout
transport remains separate from executable curved-conductor physics.

Use one shared bounded normalizer for straight Edge.Cuts rings. It requires
exact endpoint closure, one simple outer loop and strictly contained disjoint
cutouts; it rejects branches, duplicate edges, touching/overlapping holes,
islands, nonfinite coordinates and unsupported curved primitives. Imported
normalized rings use the established `board_outline_rings` metadata contract.
Bounds come from the retained outer ring, never from a replacement rectangle.

## Scope and evidence

The original parity fixture supplies a radius-2-mm semicircle, rotated pad,
31-by-21-mm outer outline and 2-by-2-mm cutout. Tests cover exact source values,
unique conductor transport, lossless legacy order, stale/forged projections,
anonymous occurrence identity and rejected topology. Retained volume preparation
must preserve area 647 mm² and stack volume 1035.2 mm³. Native KiCad confirms
the unchanged source geometry; its nonclean DRC findings remain retained.

No new language, runtime engine, mesher or public ABI is introduced. Shapely
is an existing geometry dependency. This decision qualifies import/transport
of the declared classes; it does not qualify full-wave, curved SI/PI extraction,
thermal prediction, arbitrary outline curves or general package geometry.
