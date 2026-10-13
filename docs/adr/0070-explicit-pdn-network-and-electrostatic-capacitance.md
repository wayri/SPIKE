<!-- SPDX-License-Identifier: Apache-2.0 -->
# Explicit PDN networks and retained dielectric capacitance

Status: implemented bounded source capability, 2026-10-12. Physical-model and
knowledgeable numerical human review remain required before release.

## Decision

Keep the existing copper PI/PEEC workflows and PDN screening contracts intact.
Add a versioned explicit passive-network request for AC impedance/transfer and
finite-rise PWL load transients, plus a separately admitted retained dielectric
electrostatic request. Both execute in the Python worker; the Rust host only
classifies heavy operations for its existing supervision/cancellation boundary.
No new runtime dependency or implementation language is introduced.

The existing native circuit ABI does not supply the complete coupled-winding
AC multiport surface needed here. A bounded SciPy descriptor MNA implementation
therefore handles explicit constant R/L/C, ESR/ESL and signed mutual inductance.
It is not substituted for a general SPICE engine or a full-wave PCB solve.

Capacitance sources remain distinguishable: supplied lumped data, supplied
Maxwell matrices, the existing approximate planar area model, and actual P1
finite-dielectric field extraction. Reduced Maxwell matrices retain all
conductor states; mutual edges are never replaced by diagonal ground shunts.
Reference selection defaults from ground-like names for convenience only;
actual return/electrode geometry and connections remain explicit.

Power-tree setup has an additive `acPdnRequest` field. The AC panel edits the
versioned request, rejects stale/malformed results and plots only solved data.
It saves setup, not newly fabricated result qualification. Imported field
returns must match the explicitly selected circuit reference before attachment.

Series capacitor legs use explicit intermediate nodes. A separate analytical
sharing review evaluates capacitance tolerance and supplied leakage/balancing
resistance; it never sums nameplate voltages into an automatic safe rating.

## Consequences

Dense-network work and control/result sizes are bounded. Singular, nonpassive,
invalid, cancelled or ill-conditioned solves fail explicitly. Condition checks
use equilibrated matrices and unscaled backward errors. Trapezoidal energy
checks use compensated cumulative physical work/dissipation to avoid false
failures when the stored energy decays to zero; per-step gates remain active.

These capabilities do not establish automatic arbitrary-PCB conductor/port
meshing, dielectric/ferrite dispersion, magnetic saturation, regulator control,
measured hardware correlation, or general AC layer/EM-field qualification.
See [workflow and model boundaries](../PDN_SCREENING.md#explicit-ac-pdn-and-filter-workflow).
