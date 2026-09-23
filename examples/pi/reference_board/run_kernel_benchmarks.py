#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yawar Badri
"""Run only the retained PI numerical reference benchmarks, failing on skips."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from python.spike_core import benchmarks as current_benchmarks
from python.spike_core import peec_plugin
from python.spike_core.benchmark_pdn import run_pdn_two_port_loading_benchmark


PI_KERNEL_CASES = (
    current_benchmarks._trace_benchmark,
    current_benchmarks._via_benchmark,
    current_benchmarks._zone_convergence_benchmark,
    current_benchmarks._hybrid_connectivity_benchmark,
    current_benchmarks._native_trace_inductance_benchmark,
    current_benchmarks._native_hybrid_smoke_benchmark,
    current_benchmarks._capacitance_asymptote_benchmark,
    current_benchmarks._native_ac_loss_benchmark,
    current_benchmarks._shared_reference_multiport_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not peec_plugin.native_available():
        parser.error("The native PEEC extension is required for the PI kernel benchmarks.")
    results = [run() for run in PI_KERNEL_CASES]
    results.append(run_pdn_two_port_loading_benchmark(current_benchmarks._result,
                                                      current_benchmarks.Benchmark))
    records = [item.to_dict() for item in results]
    report = {
        "contract": "spike/public-pi-kernel-benchmarks/v1",
        "native_peec_sha256": hashlib.sha256(Path(peec_plugin.native.__file__).read_bytes()).hexdigest(),
        "summary": {"total": len(records), "passed": sum(item["status"] == "passed" for item in records),
                    "failed": sum(item["status"] == "failed" for item in records),
                    "skipped": sum(item["status"] == "skipped" for item in records)},
        "status": "passed" if all(item["status"] == "passed" for item in records) else "failed",
        "benchmarks": records,
        "scope": "Numerical kernels and bounded analytical references; no measured-board correlation.",
        "release_validated": False,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    print(f"SPIKE PI kernels: {report['summary']['passed']}/{report['summary']['total']} passed; "
          f"{report['summary']['skipped']} skipped")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
