<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0096: Bounded sheet folding geometry

Status: implemented in development; geometric preview, not a deformation solver.

## Context

Rigid-flex imports retain flat fabrication geometry and bend metadata. Sheet
metal, nonmetal sheets and flex studies need explicit developed dimensions,
thickness, bend radii and flat/folded states without changing solver eligibility.

## Decision

Add a versioned inert rectangular-sheet contract and Python geometry service.
Parallel finite-radius bend strips compose in a declared fixed-side sequence.
Their supplied neutral-axis factor determines developed bend allowance. Flex
definitions require each bend strip to lie within a declared flex region.
JSON and a bounded planar DXF rectangle adapter feed the same definition.
No new dependency or implementation language is introduced.

The desktop edits definitions and displays returned triangle meshes through the
existing worker. Imports read selected text, exports use the native save dialog,
and previews perform no project or source mutation. Arbitrary host paths and
scripts are not accepted by the worker methods.

## Consequences

Material snapshots remain evidence rather than constitutive input. Thickness
and unit assumptions must be reviewed. Flat PCB geometry, electrical topology,
components and solver contracts remain independent. General CAD unfolding,
folded BREP/STEP, source-board mapping, collision admission and folded physics
require further explicit implementations and qualification.

See [derivation, method reference, workflows and limitations](../SHEET_FOLDING.md)
and [existing rigid-flex solver policy](../RIGID_FLEX_SUPPORT.md).
