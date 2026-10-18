# ADR 0085: Conservative dielectric-to-thermal coupling

Status: Accepted for bounded experimental development; human review before release.

Date: 2026-10-16.

## Decision

Add one-way coupling of the existing finite-dielectric AC and retained thermal
solvers within the Python worker. Recompute actual complex electric fields for
one supplied coherent RMS tone, integrate conductive/dielectric dissipation and
bind volumetric heat to the identical retained mesh by exact cell identity.
Check volume power against terminal power before executing the thermal solve.

Preserve original requests, ownership, material/geometry units and source/context
digests. Reject mismatched meshes, missing drives and pre-existing heat sources.
Require independent heated-slab temperature refinement as well as energy balance.
See [contract and derivation](../PDN_DIELECTRIC_THERMAL.md).

## Consequences

This advances reusable multiphysics handoffs while PI/SI stays first priority.
It introduces no language or solver dependency. The original AC and thermal
APIs retain authority; their admitted states are not promoted to production
qualification. Electrical properties do not receive temperature feedback, and
the existing thermal solve cannot be internally interrupted through a callback.
General multiphysics expansion and different-mesh transfer remain separate gates.
