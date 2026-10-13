<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0074: Two visible applications, explicitly managed backend engines

Status: product boundary agreed; project preflight/layout-inspection foundation implemented.

Decision: SPIKES owns IC/ASIC design, simulation, constraints and flow management;
KLayout owns interactive layout and its native verification ecosystem. The user
explicitly permits approved engines bundled behind SPIKES, so additional user-
operated synthesis/timing/place-route/extraction applications are not required
by the target UX. Backends remain declared, versioned process interfaces with
licence, platform, capability and artifact-provenance gates.

`.spkasic` preflight binds actual artifacts/engines/runsets by hashes, exposes
unexecuted/missing gates and never claims release readiness. KLayout inspection
uses a checked-in headless probe and bounded result admission, preserving
geometry, hierarchy, units and hashes. KLayout's separate process does not add
Qt to the SPIKES interpreter or bundle, and is not a hostile-code sandbox.

No implicit engine substitution or device-model approximation is introduced.
Connectivity extraction is not PEX. Managed physical-design engines, PDK DRC/
LVS execution, distributed parasitic extraction and post-layout closure are
still pending; see SPIKES_ASIC_TWO_APPLICATION_FLOW.md for release gates.
