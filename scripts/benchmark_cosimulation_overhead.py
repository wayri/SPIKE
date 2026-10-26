# SPDX-License-Identifier: Apache-2.0
"""Measure fixed-grid co-simulation orchestration overhead."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.solvers.execution.coupling.cosimulation import run_cosimulation


def fixture(steps: int) -> dict:
    participant = {
        "adapter": "gain", "model_revision": "1", "model_status": "experimental",
        "inputs": {"u": "V"}, "outputs": {"y": "V"}, "config": {"gain": 0.999},
    }
    return {
        "contract": "spike/cosimulation-request/v1", "model_id": "overhead-benchmark",
        "model_revision": "r1", "step_s": 1e-4, "steps": steps,
        "participants": [
            {**participant, "id": "a", "initial_outputs": {"y": 1.0}},
            {**participant, "id": "b", "initial_outputs": {"y": 2.0}},
        ],
        "connections": [
            {"source": ["a", "y"], "target": ["b", "u"]},
            {"source": ["b", "y"], "target": ["a", "u"]},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    request = fixture(args.steps)
    run_cosimulation(request)
    samples = []
    digest = None
    for _ in range(args.repeats):
        started = time.perf_counter_ns()
        result = run_cosimulation(request)
        samples.append((time.perf_counter_ns() - started) / 1e6)
        if result["status"] != "completed" or result["completed_steps"] != args.steps:
            raise RuntimeError("Benchmark co-simulation did not complete")
        current = result["request_sha256"]
        if digest is not None and current != digest:
            raise RuntimeError("Benchmark request identity changed")
        digest = current
    payload = {
        "contract": "spike/cosimulation-overhead-benchmark/v1",
        "steps": args.steps, "participants": 2, "repeats": args.repeats,
        "median_ms": statistics.median(samples), "minimum_ms": min(samples),
        "maximum_ms": max(samples), "samples_ms": samples,
        "request_sha256": digest,
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
