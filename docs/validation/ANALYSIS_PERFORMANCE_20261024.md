# Analysis preparation performance evidence — 2026-10-24

## Scope

This change reduces request-local CFD/CHT mesh snapshot and provenance overhead.
It does not change mesh admission, matrix assembly, solvers, tolerances, time
steps, cancellation, or published fields. The retained ticket remains private
to one synchronous composed solve.

The prior reviewed implementation walked the plain JSON tree to enforce type,
node, and depth limits, then consumed `JSONEncoder.iterencode` chunks to enforce
the 32 MiB serialized limit, calculate SHA-256, and reconstruct a private
snapshot. Profiling showed this Python iterator path repeated for initial and
retained mesh checks.

## Implementation and preserved gates

`python/spike_core/cfd_tetra_mesh.py` now calculates the exact compact,
`ensure_ascii=True` JSON byte length during the existing bounded plain-tree
walk. It rejects inputs over 32 MiB before allocating the complete encoding,
then uses the standard-library C JSON encoder once. SHA-256 still covers the
same insertion-order-sensitive JSON bytes, and retained snapshots still use
`json.loads` of those bytes.

The implementation preserves:

- exact 32 MiB serialized-byte, 500,000-node, and depth-32 gates;
- plain `dict`/`list` containers, string keys, finite numbers, and cycle rejection;
- mapping insertion order, including boundary-patch summation order;
- mutation and ABA-safe admission from the pre-callback private snapshot;
- cancellation checks and rejection of stale retained tickets.

The focused regression additionally compares DEL (`U+007F`), Unicode, astral
Unicode, finite float, boolean, null, and mapping-order digest/snapshot results
with the reviewed JSON representation.

## Measurement

Evidence: `output/performance-20261024/analysis/report.json`.

- Runtime: CPython 3.11.9, NumPy 2.4.6, SciPy 1.17.1, Windows.
- Fixed workload: refinement 2, 96 tetrahedra, request SHA-256
  `583df8b7cedc27bdd66826ee9088191b3b44419513b335c16ebbacc5d8a6094d`.
- Alternating order: 10 complete solves and 15 preparation batches per method;
  each preparation sample averages 20 calls alternating retained/non-retained.
- Stable fields and diagnostics fingerprint:
  `2dd13647448f4fc2577bbd4a5645dd399f3d8889c51fa9c72b35d42b34a57eec`.
- Preparation median: 2.178375 ms to 1.12684 ms, 1.93x faster (48.3% less).
- Complete CHT medians were 287.5424 ms and 287.6331 ms in the final run;
  their broad 99.8--476.1 ms ranges do not establish an end-to-end change.

Complete-solve samples were affected by substantial concurrent-system noise;
the interleaved isolated preparation measurement establishes the optimized
operation's effect. This work does not claim an end-to-end gain or similar
gains for larger solver-dominated cases.

## Verification

Executed with `build/qualification-py311/Scripts/python.exe`:

- `python -m unittest tests.python.test_cfd_tetra_cht -v`
- `python scripts/benchmark_analysis_preparation.py --refinement 2 --repeats 10 --output output/performance-20261024/analysis`

The unit suite covers exact affine flow/coupled energy behavior, identity and
failure publication, one-admission composition, cancellation-time nested
mutation, admission ABA mutation, tuple/list distinction, mapping-order
mutation, mutation during flow, and JSON-byte compatibility.
