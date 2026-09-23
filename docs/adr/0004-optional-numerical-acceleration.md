# ADR 0004: Optional Numerical Acceleration

- Status: Accepted
- Date: 2026-08-09

## Context

Large connected copper meshes make graph assembly and sparse factorization
expensive, but SPIKE must remain usable offline on machines without specialist
numerical runtimes. Acceleration must not fork the physical model, hide a
different approximation, or make result reproducibility depend on an
undocumented local package.

The workload has two distinct boundaries: construction of sparse matrix
triplets and solution of the reduced sparse linear system. Treating them as one
backend would obscure which implementation executed and would incorrectly imply
that a JIT assembly tool is also a matrix solver.

## Decision

Provide an optional, versioned acceleration layer in
`python/spike_core/acceleration.py` with deterministic baseline implementations:

- NumPy is the required graph-Laplacian assembly backend.
- Numba is an optional JIT backend for the same assembly kernel only.
- SciPy SuperLU is the required sparse direct solver, with tested real and
  complex-system paths.
- PETSc with MUMPS is an optional sparse direct backend, packaged and supported
  Linux-first.

`AnalysisSpec.options.assembly_backend` selects `auto`, `numpy`, or `numba`.
`AnalysisSpec.options.sparse_backend` selects `auto`, `scipy-superlu`, or
`petsc-mumps`. Automatic selection uses explicit workload thresholds and only
selects an optional backend after runtime discovery. Environment variables may
change known backend IDs and thresholds, but may not provide executable shell
commands.

Numba accelerates assembly kernels. It does not accelerate geometry import,
meshing, sparse factorization, result generation, or dense PEEC matrices.
PETSc/MUMPS replaces only the reduced sparse solve. The current adapter uses
`PETSc.COMM_SELF`; its published capabilities are limited to that
single-process path and the scalar type provided by the local PETSc build.
Distributed MPI and out-of-core orchestration are not part of this decision.

The SuperLU regression suite exercises real systems and preservation of complex
solutions, including a complex matrix with a real right-hand side. Test
documentation describes covered behavior rather than a brittle exact count.

An automatic optional-backend initialization failure may use the deterministic
baseline and must record the fallback. An explicitly requested unavailable
backend fails. Requested backend, selected backend, selection reason, fallback,
matrix dimensions, residuals, and timings are stored in result provenance.
Acceleration never changes model-status or validity labels.

Optional runtimes are discovered from the configured worker environment. SPIKE
never downloads or installs them implicitly. Signed runtime bundles and
administrator allowlists remain production-packaging work rather than a
current developer-runtime trust claim.

## Consequences

- The baseline solver remains functional without Numba, PETSc, or MUMPS.
- Backend policy and actual execution are inspectable in UI, reports, and saved
  results.
- Numerical equivalence can be tested independently from performance.
- Numba's first use can incur JIT compilation latency.
- PETSc/MUMPS packaging is operationally complex and remains Linux-first.
- A compatible complex PETSc build is required for complex systems.
- The current implementation does not solve motherboard-scale dense PEEC
  extraction; that requires a separate scalable-matrix design.
- Real optional-runtime qualification, memory limits, and platform benchmarks
  remain release gates.

## Rejected alternatives

- Make Numba or PETSc mandatory: breaks lightweight/offline installations and
  complicates cross-platform packaging.
- Hide backend choice: prevents reproducibility and makes fallback failures hard
  to diagnose.
- Treat Numba as a complete solver accelerator: misrepresents its implemented
  assembly-only scope.
- Treat PETSc availability as proof of MUMPS readiness: PETSc may be built
  without MUMPS or without required scalar support.
- Promote accelerated output to a higher validity class: execution speed is not
  validation evidence.
- Add GPU or distributed execution before stable CPU baselines: increases
  deployment and numerical risk without addressing current correctness gates.
