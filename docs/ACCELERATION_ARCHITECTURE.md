# Numerical Acceleration Architecture

## Purpose

SPIKE uses optional numerical backends to reduce execution time without
changing the requested physical model, geometry, mesh, units, limits, or result
validity. Acceleration is an execution policy, not a solver capability and not
an accuracy upgrade. A result remains `validated`, `approximate`,
`unsupported`, or `failed` according to the solver and validation evidence that
produced it.

The implemented acceleration boundary is
`python/spike_core/acceleration.py`. The current production consumer is the
hybrid copper-geometry DC solver in
`python/spike_core/hybrid_dc_solver.py`.

## Current execution path

```text
DesignIR + AnalysisSpec
  -> hybrid mesh construction
  -> active branch graph
  -> graph-Laplacian triplet assembly
       -> NumPy, always available
       -> NumPy multicore chunks for large graphs
       -> Numba, optional assembly-kernel acceleration
  -> SciPy CSR matrix
  -> reduced sparse linear system
       -> SciPy SuperLU, default baseline
       -> PETSc/MUMPS, optional sparse direct backend
       -> CuPy/CUDA, optional FP64 sparse QR with residual validation
  -> residual checks, fields, probes, analytics, and AnalysisResult
  -> acceleration metadata in summary and provenance
```

These numerical backends do not accelerate hybrid mesh construction, zone
discretization, geometry parsing, result visualization, report generation, or
the dense partial-inductance matrices used by PEEC. In particular, installing
Numba or PETSc/MUMPS does not remove the PEEC branch-count limits.

## Backend catalog

The worker exposes `list_accelerators` and includes the same catalog under the
`capabilities` response. The contract is
`spike/acceleration-catalog/v1`.

| Backend | Kind | Required | Current role |
|---|---|---|---|
| `numpy` | Assembly | Yes | Vectorized graph-Laplacian triplet assembly |
| `numpy-threaded` | Assembly | Yes | Disjoint NumPy chunks using the CPU thread budget |
| `numba` | Assembly | No | JIT compilation of the same triplet assembly kernel |
| `scipy-superlu` | Sparse direct solve | Yes | Tested baseline real/complex sparse LU solve |
| `petsc-mumps` | Sparse direct solve | No | PETSc AIJ plus MUMPS LU through `COMM_SELF` only |
| `cupy-cuda` | Sparse direct solve | No | NVIDIA CUDA sparse QR, double precision, validated against the original CPU system |

Catalog discovery imports `petsc4py` to verify MUMPS readiness and, when locally
installed, CuPy to check CUDA device availability. It never downloads a runtime.

The same catalog is available from the headless interface with
`spike accelerators`. Catalog capabilities describe only the execution surface
implemented by SPIKE. In particular, the PETSc/MUMPS entry is limited to the
single-process `COMM_SELF` adapter and its available real or complex scalar
type; it does not advertise distributed MPI or out-of-core operation.

## Assembly policy

The solver reads `AnalysisSpec.options.assembly_backend` with these values:

- `auto`: use multicore NumPy at `SPIKE_PARALLEL_MIN_BRANCHES` (default 500,000)
  when the CPU budget exceeds one; otherwise use Numba when available and at or
  above `SPIKE_NUMBA_MIN_BRANCHES`, then NumPy.
- `numpy`: always use the deterministic NumPy implementation.
- `numpy-threaded`: fill disjoint triplet ranges concurrently, with at least
  65,536 branches per allocated worker. No parallel floating-point reduction.
- `numba`: require Numba; fail explicitly if it is unavailable or cannot
  initialize.

The default automatic threshold is 50,000 branches and can be changed with
`SPIKE_NUMBA_MIN_BRANCHES`. Numba accelerates only the approved assembly kernel
that emits four sparse triplets per resistive branch. It does not solve the
matrix, mesh geometry, add physics, infer material data, or improve numerical
accuracy. `@njit(cache=True)` permits a persistent local JIT cache where the
runtime allows it, so the first invocation can still include compilation cost.

When `auto` selects Numba and JIT initialization raises an import, operating
system, or runtime error, assembly falls back to NumPy and records the fallback.
An explicitly requested `numba` backend never falls back silently.

## Sparse-solver policy

The solver reads `AnalysisSpec.options.sparse_backend` with these values:

- `auto`: select available CUDA at `SPIKE_GPU_MIN_UNKNOWNS` (default 100,000),
  unless `SPIKE_GPU_COMPUTE=off`; then select compatible PETSc/MUMPS at
  `SPIKE_MUMPS_MIN_UNKNOWNS`, otherwise SuperLU.
- `scipy-superlu`: require the baseline SciPy sparse LU path.
- `petsc-mumps`: require a compatible `petsc4py` installation whose PETSc build
  reports the MUMPS package.
- `cupy-cuda`: require local CuPy and NVIDIA CUDA. Explicit GPU selection takes
  precedence over the automatic GPU opt-out and reports failures to the caller.

