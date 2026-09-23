# Custom Autorouter and Autoplacer Integration

`spike/layout-evaluation/v1` is the public, solver-independent boundary between
a custom layout search and SPIKE/SPIKES evaluators. It lets an autorouter,
autoplacer, or joint optimizer submit an immutable candidate, declare bounded
hard/soft requirements and objectives in SI units, create integrity-bound
native jobs, and correlate the returned metrics with the exact candidate.

It does not route, place, run CAD DRC, translate a PCB into a physics model, or
claim that a solver result is qualified. Search strategy and candidate mutation
remain owned by the custom router/placer.

## Worker API

The JSON-line worker exposes six methods:

| Method | Parameters | Result |
| --- | --- | --- |
| `validate_layout_evaluation` | `request` | Strict normalized request |
| `validate_layout_metric_registry` | `registry` | Strict normalized evaluator registry |
| `negotiate_layout_requirements` | `request`, `registry`, optional batch/incremental policy | Per-requirement capability decisions |
| `preflight_layout_candidate` | `request`, complete `candidate`, optional `baseline`/`parent` | Digest, byte, entity-reference, scope, and lineage evidence |
| `prepare_layout_native_jobs` | `request`, complete `candidate`, `registry`, optional `baseline`/`parent` and batch/incremental policy | Deterministic list of correlated `spike/solver-job/v1` envelopes after mandatory negotiation and candidate preflight |
| `map_layout_evaluation_results` | `request`, `native_results`, optional `external_results` | `spike/layout-evaluation/v1` result with feasibility, margins, and an optional normalized objective score |

`native_results` is keyed by the `request_id` returned by
`prepare_layout_native_jobs`. `external_results` is keyed by requirement ID and
is used for `cad_drc` or `custom` requirements. A layout validation failure uses
the standard worker error code and also returns the more specific
`layout_error_code` (for example `SPIKE-LAYOUT-CONTRACT-0004`).

Python consumers can use the same operations directly through:

- `validate_layout_request`
- `preflight_layout_candidate`
- `canonical_layout_json`
- `validate_metric_registry`
- `validate_requirements_for_launch`
- `prepare_native_jobs`
- `map_layout_results`

The same preparation and scoring operations are also exposed through the
dedicated fixed process interface:

```text
spike-layout-scoring-worker --request <job>/request.json --result <job>/result.json
```

Its strict `spike/layout-scoring-process-job/v1` envelope has two actions.
`prepare` performs registry negotiation, complete-candidate preflight and
deterministic native-job derivation. `score` maps already correlated native and
external results. Controls are normalized job-relative paths, results are
published atomically, and duplicate/nonfinite JSON, traversal, symlinks or
reparse points fail closed. The process is experimental and source-runnable;
it does not route, place, mesh, solve, or presently constitute a qualified
packaged artifact.

## Evaluator capability registry

Before preparing any native, DRC, or custom evaluator job, load a strict
`spike/layout-metric-registry/v1` document and call:

```python
from spike_core.layout_metric_registry import (
    validate_metric_registry,
    validate_requirements_for_launch,
)

registry = validate_metric_registry(registry_document)
negotiation = validate_requirements_for_launch(
    layout_request,
    registry,
    batch_size=len(candidate_batch),
    incremental=use_incremental_evaluation,
    change_kind="routing" if use_incremental_evaluation else None,
)
# Only after this point may prepare_native_jobs(...) or another evaluator run.
```

Each registered metric binds its stable ID to a seven-base SI dimension,
evaluator kind, supported consumers/kinds/relations, native result key when
applicable, validation state, immutable hashed evidence, and explicit batch and
incremental limits. Negotiation fails closed on an unknown metric or any
evaluator, dimension, result-key, consumer, relation, validation-policy, batch,
or incremental mismatch.

The module also exposes `negotiate_layout_requirements` for the same typed
operation and `canonical_metric_registry_json` for reproducible registry
serialization. The worker requires the host-selected registry on every prepare
request and runs `validate_requirements_for_launch(...)` immediately before job
construction. This keeps evaluator trust policy explicit and host-owned.

## Integration sequence

