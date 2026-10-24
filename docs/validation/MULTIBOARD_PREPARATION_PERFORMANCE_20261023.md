# Multi-board preparation performance evidence (2026-10-23)

## Scope

This evidence covers repeated retained-design preparation for bounded multi-board analysis. It does not change a solver, numerical method, coupling model, execution gate, or capability claim.

`plan_multiboard_analysis` previously rescanned the same retained design geometry for every physical occurrence. `run_independent_si_batch` also reconstructed an identical `SpiDeRV2` for every occurrence using that design. Both operations are now cached by the explicit retained `design_id` for the lifetime of one request. Parsed-design reuse is admitted only for callback-free plain-JSON trees, checked once per retained design with bounded depth and node counts. A supplied cancellation callback or Python-only container retains per-occurrence parsing and validation. Board occurrence IDs, namespaces, placements, selected-board coverage, explicit harness/connector links, and result rows remain occurrence-specific.

## Fixture and method

The bounded synthetic fixture has 30 occurrences of one retained design with 4,000 tracks. The benchmark measures geometry summary plus `SpiDeRV2` construction only; no solve, native UI, large-board load, CFD run, or responsiveness stress was performed. Seven warmed repetitions were recorded using:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_multiboard_preparation.py --output output\performance-20261023\multiboard-round2
```

The benchmark independently compares every prepared summary and serialized parsed design against the uncached reference. It also verifies 30 unique occurrence IDs and 30 unique assembly namespaces bound to the unchanged `shared-layout` source identity.

## Result

| Measurement | Before | After |
| --- | ---: | ---: |
| Median preparation time | 340.986 ms | 24.654 ms |
| Retained geometry scans | 30 | 1 |
| `SpiDeRV2` parses | 30 | 1 |
| Bounded plain-JSON admission walks | 0 | 1 |
| Median speedup | 1.00x | 13.83x |

Raw samples and fixture metadata are retained in `output/performance-20261023/multiboard-round2/report.json`.

Final integration also restores independent bounds/dimension lists for every
returned occurrence by copying the small cached summary. The scan remains once
per retained design. The reported component benchmark excludes this small
per-occurrence copy; it does not time the complete planning/dispatch workflow.

## Correctness checks

- `test_repeated_design_summary_is_computed_once_without_merging_board_identity` verifies one source scan while retaining every board ID and namespace.
- `test_independent_si_batch_parses_each_retained_design_once_without_merging_occurrences` verifies one parse while retaining six independently identified result rows.
- `test_independent_si_batch_revalidates_shared_source_mutated_between_jobs` mutates the retained source through the cancellation callback after the first occurrence and verifies the next occurrence rejects the now-invalid payload instead of using stale parsed data.
- `test_independent_si_batch_binding_distinguishes_parser_significant_container_types` changes a valid custom polygon from a list to an invalid tuple inside a callback and verifies the second occurrence reparses and rejects it.
- `test_independent_si_batch_preserves_accepted_python_container_payloads` verifies a valid hydrated tuple remains accepted and is reparsed for each occurrence.
- A workspace-local temporary directory was supplied for sandbox compatibility; 61 tests across `test_multiboard_analysis`, `test_multiboard_circuit`, `test_assembly_linked_nets`, and `test_assembly_analysis_scope` passed. This includes all five new cache checks, the real two-board SI batch, explicit-link identity checks, numerical circuit oracles, and fail-closed scope gates.

## Limits

The cache is request-local and keyed by canonical retained `design_id`. Different design identities are never coalesced, even if their payloads happen to be equal. Callback-bearing execution disables parsed-design reuse because callbacks are caller code that can mutate the raw request between occurrences. Payloads containing tuples, custom mappings, cycles, excessive depth, or excessive node counts also bypass reuse without being normalized or rejected by the cache policy; the original parser decides their validity on every occurrence. The runner still executes one job per board occurrence sequentially and preserves existing aggregate resource admission and cancellation checks. This measurement isolates preparation overhead and does not predict solver runtime.
