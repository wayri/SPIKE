# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Pre-import numerical thread budgets; no solver equations or host policy.

BLAS scratch/thread allocation is separate from outer CPU job concurrency.
Changing environment variables after a numerical import cannot reclaim it.
"""
from __future__ import annotations

from collections.abc import Mapping
import os
import sys

from .compute_policy import cpu_thread_budget

BLAS_ENVIRONMENT_KEYS = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OPENBLAS_DEFAULT_NUM_THREADS",
    "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS",
)


def _budget(value, name):
    if type(value) is not int or not 1 <= value <= 256:
        raise ValueError(f"{name} must be an integer in 1..256")
    return value


def numerical_child_environment(*, cpu_threads: int, blas_threads: int = 1,
                                base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy a child environment; never mutate the caller or process environment.

    Explicit BLAS threads cannot exceed the outer CPU allocation. Native
    OpenMP shares this inner budget; independently scheduled assembly/Numba
    work retains the outer allocation. This is not OS-enforced CPU isolation.
    """
    cpu = _budget(cpu_threads, "cpu_threads")
    blas = _budget(blas_threads, "blas_threads")
    if blas > cpu:
        raise ValueError("blas_threads must not exceed cpu_threads")
    environment = dict(os.environ if base is None else base)
    # Domain-specific MKL settings take precedence over MKL_NUM_THREADS.
    environment.pop("MKL_DOMAIN_NUM_THREADS", None)
    environment.update({name: str(blas) for name in BLAS_ENVIRONMENT_KEYS})
    environment.update(SPIKE_CPU_THREADS=str(cpu), SPIKE_BLAS_THREADS=str(blas),
                       NUMBA_NUM_THREADS=str(cpu), OMP_MAX_ACTIVE_LEVELS="1")
    return environment


def bootstrap_worker_numerics() -> dict:
    """Apply only from an owned executable entry, before numerical imports.

    SPIKE_BLAS_THREADS is the authoritative explicit worker knob. Legacy
    backend variables are replaced coherently rather than retaining divergent
    inherited values. Ordinary library imports never call this function.
    """
    if any(name in sys.modules for name in ("numpy", "scipy")):
        raise RuntimeError("Numerical runtime budget must be applied before NumPy/SciPy import")
    cpu = min(cpu_thread_budget(), 256)
    raw = os.environ.get("SPIKE_BLAS_THREADS", "1")
    if not (raw.isascii() and raw.isdecimal() and len(raw) <= 3 and str(int(raw)) == raw):
        raise ValueError("SPIKE_BLAS_THREADS must be a canonical positive integer")
    environment = numerical_child_environment(cpu_threads=cpu, blas_threads=int(raw))
    applied = {name: environment[name] for name in (*BLAS_ENVIRONMENT_KEYS,
               "SPIKE_CPU_THREADS", "SPIKE_BLAS_THREADS", "NUMBA_NUM_THREADS", "OMP_MAX_ACTIVE_LEVELS")}
    os.environ.pop("MKL_DOMAIN_NUM_THREADS", None)
    os.environ.update(applied)
    return {"status": "configured_before_numerical_import", "cpu_threads": cpu,
            "blas_threads": int(raw), "environment": applied}
