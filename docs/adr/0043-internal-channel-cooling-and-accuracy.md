<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0043: Internal channel cooling and solution-specific thermal checks

Status: experimental implementation, pending numerical human review before release.
Date: 2026-10-09.

## Decision

Keep the original laminar parallel-plate reference in Python, with a bounded
versioned request/result and explicit applicability envelope. The worker and
MCP expose the same operation; the desktop plots only returned temperatures and
velocities. No executable, upstream implementation or new language is required.
This is a prescribed-flow fluid energy calculation, not an assembly CHT solver.

Retain the proven solid backward-Euler contract. A separate operation runs
three admitted histories and returns time-refinement evidence plus the fine
result. Evidence cannot mutate per-result qualification or solver diagnostics.
Each run and the combined returned envelope obey the serialized size bounds.

## Consequences and evidence

Original analytical momentum, enthalpy, semidiscrete exponential and continuous
temperature-profile oracles verify the channel discretization; exact discrete
single-DOF decay verifies the time audit. Event-limited grids cannot pass.
See [channel derivation](../INTERNAL_AIRFLOW.md),
[accuracy checks](../THERMAL_ACCURACY_CHECKS.md), and
[established solver evidence](../validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md).

General 3D fluid momentum, turbulence, arbitrary CAD domain extraction and
coupling to solid temperatures require additional contracts, independent
benchmarks and reviews. Availability of this screen cannot enable those claims.
