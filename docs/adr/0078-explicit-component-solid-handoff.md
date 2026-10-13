# Explicit component-solid handoff

Status: Accepted for bounded mechanical exchange.

## Context

Source model references and vectors do not establish package geometry or a
qualified model-to-board transform. Automatic board projection previously
reported every component as missing geometry, even when a caller could supply
a complete STEP body and explicit placement. Source KiCad placement remains
unapplied until an independent composed-placement reference is available.

## Decision

The Python mechanical projection accepts optional `parameters.component_models`
bindings. Each identifies one component occurrence and one of its retained
canonical model IDs, the exact retained design digest, an embedded STEP asset,
an explicit board-local rigid transform in millimetres and a placement reference.
The reference is a supplied provenance statement, not authenticated approval.

`mcad_component_models.py` checks ownership, baseline, uniqueness, resource
budget and transform semantics. Existing MCAD validation checks STEP bytes and
digest, material identity and solid geometry. Binding validation happens on a
copy before projection changes. No path or URL is opened by the handoff.
The manifest retains the supplied STEP byte digest as well as the source model
URI and design baseline. The reference gate checks board/material ownership and
requires the native export's solver qualification to remain explicitly false.

Each body is parented to its board occurrence. The existing native kernel
composes assembly/board placement. Repeated boards require independent bindings.
Only a completely supplied component model list closes that occurrence's
missing-solid diagnostic. Partial coverage continues to require `allow_partial`.

Source design/model transforms stay unchanged. Nonuniform scale and reflections
must be explicitly baked into supplied geometry; assembly placements admit only
proper rigid transforms. A supplied material ID retains its properties but
does not establish material-law applicability. Every new body records
`solver_ready: false` and `material_qualified: false`.

## Evidence and limits

Original 2x3x4 mm cuboid geometry is exported/read back through FreeCAD 1.1.3 and
Open CASCADE. Three independent explicit neutral placements have volume 24 mm3
and analytically specified bounds, checked to 1e-6 mm/mm3. Invalid ownership,
stale baselines, duplicate/nonrigid bindings, partial coverage, repeated boards
and the isolated extension boundary have regression coverage. See
[stage evidence](../validation/parity/WF01-S04C1.json).

This verifies explicit mechanical exchange. It does not authenticate a model
publisher or substitute supplied solids for qualified original URI contents.
KiCad source rotation order, nonuniform scale, offsets and front/back composition
remain unqualified. Native export attempts and missing evidence are retained in
[S04C progress](../validation/parity/WF01-S04C-progress.json).
