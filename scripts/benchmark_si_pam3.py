# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Immutable generic PAM3 request-to-result timing; not protocol qualification."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from python.spike_core.si_pam3 import ternary_test_symbols
    from python.spike_core.service_si_pam3 import simulate_pam3_request
    import numpy
    import scipy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Fresh output file required")
    paths = ["scripts/benchmark_si_pam3.py", "python/spike_core/si_pam3.py",
             "python/spike_core/service_si_pam3.py", "python/spike_core/si_channel.py"]
    def identity():
        return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    sources = identity()
    cases = []
    for count in (1024, 8192, 16384):
        request = {"contract": "spike/si-pam3-request/v1", "symbols": ternary_test_symbols(count, seed=7).tolist(),
                   "levels_v": [-.4, 0., .4], "channel_impulse": [1.],
                   "symbol_rate_hz": 20e9, "samples_per_ui": 32}
        durations = []
        for run in range(6):
            start = perf_counter()
            result = simulate_pam3_request(request)
            duration = perf_counter() - start
            if len(result["eyes"]) != 2 or result["errors"]["observed_symbol_errors"] != 0:
                raise RuntimeError("Identity-channel numerical oracle failed")
            if any(abs(eye["height_v"] - .4) > 1e-12 for eye in result["eyes"]):
                raise RuntimeError("Identity-channel eye-opening oracle failed")
            if run:
                durations.append(duration)
        cases.append({"symbols": count, "samples_per_ui": 32, "seconds": durations,
                      "median_seconds": median(durations), "maximum_seconds": max(durations),
                      "request_sha256": result["request_sha256"]})
    if sources != identity():
        raise RuntimeError("Source changed during benchmark")
    report = {"contract": "spike/si-pam3-benchmark/v1", "status": "passed", "warmups": 1,
              "measured_runs": 5, "cases": cases, "source_sha256": sources,
              "platform": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count(),
              "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
              "threads": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
              "scope": "in-process strict request validation, FIR convolution, fixed-sample eyes and SER; excludes IPC, extraction and native AMI",
              "production_qualified": False}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "passed", "median_ms": [row["median_seconds"] * 1000 for row in cases]}))


if __name__ == "__main__":
    raise SystemExit(main())
