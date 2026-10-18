<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0102: supplied crosstalk timing corners

Status: accepted for experimental implementation, 18 October 2026.

## Context

SI07 requires timing/noise budgets beyond simultaneous switching. The verified
sampled multi-aggressor API already separates common initial response from
aggressor deviations and directly checks complete extreme patterns.

## Decision

Add `sparameter_crosstalk_timing.py` above the existing parent through the same
worker boundary. A distinct v1 contract requires finite named delay corners,
explicit endpoint-held PWL translation on the unchanged horizon and identical
supplied initial states. Execute every admitted corner, retaining complete
parent results and identities; combine sampled extrema and attaining corner ids.
Preflight aggregate work and nested result size across all corners before fits.
No changes to old numerical/public contracts or new dependencies are needed.

## Consequences

Cost is C*(N+3) actual fits/trajectories. Finite corners and observation samples
bound the claim; negative delays do not infer settled prehistory. Complete
source/state records support later multiphysics ownership, while quadratic
energy requires a full selected-pattern solve. Referenced mathematics,
conditioning, tests and open gates are in the
[method ledger](../CROSSTALK_TIMING_CORNERS.md).
