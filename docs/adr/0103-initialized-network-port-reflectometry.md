<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0103: initialized network-port reflectometry

Status: accepted for experimental implementation, 18 October 2026.

## Context

SI07 needs reflectometry diagnostics tied to executed network waveforms and
physical port/current identity. Boundary source current includes shunt-C current
and is not the current crossing the fitted-network reference plane.

## Decision

Add `sparameter_reflectometry.py` above the initialized RLC solver through the
existing network worker, with distinct strict v1 request/result contracts.
Execute once, use the actual port a/b and network V/I, and verify reconstruction.
Require explicit incident-voltage/current floors; unresolved ratios retain null
and reason statuses while raw samples remain available. Compute apparent
impedance directly as V/I and signed transported power as V*I. Preserve the
complete parent result, request identity, probe plane and thresholds.

## Consequences

No old numerical contract, propagator or dependency changes. Apparent ratios
depend on other drives and supplied initial state; they are not automatically
isolated S11, spatial TDR or material properties. Signed transported power is
not heat. Referenced derivation, numerical admission, independent verification
and open physical gates are in the [method ledger](../NETWORK_REFLECTOMETRY.md).
