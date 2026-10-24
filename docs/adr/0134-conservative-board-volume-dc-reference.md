<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0134: explicit board-volume contacts and conservative tetrahedral DC

Status: accepted for isolated experimental reference development; not release qualified.
Date: 2026-10-23.

## Problem and decision

A planar sheet field plus an axial branch histogram cannot establish current
density in the physical landing and barrel volumes. The annular reference is
restricted to one coaxial axisymmetric assembly. General board finite contacts
and through-thickness transitions need a conforming physical-volume model.

Add a small offline RT0/P0 tetrahedral reference on the existing retained solid
mesh contract. Reuse the strict solid geometry/overlap/hanging-node audits;
independently derive exact tetrahedral Ohmic mass and face-trace elimination.
One shared face identity enforces normal-current continuity. Finite polygonal
board contacts map to complete exterior triangles with uniform normal current
and conjugate mean potential. No electrode comes from a coordinate alone.

Geometry preparation, numerical admission, field solve, physical-volume density
statistics and retained-result validation have separate owners. A board compiler
must retain all explicit slabs and barrel gaps, prove their disjoint coverage and
record source/model assumptions. All unexcited conductor components contribute
their physical volume. The generic solver cannot declare a complete source board
from a supplied mesh. See [governing derivation and acceptance](../DC_TETRA_RT0.md).

## Language, performance and qualification

This is a bounded NumPy/SciPy reference using existing Shapely geometry
operations, not a second production framework or additional dependency. Sparse
assembly and bounded per-cell matrices support verification first; native
acceleration requires separate profiling, independent equivalence and release
evidence. No existing public solver dispatch, schema or original board threshold
is changed. Existing P1 assembly electrical and planar RT0 users remain separate.

Knowledgeable human numerical review, original EBrake/Marble study acceptance,
mesh/physical uncertainty, AC/SI and installed qualification stay open. Failures
and unsupported contact/material/source geometry must remain explicit. Full
PI01-S02 may be marked done only after its existing acceptance evidence passes.

24 October development extension: a separately named explicit scalable request
and board-model profile can evaluate localized partitions and one-factor trace
solves under isolated memory/time supervision. Original admission remains
unchanged. See [derivation, controls and limits](../DC_TETRA_SCALABLE.md).
This decision permits experimental evaluation, not a runtime or board-parity
promotion; retained board refinement and human numerical review remain gates.
