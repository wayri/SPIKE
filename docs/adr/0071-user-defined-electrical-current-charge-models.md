<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0071: Inert user-defined current/charge device composition

Status: implemented experimental interface; numerical human review pending.

Decision: extend model composition rather than add material-name dispatch.
`spikes/equation-device/v1` supplies ordered terminals, unit-bearing parameters,
and paired branch I/Q equations. The builder emits bounded B/V/C subcircuits
executed by existing owned C++ MNA kernels. Conservative charge is lowered
through an auxiliary Q/Cr voltage, Cr capacitor and sensed-current copy. The
derivation and discrete integration oracles are in SPIKES_EQUATION_DEVICES.md.

Package parasitics remain an independent `spikes/device-parasitics/v1` wrapper
with arbitrary pin count/order and constant R/L/C/leakage. No core implementation
or dependency is executed during library construction. A missing model never
becomes a resistor or a different semiconductor family.

Consequences: portable `.lib` artifacts and no new solver device-family enum,
DLL loader or Python runtime callback. Added auxiliary unknowns reduce efficiency
relative to direct native charge stamping. Internal-state DAEs, thermal/noise
callbacks and dimensional proof remain separate work, not inferred capabilities.
Compiled plugins still require the existing explicit trust boundary. Optional
K output is not owned-runner execution support. The interfaces preserve
unqualified model status and do not establish manufacturer/material validation.
