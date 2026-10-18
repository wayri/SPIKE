<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0095: Shared material evidence snapshots

Status: implemented in development; not a solver qualification.

## Context

Mechanical parts previously carried a material ID without a portable property
record. PCB and mechanical analysis require different subsets of the same
thermal, electrical and mechanical evidence. A name such as FR4 or aluminium
does not identify a grade, orientation, temperature range or measurement method.

## Decision

Python owns a versioned SI material evidence contract and original local catalog.
Each property retains its own source, evidence status, applicability and shape.
Part, board and canonical board-layer assignments store complete digest-bound
snapshots in AssemblyIR extensions. Catalog updates do not alter assignments.
The desktop presents these records through the existing project worker and
manifest-bound mutations. The thin native host continues to authorize paths
and manifest identity, without interpreting material physics.

FreeCAD collaboration transports read-only material evidence with occurrences.
Its mirrored dependency-free validator verifies transport integrity; SPIKE
validates full property semantics before export. Placement feedback cannot edit
material data. Original ECAD design geometry and stackup are preserved.

## Consequences

Generic screening assumptions, unavailable properties and manufacturer typical
facts remain distinguishable. No implicit name matching, interpolation,
homogenization, material-axis rotation, or constitutive solver registration is
introduced. Solver adapters must explicitly admit supported fields and operating
conditions. Existing result contexts are invalidated and archived on an actual
assignment change. Reassigning identical evidence is a no-op.

See [records](../MATERIAL_LIBRARY.md), [assignment workflow](../MCAD_MATERIAL_WORKFLOW.md)
and [FreeCAD exchange](../FREECAD_COLLABORATION.md).
