# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Benchmark exact hybrid PCB meshing and a separate Gmsh OCC volume task.

The internal comparison uses a retained Arduino KiCad board.  The legacy row
patches only the pre-optimization point/polygon predicate.  The Gmsh row uses
an actual retained PCB conductor-volume request, but is deliberately reported
as a separate CAD-tetrahedralization task because its output is not the hybrid
electrical graph and cannot support a faster/slower winner claim.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from ctypes import wintypes
import ctypes
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import sysconfig
import tempfile
import time
import traceback
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_BOARD = ROOT / "output/arduino-em-20261011/prepared-final/shield/shield-source.kicad_pcb"
DEFAULT_GMSH_REQUEST = ROOT / "output/arduino-em-20261011/prepared-v3/shield/occ-priority-mesh/request.json"
DEFAULT_OUTPUT = ROOT / "output/pcb-mesher-benchmark-20261012"
DEFAULT_GMSH_PYTHON = Path.home() / "AppData/Local/Programs/Python/Python311/python.exe"
_REFERENCE_DISTANCE = None
_REFERENCE_SEGMENTS = None


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _legacy_point_in_polygon(point, polygon, tolerance=0.0):
    """Unmodified predicate from before the bounded edge rejection."""

    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (
                (previous[1] - current[1]) or 1e-15
            ) + current[0]
            if x < crossing:
                inside = not inside
        previous = current
    if inside:
        return True

    return bool(tolerance and any(
        _REFERENCE_DISTANCE(point, a, b) <= tolerance for a, b in _REFERENCE_SEGMENTS(polygon)
    ))


def _current_memory() -> dict[str, int] | None:
    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return None
    return {
        "current_working_set_bytes": int(counters.WorkingSetSize),
        "os_reported_peak_working_set_bytes": int(counters.PeakWorkingSetSize),
        "current_private_usage_bytes": int(counters.PrivateUsage),
        "os_reported_peak_pagefile_usage_bytes": int(counters.PeakPagefileUsage),
    }


def _mesh_summary(mesh) -> dict[str, object]:
    encoded = _canonical(asdict(mesh))
    return {
        "mesh_sha256": _sha_bytes(encoded),
        "nodes": len(mesh.nodes),
        "branches": len(mesh.branches),
        "cells": len(mesh.cells),
        "geometry_counts": mesh.geometry_counts,
        "truncated": mesh.truncated,
        "issues_sha256": _sha_bytes(_canonical([asdict(issue) for issue in mesh.issues])),
        "source_ids_sha256": _sha_bytes(_canonical(sorted({
            str(cell.get("source_id", "")) for cell in mesh.cells
        }))),
        "net_layers_sha256": _sha_bytes(_canonical(sorted({
            (node.net, node.layer) for node in mesh.nodes
        }))),
    }


def _internal_worker(payload: dict[str, object]) -> dict[str, object]:
    global _REFERENCE_DISTANCE, _REFERENCE_SEGMENTS
    from python.spike_core.contracts import AnalysisSpec
    from python.spike_core.hybrid_mesh import _distance_to_segment, _segments, build_hybrid_mesh
    from python.spike_core.kicad_importer import import_kicad_design

    # Bind the legacy predicate's unchanged helpers once before timed work.
    # Repeating import statements inside every point query would unfairly add
    # Python lookup overhead to the reference algorithm.
    _REFERENCE_DISTANCE = _distance_to_segment
    _REFERENCE_SEGMENTS = _segments

    board = Path(str(payload["board"])).resolve()
    algorithm = str(payload["algorithm"])
    instances = int(payload["instances"])
    samples = int(payload["samples"])
    warmups = int(payload["warmups"])
    design = import_kicad_design(str(board))
    spec = AnalysisSpec(
        mode="dc", net_names=[str(payload["net"])],
        mesh={
            "target_size_mm": float(payload["target_size_mm"]),
            "zone_cell_mm": float(payload["zone_cell_mm"]),
            "max_zone_cells": int(payload["max_zone_cells"]),
            "max_conductors": int(payload["max_conductors"]),
            "memory_budget_mb": int(payload["memory_budget_mb"]),
        },
    )
    context = (
        patch("python.spike_core.hybrid_mesh._point_in_polygon", _legacy_point_in_polygon)
        if algorithm == "legacy_reference" else nullcontext()
    )
    timings = []
    final_meshes = []
    with context:
        for sample in range(warmups + samples):
            started = time.perf_counter_ns()
            meshes = [build_hybrid_mesh(design, spec) for _ in range(instances)]
            elapsed = time.perf_counter_ns() - started
            if sample >= warmups:
                timings.append(elapsed)
                final_meshes = meshes
    summaries = [_mesh_summary(mesh) for mesh in final_meshes]
    first = summaries[0]
    if any(item != first for item in summaries[1:]):
        raise AssertionError("equivalent assembly instances produced different meshes")
    return {
        "status": "completed",
        "task": "internal_hybrid_electrical_graph",
        "algorithm": algorithm,
        "instances": instances,
        "unified_contacts": False,
        "assembly_interpretation": "independent equivalent PCB instances; no cross-instance contacts",
        "samples_ns": timings,
        "median_ns": int(statistics.median(timings)),
        "per_instance_median_ns": int(statistics.median(timings) / instances),
        "mesh": first,
        "combined_mesh_sha256": _sha_bytes(_canonical(summaries)),
        "aggregate_counts": {
            key: int(first[key]) * instances for key in ("nodes", "branches", "cells")
        },
        "memory_after_samples": _current_memory(),
        "fixture": {
            "path": _display_path(board), "sha256": _sha_file(board),
            "import_counts": {key: len(getattr(design, key)) for key in ("tracks", "zones", "vias", "pads")},
        },
    }


