<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0137: Separate outer CPU and inner numerical worker budgets

Date: 2026-10-24. Status: accepted for source development; package qualification open.

## Decision

Use a stdlib-only Python policy owner for fresh numerical-child environments
and owned executable bootstrap. Default the inner BLAS/OpenMP budget to one;
retain `SPIKE_CPU_THREADS` for outer scheduling/assembly, with an explicit
`SPIKE_BLAS_THREADS` opt-in within that allocation. A parallel batch's explicit
per-job allocation remains authoritative. Configure the desktop child before
creation and Python before numerical imports; never attempt late reclamation.
Validate desktop overrides before spawning, not only at Python entry, and
remove inherited MKL domain-specific thread overrides in every owned path.

No ordinary library import modifies its caller's environment. No dependency,
solver equation, numerical tolerance, native ABI or validation gate changes.
Rust remains a thin process launcher supplying environment values, not an
alternative solver or configuration service.

## Evidence and consequences

The [runtime benchmark](../validation/SOLVER_RUNTIME_MEMORY_20261024.md) compares
five alternating fresh processes per configuration after warmups, with the same
input identities, AC oracle and CHT conservation/residual/equivalence checks.
Peak private commit falls substantially on the tested Windows runtime while
resident memory and solve timing change much less. Larger dense/threaded
workloads may benefit from a higher explicit inner budget; benchmark rather
than infer a universal optimum. No MPI or hard memory bound is established.

See [operator/developer guidance](../WORKER_NUMERICAL_RUNTIME.md). Existing
packaged binaries do not inherit source changes until rebuilt and qualified.
