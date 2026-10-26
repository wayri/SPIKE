<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solver execution, co-simulation, and acceleration

This page maps the execution mechanisms that exist in the source tree. It does
not add numerical validation or imply that every solver can use every mechanism.
Keep these categories separate when reporting performance:

| Category | Current state | Meaning | Completion state |
| --- | --- | --- | --- |
| Independent jobs | Implemented locally and on enrolled LAN nodes | Separate solver requests run in separate worker processes. | Implemented within stated scope |
| Shared-memory work | Implemented for selected kernels/backends | One process may use bounded BLAS/OpenMP, Numba, or explicitly threaded assembly. | Implemented within stated scope |
| GPU sparse solve | Optional NVIDIA CUDA path | Selected sparse systems may use CuPy, subject to runtime and residual checks. | Optional implementation; runtime-dependent |
| Distributed single solve | Planned | MPI domain decomposition, halo exchange, distributed operators, and coupled rank groups are not implemented. | Planned / unavailable |


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| Partitioned multiphysics / electrothermal coupling | Partial / bounded implemented workflows; case convergence required |
| Local and LAN independent-job pool | Implemented scheduling; no distributed single-system solve |
| Checkpoint / continuation and runtime admission | Implemented bounded execution support; solver-specific contracts apply |

## Local worker pool

[`parallel_pool.py`](../../../python/spike_core/solvers/execution/resources/parallel_pool.py) admits a
versioned batch and supervises one fresh child process per job through
[`parallel_child.py`](../../../python/spike_core/parallel_child.py). A thread
pool supervises child processes; it is not the numerical solver itself.
Completed results retain request and response digests and are returned in input
order.

The fixed child allowlist currently covers harness PI, SI and MTL; round-wire
RLGC extraction; AC power integrity; capacitor placement; compact thermal;
bounded internal airflow; and SMPS conversion analysis. Batch JSON cannot
select scripts, shells, extensions, arbitrary executable paths, or file imports.
Other SPIKE solvers are not automatically pool-capable.

Important bounds are 64 jobs per batch, eight concurrent jobs, 32 requested
threads per job, 180 seconds per job, and 900 seconds per batch. Admission also
requires `concurrency * threads_per_job` not to exceed the detected CPU budget.
Input, output, and retained-result byte and structure limits apply. Cancellation,
timeout, or output overflow terminates the owned child. CPU limits are
cooperative; the portable pool has no hard memory or hostile multi-tenant
containment.

Run the catalog or a reviewed batch from the repository root:

```powershell
python -m python.spike_core.cluster_cli parallel-pool
python -m python.spike_core.cluster_cli parallel-run examples/parallel/harness-batch.json
```

The desktop worker boundary is
[`service_parallel_pool.py`](../../../python/spike_core/service_parallel_pool.py).
The Solver manager worker-pool panel can retain drafts and bounded result
history in a `.spike` project, but opening a project never executes, resumes, or
retries work. Existing 0.3.9 installers predate this source implementation.
See the complete setup and project-state rules in
[`PARALLEL_WORKER_MANAGER.md`](../../PARALLEL_WORKER_MANAGER.md).

## Trusted LAN pool

[`cluster_manager.py`](../../../python/spike_core/cluster_manager.py) distributes
independent jobs across explicitly enrolled nodes after every node passes
version, method, and resource preflight. Jobs are partitioned in input order;
node partitions execute concurrently. The coordinator verifies node identity,
certificate pinning, and request/result provenance.

Enrollment uses administrator-provisioned mutual TLS certificates, hostname and
chain verification, exact server pins, and client fingerprint allowlists.
Discovery emits inert address hints and cannot enroll a node or run work. A
delivery or verification failure is `unknown` and is never retried
automatically because the job may already have executed.

This control plane does not provide durable queues, resumable transfers,
automatic certificate pairing, cross-node GPU allocation, or distributed PDE
execution. Setup examples, limits, diagnostics, and security boundaries are in
[`PARALLEL_WORKER_MANAGER.md`](../../PARALLEL_WORKER_MANAGER.md).

## CPU and memory policy

[`numerical_runtime.py`](../../../python/spike_core/numerical_runtime.py) applies
thread budgets before NumPy or SciPy import in owned workers:

- `SPIKE_CPU_THREADS` is the outer scheduled-job and assembly budget.
- `SPIKE_BLAS_THREADS` is the inner BLAS/OpenMP budget and defaults to one.
- The inner budget must be a canonical integer from 1 through 256 and cannot
  exceed the outer budget.

The launcher coherently sets common BLAS, OpenMP, NumExpr, and Numba variables
and removes inherited MKL domain overrides. These settings do not enforce OS
affinity, CPU isolation, or a memory limit. Pool jobs deliberately apply their
explicit per-job allocation to both outer and inner budgets.

The source-runtime measurement in
[`SOLVER_RUNTIME_MEMORY_20261024.md`](../../validation/SOLVER_RUNTIME_MEMORY_20261024.md)
observed about 89% lower Windows private commit for one-thread workers while
preserving the selected AC and CHT checks. It did not establish a general
speedup, resident-memory reduction, large-model qualification, or packaged
runtime result. Policy and setup details are in
[`WORKER_NUMERICAL_RUNTIME.md`](../../WORKER_NUMERICAL_RUNTIME.md).

## Offline co-simulation and recorded twins

[`cosimulation.py`](../../../python/spike_core/solvers/execution/coupling/cosimulation.py) implements an
experimental fixed-grid scalar communication master. Its built-in adapters are
synthetic replay and dimensionless gain. At every tick, all participants read
the preceding accepted output snapshot; outputs and JSON state are staged and
accepted together. Exact unit labels and one driver per scalar input are
required.

This is explicit one-step-lag orchestration. It has no same-tick feedthrough,
algebraic-loop solve, interpolation, unit conversion, adaptive communication
step, rollback, checkpoint/restart, or continuous-coupling accuracy claim.
Cancellation and timeout are cooperative between adapter calls; the worker host
provides hard process termination. JSON requests cannot load adapter code or
solver executables.

The service also provides exact-timestamp comparison of supplied prediction and
telemetry series. Agreement does not promote the supplied model status. Session
adapters for SPIKES transient/thermal stepping, FMI, project twin editing,
sensor ingestion, calibration, live acquisition, and HIL are not implemented.
Run examples and review limits in
[`COSIMULATION_DIGITAL_TWIN.md`](../../COSIMULATION_DIGITAL_TWIN.md) and its
[`implementation evidence`](../../validation/COSIMULATION_DIGITAL_TWIN_20261010.md).

## CPU and GPU acceleration

[`acceleration.py`](../../../python/spike_core/solvers/execution/resources/acceleration.py) currently offers
SciPy SuperLU, optional single-process PETSc/MUMPS, optional Numba assembly, and
multicore NumPy assembly. PETSc uses `COMM_SELF`; its presence is not MPI
distribution. Threaded graph assembly splits disjoint output slices and remains
a single-process shared-memory operation.

[`gpu_acceleration.py`](../../../python/spike_core/solvers/execution/resources/gpu_acceleration.py) provides
an optional NVIDIA CuPy/CUDA sparse solve. It preserves `float64` or
`complex128`, requires 32-bit-compatible CSR indexes, checks an estimated device
working set, copies the solution back, and validates a componentwise residual
against the original CPU matrix. Automatic CUDA failure falls back to SuperLU;
an explicit CUDA request fails visibly. AMD and Intel GPU execution and
pool-level GPU allocation are unsupported.

Backend selection thresholds, dependency state, fallback behavior, and executed
checks are recorded in
[`ACCELERATION_ARCHITECTURE.md`](../../ACCELERATION_ARCHITECTURE.md). GPU
availability does not mean a particular solver uses the GPU.

## Native and distributed roadmap

[`NATIVE_HPC_MIGRATION.md`](../../NATIVE_HPC_MIGRATION.md) targets C++20 hot
kernels and prepared operators, bounded workstation SIMD/OpenMP, then native MPI
ownership, halos, distributed operators, preconditioners, and conservative
coupled rank groups. The existing Python pool remains the control plane for
independent studies.

The recorded CFD profiling baseline prioritizes geometry admission work; it is
not a completed native port, C++ speedup, MPI build, or scaling result. Future
promotion requires serial parity, multicore measurements, 2/4-rank evidence,
four-node scaling, memory and communication records, and physics-specific
validation. WASM is only a possible bounded preview target and is not the HPC
engine.