def _gmsh_worker(payload: dict[str, object]) -> dict[str, object]:
    from python.spike_core.gmsh_occ_runtime import run_occ_case

    request_path = Path(str(payload["request"])).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    original_count = len(request["solids"])
    solid_limit = int(payload["solid_limit"])
    metadata = request.get("object_metadata", {})
    copper = [
        solid for solid in request["solids"]
        if metadata.get(str(solid.get("id")), {}).get("kind") != "board_layer"
    ]
    request["solids"] = copper[:solid_limit]
    selected_ids = {str(solid["id"]) for solid in request["solids"]}
    request["object_metadata"] = {
        key: value for key, value in metadata.items() if key in selected_ids
    }
    if isinstance(request.get("focus"), dict):
        request["focus"]["source_ids"] = [str(request["solids"][0]["id"])]
        request["focus"]["net_names"] = []
    output = Path(str(payload["case_output"])).resolve()
    started = time.perf_counter_ns()
    result = run_occ_case(
        request, output, timeout_s=int(payload["timeout_s"]),
        memory_limit_mb=int(payload["memory_budget_mb"]),
    )
    elapsed = time.perf_counter_ns() - started
    return {
        "status": "completed",
        "task": "gmsh_occ_pcb_conductor_volume_tetrahedralization",
        "semantically_comparable_to_internal_hybrid_graph": False,
        "winner_eligible": False,
        "elapsed_ns": elapsed,
        "fixture": {
            "path": _display_path(request_path), "sha256": _sha_file(request_path),
            "original_solids": original_count, "retained_prefix_solids": len(request["solids"]),
            "retained_request_sha256": _sha_bytes(_canonical(request)),
        },
        "result": {
            "contract": result.get("contract"), "status": result.get("status"),
            "counts": result.get("mesh", {}).get("counts"),
            "metrics": result.get("metrics"),
            "request_sha256": result.get("request_sha256"),
        },
        "wrapper_memory_after_nested_worker": _current_memory(),
        "mesher_process_memory": None,
        "mesher_process_memory_limitation": (
            "The pinned runtime owns a nested resource-limited process; this harness records "
            "wrapper counters only and does not infer the nested mesher's peak memory."
        ),
    }


