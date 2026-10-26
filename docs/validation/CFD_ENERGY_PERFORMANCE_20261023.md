<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tetrahedral energy assembly allocation performance - 23 October 2026

Status: narrow implementation-performance evidence for the existing experimental
RT0/P0 energy kernel. This work changes no equation, coefficient, tolerance,
boundary condition, solver gate, public contract, or capability claim.

## Change and equivalence boundary

Each tetrahedron contributes exactly 16 RT0 mixed-matrix COO entries and four
signed divergence entries. The former implementation accumulated those entries
with nested Python list appends. The revised implementation allocates the six
fixed-size numeric buffers once and fills the same cell-major, row-major entry
sequence. Sparse conversion, boundary processing, advection, scaling,
factorization, condition estimation, residual checks, and cell/global energy
checks are unchanged.

`tests/python/test_cfd_tetra_energy_performance.py` independently retains the
former scalar-loop assembly definition. On an existing authored layered-mesh
fixture it requires exact equality of CSR `indptr`, `indices`, and `data` for
both mixed and divergence matrices, plus exact equality of the conductive
right-hand side and cell load. The existing energy suite continues to check
manufactured solutions, scaled conditioning, mixed residual, cell/global energy
balance, rejection, cancellation, and resource limits.

## Alternating same-process A/B measurement

Runtime: CPython 3.12.9, NumPy 2.4.2, SciPy 1.17.0, Windows 11. BLAS thread
variables `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, and `MKL_NUM_THREADS` were
all set to 1. The existing `manufactured(6, layered=True)` fixture contains
3,888 tetrahedra. Mesh admission and input preparation ran once before timing.
Both implementations were warmed once and then measured in alternating original,
preallocated order for five samples in one process. Every measured result was
compared exactly against a fresh original-loop result.

| implementation | samples (s) | median (s) |
| --- | --- | ---: |
| original list append | 0.287610, 0.271305, 0.298265, 0.284712, 0.291719 | 0.287610 |
| preallocated arrays | 0.276789, 0.254711, 0.264753, 0.239901, 0.198318 | 0.254711 |

The observed assembly-stage median ratio is 1.129x (11.4% lower median time).
This is a small local allocation improvement, not a solver or end-to-end CFD
speedup claim. A separate earlier public-call sample had a 1.948 s baseline
median, while a later post-change sample under heavier machine load measured
3.136 s. Full calls are dominated by mesh admission and were not controlled
well enough to attribute that difference to this change. The local solved-field
SHA-256 remained
`febdf1ff776778388a1e250bc47d76c2c31ffe1c55bbc8f8a62949b038a39e88`, but it is
recorded only as local evidence; it is deliberately not a cross-platform test
oracle because sparse factorization details may vary across supported runtimes.

## Verification and limits

Executed with the repository `.venv` and single-thread BLAS settings:

- `python -m unittest tests.python.test_cfd_tetra_energy_performance tests.python.test_cfd_tetra_energy -v`: 10 tests passed.
- `python -m unittest tests.python.test_cfd_tetra_energy tests.python.test_cfd_tetra_energy_performance tests.python.test_cfd_tetra_cht tests.python.test_service_cfd -v`: 21 tests passed before the portable-oracle refinement.
- `python scripts/check_architecture.py`: passed.

The benchmark excludes admission, factorization, condition estimation, result
certification, serialization, IPC, CAD import, peak-memory measurement, and
large-mesh scaling. It does not establish production qualification, physical
accuracy, native acceleration, parallel scaling, or a general co-simulation
performance improvement.
