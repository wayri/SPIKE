# ADR 0121: refined obstacle-inertial enclosure CHT

Date: 2026-10-20. Status: experimental development; not release qualification.

## Decision

Keep enclosure CHT v1 and its full-rectangular inertial admission unchanged.
Add an explicitly selected v2 composition with shared nonuniform rectilinear
momentum/thermal cells and stationary supplied voxel obstacles. Re-solve actual
momentum after user-selected nested cuts, rather than relabeling interpolated
coarse velocities as refined flow. The cuts propagate tensor planes; they are
not confined hanging-face/octree AMR patches or curved-body conforming geometry.

The internal momentum implementation uses integrated primal mass and dual
momentum balances, pressure as the discrete divergence adjoint, physical dual
volumes and boundary-aware diffusion/transport. Retain the experimental computed
Reynolds ceiling of 20, nonlinear/mass/work checks, conditioning and resource
admission. Existing material, heat, boundary, startup-energy and publication
gates remain active. Do not automatically switch old jobs to the new method.

Expose separate `spike/enclosure-cht-request/v2` and result/v2 through the
existing isolated CFD worker/CLI. Supplied coarse cell data remain piecewise
constant under refinement and the input digest identifies the actual public
v2 request, not the internal admission projection. No new language/dependency.

## Acceptance and exclusions

Require actual uniform/nonuniform and obstacle mathematical checks, repeated
refinement, emitted-face mass/wall checks, source/flux/storage conservation,
failure/cancellation/contract tests and actual process runs. Source-bound
benchmark receipts distinguish these from independent physical validation.
Numerical evidence is linked in the accompanying method and workflow records.
Knowledgeable human review remains required before numerical release.

No turbulence closure, inflow/outflow, rotating blade boundary, MRF/sliding/ALE
mesh, propeller thrust/torque validation, or FSI is implied. These need separate
equations, boundary geometry, numerical checks and physical operating envelopes;
neither a viscosity knob nor a Coriolis postprocessor completes them.
