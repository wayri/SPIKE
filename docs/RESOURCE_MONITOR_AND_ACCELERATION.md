# Resource monitoring and compute allocation

## Reading the monitor

The desktop CPU badge reports SPIKE and its live descendants as a percentage of
total logical CPU capacity, bounded to 0–100%. A fully occupied core on a
16-logical-CPU machine contributes 6.25%. The popup also shows system CPU and
the worker thread allocation. Exited processes are removed on refresh. The
first CPU interval is unavailable rather than a fabricated measurement.

The RAM badge uses physical system used/total memory. Windows application RAM
uses private working sets matched to the current process tree, avoiding shared
pages counted once per process. If private counters are unavailable, the popup
explicitly labels the fallback as summed working sets with repeated shared
pages; it never uses that sum as the system RAM percentage. Browser preview
shows JavaScript heap usage and has no process CPU/GPU measurements.

Windows GPU telemetry uses PDH GPU Engine counters: utilization is the busiest
physical engine after summing its process contributions. Unrelated engines and
adapters are never added into an impossible percentage. The popup distinguishes
SPIKE-tree and system utilization, plus SPIKE dedicated/shared GPU memory.
GPU memory is labeled as a process sum: shared allocations can occur in more
than one process counter, so it is not represented as unique VRAM consumption.
Warmup, unsupported drivers, unavailable counters and non-Windows runtimes show
unavailable values. Rendering FPS is never substituted for measured GPU usage.
See Microsoft's [GPU measurement explanation](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/)
and [PDH array API](https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhgetformattedcounterarrayw).

Sampling is completion-driven with a 1.5-second delay, preventing overlapping
polls. Failed reads clear stale values. Frame CPU work measures executed render
callback work, excluding intentional idle frame throttling; it is not GPU time.

## CPU and GPU execution

The desktop allocates available logical CPUs minus two (minimum one) instead of
capping workers at eight. `SPIKE_CPU_THREADS` overrides this budget, clamped to
available CPUs. The host passes it to OpenMP, BLAS, NumExpr, Numba and the owned
native circuit solver. Nested OpenMP teams are disabled. Set the variable before
launching SPIKE; it applies to newly launched workers.

Large hybrid DC graph assembly fills disjoint NumPy output chunks concurrently.
Native operating-point solves consume the budget in supported OpenMP kernels;
explicit API thread options remain available. Older native DLLs retain their
single-thread compatibility path. Standalone native API calls without a host
allocation keep their existing one-thread default. These changes do not make
serial SuperLU or every native factorization parallel, and do not launch
multiple heavy jobs simultaneously.

Optional CuPy/CUDA sparse execution is implemented in the Python numerical
boundary and used by hybrid DC's existing acceleration route. It requires
CuPy compatible with the local NVIDIA CUDA runtime inside the actual worker
environment; installing it in an unrelated Python does not enable a frozen
worker. It is not bundled or installed automatically. Rendering already uses
the Three/WebGL GPU path, independently of optional numerical CUDA.

See [Numerical acceleration architecture](ACCELERATION_ARCHITECTURE.md) for
selection, thresholds, precision, residual checks and fallback semantics. CUDA
does not currently accelerate every EMI/SI, PEEC, thermal or native circuit
workflow. Worker catalog metadata reports availability; backend execution
metadata records selection and fallback.

## Validation on 2026-09-07

- On this Windows host, the live OS-counter smoke check returned system GPU
  utilization of 12.7%, idle test-process GPU utilization of 0%, and 6,344,704
  bytes of private resident memory. These are individual samples, not targets.
- `benchmarks/benchmark_compute_assembly.py` tested 1,000,000 branches, five
  samples, on 16 logical CPUs with a 14-thread budget. Median serial assembly:
  82.8 ms; multicore: 54.9 ms (about 1.5x). All output arrays matched exactly.
  This is assembly-only evidence and is sensitive to memory bandwidth and load.
- Resource tests cover old CPU-unit compatibility, invalid readings, independent
  system RAM accounting and GPU percentage bounds. Rust tests exercise engine
  aggregation across processes, engines and adapters.
- Numerical tests cover parallel chunk boundaries, CPU budget bounds, residual
  validation, automatic CUDA failure fallback and explicit failure reporting.
  The native ABI test checks the host allocation reaches a 256-node solve.
- This worker environment has no CuPy. Real CUDA execution is therefore an
  explicitly skipped hardware test, not a qualified speedup claim.

Source changes require rebuilding the desktop and its packaged Python workers
before they are present in a distributed installer.
