# Independent PCB preparation index review — 2026-10-23

## Scope and result

This bounded independent review found no actionable defects in the exact
selection optimization described in
`PCB_PREPARATION_OPTIMIZATION_20261023.md`. The reviewed changes select physical
edges for `FilledCopperDomain.cell_fragments()` through the existing boundary
index and maintain slab crossings through sorted endpoint events.

The review covered `boundary_spatial_index.py`, its
`source_filled_boundary.py` forwarder, and the relevant-edge and active-slab
selection in `filled_copper_path.py`. It did not repeat the earlier general
mesher audit or qualify solver physics.

## Preservation argument

1. The index's conservative edge boxes include both original endpoints. Any
   nonvertical edge satisfying the former strict cell-x overlap test therefore
   intersects the closed query `(x0, -inf, x1, inf)`. Applying the unchanged
   strict overlap test to these candidates removes extras and preserves the
   original relevant-edge set.
2. `query_indexed_edges()` returns original directed edges with their original
   integer indices in ascending index order. Thus source direction, event
   construction, clip-event keys, and tie-breaking retain their former inputs.
3. Slab endpoints are sorted. A slab without a strictly interior representable
   midpoint still fails before crossing evaluation. For the remaining slabs,
   midpoints strictly increase. Adding edges with `low_x < middle_x` and
   removing edges with `high_x <= middle_x` maintains exactly the former
   predicate `low_x < middle_x < high_x`.
4. Active edges are evaluated in ascending original-index order. `_edge_y`
   arithmetic and the crossing sort key `(y, original_index)` remain unchanged.
5. Each slab charges `len(relevant)` work units. This reaches the same declared
   fragment-work threshold as the former per-relevant-edge loop. The small
   differential checks below also compare exception types and messages.

The sweep uses storage proportional to the relevant-edge count. This argument
does not establish latency or whole-process peak-memory limits.

## Executed checks

Two independently authored scripts were executed through project
`.venv/Scripts/python.exe` during this review. Their exact source was retained
afterward, without rerunning, at:

- `output/performance-20261023/pcb-preparation-review/compare_full_scan.py`
- `output/performance-20261023/pcb-preparation-review/check_candidate_sets.py`

The first script reconstructs the former full-scan selection and per-slab
crossing loop **in memory from the current method**. It replaces the indexed
candidate query with `enumerate(self.edges)`, removes the endpoint sweep, and
restores the per-edge work charge and strict midpoint predicate. It does not
load a historical source snapshot and is not an independent triangulation
oracle. Fragment construction and all other predicates are shared deliberately
to isolate this optimization.

With seed `231091`, it checked 32 rotated annuli, alternating source traversal
direction, scales from `1e-6` through `1e6`, and offsets of zero or magnitude
`1e8`. For each domain it checked seven random rectangles at work budgets
`0`, `1`, `7`, `50`, and `2000000`, plus one cell whose x bounds are adjacent
representable floats. All **1,152 comparisons matched**. Successful results
were compared using their complete `repr`; failures were compared by exception
type and message. **643 comparisons were matching rejections**.

The second script used seed `231092`, 128 synthetic sets of 16 directed edges,
and eight x-interval queries per set. Coordinate exponents included `-1074`,
`-1070`, `-1022`, `-500`, `0`, `53`, `500`, and `1023`. After the unchanged
strict overlap filter, all **1,024 comparisons** preserved the exact relevant
edge set, original indices, direction, and order. These synthetic edge sets
need not be valid copper domains; this check isolates index selection.

Observed script output:

```text
old_fullscan_vs_indexed_sweep 1152 matching_rejections 643
extreme_relevant_edge_sets_and_order 1024
```

## Reviewed source identity

SHA-256 values read from the working files after the checks matched the
optimization evidence document:

| File under `python/spike_core/` | SHA-256 |
| --- | --- |
| `boundary_spatial_index.py` | `48690a6247e37078b08f196d612c8ae55538267d30961862e23c67d1560d0317` |
| `source_filled_boundary.py` | `9ce5628f8c882a0f014255aa6fdb113ef665c3d26e607371cf9e524dba9a653e` |
| `filled_copper_path.py` | `0642ec4926091f6875be8a74cd513ebe265ba46d17973a7a040981ef85385212` |

## Limits

No production files were edited by this review. No large-board, stress,
benchmark, native-UI, or solver run was performed. The review honored the
parent task's below-6-GiB available-memory restriction by using small synthetic
inputs. It does not independently verify the reported timing improvement,
large-board capacity, or broader integration-test counts.

The retained scripts depend on current internal method text and project test
helpers; later source changes may require deliberate review before reuse.
They preserve the actual checks performed, not a permanent public test API.
No external mesher implementation, comments, examples, or test data were read
or adapted. Required knowledgeable human review before numerical release
remains applicable.
