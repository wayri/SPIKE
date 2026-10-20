<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native-first performance and distributed solver roadmap

Owner direction, 21 October 2026: the complete suite must target fast native
numerical execution, multicore workstations and coordinated trusted LAN/HPC
clusters, while remaining maintainable and cross-platform. This is an
implementation direction, not a claim that MPI or production CFD is available.
Existing correctness, capability, dependency and release gates remain intact.

## Technology and ownership decision

| Layer | Chosen direction |
|---|---|
| Numerical kernels and hot mesh operations | C++20, portable contiguous data, explicit ownership and reusable prepared operators; existing C libraries through narrow adapters |
| One workstation | Target-scoped SIMD/OpenMP or established threaded numerical backend, one coherent core/BLAS/job budget |
| One distributed physical solve | Native MPI domain decomposition: owned entities, ghosts/halos, global IDs and distributed operators/preconditioners |
| Independent studies and remote control | Reuse Python worker pools and trusted LAN manager; do not invent another scheduler or security stack |
| Specifications/imports/provenance/reports | Python; retain independent reference kernels and regression oracles during migration |
| Desktop host and presentation | Existing thin Rust host and TypeScript UI; no parallel physics implementation there |
| Optional browser execution | Selected same-source C++ kernels compiled to WASM after separate evidence; not the MPI/HPC engine |

No new implementation language is introduced. C is appropriate for dependency
interfaces, not an instruction to duplicate the C++ suite. Do not add another
compiled runtime merely for novelty. Human-readable modules, normal debuggers,
ordinary builds and checked-in derivations remain mandatory.

Existing C++ circuit/field/airflow kernels are migration assets, not code to
discard. The tetrahedral research kernels are currently Python plus compiled
NumPy/SciPy primitives. Rewriting a call to a native sparse solver in C++ does
not by itself remove factor fill, copying or algorithmic bottlenecks.

## Current execution versus target

The [parallel worker manager](PARALLEL_WORKER_MANAGER.md) already schedules
bounded independent jobs locally and across explicitly enrolled trusted nodes.
Its control plane has mTLS, hostname/chain checks, certificate pins and client
allowlists. Discovery is inert; retained projects cannot enroll machines or
execute commands. Existing tests are not large physical-LAN scaling evidence.
Only its fixed operation allowlist is admitted; this does not automatically
make the new tetrahedral CFD kernels remotely executable.

That manager is **not** a distributed PDE solver. The present optional
[PETSc/MUMPS adapter](ACCELERATION_ARCHITECTURE.md) uses COMM_SELF, not a
distributed communicator. Native cavity/CHT code likewise does not establish
parallel tetrahedral CFD. Capability reports must distinguish job concurrency,
shared-memory kernel parallelism and distributed single-problem execution.

Reuse `parallel_pool.py`/`parallel_child.py` for local jobs and
`cluster_protocol.py`, `cluster_transport.py`, `cluster_manager.py`,
`cluster_discovery.py`, `cluster_cli.py` for enrolled-node control. No network
jobs, MPI launch, firewall changes, package installation or new dependency
approval is performed by this roadmap.

## Migration sequence and checkable exits

1. **Measure, retain and rank.** Capture warm-up plus five uninstrumented
   timings at fixed model/error/hardware/thread settings; report stage and
   whole-workflow costs separately. Record allocation/copy costs and native
   memory with appropriate tools; Python allocation counters are insufficient.
   Existing measured 3072-tetra admission took12.442 s, making geometry a
   concrete first candidate rather than assuming every Python function is slow.
2. **Native geometry/admission boundary.** First prototype batched bounding
   boxes, candidate screening and filtered predicates; preserve exact fallback,
   all separating axes, topology/patch identity, underflow rejection, budgets
   and cancellation. A batched native filter may initially return uncertain
   cases to the existing exact reference. Full exact native arithmetic needs
   an independently verified implementation or an approved dependency; do not
   bypass admission to eliminate that cost. Keep deterministic classification
   and near-contact, one-ulp, scaled and adversarial fixtures.
3. **Native assembly and prepared state.** Migrate measured element/face loops,
   coupling transfers and operator application with existing sparse backends.
   Retain immutable mesh/operator handles across RHS/time windows; amortize
   setup, avoid transient full-matrix copies and keep buffers alive explicitly.
   Preserve gauges, exact Jacobians, positivity, conservation and rollback.
4. **Multicore parity.** Benchmark1/2/4/available physical cores, pinning and
   NUMA placement where supported. Never multiply worker concurrency by
   unbounded BLAS/OpenMP pools. Parallelize independent work with documented
   reduction order; verify identical-model fields and physical certificates.
5. **Distributed numerical state.** Introduce partition ownership, halo
   exchange, local assembly/matrix-free operators and distributed Krylov/
   preconditioning. No full mesh/matrix/field replication or unbounded rank-zero
   gather. Prove shared-interface work/flux cancellation and distributed
   nullspace handling. Dependency discovery is not an executed MPI build.
6. **Coupled solver coordination.** Allocate bounded rank groups per solver,
   versioned conservative interfaces and agreed time windows. State updates,
   residuals and accepted checkpoints must describe the same coupled state.
   Support rollback, collective error/cancellation and partition-independent
   restart before enabling tightly coupled distributed physics. MPI progress
   cannot depend on one rank skipping a required collective after an error.
