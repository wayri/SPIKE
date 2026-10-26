# SPDX-License-Identifier: Apache-2.0
"""Benchmark bounded C JSON mesh snapshots against reviewed iterator transport."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import scipy
import python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_mesh as mesh_module
from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_cht import solve_cfd_tetra_cht
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_cfd_tetra_cht import affine_two_phase_request


def legacy_json_encoding(raw, *, retain):
    """Immediately preceding reviewed bounded order-preserving transport."""
    pending = [(raw, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 500_000 or depth > 32:
            raise mesh_module.CfdTetraMeshError(
                "Tetra mesh reuse JSON structure exceeds node/depth budget")
        if type(value) is dict:
            if not all(type(key) is str for key in value):
                raise mesh_module.CfdTetraMeshError(
                    "Tetra mesh reuse requires string JSON object keys")
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            pending.extend((item, depth + 1) for item in value)
        elif value is not None and type(value) not in (str, bool, int, float):
            raise mesh_module.CfdTetraMeshError(
                "Tetra mesh reuse requires plain JSON containers")
    digest = hashlib.sha256()
    size = 0
    parts = [] if retain else None
    encoder = json.JSONEncoder(sort_keys=False, allow_nan=False, separators=(",", ":"))
    for part in encoder.iterencode(raw):
        encoded = part.encode("utf-8")
        size += len(encoded)
        if size > 32 * 1024**2:
            raise mesh_module.CfdTetraMeshError("Tetra mesh reuse digest exceeds 32 MiB")
        digest.update(encoded)
        if parts is not None:
            parts.append(part)
    snapshot = json.loads("".join(parts)) if parts is not None else None
    return digest.hexdigest(), snapshot


def fingerprint(result):
    if result.get("status") != "completed":
        raise RuntimeError(f"benchmark solve failed: {result.get('issues')}")
    stable = {"fields": result["fields"], "diagnostics": result["diagnostics"]}
    stable["diagnostics"] = json.loads(json.dumps(stable["diagnostics"]))
    stable["diagnostics"]["energy"].pop("elapsed_seconds", None)
    return canonical_json_digest(stable)


def timed_solve(request, encoding):
    original = mesh_module._raw_mesh_encoding
    mesh_module._raw_mesh_encoding = encoding
    try:
        started = time.perf_counter_ns()
        result = solve_cfd_tetra_cht(request)
        elapsed = (time.perf_counter_ns() - started) / 1e6
    finally:
        mesh_module._raw_mesh_encoding = original
    return elapsed, fingerprint(result)


def timed_preparation(raw, encoding, iterations=20):
    started = time.perf_counter_ns()
    results = [encoding(raw, retain=bool(index % 2)) for index in range(iterations)]
    elapsed = (time.perf_counter_ns() - started) / (iterations * 1e6)
    return elapsed, {digest for digest, _ in results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refinement", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.refinement <= 3 or not 5 <= args.repeats <= 15:
        raise ValueError("bounded benchmark requires refinement 1..3 and repeats 5..15")
    request, _ = affine_two_phase_request(args.refinement)
    current = mesh_module._raw_mesh_encoding
    timed_solve(request, legacy_json_encoding)
    timed_solve(request, current)
    methods = (("reviewed_json_iterator", legacy_json_encoding),
               ("bounded_c_json", current))
    samples = {name: [] for name, _ in methods}
    fingerprints = set()
    for repeat in range(args.repeats):
        for name, encoding in (methods if repeat % 2 == 0 else reversed(methods)):
            elapsed, value = timed_solve(request, encoding)
            samples[name].append(elapsed)
            fingerprints.add(value)
    if len(fingerprints) != 1:
        raise RuntimeError("preparation change altered fields or stable diagnostics")
    sources = [ROOT / "python/spike_core" / name for name in (
        "cfd_tetra_mesh.py", "cfd_tetra_intersections.py", "cfd_tetra_stokes.py",
        "cfd_tetra_energy.py", "cfd_tetra_cht.py")]
    preparation = {name: [] for name, _ in methods}
    preparation_digests = set()
    for repeat in range(15):
        for name, encoding in (methods if repeat % 2 == 0 else reversed(methods)):
            elapsed, digests = timed_preparation(request["mesh"], encoding)
            preparation[name].append(elapsed)
            preparation_digests.update(digests)
    if len(preparation_digests) != 1:
        raise RuntimeError("preparation methods produced different source digests")

    summarize = lambda values: {"samples_ms": values,
                                "median_ms": statistics.median(values),
                                "minimum_ms": min(values), "maximum_ms": max(values)}
    payload = {
        "contract": "spike/analysis-preparation-benchmark/v1",
        "runtime": {"python": sys.version, "numpy": np.__version__,
                    "scipy": scipy.__version__, "platform": platform.platform()},
        "workload": {"refinement": args.refinement,
                     "tetrahedra": len(request["mesh"]["cells"]),
                     "request_sha256": canonical_json_digest(request)},
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sources},
        "repeats": args.repeats, "result_fingerprint": fingerprints.pop(),
        "full_solve_measurements": {name: summarize(values)
                                    for name, values in samples.items()},
        "preparation_measurements": {name: summarize(values)
                                     for name, values in preparation.items()},
        "preparation_digest": preparation_digests.pop(),
        "scope": "in-process retained tetra CHT mesh snapshot/digest preparation",
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
