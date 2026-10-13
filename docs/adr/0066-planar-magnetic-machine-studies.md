# ADR 0066: Experimental planar magnetic machine field studies

Status: implemented experimental boundary, numerical review pending.

## Decision

Keep the existing parameter-machine contract unchanged. Add a bounded original
Python P1 magnetic kernel, conforming planar geometry builder, thermal kernel and
study service behind the existing supervised worker. The same versioned study
is accessible from CLI and the EM workbench and retained in project EM setup.
TypeScript renders returned data only. No third-party implementation, geometry
fixture or test data is incorporated.

## Rationale and limits

An installed solver runtime or a reduced mechanical model does not establish
machine FEM support. Independent analytical tests qualify the initial planar
operator and stationary eddy/thermal coupling. Force extraction uses explicitly
meshed air contours; unsupported moving-conductor coupling fails closed.
Conforming rotating interfaces and 3D STEP machines remain separate work.
This decision does not authorize claims of a complete or production-qualified
machine solver. See [workflow and contracts](../MAGNETIC_MACHINE_STUDIES.md),
[magnetic derivation](../MAGNETIC_FEM.md) and
[thermal derivation](../MAGNETIC_THERMAL.md).
