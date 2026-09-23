"""CPU allocation shared by numerical adapters; never infer solver validity."""
from __future__ import annotations
import os


def cpu_thread_budget() -> int:
    count = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    if hasattr(os, "sched_getaffinity"):
        try:
            count = min(count, len(os.sched_getaffinity(0)))
        except OSError:
            pass
    count = max(1, count)
    try:
        requested = int(os.environ.get("SPIKE_CPU_THREADS", "0"))
    except ValueError:
        requested = 0
    return min(count, requested) if requested > 0 else max(1, count - 2)