def worker(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("backend") == "internal":
        return _internal_worker(payload)
    if payload.get("backend") == "gmsh_occ":
        return _gmsh_worker(payload)
    raise ValueError("unknown benchmark backend")


def _process_memory(process: subprocess.Popen[str]) -> dict[str, int] | None:
    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(
        wintypes.HANDLE(process._handle), ctypes.byref(counters), counters.cb
    ):
        return None
    return {
        "current_working_set_bytes": int(counters.WorkingSetSize),
        "os_reported_peak_working_set_bytes": int(counters.PeakWorkingSetSize),
        "current_private_usage_bytes": int(counters.PrivateUsage),
        "os_reported_peak_pagefile_usage_bytes": int(counters.PeakPagefileUsage),
    }


def _isolated(payload: dict[str, object], timeout_s: float, executable: Path | None = None) -> dict[str, object]:
    # The Windows venv executable can act as a short-lived redirector, making
    # its process counters unrelated to the real worker. Launch the trusted
    # base interpreter directly so sampled current/peak counters cover the
    # process that imports and meshes the board.
    worker_python = executable or Path(getattr(sys, "_base_executable", sys.executable))
    command = [str(worker_python), str(Path(__file__).resolve()), "--worker"]
    worker_environment = os.environ.copy()
    if executable is None and worker_python != Path(sys.executable):
        packages = str(Path(sysconfig.get_path("purelib")).resolve())
        existing = worker_environment.get("PYTHONPATH", "")
        worker_environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (packages, existing) if item
        )
    started = time.perf_counter_ns()
    stdout_file = tempfile.TemporaryFile()
    stderr_file = tempfile.TemporaryFile()
    process = subprocess.Popen(
        command, cwd=ROOT, stdin=subprocess.PIPE, stdout=stdout_file,
        stderr=stderr_file, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=worker_environment,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    process.stdin.close()
    samples = []
    deadline = time.monotonic() + timeout_s
    while process.poll() is None and time.monotonic() < deadline:
        memory = _process_memory(process)
        if memory:
            samples.append(memory)
        time.sleep(0.005)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
        stdout_file.close()
        stderr_file.close()
        return {"status": "timeout", "timeout_s": timeout_s}
    stdout_file.seek(0)
    stderr_file.seek(0)
    stdout = stdout_file.read().decode("utf-8", errors="replace")
    stderr = stderr_file.read().decode("utf-8", errors="replace")
    stdout_file.close()
    stderr_file.close()
    memory = _process_memory(process)
    if memory:
        samples.append(memory)
    observed = None
    if samples:
        memory_scope = (
            "entire isolated internal worker including interpreter, imports, board import, and meshing"
            if payload.get("backend") == "internal"
            else "benchmark wrapper process; nested Gmsh worker memory is excluded"
        )
        observed = {
            "sampled_peak_current_working_set_bytes": max(x["current_working_set_bytes"] for x in samples),
            "sampled_peak_current_private_usage_bytes": max(x["current_private_usage_bytes"] for x in samples),
            "os_reported_peak_working_set_bytes": max(x["os_reported_peak_working_set_bytes"] for x in samples),
            "os_reported_peak_pagefile_usage_bytes": max(x["os_reported_peak_pagefile_usage_bytes"] for x in samples),
            "scope": memory_scope,
        }
    if process.returncode != 0:
        return {
            "status": "failed", "exit_code": process.returncode,
            "error": (stderr or stdout)[-4000:], "process_memory": observed,
            "wall_elapsed_ns": time.perf_counter_ns() - started,
        }
    result = json.loads(stdout)
    result["process_memory"] = observed
    result["wall_elapsed_ns"] = time.perf_counter_ns() - started
    return result


def _internal_payload(args, algorithm: str, instances: int, samples: int, warmups: int) -> dict[str, object]:
    return {
        "backend": "internal", "algorithm": algorithm, "board": str(args.board.resolve()),
        "net": args.net, "instances": instances, "samples": samples, "warmups": warmups,
        "target_size_mm": args.target_size_mm, "zone_cell_mm": args.zone_cell_mm,
        "max_zone_cells": args.max_zone_cells, "max_conductors": args.max_conductors,
        "memory_budget_mb": args.memory_budget_mb,
    }


def benchmark(args) -> dict[str, object]:
    mesher_source = ROOT / "python/spike_core/hybrid_mesh.py"
    source_before = _sha_file(mesher_source)
    rows = []
    for algorithm in ("legacy_reference", "bounded_edge_rejection"):
        cold = [
            _isolated(_internal_payload(args, algorithm, 1, 1, 0), args.timeout_s)
            for _ in range(args.samples)
        ]
        warm = _isolated(
            _internal_payload(args, algorithm, 1, args.samples, args.warmups), args.timeout_s
        )
        rows.append({"algorithm": algorithm, "cold_processes": cold, "warm_process": warm})
    reference = rows[0]["warm_process"]
    optimized = rows[1]["warm_process"]
    exact = (
        reference.get("status") == optimized.get("status") == "completed"
        and reference.get("mesh") == optimized.get("mesh")
        and not reference.get("mesh", {}).get("truncated", True)
        and not optimized.get("mesh", {}).get("truncated", True)
    )
    assembly = [
        _isolated(_internal_payload(args, "bounded_edge_rejection", count, 1, 0),
                  args.timeout_s * count)
        for count in (10, 20)
    ]
    gmsh_payload = {
        "backend": "gmsh_occ", "request": str(args.gmsh_request.resolve()),
        "solid_limit": args.gmsh_solid_limit,
        "case_output": str((args.output / "gmsh-occ-case").resolve()),
        "timeout_s": int(args.gmsh_timeout_s), "memory_budget_mb": args.memory_budget_mb,
    }
    gmsh = _isolated(gmsh_payload, args.gmsh_timeout_s + 30, args.gmsh_python)
    source_after = _sha_file(mesher_source)
    if source_after != source_before:
        raise RuntimeError("hybrid mesher source changed during benchmark")
    legacy_warm_ns = int(reference["median_ns"]) if reference.get("status") == "completed" else None
    optimized_warm_ns = int(optimized["median_ns"]) if optimized.get("status") == "completed" else None
    legacy_cold_ns = [int(item["wall_elapsed_ns"]) for item in rows[0]["cold_processes"]
                      if item.get("status") == "completed"]
    optimized_cold_ns = [int(item["wall_elapsed_ns"]) for item in rows[1]["cold_processes"]
                         if item.get("status") == "completed"]
    internal_passed = exact and all(
        item.get("status") == "completed"
        for row in rows for item in [*row["cold_processes"], row["warm_process"]]
    ) and all(item.get("status") == "completed" for item in assembly)
    return {
        "contract": "spike/pcb-mesher-benchmark/v1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if internal_passed and gmsh.get("status") == "completed" else "failed",
        "host": {"python": sys.version, "executable": sys.executable, "platform": sys.platform},
        "hybrid_mesher_source_sha256": source_before,
        "settings": {
            "samples": args.samples, "warmups": args.warmups, "net": args.net,
            "target_size_mm": args.target_size_mm, "zone_cell_mm": args.zone_cell_mm,
            "max_zone_cells": args.max_zone_cells, "memory_budget_mb": args.memory_budget_mb,
        },
        "internal_equivalence": {
            "exact_complete_mesh": exact,
            "summary": {
                "legacy_warm_median_ns": legacy_warm_ns,
                "optimized_warm_median_ns": optimized_warm_ns,
                "warm_speedup": (legacy_warm_ns / optimized_warm_ns
                                   if legacy_warm_ns and optimized_warm_ns else None),
                "legacy_cold_wall_median_ns": (int(statistics.median(legacy_cold_ns))
                                                 if legacy_cold_ns else None),
                "optimized_cold_wall_median_ns": (int(statistics.median(optimized_cold_ns))
                                                    if optimized_cold_ns else None),
                "cold_wall_speedup": (
                    statistics.median(legacy_cold_ns) / statistics.median(optimized_cold_ns)
                    if legacy_cold_ns and optimized_cold_ns else None
                ),
            },
            "rows": rows,
        },
        "real_assembly_repetitions": assembly,
        "gmsh_separate_task": gmsh,
        "comparison_boundary": (
            "Internal rows produce resistor-graph conductors; Gmsh produces tetrahedra from a "
            "retained prefix of actual PCB conductor volumes. No cross-task winner is reported."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--gmsh-request", type=Path, default=DEFAULT_GMSH_REQUEST)
    parser.add_argument("--gmsh-python", type=Path,
                        default=DEFAULT_GMSH_PYTHON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--net", default="GND")
    parser.add_argument("--samples", type=int, choices=(3, 5), default=3)
    parser.add_argument("--warmups", type=int, choices=range(0, 4), default=1)
    parser.add_argument("--target-size-mm", type=float, default=1.0)
    parser.add_argument("--zone-cell-mm", type=float, default=0.5)
    parser.add_argument("--max-zone-cells", type=int, default=3000)
    parser.add_argument("--max-conductors", type=int, default=100000)
    parser.add_argument("--memory-budget-mb", type=int, default=2048)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--gmsh-timeout-s", type=float, default=180.0)
    parser.add_argument("--gmsh-solid-limit", type=int, default=8)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(worker(json.load(sys.stdin)), separators=(",", ":"), allow_nan=False))
            return 0
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 2
    if not args.board.is_file() or not args.gmsh_request.is_file() or not args.gmsh_python.is_file():
        parser.error("board, Gmsh request, and CPython 3.11 paths must exist")
    positive_floats = (
        args.target_size_mm, args.zone_cell_mm, args.timeout_s, args.gmsh_timeout_s,
    )
    if any(not math.isfinite(value) or value <= 0.0 for value in positive_floats):
        parser.error("mesh sizes and timeouts must be finite and positive")
    if any(value <= 0 for value in (
        args.max_zone_cells, args.max_conductors, args.memory_budget_mb, args.gmsh_solid_limit,
    )):
        parser.error("resource limits and Gmsh solid count must be positive")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite benchmark directory: {args.output}")
    args.output.mkdir(parents=True)
    result = benchmark(args)
    target = args.output / "benchmark.json"
    target.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(target)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
