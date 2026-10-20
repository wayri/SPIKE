<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0118: sampled series-R/L and shunt-C physical coupled-line boundaries

Status: accepted for experimental development, 20 October 2026.

Loaded coupled-line SI requires explicitly reactive endpoint laws as well as
resistive sources/loads. Add a narrow sampled physical-port closure around the
unchanged supplied symmetric pair, reusing its physical fields and provenance.
The existing RF worker and CLI expose separate versioned request/result schemas.

Conditioned four-port feedback solves the physical KCL/KVL equations. Keep source
current distinct from line current, real resistor/line heat W distinct from
mean stored J and reactive var. This preserves an explicit future multiphysics
handoff without inventing thermal geometry or deposition. No dependency,
language, mesh kernel or native solver is added. Numerical implementation remains
experimental pending human release review; general topologies and full board
qualification are open. See [method and primary references](../RLGC_REACTIVE_PAIR.md).
