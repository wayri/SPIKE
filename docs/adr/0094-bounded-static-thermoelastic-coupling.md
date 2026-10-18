<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0094: Bounded static thermoelastic coupling

Status: accepted for experimental development; release qualification open.

## Context

The user explicitly requested mechanical stress/deformation integrated with
thermal, electrical and magnetic studies now. Existing thermal volumes and
source ownership are reusable; a viewport mesh or CAD solid alone is not an
admitted structural problem. General 3D machines and Hall transport remain open.

## Decision

Add original isotropic small-strain static P1 tetra elasticity using existing
NumPy/SciPy and conforming retained-mesh validation. Admit supplied nodal forces,
component displacement constraints and per-node temperatures with material
thermal expansion. Reject rigid modes, poor conditioning and resource overruns.
Keep engineering strain shear and physical stress shear explicit.

Expose two bounded worker methods and versioned contracts. The thermal adapter
executes the existing steady heat solver and transfers actual nodal Kelvin
temperatures only on an identical indexed owned mesh. Hash the initial request
and generated structural request separately. No automatic CAD mutation or
deformed-geometry feedback is introduced.

## Consequences

Independent stress/energy/reaction/thermal references and manufactured refinement
support this bounded stage. Mechanical contact, dynamics, nonlinear materials,
failure/lifetime, moving machines, Hall devices and nonmatching transfers retain
separate stages. The explicitly scoped parallel policy does not establish parity
or authorize unrelated expansion. No new dependency or implementation language
is added; knowledgeable human numerical review remains required before release.