CUDA execution preserves float64/complex128 precision, checks 32-bit CSR index
limits, performs a free-device-memory admission estimate, and validates the
componentwise backward residual against the original CPU matrix at 1e-9. It
releases its private allocation pool after each operation. Automatic GPU
allocation, runtime, or validation failures fall back to SuperLU with a recorded
reason; explicit CUDA requests fail. Factorization fill-in can exceed admission
estimates, so the estimate is not a capacity guarantee. A CUDA residual check
does not promote the underlying physics model's validity.
The adapter uses [CuPy's sparse solve API](https://docs.cupy.dev/en/stable/reference/generated/cupyx.scipy.sparse.linalg.spsolve.html).

`SPIKE_SPARSE_BACKEND` and `SPIKE_ASSEMBLY_BACKEND` supply defaults when the
analysis requests `auto`; an explicit analysis backend takes precedence. CPU
allocation, telemetry semantics and measured performance are documented in
[Resource monitoring and compute allocation](RESOURCE_MONITOR_AND_ACCELERATION.md).

The default automatic threshold is 100,000 unknowns and can be changed with
`SPIKE_MUMPS_MIN_UNKNOWNS`. The PETSc adapter converts the SciPy matrix to AIJ,
uses `KSPPREONLY` with LU and MUMPS, and checks the PETSc converged reason.
Complex systems additionally require a PETSc build with complex scalar support.

The required SuperLU baseline supports both real and complex sparse systems.
Regression coverage includes a complex matrix with a real right-hand side so a
future refactor cannot silently discard the complex solution dtype.

PETSc/MUMPS is optional and Linux-first for packaging and support. Windows and
macOS discovery is permitted for administrator-provided compatible builds, but
SPIKE does not currently publish or qualify equivalent accelerator bundles on
those platforms. The current implementation uses `PETSc.COMM_SELF`; it is a
single-process direct solve and does not yet orchestrate distributed MPI jobs.
MUMPS capabilities such as MPI or out-of-core operation must therefore not be
claimed as active SPIKE execution modes without additional implementation and
validation.

In `auto` mode, import or operating-system initialization failures fall back to
SuperLU and are recorded. An explicit `petsc-mumps` request fails if the backend
is unavailable. Numerical MUMPS failures are returned as solver failures rather
than being silently re-solved and promoted.

## Result provenance

Every hybrid DC result records:

- requested and selected assembly backend;
- requested and selected sparse backend;
- selection reason and configured workload size;
- whether a fallback occurred and its diagnostic;
- node count, edge count, matrix nonzero count, and scaled residual;
- mesh, assembly, linear-solve, and total execution times.

The summary exposes the selected backend names for immediate diagnostics. The
full records are stored under `provenance.acceleration`. This metadata is part
of reproducibility evidence and must be retained in project results and reports.

## Offline packaging and security

Numba, PETSc/MUMPS and CuPy/CUDA are optional entries in `dependencies.lock.json`.
CUDA has no bundled or release-qualified artifact in the manifest.
Discovery never installs Python packages, invokes a package manager, or
downloads an accelerator. Approved releases may offer signed offline bundles;
administrators may also provide a compatible local runtime. Missing optional
backends leave NumPy and SuperLU operational.

Environment variables select only known backend IDs and thresholds. They do not
accept executable paths or shell commands. Backend availability and versions
are visible in the desktop External Engines/Acceleration center. That center is
currently status-only; backend selection is supplied through `AnalysisSpec`
options or the documented worker environment policy.

## Tests and validation limits

`tests/python/test_acceleration.py` covers catalog classification, NumPy
Laplacian assembly, real and complex SuperLU agreement with dense references,
mixed matrix/right-hand-side dtype promotion, automatic MUMPS selection policy,
and explicit-unavailable Numba behavior.
Hybrid DC fixtures exercise the same solver path used by the application. This
description is intentionally capability-based rather than tied to a test count.

Before an optional backend is release-qualified, add platform-specific tests
that compare its matrix and solution against the baseline within declared
tolerances, exercise fallback and out-of-memory behavior, and record peak memory
and timing on representative large boards. Current tests do not validate a real
PETSc/MUMPS installation, distributed MPI execution, or Numba speedup on release
hardware. The CUDA hardware test is skipped when the worker lacks CuPy/CUDA;
CPU-side validation and fallback coverage do not substitute for device tests.

## Known constraints

- This backend catalog is wired into hybrid DC graph assembly and sparse
  solving. The host CPU allocation also reaches supported native circuit kernels.
- Numba accelerates assembly kernels, not meshing or the numerical solve.
- PETSc/MUMPS is optional, Linux-first, and currently single-process through
  `COMM_SELF`.
- Dense PEEC R/L extraction and transient dense factorizations are unchanged.
- Automatic thresholds are policy defaults, not benchmark-derived guarantees
  for every machine.
- Backend changes require numerical-equivalence evidence before release.
