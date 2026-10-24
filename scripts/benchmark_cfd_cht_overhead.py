# SPDX-License-Identifier: Apache-2.0
"""Compare composed tetra CHT with and without admitted-mesh reuse."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import scipy
from python.spike_core.cfd_tetra_mesh import admit_cfd_tetra_mesh
from python.spike_core.cfd_tetra_cht import solve_cfd_tetra_cht
from python.spike_core.multiboard_identity import canonical_json_digest
import python.spike_core.cfd_tetra_energy as energy_module
import python.spike_core.cfd_tetra_stokes as stokes_module
from tests.python.test_cfd_tetra_cht import affine_two_phase_request


def source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_fingerprint(result: dict) -> str:
    if result.get("status") != "completed":
        raise RuntimeError(f"CHT benchmark failed: {result.get('issues')}")
    stable = {"fields": result["fields"], "diagnostics": result["diagnostics"]}
    stable["diagnostics"] = json.loads(json.dumps(stable["diagnostics"]))
    stable["diagnostics"]["energy"].pop("elapsed_seconds", None)
    return canonical_json_digest(stable)


def run_once(request: dict, duplicate_admission: bool) -> tuple[float, str]:
    original_energy = energy_module._resolve_admission
    original_stokes = stokes_module._resolve_admission
    if duplicate_admission:
        def admit_again(raw, _reuse, cancel):
            return admit_cfd_tetra_mesh(raw, cancel_check=cancel)
        energy_module._resolve_admission = admit_again
        stokes_module._resolve_admission = admit_again
    try:
        started = time.perf_counter_ns()
        result = solve_cfd_tetra_cht(request)
        elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    finally:
        energy_module._resolve_admission = original_energy
        stokes_module._resolve_admission = original_stokes
    return elapsed_ms, result_fingerprint(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refinement", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.refinement <= 3 or not 5 <= args.repeats <= 15:
        raise ValueError("bounded benchmark requires refinement 1..3 and repeats 5..15")
    request, _ = affine_two_phase_request(args.refinement)
    run_once(request, True)
    run_once(request, False)
    samples = {"duplicate_admission": [], "reuse": []}
    fingerprints = set()
    for _ in range(args.repeats):
        for name, duplicate in (("duplicate_admission", True), ("reuse", False)):
            elapsed, fingerprint = run_once(request, duplicate)
            samples[name].append(elapsed)
            fingerprints.add(fingerprint)
    if len(fingerprints) != 1:
        raise RuntimeError("Before/after CFD fields or diagnostics changed")
    paths = [ROOT / "python/spike_core" / name for name in (
        "cfd_tetra_mesh.py", "cfd_tetra_intersections.py", "cfd_tetra_stokes.py",
        "cfd_tetra_energy.py", "cfd_tetra_cht.py")]
    payload = {
        "contract": "spike/cfd-cht-overhead-benchmark/v1",
        "runtime": {"python": sys.version, "numpy": np.__version__,
                    "scipy": scipy.__version__, "platform": platform.platform()},
        "workload": {"refinement": args.refinement,
                     "tetrahedra": len(request["mesh"]["cells"]),
                     "request_sha256": canonical_json_digest(request)},
        "source_sha256": {str(path.relative_to(ROOT)): source_digest(path) for path in paths},
        "repeats": args.repeats, "result_fingerprint": fingerprints.pop(),
        "measurements": {name: {"samples_ms": values,
                                  "median_ms": statistics.median(values),
                                  "minimum_ms": min(values), "maximum_ms": max(values)}
                         for name, values in samples.items()},
        "scope": "in-process composed tetra CHT; exact duplicate mesh admission only",
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
