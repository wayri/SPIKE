# ADR0128: Same-mesh AC loss to heat to elasticity

Status: Accepted for bounded experimental in-process development; human numerical
review required before release. Date: 23 October 2026.

Compose the existing `pdn_dielectric_thermal` and `assembly_tetra_structural`
owners in `pdn_dielectric_thermomechanical`. Numerical kernels and their gates
are unchanged. Require exact canonical mesh/ownership and common supplied context,
null caller structural temperatures, existing structural preflight and actual
solved Kelvin temperatures. Retain nested solver evidence, child input digests,
transferred-temperature identity and distinct legacy Unicode digest profiles.

The new versioned request/result are internal Python API records. No worker,
UI, plugin manifest, public native ABI, new dependency or persistence route is
registered. Request/result budgets remain 8/16 MiB; cancellation/failure publishes
no partial success. Thermal cancellation remains between subsolves.

Single-tone finite electroquasistatic dielectric heating, steady heat and
small-strain isotropic static elasticity do not establish general PCB/SI,
transient electrothermal mechanics, deformation feedback, contact or fatigue.
See [method and executable example](../validation/AC_THERMAL_ELASTIC_20261023.md).
