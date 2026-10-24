<!-- SPDX-License-Identifier: Apache-2.0 -->
# Numerical worker thread and memory policy

## What changed

Owned worker executables now default to **one inner BLAS/OpenMP thread**, while
retaining a separate outer CPU allocation for scheduled jobs and assembly.
This avoids initializing a large numerical-library thread/scratch pool merely
because the workstation has many logical CPUs. It is a resource policy, not a
new numerical method, physical capability or distributed solver.

`SPIKE_CPU_THREADS` remains the outer budget. `SPIKE_BLAS_THREADS` explicitly
selects the inner numerical budget, default 1. It must be a canonical integer
in 1..256 and no greater than the effective outer allocation. Worker bootstrap
respects CPU availability/affinity through the existing CPU policy and caps the
outer bootstrap allocation at 256. Invalid inner settings fail clearly rather
than silently oversubscribing. Native OpenMP shares the inner budget; opt in to
more threads for workloads that benefit, then benchmark that exact case.

Example, in a local PowerShell session:

```powershell
$env:SPIKE_CPU_THREADS = "8"
$env:SPIKE_BLAS_THREADS = "1"
.venv/Scripts/python.exe -m python.spike_core.service
```

For inner parallelism, choose an admitted value such as 2 or 4 within the
available outer budget. The SPIKE knob is authoritative at owned executable
entry: inherited backend-specific thread values are replaced coherently. Do
not expect a separate `OPENBLAS_NUM_THREADS=8` to override
`SPIKE_BLAS_THREADS=1`. No system/user environment settings are persisted.

## Implementation and boundaries

`python/spike_core/numerical_runtime.py` is standard-library-only.
`numerical_child_environment(cpu_threads=..., blas_threads=..., base=...)`
returns a copied environment without mutating its input or the calling process.
The launcher must pass it to a **fresh** child before numerical imports.
Inherited `MKL_DOMAIN_NUM_THREADS` is removed because domain settings can override
the global MKL thread budget. The parent application's original environment
remains unchanged.

`bootstrap_worker_numerics()` is called only at owned executable entry, before
NumPy/SciPy imports: source service, module CLI and frozen-worker entry source.
Ordinary library imports do not alter the importing application's environment.
Bootstrap rejects late calls; it cannot reclaim an already initialized backend.
The desktop Rust process launcher supplies the same inner setting before child
creation, covering frozen runtime hooks without moving solver logic into Rust.
The desktop launcher independently validates a canonical bounded override
against its CPU allocation **before** child creation; Python admission alone
would be too late to protect import-time allocations in frozen hooks.
The frozen executable/installer has not been rebuilt or qualified by this change.

The local parallel pool uses the shared environment builder and retains its
**explicit per-job** thread allocation for both budgets. A parent worker's
one-thread setting must not silently throttle a requested multi-thread job.
Independent-job concurrency, OpenMP kernels and true MPI PDE distribution remain
different capabilities. No OS affinity, memory hard limit or CPU isolation is
provided by environment variables alone.

## Why it must happen before import

Primary documentation reviewed on 24 October 2026:

- NumPy stable documentation (page labeled v2.5),
  [global configuration: linear-algebra threads](https://numpy.org/doc/stable/reference/global_state.html).
  Backend threading is library-dependent; this does not upgrade the tested
  NumPy 2.4.2 runtime or add a dependency.
- OpenBLAS official [runtime variables](https://www.openmathlib.org/OpenBLAS/docs/runtime_variables/):
  pthread and OpenMP builds use different controls, so the policy supplies
  `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and
  `OPENBLAS_DEFAULT_NUM_THREADS` together.
- OpenBLAS official [multithreaded application FAQ](https://www.openmathlib.org/OpenBLAS/docs/faq/):
  application and backend parallelism require coordinated budgets.
- Intel oneMKL Windows developer guide **2025.0**, section
  [MKL_DOMAIN_NUM_THREADS](https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-windows/2025-0/mkl-domain-num-threads.html):
  reviewed the domain/global precedence rule, not external implementation or
  example code. Removing inherited domain overrides avoids bypassing the cap;
  this is not an MKL backend installation or qualification.

Only documented configuration semantics were used. No external implementation,
example code, numerical model or dataset was copied. Existing solver equations,
units, tolerances, condition checks and conservation gates are unchanged.

## Reproduce and interpret measurements

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_numerical_runtime tests.python.test_process_memory_observation tests.python.test_solver_runtime_memory_benchmark -v
.venv/Scripts/python.exe scripts/benchmark_solver_runtime_memory.py --output build/new-runtime-report.json --samples 5 --timeout-seconds 120
```

The [executed memory/accuracy record](validation/SOLVER_RUNTIME_MEMORY_20261024.md)
separates Windows private commit from resident RAM, and import snapshots from
lifetime peaks. The matched AC and flowing CHT fixture preserved numerical
outputs while peak private commit fell approximately 89%; solve medians were
effectively unchanged. This is not a universal speedup, memory cap or large-mesh
qualification. Native Linux source execution is now recorded in the
[Linux qualification record](validation/LINUX_AC_CHT_QUALIFICATION_20261024.md).
Frozen Linux, installer and clean-machine package qualification remain separate.
