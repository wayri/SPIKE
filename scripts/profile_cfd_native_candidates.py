# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Profile existing tetra kernels before native migration; no speedup claim.

One warm-up, five uninstrumented samples, then a separate instrumented pass.
Request loading/reporting/I/O are excluded from kernel timings explicitly.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(result):
    import numpy as np
    if "status" in result:
        if result["status"] != "completed":
            raise ValueError("Kernel did not complete: "+str(result.get("issues")))
        payload = json.dumps(result["fields"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    else:
        parts = []
        for key in ("cell_volumes", "face_areas", "cell_faces", "face_normals"):
            array = np.ascontiguousarray(result[key])
            parts.append(str((key, array.shape, array.dtype)).encode()+array.tobytes())
        payload = b"".join(parts)
    return hashlib.sha256(payload).hexdigest()


def measure(function, runs=5):
    if type(runs) is not int or not 5 <= runs <= 20:
        raise ValueError("Need 5 through 20 measured samples after one warm-up")
    expected = fingerprint(function())
    wall, cpu = [], []
    for _ in range(runs):
        started, processor = time.perf_counter(), time.process_time()
        result = function()
        cpu.append(time.process_time()-processor)
        wall.append(time.perf_counter()-started)
        if fingerprint(result) != expected:
            raise ValueError("Repeated kernel fields changed; baseline rejected")
    profiler = cProfile.Profile()
    result = profiler.runcall(function)
    if fingerprint(result) != expected:
        raise ValueError("Instrumented kernel fields changed; baseline rejected")
    rows = []
    for (filename, line, name), (primitive, total, own, cumulative, _callers) in pstats.Stats(profiler).stats.items():
        rows.append({"file": filename, "line": line, "function": name,
                     "primitive_calls": primitive, "total_calls": total,
                     "self_seconds": own, "cumulative_seconds": cumulative})
    return {"warmups": 1, "wall_seconds": wall, "cpu_seconds": cpu,
            "median_wall_seconds": statistics.median(wall), "minimum_wall_seconds": min(wall),
            "maximum_wall_seconds": max(wall), "field_fingerprint": expected,
            "instrumented_top_cumulative": sorted(rows, key=lambda r: r["cumulative_seconds"], reverse=True)[:30],
            "instrumented_top_self": sorted(rows, key=lambda r: r["self_seconds"], reverse=True)[:30]}


def run(case, output, runs=5):
    import numpy as np
    import scipy
    from python.spike_core.cfd_tetra_mesh import admit_cfd_tetra_mesh
    from python.spike_core.cfd_tetra_stokes import solve_cfd_tetra_stokes
    from python.spike_core.cfd_tetra_energy import solve_cfd_tetra_energy

    inputs = {name: case/(name+"-request.json") for name in ("flow", "energy")}
    requests = {}
    for name, path in inputs.items():
        if not path.is_file() or not 0 < path.stat().st_size <= 8*1024**2:
            raise ValueError("Missing/oversized retained request: "+str(path))
        requests[name] = json.loads(path.read_text(encoding="utf-8"))
    if requests["flow"]["mesh"] != requests["energy"]["mesh"]:
        raise ValueError("Cross-solver inputs must use the identical mesh")
    if len(requests["flow"]["mesh"]["cells"]) > 4096:
        raise ValueError("Mesh budget exceeded")
    output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), *[ROOT/"python/spike_core"/name for name in (
        "cfd_tetra_mesh.py", "cfd_tetra_intersections.py", "cfd_tetra_stokes.py",
        "cfd_tetra_energy.py", "enclosure_sa_transport.py")]]
    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    input_hashes = {str(path.resolve()): digest(path) for path in inputs.values()}
    report = {"contract": "spike/native-migration-profile/v1", "status": "running",
              "source_sha256": source_hashes, "input_sha256": input_hashes,
              "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
                          "platform": platform.platform(), "machine": platform.machine(),
                          "logical_cpus": os.cpu_count(), "thread_environment": {
                              name: os.environ.get(name) for name in (
                                  "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}},
              "scope": "individual in-process kernels including their admission; excludes CAD/import/IPC/serialization/I/O",
              "tetrahedra": len(requests["flow"]["mesh"]["cells"]), "stages": {},
              "peak_native_memory_measured": False, "production_qualified": False,
              "speedup_measured": False,
              "limits": ["cProfile has overhead; instrumented pass is not a performance sample",
                         "Python call profiles cannot attribute all compiled BLAS/SciPy internals",
                         "No multicore, MPI, GPU or cluster scaling qualification"]}
    def publish():
        (output/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    publish()
    try:
        for name, function in (
                ("mesh_admission", lambda: admit_cfd_tetra_mesh(requests["flow"]["mesh"])),
                ("flow_with_admission", lambda: solve_cfd_tetra_stokes(requests["flow"])),
                ("energy_with_admission", lambda: solve_cfd_tetra_energy(requests["energy"]))):
            report["stages"][name] = measure(function, runs)
            publish()
        stable = (all(digest(ROOT/path) == value for path, value in source_hashes.items()) and
                  all(digest(Path(path)) == value for path, value in input_hashes.items()))
        if not stable:
            raise ValueError("Profile inputs/sources changed while running")
        report.update(status="completed", sources_and_inputs_unchanged=True)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        publish()
        raise
    publish()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    arguments = parser.parse_args()
    result = run(arguments.case, arguments.output, arguments.runs)
    print(json.dumps({"status": result["status"], "tetrahedra": result["tetrahedra"],
                      "medians": {name: stage["median_wall_seconds"] for name, stage in result["stages"].items()}}))
