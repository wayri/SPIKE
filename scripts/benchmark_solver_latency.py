# SPDX-License-Identifier: Apache-2.0
"""Time bounded solver reference fixtures without relaxing their tolerances.

This is an in-process latency sample, not an arbitrary-workload qualification.
Imports and first use are reported separately from repeated solves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=11)
    args = parser.parse_args()
    if not 3 <= args.repeats <= 100:
        parser.error("repeats must be between 3 and 100")
    started = time.perf_counter_ns()
    from python.spike_core.solvers.circuits.models.benchmark_native_mna import _native_mna_dc_benchmark, _native_mna_ac_benchmark, _native_mna_transient_benchmark
    import_ms = (time.perf_counter_ns() - started) / 1e6

    def reference(name, measured, expected, tolerance, units, detail):
        error = abs(measured - expected) / max(abs(expected), 1e-30)
        if not error <= tolerance:
            raise AssertionError(f"{name}: relative error {error} > {tolerance}")
        return dict(name=name, measured=measured, expected=expected,
                    relative_error=error, tolerance=tolerance, units=units)

    cases = []
    for fixture in (_native_mna_dc_benchmark, _native_mna_ac_benchmark,
                    _native_mna_transient_benchmark):
        samples = []
        for _ in range(args.repeats + 1):
            started = time.perf_counter_ns()
            result = fixture(reference)
            samples.append((time.perf_counter_ns() - started) / 1e6)
        cases.append(dict(reference=result, first_use_ms=samples[0],
                          repeated_ms=samples[1:],
                          median_ms=statistics.median(samples[1:])))
    # Same admitted scalar values with only protocol formatting changed.
    payload = {"id": "encoding-fixture", "ok": True, "result": {"samples": [
        {"element_id": str(i), "value": i / 7, "layer": "F.Cu",
         "position_mm": [i % 100, i // 100, 0]} for i in range(10_000)
    ]}}
    encoding = {}
    for name, options in (("formatted", {}), ("compact", {"separators": (",", ":")})):
        samples = []
        for _ in range(args.repeats + 1):
            started = time.perf_counter_ns()
            wire = json.dumps(payload, default=str, **options)
            samples.append((time.perf_counter_ns() - started) / 1e6)
        assert json.loads(wire) == payload
        encoding[name] = dict(bytes=len(wire.encode("utf-8")),
                              repeated_ms=samples[1:],
                              median_ms=statistics.median(samples[1:]))
    paths = [Path(__file__), ROOT / "python/spike_core/solvers/circuits/models/benchmark_native_mna.py",
             ROOT / "python/spike_core/solvers/circuits/models/native_mna.py", ROOT / "python/spike_core/__init__.py",
             ROOT / "python/spike_core/worker_protocol.py"]
    report = dict(contract="spike/bounded-solver-latency/v1", python=sys.version,
                  platform=platform.platform(), import_ms=import_ms, cases=cases, encoding=encoding,
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in paths},
                  limitations=["Three tiny linear MNA fixtures only; not all solver families.",
                               "In-process calls include validation and result construction; exclude worker transport.",
                               "Existing analytical/discrete references and tolerances are unchanged."])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"import_ms": import_ms, "cases": [
        {"name": c["reference"]["name"], "first_use_ms": c["first_use_ms"],
         "median_ms": c["median_ms"]} for c in cases]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
