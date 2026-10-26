# PCB preparation edge-scan optimization (2026-10-23)

## Scope

This pass profiles and optimizes the strict source-filled copper cell-fragment
preparation path. It changes data selection only. Polygon admission, source
coordinates, physical edges, crossing arithmetic, fragment construction,
ownership, topology, material data, solver gates, and resource limits are
unchanged.

The retained input was
`output/arduino-em-20261011/prepared-final/shield/shield-source.kicad_pcb`
(SHA-256
`a2411733cfd4bcf91f7e7504610c662d330b6cffcb075229ab6e1b68e3fd9048`).
The run used project CPython 3.12.9 and the following DC mesh configuration:

- net: `GND`
- target size: 1.0 mm
- zone cell: 0.5 mm
- maximum zone cells: 3,000
- maximum conductors: 100,000
- memory budget: 2,048 MiB

Import occurred once before each three-sample timing series and was outside the
timed region. Each sample built a fresh mesh from the retained imported design.
No large-board, stress, native-UI, or solver-capacity inference was attempted;
available host memory was below the task's 6 GB (6,000,000,000-byte) gate.

## Profile and change

The current-source baseline cProfile run took 10.963 seconds. `zones()` took
9.240 seconds, and 666 `FilledCopperDomain.cell_fragments()` calls took 7.653
seconds. The method repeatedly scanned every physical edge first for every
cell, then again for every vertical slab within that cell.

The optimized path asks the existing conservative boundary BVH for cell-x
candidates and applies the original strict x-overlap predicates to that
superset. The index returns each original directed physical edge with its
original integer index, in original-index order. A monotonic endpoint sweep
then maintains the edges satisfying the unchanged slab predicate
`low_x < middle_x < high_x`; crossings are still evaluated in original-index
order with the same `_edge_y` operation and sort key. The resource work counter
still advances by `len(relevant)` for every slab, so the same input crosses the
same fragment-work threshold.

After the change, the corresponding cProfile run took 4.583 seconds;
`zones()` took 3.341 seconds and `cell_fragments()` took 2.626 seconds. Profile
time includes instrumentation overhead and is reported separately from the
wall-clock series.

## Wall time and exact output

| Current-source state | Three mesh times (s) | Median (s) |
| --- | --- | ---: |
| Before this pass | 4.867400, 4.095480, 4.093750 | 4.095480 |
| After this pass | 2.013914, 1.408197, 1.346702 | 1.408197 |

The measured median improvement is 2.91x (65.6% less timed wall time) on this
small retained fixture. Timing is host- and workload-specific and is not a
millisecond latency or large-board capacity claim.

Every before/after sample produced the same canonical compact-JSON SHA-256 over
the complete mesh dataclass:
`0fbfb8652b8368d9b8fa2259861c5f2c5e1cf36a71ed37f9c7cfe6046c5538d6`.
Every sample also produced 3,185 nodes, 0 branches, 3,411 cells, geometry counts
`track=2, zone=1, via=16, pad=0`, and `truncated=false`.

## Verification

The focused boundary, strict filled-path, source-boundary, and hybrid filled
path run passed 29 tests. The broader affected hybrid/geometry run executed 91
tests: 90 passed in the combined run, while the KiCad filled-plane test could
not create its sandbox-managed temporary file. Re-running that unchanged test
with `tempfile.tempdir` set to a repository-owned temporary directory passed.
The temporary directory was empty after the test and was removed.

New regression coverage verifies that indexed candidates preserve original
edge indices and order and that the complete hole-aware mesh matches a build
whose candidate query returns the former full physical-edge sequence. Existing
tests cover cutout area, containment, topology connectivity, narrow holes,
fragment budgets, extreme coordinates, DC conservation, and imported filled
copper.

Final source hashes at `2026-10-23T13:29:13.133Z`:

- `boundary_spatial_index.py`:
  `48690a6247e37078b08f196d612c8ae55538267d30961862e23c67d1560d0317`
- `source_filled_boundary.py`:
  `9ce5628f8c882a0f014255aa6fdb113ef665c3d26e607371cf9e524dba9a653e`
- `filled_copper_path.py`:
  `0642ec4926091f6875be8a74cd513ebe265ba46d17973a7a040981ef85385212`

The optimization adds no dependency and changes no public solver or file
schema.
