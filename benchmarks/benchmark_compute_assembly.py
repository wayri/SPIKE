"""Reproducible serial/multicore triplet benchmark; no solver speedup claim."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.spike_core.acceleration import assemble_graph_laplacian
from python.spike_core.compute_policy import cpu_thread_budget

parser = argparse.ArgumentParser()
parser.add_argument("--branches", type=int, default=1_000_000)
parser.add_argument("--repeats", type=int, default=5)
args = parser.parse_args()
if args.branches < 1 or args.repeats < 1:
    parser.error("branches and repeats must be positive")
p = np.arange(args.branches, dtype=np.int64) % 100000
n = (p + 1) % 100000
g = np.linspace(.01, 1000, args.branches)
baseline = assemble_graph_laplacian(p, n, g, requested="numpy")
report = {"branches": args.branches, "logical_cpus": os.cpu_count(), "thread_budget": cpu_thread_budget(), "runs": {}}
for backend in ("numpy", "numpy-threaded"):
    durations = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        result = assemble_graph_laplacian(p, n, g, requested=backend)
        durations.append((time.perf_counter() - started) * 1000)
        for expected, actual in zip(baseline[:3], result[:3]):
            np.testing.assert_array_equal(expected, actual)
        threads = result[3]["threads"]
        del result
    report["runs"][backend] = {"median_ms": statistics.median(durations), "samples_ms": durations, "threads": threads, "exact_match": True}
print(json.dumps(report, indent=2))