1. Write a complete candidate artifact, normally `spike/design-ir/v2`, into the
   job directory and compute its SHA-256 digest. A delta may be described using
   `parent_candidate_sha256` and `changed_entity_ids`, but the candidate
   reference still identifies a complete immutable artifact.
2. Translate the candidate into each independently reviewed
   `spike/physics-model/v1` artifact required by the requested evaluations.
3. Build the layout request. Every requirement declares its evaluator, kind,
   relation, seven-base SI dimension vector, scope frame, and entity IDs.
   Native requirements also declare the bounded scalar `result_key` expected in
   a `result-bundle/v2` summary.
4. Validate the request, negotiate every metric against the selected registry,
   and preflight the complete canonical candidate before preparing native jobs.
   The derived request IDs are
   deterministic and bind the canonical layout request to each physics
   evaluation. Layout and consumer data are intentionally not injected into the
   solver job.
5. Launch each job only through the trusted fixed process interface:
   `spike-native-solver --request <job>/request.json --result <job>/result.json`.
6. Run CAD DRC and custom evaluators separately and provide their bounded
   results to the mapping operation.
7. Accept a candidate only when `feasible` is true. The adapter makes a hard
   constraint feasible only when it is satisfied and its validation state is
   `qualified`, `validated`, `reference_validated`, `verification_only`, or
   `cad_drc`; callers may impose a stricter policy. Any unknown, unsupported,
   missing, failed, approximate, experimental, unvalidated, or contradictory
   hard constraint fails closed.
8. When one scalar lower-is-better search score is required, give every
   objective a positive `normalization_si`. The adapter divides each SI value
   (or target/constraint deviation) by its own declared scale, applies its
   weight, and sums the dimensionless terms. It emits `objective_score` only
   when every objective has both a usable result and a normalization; otherwise
   `objective_score_state` explains that the score is unavailable. This avoids
   silently adding quantities such as ohms, seconds, watts, kelvins, and BER.

Useful router metrics include clearance, trace width, via count, route length,
differential-pair skew, impedance, loss, current density, and thermal margin.
Useful placer metrics include courtyard/keepout clearance, side and orientation
rules, component height, connection length, temperature, airflow obstruction,
mechanical clearance, and electromagnetic coupling. Metric IDs are stable
identifiers; numerical values are SI-valued and dimensional rather than
unit-bearing strings.

## Bounds and trust boundary

The adapter rejects unknown fields, absolute or traversing artifact paths,
invalid digests, non-finite numbers, duplicate IDs, contradictory bounds,
unbound native requirements, and resource-limit violations. Current hard limits
include 1,024 requirements, 64 physics evaluations, 4,096 scoped or changed
entity IDs, a 1 GiB candidate artifact, and a 64 MiB physics-model artifact.

The adapter validates references and correlations; the trusted launcher must
still verify artifact bytes against their declared digests before execution.
No shell text or executable path is accepted through this contract.

## Readiness

Ready in the source tree now:

- strict schema and typed semantic validation for router, placer, and joint
  candidate evaluation;
- canonical serialization and deterministic job derivation;
- immutable candidate/model correlation and resource bounds;
- SI-dimensional hard constraints and soft constraints, plus explicitly
  normalized weighted objective scoring;
- native-result plus external DRC/custom-result mapping with fail-closed
  feasibility;
- Python API and JSON-line worker methods, covered by focused tests.
- source-runnable fixed process preparation/scoring for autorouter,
  autoplacer, and joint consumers.

Not ready yet:

- a router, placer, candidate mutation engine, CAD DRC engine, or automatic
  DesignIR-to-physics-model compiler;
- incremental solver-state reuse based only on `changed_entity_ids`;
- qualified PCB thermal, SI, EMI, CFD, mechanics, or coupled multiphysics
  scoring in the private SPIKES runtime;
- production packaging of this newly added source interface. Existing portable
  artifacts remain unchanged until the package is rebuilt and requalified.

Consequently, custom tools can immediately integrate and test their orchestration,
constraint handling, deterministic correlation, CAD/custom scoring, and native
job generation. Physics-backed route/place optimization remains
`integration_pending` until the required model translators and qualified solver
backends are available.
