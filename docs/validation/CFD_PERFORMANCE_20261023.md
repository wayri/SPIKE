<!-- SPDX-License-Identifier: Apache-2.0 -->
# Composed tetrahedral CFD/CHT admission performance - 23 October 2026

Status: exact orchestration optimization for the existing experimental retained
tetrahedral CHT workflow. This change adds no equation, coefficient, boundary
condition, solver, tolerance, time-step change, capability, or qualification
claim.

The **final reviewed** 96-tetrahedron paired measurement is **106.840 ms →
62.241 ms median (1.72x)** with identical fields and stable diagnostics. It
includes private snapshot allocation, order/type-sensitive source binding and
all final reuse guards. Earlier measurements retained below are exploratory
history and do not qualify the final implementation by themselves.

## Profile finding and change

The retained CHT composition admits the complete solid/fluid mesh, derives and
admits its exact fluid submesh, solves Stokes on that submesh, maps accepted mass
flux, and solves energy on the complete mesh. Before this change the standalone
Stokes and energy entry points each repeated full topology, geometry,
conditioning and positive-volume-intersection admission, even though the
composition had just admitted the identical in-memory mesh objects. On the
96-tetrahedron reference case, four admissions occupied 292 ms of a 329 ms
instrumented run.

The mesh owner computes a bounded order-preserving JSON digest and private
snapshot before admission, performs full admission on that snapshot, verifies
the raw source is still identical, and only then issues
a private identity- and digest-bound reuse ticket. The composed owner retains
the full-mesh ticket before any flow callbacks and creates the fluid-submesh
ticket by the same sequence. A ticket is accepted only by the internal keyword
path and only for its exact source object. Reuse first performs the cancellation
callback, then recomputes the order-sensitive digest; nested mutation during admission or any
later stage is rejected before stale admitted arrays reach a child solver.
Standalone public calls pass no ticket and retain complete admission. The
composition still performs two necessary admissions: the retained mesh and the
distinct derived fluid submesh.

All numerical assembly, sparse factorization, condition estimation, residual,
mass/work/energy conservation, field-size and failure-publication gates execute
unchanged. No admitted array is modified by either downstream kernel.

## Benchmark

Command:

```
build/qualification-py311/Scripts/python.exe scripts/benchmark_cfd_cht_overhead.py --refinement 2 --repeats 7 --output output/performance-20261023/cfd-round2
```

Runtime: Python 3.11.9, NumPy 2.4.6, SciPy 1.17.1 on Windows. The workload is
the independently checked affine two-phase CHT fixture at refinement 2: 96
tetrahedra, request SHA-256
`583df8b7cedc27bdd66826ee9088191b3b44419513b335c16ebbacc5d8a6094d`.
The script warms both paths and alternates seven measurements. Its comparison
path restores the immediately preceding behavior by forcing Stokes and energy
to admit their mesh again. Every sample must complete and produce the same
fields-and-stable-diagnostics fingerprint
`2dd13647448f4fc2577bbd4a5645dd399f3d8889c51fa9c72b35d42b34a57eec`.
The volatile energy elapsed-time diagnostic is excluded from that fingerprint.

| path | median | range |
| --- | ---: | ---: |
| duplicate downstream admission | 117.884 ms | 114.023-124.924 ms |
| exact admitted-mesh reuse | 65.654 ms | 65.002-67.721 ms |

The observed median decreased 44.3% (1.80x). Raw samples, runtime identity,
source hashes, workload identity and result fingerprint are retained in
`output/performance-20261023/cfd-round2/report.json`.

An independent hardening review identified that object identity alone did not
prove nested values remained unchanged. After adding the canonical digest gate,
the same benchmark was repeated into
`output/performance-20261023/cfd-round2-hardened/report.json`, preserving the
original report. The hardened run measured 113.048 ms median with duplicate
admission and 71.144 ms with reuse, a 37.1% reduction (1.59x). All seven pairs
retained the same result fingerprint above. The wider 59.298-131.153 ms reuse
range and 108.292-264.636 ms comparison range reflect contemporaneous machine
load; the alternating paired workload and correctness fingerprint were unchanged.

A second independent review found that binding the retained ticket only after
the flow solve could bind a newly mutated raw mesh to the older admitted arrays.
The final implementation now captures and verifies both tickets immediately
around their original admissions. The reviewer independently reproduced a
mutation of full-mesh cell connectivity from inside the Stokes cancellation
callback: the composed solve blocked with no fields. After review clearance and
CPU coordination, the single final paired benchmark was retained in
`output/performance-20261023/cfd-round2-final/report.json`: duplicate admission
measured 119.862 ms median and final reuse measured 71.003 ms, a 40.8% reduction
(1.69x). Its seven pairs retain the same workload digest and result fingerprint.

Final review then exercised two less obvious identity failures. First, callbacks
could temporarily mutate and restore the raw mesh during admission (ABA), making
before/after digests equal while admitted arrays captured the transient values.
The owner now validates and serializes at most 32 MiB into a private plain-JSON,
order-preserving snapshot before callbacks and admits only that snapshot. The
source object must still match its order-sensitive digest after admission and at
reuse. The prewalker is bounded to 500,000 nodes and depth 32 before encoding,
so cycles cannot hang. It rejects tuples and other non-JSON containers instead
of normalizing them into contract-valid lists. Key sorting is deliberately off:
boundary patch insertion order controls exact floating-point reduction order.

The reviewer independently confirmed the ABA, tuple/list, cycle and flow-stage
reproducers, 30 exact hexadecimal temperature-lift cases, patch-reorder
rejection, and a paired complete fields/stable-diagnostics digest. After final
clearance, the one final timing run was retained in
`output/performance-20261023/cfd-round2-aba-final/report.json`. Duplicate
admission measured 106.840 ms median and snapshot-backed reuse measured 62.241
ms, a 41.7% reduction (1.72x). This final timing includes the bounded snapshot,
strict structural walk, source digests and exact-order preservation costs. All
seven pairs retained request SHA-256
`583df8b7cedc27bdd66826ee9088191b3b44419513b335c16ebbacc5d8a6094d`
and result fingerprint
`2dd13647448f4fc2577bbd4a5645dd399f3d8889c51fa9c72b35d42b34a57eec`.

## Verification and limits

Executed with the repository qualification Python 3.11 environment:

- `tests.python.test_cfd_tetra_cht` and `tests.python.test_service_cfd`: 11 tests passed.
- `tests.python.test_cfd_tetra_stokes` and `tests.python.test_cfd_tetra_energy`: 23 tests passed.
- The new regression proves the composition invokes admission exactly once for
  each distinct retained and fluid-submesh object.
- A cancellation callback that mutates a nested raw vertex is rejected as stale
  before reuse; ordinary standalone calls still execute complete admission.
- A callback invoked from inside Stokes that corrupts retained full-mesh cell
  connectivity returns false but still causes the composition to block before
  energy, with no fields published.
- Translate-and-restore ABA mutation cannot affect admitted coordinates because
  admission reads the pre-callback private snapshot.
- Tuple/list digest collisions are rejected before snapshot normalization, and
  admitted boundary-patch insertion order matches the source exactly.

The benchmark is deliberately small because available RAM was below the
project's 6 GB (6,000,000,000-byte) large-stress gate. It does not measure CAD/OCC import, SU2,
native cavity CFD, turbulent flow, large assemblies, process startup, JSON IPC,
or distributed execution. Mesh admission remains necessary once per distinct
mesh and can still dominate larger retained meshes. This evidence supports only
removal of duplicate in-process admission in this composed workflow.
