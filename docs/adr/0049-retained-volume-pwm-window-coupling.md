<!-- SPDX-License-Identifier: Apache-2.0 -->
# Retained volume PWM window coupling

Status: implemented experimental source interface, 2026-10-10. Numerical human
review remains required before release. Existing lumped PWM contracts are unchanged.

## Decision

Add `spike/pwm-volume-electrothermal-request/v1` and result v1 as separate
headless contracts. Python orchestrates the existing persistent native MNA and
retained P1 solid thermal kernel. No new solver language, native executable or
external dependency is introduced. Only generated winding R(T) is admitted;
requests cannot supply executable expressions or DLL paths.

The retained mesh is the sole owner of thermal capacity. The new circuit has
no embedded thermal resistor/capacitor. Every dissipative element (Rw, SH, SL,
Load) must have a normalized explicit device-to-cell mapping. The original
winding-only RC mode remains available under its original contract.

`retained_thermal_step.py` prepares sparse stiffness/capacity matrices once and
offers a stateless energy-driven advance. The coupling loop snapshots native
history and restores it for every macro iteration; controller and thermal
starting states are unchanged until a converged window commits atomically.
Cancellation returns only the last committed public state. Nonconvergence
fails without publishing a partially accepted window.

## Consequences

This is constant-property solid conduction and bounded ideal-switch buck
coupling, not general semiconductor or enclosure qualification. Window-averaged
device heating requires separate electrical-step, thermal-window and mesh
refinement. CalculiX batch histories serve as independent oracles, not live
thermal stepping or rollback. Consistent P1 versus centroid DC3D4 capacity
differences remain explicit rather than forcing artificial cross-solver agreement.

See [workflow and derivation](../PWM_VOLUME_ELECTROTHERMAL.md) and
[correlation evidence](../validation/PWM_VOLUME_CORRELATION_20261010.md).