7. **Qualification and promotion.** Serial/reference, multicore,2/4 ranks,
   then four physical nodes; strong/weak scaling, peak per-rank memory,
   communication and I/O included. Preserve existing four-node75% weak/70%
   strong targets and five measured runs after one warm-up; do not claim larger
   cluster counts from four-node evidence. Record time to the same numerical
   error, not just iterations/second. Existing no-regression gates remain.

This sequence applies across SI/PI/EM, circuits, thermal, CFD and coupling, with
separate physics-specific parity corpora. Native migration cannot qualify
previously unsupported geometry, turbulence, device models or physics.

## ABI, data and maintainability requirements

- External native boundary: versioned C ABI/process contracts, opaque handles,
  explicit lengths/strides/scalar/index types, ownership and structured errors.
  No STL, Eigen, PETSc or MPI implementation types across public ABI boundaries.
- Validate once per immutable prepared state, invalidate on geometry/material/
  boundary/partition changes, and retain provenance. Do not skip validation
  because a pointer or old digest happens to match.
- Binary artifact references and bounded metadata at process boundaries;
  contiguous buffers inside kernels. JSON is not an inner-iteration transport.
- Separate discretization, linear algebra, transport and job supervision.
  Keep modules within the architecture guard; document equations, extension
  points and retirement of migrated production paths. References remain test
  oracles, not two silently diverging production authorities.
- Strict reference floating-point policy; no inherited fast-math or mandatory
  build-host ISA. Optimized paths require numerical equivalence, safe runtime
  ISA dispatch and sanitizer/race checks. Existing legacy optimization debt is
  not the template for new kernels.

## Cross-platform and network limits

Target native Windows/MSVC, Linux/GCC/Clang and desktop macOS/Clang where each
dependency is supported. Build/pin/test actual platform artifacts separately.
MPI distributions and ABI/scalar/index compatibility must be checked per job;
do not promise mixed Windows/Linux ranks in one communicator. Mixed-platform
independent jobs are a distinct control-plane capability.

MPI launch extends the existing trusted-host/fixed-operation policy, not an
arbitrary shell/SSH/executable service. Preserve uncertain-delivery/no-automatic-
retry semantics, administrator-owned credentials outside projects, resource
quotas, process-tree cancellation and artifact integrity. mTLS control traffic
does not automatically encrypt MPI data traffic: document and secure the
trusted compute fabric separately. Portable hard containment remains work,
not something cooperative thread caps already provide.

WASM is an optional compilation target for bounded previews or matching kernel
tests. Its memory, threading, deployment isolation, cancellation and dependency
limits require separate qualification. Browser threads are not a substitute for
native MPI. No WASM runtime or toolchain is added now.

## First executable performance baseline

`scripts/profile_cfd_native_candidates.py` measures actual mesh admission,
Stokes-with-admission and energy-with-admission for a retained case. One warm-up
and five timed runs precede a separate cProfile pass. Fingerprints must match
across repeats; failed kernels or changed inputs/sources reject the baseline.
It records CPU/wall times, platform/library/thread settings, input/source hashes
and hotspots. It explicitly excludes CAD/import/IPC/serialization/I/O and does
not claim peak native memory, a speedup or parallel qualification.

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
.venv-emerge3/Scripts/python.exe -Werror scripts/profile_cfd_native_candidates.py --case build/cad-cfd-open-flow-qualified-increment-20261021/box-0.18 --output build/my-native-profile
```

This is the starting baseline for a separately reviewed native port, not a
completed migration. Per-subsystem profiling, end-to-end measurement and actual
native/parallel comparison still follow.

### Executed baseline, 21 October 2026

The command above was executed against the1198-tetra retained box case, using
`build/native-migration-profile-20261021` as the fresh output. It completed
with unchanged selected sources/inputs and identical field fingerprints across
all repeats and instrumented passes. Runtime/platform/thread identities and
all measured samples are in that directory's `report.json`.

| Operation | Median wall seconds, five samples |
|---|---:|
| Mesh admission | 5.82834 |
| Flow including its admission | 6.74582 |
| Energy including its admission | 6.37648 |

The separate instrumented mesh pass attributed9.663 s cumulative to
`screen_positive_volume_intersections` out of11.234 s whole admitted geometry.
Its instrumented times **must not be compared** with the uninstrumented table
to claim overhead-free speed or a prospective native speedup. Together these
measurements prioritize overlap/admission work for the first C++ prototype.
Do not subtract independently measured medians to infer exact phase timings.

Two profiler regression tests passed with warnings treated as errors on both
Python3.11 and3.12. They require five samples plus separate warm-up/profile,
and reject varying fields, failed numerical results and invalid sample counts.
The architecture guard passed. No numerical solver was modified or ported by
this baseline; C++ equivalence/speedup and actual MPI scaling remain future
executed gates, not assumed benefits.

## Primary architecture references reviewed

- [MPI Forum documents](https://www.mpi-forum.org/docs/), reviewed21October2026:
  standard/implementation distinction; this does not require every deployment
  to implement the newest standard or approve a particular MPI dependency.
- [PETSc performance guide](https://petsc.org/release/manual/performance/),
  release page identifying3.26.0 on review: profiling, memory traffic and
  placement considerations; no dependency pin is upgraded by this review.
- [Emscripten pthread guidance](https://emscripten.org/docs/porting/pthreads.html),
  reviewed21October2026: worker/thread and deployment-isolation constraints.
  This is a feasibility reference, not adopted external implementation code.

No external source implementation, example or data was copied. No numerical
formulation, capability manifest, dependency pin or public ABI changes here.
