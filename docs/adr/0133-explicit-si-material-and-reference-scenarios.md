# ADR 0133: Explicit SI material and reference scenarios

Date: 2026-10-23

Status: Accepted for experimental source and Windows worker execution;
physical qualification and release promotion remain separate.

## Context

Complete imported boards can omit conductor conductivity and retain multiple
reference regions. Silent copper defaults, arbitrary plane selection and
editing imported source identity would make results misleading or stale.
Large retained boards also exceed the worker's inline control-message budget.

## Decision

Keep import identity immutable. A new Python application-service API,
`prepare_si_material_scenario`, admits a strict versioned request bound to both
canonical design and original source digests. It returns a separate copied
design with exact material-ID overrides and caller-declared provenance.
No material-name inference, class relabeling, geometry replacement or implicit
temperature/frequency law is permitted. Conductivity uses S/m and temperature
uses kelvin; provenance declarations are not independently authenticated.

Use the existing SI service composition root for an exact `{design, request}`
inline method, limited to 8 MiB input and result. Retained in-process designs
have a separately documented 128 MiB/250,000-entity bound. This is not permission
to truncate a board, enlarge shared IPC limits or add filesystem access.

Add optional exact `reference_zone_id` selection to the existing SI request.
It must match the declared reference net/layer and pass unchanged outline,
hole and coverage checks. Without it, ambiguous regions remain rejected.
Omitted competing regions are reported as an approximation, never merged.
Uniform and coupled extraction share the selection rule. Both physical material
inputs and the complete declared scenario context enter extraction identity.

No new numerical kernel, dependency, implementation language or native-code
execution boundary is introduced. Python owns preparation and orchestration;
the existing channel operator remains experimental.

## Consequences and evidence

Callers must explicitly supply missing physical inputs and rebuild a scenario
from its bound original design when inputs change. Legacy conversion loss
cannot be repaired through this API. A selected region is not a validated
complete return-current model. Large boards use the retained API, not inline
worker transport. See [the workflow](../SI_MATERIAL_SCENARIOS.md) and
[executed checks and remaining gates](../validation/SI_BOARD_SCENARIOS_20261023.md).
No production, protocol-compliance or measured-accuracy claim follows from
the new boundary.
