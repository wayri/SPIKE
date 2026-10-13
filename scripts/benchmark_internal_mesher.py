# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Reproducible black-box comparison for convex point-cloud tetrahedralizers.

The corpus and validation code are original SPIKE material. External engines
are called only through their public APIs in finite-time subprocesses. No
third-party examples, source, meshes, or binaries are copied or bundled.
Geometry checks establish a valid tetrahedral complex, not solver accuracy or
production qualification.
"""
from __future__ import annotations

import argparse
import cProfile
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import platform
import pstats
import random
import statistics
import subprocess
import sys
import threading
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
DEFAULT_OUTPUT = ROOT / "output" / "internal-mesher-benchmark-20261012"
BENCHMARK_SOURCE = Path(__file__).resolve()
BENCHMARK_TEST_SOURCE = ROOT / "tests" / "python" / "test_internal_mesher_benchmark.py"
INTERNAL_SOURCE = ROOT / "python" / "spike_core" / "internal_tetra_generation.py"
BASELINE_SOURCE_SNAPSHOT = DEFAULT_OUTPUT / "baseline-internal_tetra_generation.py"
GMSH_API = Path("C:/msys64/ucrt64/lib/gmsh.py")
GMSH_DLL = Path("C:/msys64/ucrt64/bin/libgmsh.dll")
GMSH_PIN = {
    str(GMSH_API): "f4b0935cebde899750293d87a643090e5ea33c9b18d249267f507db68a0e01c3",
    str(GMSH_DLL): "a43b4c96644b3c7dc57f79285cd68814ecb3995e582939378a27d238533ed599",
}
MANUAL_URL = "https://gmsh.info/doc/texinfo/gmsh.html"
BACKENDS = ("internal_kernel", "internal_fullrun", "scipy_qhull", "gmsh_4_15_2")
ALL_BACKENDS = ("internal_baseline_snapshot", *BACKENDS)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fixture_corpus() -> list[dict]:
    """Return independently generated, deterministic point clouds."""
    fixtures = []
    for count in (8, 32, 64, 128):
        rng = random.Random(20261012 + count)
        points = [[rng.random(), rng.random(), rng.random()] for _ in range(count)]
        fixtures.append({"id": f"generic_{count}", "kind": "generic_uniform_cloud",
                         "seed": 20261012 + count, "expected": "success", "points": points})
    cube = [list(point) for point in itertools.product((0.0, 1.0), repeat=3)]
    fixtures.append({"id": "cube_lattice_cospherical", "kind": "integer_lattice_cube_corners",
                     "seed": None, "expected": "success", "points": cube})
    rng = random.Random(7201)
    thin = [[rng.random(), rng.random(), rng.random() * 1e-8] for _ in range(20)]
    fixtures.append({"id": "thin_conditioned", "kind": "near_coplanar_uniform_cloud",
                     "seed": 7201, "z_scale": 1e-8, "expected": "reported_status",
                     "points": thin})
    for fixture in fixtures:
        fixture["points_sha256"] = _sha_bytes(_canonical(fixture["points"]))
    return fixtures


def fixture_manifest() -> dict:
    rows = [{key: value for key, value in item.items() if key != "points"}
            for item in fixture_corpus()]
    return {"contract": "spike/internal-mesher-corpus/v1",
            "source": "original deterministic synthetic SPIKE fixtures",
            "fixtures": rows, "corpus_sha256": _sha_bytes(_canonical(rows))}


def _tetra_volume(vertices: list[list[float]], cell: list[int]) -> float:
    a, b, c, d = (vertices[index] for index in cell)
    ax, ay, az = (a[k] - d[k] for k in range(3))
    bx, by, bz = (b[k] - d[k] for k in range(3))
    cx, cy, cz = (c[k] - d[k] for k in range(3))
    return (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
            + az * (bx * cy - by * cx)) / 6.0


def _oriented_cells(vertices: list[list[float]], cells: list[list[int]]) -> list[list[int]]:
    result = []
    for raw in cells:
        cell = [int(value) for value in raw]
        if _tetra_volume(vertices, cell) < 0:
            cell[0], cell[1] = cell[1], cell[0]
        result.append(cell)
    return result


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    location = fraction * (len(ordered) - 1)
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - location) + ordered[upper] * (location - lower)


def _mean_ratio(vertices: list[list[float]], cell: list[int], volume: float) -> float:
    squared_edges = 0.0
    for left, right in itertools.combinations(cell, 2):
        squared_edges += sum((vertices[left][axis] - vertices[right][axis]) ** 2
                             for axis in range(3))
    return 12.0 * (3.0 * volume) ** (2.0 / 3.0) / squared_edges


def validate_tetrahedralization(points: list[list[float]], vertices: list[list[float]],
                                cells: list[list[int]]) -> dict:
    """Independently audit coverage, topology, volume and element quality."""
    started = time.perf_counter_ns()
    if len(vertices) < len(points) or vertices[:len(points)] != points:
        raise ValueError("output does not retain original points in their input order")
    if not cells:
        raise ValueError("tetrahedralization contains no cells")
    if any(len(cell) != 4 or len(set(cell)) != 4 or min(cell) < 0 or max(cell) >= len(vertices)
           for cell in cells):
        raise ValueError("tetrahedralization contains invalid connectivity")
    canonical_cells = [tuple(sorted(cell)) for cell in cells]
    if len(set(canonical_cells)) != len(canonical_cells):
        raise ValueError("tetrahedralization contains duplicate cells")
    used = {index for cell in cells for index in cell}
    if not set(range(len(points))) <= used:
        raise ValueError("not all original input points are used")

    span = max(max(point[axis] for point in points) - min(point[axis] for point in points)
               for axis in range(3))
    volumes = [_tetra_volume(vertices, cell) for cell in cells]
    scale_tiny_threshold = span ** 3 * 1e-15
    bad_volumes = [value for value in volumes
                   if not math.isfinite(value) or value <= scale_tiny_threshold]
    if bad_volumes:
        raise ValueError("tetrahedralization contains nonpositive or numerically tiny cells "
                         f"(count={len(bad_volumes)}, min_volume={min(bad_volumes)}, "
                         f"scale_threshold={scale_tiny_threshold})")

    try:
        from scipy.spatial import ConvexHull
    except ImportError as exc:
        raise RuntimeError("independent validation requires separately installed SciPy") from exc
    oracle_started = time.perf_counter_ns()
    hull = ConvexHull(points)
    oracle_ns = time.perf_counter_ns() - oracle_started
    hull_volume = float(hull.volume)
    tiny_threshold = max(hull_volume * 1e-14, span ** 3 * 1e-15)
    bad_volumes = [value for value in volumes if not math.isfinite(value) or value <= tiny_threshold]
    if bad_volumes:
        raise ValueError("tetrahedralization contains nonpositive or numerically tiny cells "
                         f"(count={len(bad_volumes)}, min_volume={min(bad_volumes)}, "
                         f"hull_threshold={tiny_threshold})")

    owners: dict[tuple[int, int, int], list[int]] = {}
    for cell_index, cell in enumerate(cells):
        for face in itertools.combinations(cell, 3):
            key = tuple(sorted(face))
            owners.setdefault(key, []).append(cell_index)
    if any(len(face_owners) not in (1, 2) for face_owners in owners.values()):
        raise ValueError("tetrahedralization has a nonmanifold face")
    neighbours = [set() for _ in cells]
    for face, face_owners in owners.items():
        if len(face_owners) != 2:
            continue
        left, right = face_owners
        opposite_left = next(index for index in cells[left] if index not in face)
        opposite_right = next(index for index in cells[right] if index not in face)
        if (_tetra_volume(vertices, [*face, opposite_left]) *
                _tetra_volume(vertices, [*face, opposite_right]) >= 0):
            raise ValueError("interior-face owners lie on the same side or are locally degenerate")
        neighbours[left].add(right)
        neighbours[right].add(left)
    reached, pending = set(), [0]
    while pending:
        cell_index = pending.pop()
        if cell_index not in reached:
            reached.add(cell_index)
            pending.extend(neighbours[cell_index] - reached)
    if len(reached) != len(cells):
        raise ValueError("tetrahedralization cell adjacency is disconnected")

    boundary = [face for face, face_owners in owners.items() if len(face_owners) == 1]
    boundary_edges: dict[tuple[int, int], int] = {}
    for face in boundary:
        for edge in itertools.combinations(face, 2):
            key = tuple(sorted(edge))
            boundary_edges[key] = boundary_edges.get(key, 0) + 1
    if not boundary or any(count != 2 for count in boundary_edges.values()):
        raise ValueError("boundary is not a closed two-manifold")
    boundary_vertices = {vertex for face in boundary for vertex in face}
    for vertex in boundary_vertices:
        link: dict[int, set[int]] = {}
        for face in boundary:
            if vertex in face:
                left, right = [index for index in face if index != vertex]
                link.setdefault(left, set()).add(right)
                link.setdefault(right, set()).add(left)
        if not link or any(len(adjacent) != 2 for adjacent in link.values()):
            raise ValueError("exterior vertex link is not a single manifold cycle")
        link_reached, link_pending = set(), [next(iter(link))]
        while link_pending:
            index = link_pending.pop()
            if index not in link_reached:
                link_reached.add(index)
                link_pending.extend(link[index] - link_reached)
        if len(link_reached) != len(link):
            raise ValueError("exterior vertex link is not a single manifold cycle")

    summed_volume = math.fsum(volumes)
    volume_error = abs(summed_volume - hull_volume)
    volume_tolerance = max(hull_volume * 2e-10, span ** 3 * 1e-13)
    if volume_error > volume_tolerance:
        raise ValueError("tetrahedral volume does not match the independent convex hull "
                         f"(tetra_volume={summed_volume}, scipy_hull_volume={hull_volume}, "
                         f"absolute_error={volume_error}, tolerance={volume_tolerance})")
    plane_tolerance = max(span * span * span * 2e-12, 1e-15)
    for face in boundary:
        signs = [_tetra_volume(vertices, [*face, index]) for index in range(len(points))]
        if min(signs) < -plane_tolerance and max(signs) > plane_tolerance:
            raise ValueError("boundary face is not a supporting convex-hull face")

    qualities = [_mean_ratio(vertices, cell, volume) for cell, volume in zip(cells, volumes)]
    if any(not 0.0 < quality <= 1.0 + 1e-10 for quality in qualities):
        raise ValueError("invalid mean-ratio quality")
    elapsed = time.perf_counter_ns() - started
    return {"status": "passed", "all_original_points_used": True,
            "positive_nontiny_volumes": True, "face_manifold": True,
            "interior_face_opposite_sides": True, "connected_cell_adjacency": True,
            "exterior_vertex_links_single_cycle": True, "supporting_hull": True,
            "global_intersection_check": False,
            "validation_limit": "face-local topology and convex-volume checks do not prove absence of every non-face global tetrahedron intersection",
            "vertex_count": len(vertices), "cell_count": len(cells),
            "steiner_vertex_count": len(vertices) - len(points),
            "tetra_volume": summed_volume, "scipy_convex_hull_volume": hull_volume,
            "volume_absolute_error": volume_error, "tiny_volume_threshold": tiny_threshold,
            "quality_mean_ratio": {"min": min(qualities), "mean": statistics.fmean(qualities),
                                   "p10": _quantile(qualities, 0.10),
                                   "p50": _quantile(qualities, 0.50),
                                   "p90": _quantile(qualities, 0.90)},
            "validation_ns": elapsed, "convex_hull_oracle_ns": oracle_ns}


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def _memory_for_handle(handle: int | None = None) -> dict | None:
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                           ctypes.POINTER(_ProcessMemoryCountersEx),
                                           wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if handle is None:
        handle = kernel32.GetCurrentProcess()
    counters = _ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return None
    result = {"working_set_bytes": counters.WorkingSetSize,
              "peak_working_set_bytes": counters.PeakWorkingSetSize,
              "pagefile_usage_bytes": counters.PagefileUsage,
              "peak_pagefile_usage_bytes": counters.PeakPagefileUsage,
              "current_private_usage_bytes": counters.PrivateUsage}
    return result


def _load_gmsh():
    for raw, expected in GMSH_PIN.items():
        path = Path(raw)
        if not path.is_file() or path.is_symlink() or _sha_file(path) != expected:
            raise RuntimeError("Gmsh entry artifact is missing or differs from the 4.15.2 pin")
    import ctypes.util
    started = time.perf_counter_ns()
    with os.add_dll_directory(str(GMSH_DLL.parent)):
        previous = ctypes.util.find_library
        try:
            ctypes.util.find_library = lambda name: str(GMSH_DLL) if name in ("gmsh", "gmsh-4.15") else previous(name)
            spec = importlib.util.spec_from_file_location("spike_benchmark_gmsh", GMSH_API)
            if spec is None or spec.loader is None:
                raise RuntimeError("unable to create Gmsh API module")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            ctypes.util.find_library = previous
    return module, time.perf_counter_ns() - started


def _prepare_backend(name: str):
    started = time.perf_counter_ns()
    metadata = {}
    if name == "internal_baseline_snapshot":
        if not BASELINE_SOURCE_SNAPSHOT.is_file():
            raise RuntimeError("baseline source snapshot is unavailable")
        spec = importlib.util.spec_from_file_location(
            "python.spike_core._benchmark_baseline_internal_tetra_generation",
            BASELINE_SOURCE_SNAPSHOT)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load baseline source snapshot")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        execute = lambda points: module.generate_tetra_mesh(points)
        version = "spike-internal-tetra-v1-baseline-" + _sha_file(BASELINE_SOURCE_SNAPSHOT)[:12]
    elif name == "internal_kernel":
        from python.spike_core.internal_tetra_generation import generate_tetra_mesh
        execute = lambda points: generate_tetra_mesh(points)
        version = "spike-internal-tetra-v1"
    elif name == "internal_fullrun":
        from python.spike_core.internal_meshing_engine import run_internal_meshing
        def execute(points):
            request = {"contract": "spike/internal-mesh-request/v1", "operation": "generate",
                       "parameters": {"points": points, "optimize": False}}
            return run_internal_meshing(request)["candidate"]
        version = "spike/internal-mesh-result/v1"
    elif name == "scipy_qhull":
        import scipy
        from scipy.spatial import Delaunay
        execute = lambda points: {"vertices": points,
                                  "cells": Delaunay(points).simplices.tolist()}
        version = scipy.__version__
    elif name == "gmsh_4_15_2":
        gmsh, load_ns = _load_gmsh()
        init_started = time.perf_counter_ns()
        gmsh.initialize(["gmsh", "-nopopup"], readConfigFiles=False)
        metadata.update(api_load_ns=load_ns,
                        initialize_ns=time.perf_counter_ns() - init_started,
                        scope="Gmsh 4.15.2 raw point-cloud API only; no OCC/CAD generalization",
                        api_index_base=1,
                        steiner_semantics="returned xyz triplets appended after original points")
        if hasattr(gmsh, "algorithm") and hasattr(gmsh.algorithm, "tetrahedralize"):
            tetrahedralize = gmsh.algorithm.tetrahedralize
            metadata["public_api"] = "gmsh.algorithm.tetrahedralize"
        elif hasattr(gmsh.model.mesh, "tetrahedralize"):
            tetrahedralize = gmsh.model.mesh.tetrahedralize
            metadata["public_api"] = "gmsh.model.mesh.tetrahedralize"
        else:
            gmsh.finalize()
            raise RuntimeError("installed Gmsh lacks a public raw tetrahedralize API")
        def execute(points):
            flattened = [coordinate for point in points for coordinate in point]
            tetrahedra, steiner = tetrahedralize(flattened)
            extra = [list(map(float, steiner[index:index + 3]))
                     for index in range(0, len(steiner), 3)]
            raw = list(map(int, tetrahedra))
            return {"vertices": points + extra,
                    "cells": [[raw[index + offset] - 1 for offset in range(4)]
                              for index in range(0, len(raw), 4)]}
        version = "4.15.2-entry-artifact-pin"
        metadata["finalize"] = gmsh.finalize
    else:
        raise ValueError("unknown backend")
    return execute, version, time.perf_counter_ns() - started, metadata


def _normalize_result(raw: dict) -> tuple[list[list[float]], list[list[int]], dict]:
    if "mesh" in raw:
        vertices = raw["mesh"]["vertices"]
        cells = [cell["vertices"] for cell in raw["mesh"]["cells"]]
        snapshot = raw
    else:
        vertices, cells, snapshot = raw["vertices"], raw["cells"], raw
    return vertices, _oriented_cells(vertices, cells), snapshot


def worker(payload: dict) -> dict:
    backend = payload["backend"]
    points = payload["points"]
    samples = payload["samples"]
    warmups = payload["warmups"]
    prepared_at = time.perf_counter_ns()
    execute, version, import_ns, metadata = _prepare_backend(backend)
    after_import_memory = _memory_for_handle()
    timings = []
    private_samples = []
    output_hashes = []
    output_counts = []
    final = None
    try:
        for sample in range(warmups + samples):
            started = time.perf_counter_ns()
            raw = execute(points)
            elapsed = time.perf_counter_ns() - started
            vertices, cells, snapshot = _normalize_result(raw)
            final = {"vertices": vertices, "cells": cells, "snapshot": snapshot}
            memory = _memory_for_handle()
            if memory:
                private_samples.append(memory["current_private_usage_bytes"])
            if sample >= warmups:
                timings.append(elapsed)
                output_hashes.append(_sha_bytes(_canonical(snapshot)))
                output_counts.append({"vertices": len(vertices), "cells": len(cells)})
    finally:
        finalize = metadata.pop("finalize", None)
        if finalize:
            finalize_started = time.perf_counter_ns()
            finalize()
            metadata["finalize_ns"] = time.perf_counter_ns() - finalize_started
    if final is None:
        raise RuntimeError("backend produced no sample")
    memory = _memory_for_handle()
    baseline_private = (after_import_memory or {}).get("current_private_usage_bytes")
    max_sample_private = max(private_samples) if private_samples else None
    memory_evidence = {"after_import": after_import_memory, "after_samples": memory,
                       "max_observed_post_call_current_private_usage_bytes": max_sample_private,
                       "observed_post_call_private_growth_bytes":
                           (max(0, max_sample_private - baseline_private)
                            if max_sample_private is not None and baseline_private is not None else None),
                       "growth_scope": "current-process snapshots immediately after calls; includes retained output and Python bookkeeping; neither peak allocation nor mesh-only usage",
                       "mesh_only_increment_bytes": None,
                       "mesh_only_increment_reason": "GetProcessMemoryInfo exposes process counters, so a mesh-only allocation peak cannot be isolated without allocator instrumentation",
                       "counter_semantics": "PeakWorkingSetSize is peak resident; PeakPagefileUsage is peak pagefile/commit; PrivateUsage is current private usage"}
    return {"status": "completed", "backend": backend, "runtime_version": version,
            "import_and_startup_ns": import_ns, "backend_metadata": metadata,
            "warmups": warmups, "generation_samples_ns": timings,
            "sample_output_sha256": output_hashes,
            "distinct_sample_outputs": len(set(output_hashes)),
            "sample_output_counts": output_counts,
            "generation_median_ns": int(statistics.median(timings)),
            "generation_min_ns": min(timings), "memory": memory_evidence,
            "result": final, "worker_elapsed_ns": time.perf_counter_ns() - prepared_at}


def _isolated(payload: dict, timeout_s: float) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    started = time.perf_counter_ns()
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    captured: dict[str, tuple[str, str] | BaseException] = {}
    def communicate() -> None:
        try:
            captured["io"] = process.communicate(json.dumps(payload, separators=(",", ":")))
        except BaseException as exc:  # surfaced as an explicit failed row
            captured["error"] = exc
    reader = threading.Thread(target=communicate, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_s
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.002)
    if process.poll() is None:
        process.kill()
        reader.join(timeout=5)
        return {"status": "timeout", "timeout_s": timeout_s,
                "isolated_process_elapsed_ns": time.perf_counter_ns() - started}
    reader.join(timeout=5)
    io = captured.get("io")
    if not isinstance(io, tuple):
        return {"status": "failed", "exit_code": process.returncode,
                "error": f"worker pipe failure: {captured.get('error', 'no result')}",
                "isolated_process_elapsed_ns": time.perf_counter_ns() - started}
    stdout, stderr = io
    if process.returncode != 0:
        return {"status": "failed", "exit_code": process.returncode,
                "error": stderr[-4000:] or stdout[-4000:],
                "isolated_process_elapsed_ns": time.perf_counter_ns() - started}
    try:
        lines = [line for line in stdout.splitlines() if line.strip()]
        result = json.loads(lines[-1] if lines else "")
    except json.JSONDecodeError as exc:
        return {"status": "failed", "exit_code": process.returncode,
                "error": f"invalid worker JSON: {exc}; stderr={stderr[-2000:]}",
                "isolated_process_elapsed_ns": time.perf_counter_ns() - started}
    if len(lines) > 1:
        result["worker_stdout"] = "\n".join(lines[:-1])[-4000:]
    result["isolated_process_elapsed_ns"] = time.perf_counter_ns() - started
    return result


def run_benchmark(*, samples: int = 5, warmups: int = 1, timeout_s: float = 60.0,
                  backends: tuple[str, ...] = BACKENDS) -> dict:
    rows = []
    for fixture in fixture_corpus():
        for backend in backends:
            payload = {"backend": backend, "points": fixture["points"],
                       "samples": samples, "warmups": warmups}
            row = {"fixture": fixture["id"], "points_sha256": fixture["points_sha256"],
                   "point_count": len(fixture["points"]), "backend": backend,
                   "expected": fixture["expected"]}
            result = _isolated(payload, timeout_s)
            row.update({key: value for key, value in result.items() if key != "result"})
            if result.get("status") == "completed":
                generated = result["result"]
                row["output_sha256"] = _sha_bytes(_canonical(generated["snapshot"]))
                row["generated_counts"] = {
                    "vertices": len(generated["vertices"]), "cells": len(generated["cells"]),
                    "steiner_vertices": len(generated["vertices"]) - len(fixture["points"]),
                    "used_original_points": len({index for cell in generated["cells"] for index in cell}
                                                & set(range(len(fixture["points"])))),
                }
                try:
                    row["validation"] = validate_tetrahedralization(
                        fixture["points"], generated["vertices"], generated["cells"])
                except Exception as exc:  # failure remains in the report
                    row["validation"] = {"status": "failed", "error": str(exc)}
            rows.append(row)
    successful_expected = [row for row in rows if row["expected"] == "success"]
    internal_rows = [row for row in successful_expected
                     if row["backend"] in ("internal_kernel", "internal_fullrun")]
    internal_passed = bool(internal_rows) and all(
        row.get("status") == "completed" and row.get("validation", {}).get("status") == "passed"
        for row in internal_rows)
    internal_status = "passed" if internal_passed else ("not_run" if not internal_rows else "failed")
    backend_summary = {}
    for backend in backends:
        selected = [row for row in rows if row["backend"] == backend]
        expected_selected = [row for row in selected if row["expected"] == "success"]
        backend_summary[backend] = {
            "cases": len(selected),
            "completed": sum(row.get("status") == "completed" for row in selected),
            "independently_validated": sum(row.get("validation", {}).get("status") == "passed"
                                           for row in selected),
            "reported_failures": sum(row.get("status") != "completed" or
                                     row.get("validation", {}).get("status") == "failed"
                                     for row in selected),
            "expected_success_cases_valid": all(
                row.get("status") == "completed" and
                row.get("validation", {}).get("status") == "passed"
                for row in expected_selected),
        }
    comparison_has_failures = any(not summary["expected_success_cases_valid"]
                                  for summary in backend_summary.values())
    return {"contract": "spike/internal-mesher-benchmark/v1",
            "status": "completed", "internal_status": internal_status,
            "comparison_status": "completed_with_reported_failures" if comparison_has_failures else "passed",
            "production_qualified": False,
            "scope": "convex point-cloud tetra generation and independent geometry audit only",
            "configuration": {"samples": samples, "warmups": warmups,
                              "timeout_s_per_backend_fixture": timeout_s,
                              "backends": list(backends),
                              "timing_boundary": "reported generation samples exclude this harness's independent post-run audit; internal backends still include their mandatory built-in certification and validation, so backend timing boundaries are not identical"},
            "environment": {"platform": platform.platform(), "python": sys.version,
                            "executable": str(Path(sys.executable).resolve()),
                            "processor": platform.processor(), "cpu_count": os.cpu_count()},
            "provenance": {"internal_source": str(INTERNAL_SOURCE.relative_to(ROOT)),
                           "internal_source_sha256": _sha_file(INTERNAL_SOURCE),
                           "benchmark_source": str(BENCHMARK_SOURCE.relative_to(ROOT)),
                           "benchmark_source_sha256": _sha_file(BENCHMARK_SOURCE),
                           "benchmark_test_source": str(BENCHMARK_TEST_SOURCE.relative_to(ROOT)),
                           "benchmark_test_source_sha256": _sha_file(BENCHMARK_TEST_SOURCE),
                           "gmsh_manual": MANUAL_URL, "gmsh_entry_artifact_pins": GMSH_PIN,
                           "third_party_policy": "public APIs only; separately installed; no engine bundling, installation, source or examples"},
            "corpus": fixture_manifest(), "backend_summary": backend_summary, "rows": rows}


def capture_baseline(output: Path) -> Path:
    """Capture immutable pre-optimization outputs plus a 64-point cProfile."""
    output.mkdir(parents=True, exist_ok=True)
    target = output / "baseline-internal-preoptimization.json"
    profile_path = output / "baseline-internal-generic-64.prof"
    profile_text = output / "baseline-internal-generic-64-profile.txt"
    for path in (target, profile_path, profile_text):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite baseline artifact: {path}")
    source_before = _sha_file(INTERNAL_SOURCE)
    from python.spike_core.internal_tetra_generation import generate_tetra_mesh
    from python.spike_core.internal_meshing_engine import run_internal_meshing
    snapshots = []
    for fixture in fixture_corpus():
        item = {"fixture": fixture["id"], "points_sha256": fixture["points_sha256"]}
        for backend in ("kernel", "fullrun_optimize_false"):
            try:
                if backend == "kernel":
                    result = generate_tetra_mesh(fixture["points"])
                else:
                    request = {"contract": "spike/internal-mesh-request/v1", "operation": "generate",
                               "parameters": {"points": fixture["points"], "optimize": False}}
                    result = run_internal_meshing(request)
                item[backend] = {"status": "completed",
                                 "output_sha256": _sha_bytes(_canonical(result)),
                                 "output": result}
            except Exception as exc:
                item[backend] = {"status": "failed", "exception_type": type(exc).__name__,
                                 "error": str(exc),
                                 "failure_sha256": _sha_bytes(_canonical([type(exc).__name__, str(exc)]))}
        snapshots.append(item)
    generic64 = next(item for item in fixture_corpus() if item["id"] == "generic_64")
    profiler = cProfile.Profile()
    profiler.enable()
    generate_tetra_mesh(generic64["points"])
    profiler.disable()
    profiler.dump_stats(profile_path)
    with profile_text.open("w", encoding="utf-8") as stream:
        stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative")
        stats.print_stats(40)
    source_after = _sha_file(INTERNAL_SOURCE)
    if source_after != source_before:
        profile_path.unlink(missing_ok=True)
        profile_text.unlink(missing_ok=True)
        raise RuntimeError("internal mesher source changed during baseline capture")
    payload = {"contract": "spike/internal-mesher-baseline/v1",
               "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "internal_source": str(INTERNAL_SOURCE.relative_to(ROOT)),
               "internal_source_sha256": source_before, "corpus": fixture_manifest(),
               "profile": {"fixture": "generic_64", "format": "cProfile binary plus text top-40 cumulative",
                           "binary": profile_path.name, "text": profile_text.name},
               "snapshots": snapshots}
    target.write_bytes(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False).encode("utf-8"))
    return target


def materialize_baseline_source_from_head(output: Path) -> Path:
    """Recover the captured clean source only when Git HEAD matches its digest."""
    evidence = output / "baseline-internal-preoptimization.json"
    target = output / BASELINE_SOURCE_SNAPSHOT.name
    if target.exists():
        raise FileExistsError(f"refusing to overwrite baseline source artifact: {target}")
    if not evidence.is_file():
        raise FileNotFoundError("baseline evidence is unavailable")
    expected = json.loads(evidence.read_text(encoding="utf-8"))["internal_source_sha256"]
    process = subprocess.run(["git", "show", "HEAD:python/spike_core/internal_tetra_generation.py"],
                             cwd=ROOT, capture_output=True)
    if process.returncode != 0:
        raise RuntimeError("unable to read the clean baseline source from Git HEAD")
    if _sha_bytes(process.stdout) != expected:
        raise RuntimeError("Git HEAD source does not match the pre-optimization baseline digest")
    target.write_bytes(process.stdout)
    return target


def compare_current_to_baseline(output: Path) -> Path:
    """Recompute both internal entry points and require exact baseline parity."""
    baseline_path = output / "baseline-internal-preoptimization.json"
    target = output / "exact-equivalence.json"
    if target.exists():
        raise FileExistsError(f"refusing to overwrite equivalence evidence: {target}")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = {item["fixture"]: item for item in baseline["snapshots"]}
    from python.spike_core.internal_tetra_generation import generate_tetra_mesh
    from python.spike_core.internal_meshing_engine import run_internal_meshing
    rows = []
    for fixture in fixture_corpus():
        for backend in ("kernel", "fullrun_optimize_false"):
            row = {"fixture": fixture["id"], "backend": backend}
            before = expected[fixture["id"]][backend]
            try:
                if backend == "kernel":
                    result = generate_tetra_mesh(fixture["points"])
                else:
                    request = {"contract": "spike/internal-mesh-request/v1",
                               "operation": "generate",
                               "parameters": {"points": fixture["points"], "optimize": False}}
                    result = run_internal_meshing(request)
                digest = _sha_bytes(_canonical(result))
                row.update(current_status="completed", current_output_sha256=digest,
                           baseline_status=before["status"],
                           baseline_output_sha256=before.get("output_sha256"),
                           exact_match=before["status"] == "completed" and
                                       digest == before.get("output_sha256"))
            except Exception as exc:
                row.update(current_status="failed", exception_type=type(exc).__name__,
                           error=str(exc), baseline_status=before["status"],
                           exact_match=before["status"] == "failed" and
                                       type(exc).__name__ == before.get("exception_type") and
                                       str(exc) == before.get("error"))
            rows.append(row)
    passed = all(row["exact_match"] for row in rows)
    payload = {"contract": "spike/internal-mesher-exact-equivalence/v1",
               "status": "passed" if passed else "failed",
               "baseline_source_sha256": baseline["internal_source_sha256"],
               "current_source_sha256": _sha_file(INTERNAL_SOURCE), "rows": rows}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def write_artifact_status(output: Path) -> Path:
    """Mark authoritative evidence without deleting preserved exploratory runs."""
    target = output / "ARTIFACT_STATUS.json"
    if target.exists():
        raise FileExistsError(f"refusing to overwrite artifact status: {target}")
    authoritative_names = [
        "baseline-internal-preoptimization.json", "baseline-internal-generic-64.prof",
        "baseline-internal-generic-64-profile.txt", "baseline-internal_tetra_generation.py",
        "exact-equivalence.json", "authoritative-internal/benchmark.json",
        "authoritative-external/benchmark.json",
    ]
    authoritative = []
    for name in authoritative_names:
        path = output / name
        if not path.is_file():
            raise FileNotFoundError(f"authoritative artifact is unavailable: {name}")
        authoritative.append({"path": name, "sha256": _sha_file(path), "bytes": path.stat().st_size})
    payload = {
        "contract": "spike/internal-mesher-artifact-status/v1",
        "authoritative": authoritative,
        "superseded_preserved": [
            {"path": "benchmark.json", "reason": "exploratory run used obsolete parent-process startup memory polling and old summary semantics"},
            {"path": "before-after/benchmark.json", "reason": "provisional performance run before the clean serial slot"},
            {"path": "final-before-after/benchmark.json", "reason": "timings are clean, but rows retain obsolete parent-process startup memory polling"},
            {"path": "final-external/benchmark.json", "reason": "provisional external run without explicit returned counts"},
            {"path": "final-external-v2/benchmark.json", "reason": "returned-count diagnostic overlapped another performance run"},
        ],
        "memory_policy": "Use worker memory.after_samples only: PeakWorkingSetSize is process peak resident, PeakPagefileUsage is process peak pagefile/commit, and PrivateUsage is current private commit. Mesh-only peak is unavailable.",
        "gmsh_scope": "Findings apply only to the pinned Gmsh 4.15.2 raw point-cloud tetrahedralize API calls in authoritative-external; they do not characterize OCC/CAD Gmsh meshing.",
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples", type=int, choices=(3, 5), default=5)
    parser.add_argument("--warmups", type=int, choices=range(0, 4), default=1)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--backends", nargs="+", choices=ALL_BACKENDS, default=list(BACKENDS))
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--materialize-baseline-source-from-head", action="store_true")
    parser.add_argument("--compare-baseline", action="store_true")
    parser.add_argument("--write-artifact-status", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(worker(json.load(sys.stdin)), separators=(",", ":"), allow_nan=False))
            return 0
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 2
    if not 1.0 <= args.timeout_s <= 300.0:
        parser.error("timeout must be between 1 and 300 seconds")
    if args.baseline:
        path = capture_baseline(args.output)
        print(path)
        return 0
    if args.materialize_baseline_source_from_head:
        path = materialize_baseline_source_from_head(args.output)
        print(path)
        return 0
    if args.compare_baseline:
        path = compare_current_to_baseline(args.output)
        print(path)
        return 0
    if args.write_artifact_status:
        path = write_artifact_status(args.output)
        print(path)
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "benchmark.json"
    if target.exists():
        raise FileExistsError(f"refusing to overwrite benchmark artifact: {target}")
    result = run_benchmark(samples=args.samples, warmups=args.warmups,
                           timeout_s=args.timeout_s, backends=tuple(args.backends))
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(target)
    return 0 if result["status"] == "completed" and result["internal_status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(_main())
