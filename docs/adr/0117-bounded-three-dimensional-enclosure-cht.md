# ADR 0117: bounded three-dimensional enclosure CHT

Date: 2026-10-20. Status: accepted for experimental development only.

## Decision

Keep the existing creeping enclosure solver unchanged. Add a separately
admitted full-rectangular-fluid inertial MAC solver, with a computed Reynolds
ceiling of 20 and actual nonlinear convergence/kinetic checks. A composition
may surround that rectangular fluid region with solid conducting walls; it
must not fill obstacles or silently replace inertia with creeping flow.

Use shared rectilinear fluid-solid finite-volume sensible energy, steady or
backward Euler, with manually selected nested thermal cuts. Prolong normal MAC
velocities in the rectangular RT0 form so subface flux and parent divergence
are preserved. Cuts propagate tensor planes; this is not local momentum AMR.

Expose `spike/enclosure-cht-request/v1` and result/v1 in `service_cfd.py` and
the existing CFD CLI, not in the central application solver dispatch. Existing
NumPy/SciPy only; no dependency or language expansion. Inputs and accepted
results are bounded to 8 MiB. Publication rejects partial/oversized fields.

## Consequences and evidence

Supplied constant-property voxel solids, a single fluid and closed no-slip flow
are the current geometry/model boundary. Unknown fields, unsupported geometry,
unresolved anchoring, metric distortion, conservation failure, nonlinear failure
and cancellation reject without accepted fields. Sparse factorization is not
in-kernel cancellable. Thermal time evolution assumes fixed steady flow.

[Workflow and limits](../ENCLOSURE_CHT_3D.md),
[independent derivation and reviewed source scopes](../validation/ENCLOSURE_CHT_METHOD_20261020.md),
permanent enclosure tests and the reproducible benchmark runner supply the
development evidence. Human numerical review and measured/external validation
remain required. No release, installed binary, old receipt, full-suite or
arbitrary-enclosure claim is promoted. Turbulence/rotors remain later explicit
stages, not options activated by this ADR.
