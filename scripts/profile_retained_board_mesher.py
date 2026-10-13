# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Diagnose the internal hybrid mesher on a pinned retained Marble board.

The controller runs one isolated worker under finite wall-time and OS memory
limits. Import and meshing remain unprofiled; optional faulthandler sampling
records active Python stacks every five seconds during meshing. A durable,
bounded heartbeat records the worker's own Windows process-memory counters.
The worker receives the
complete imported board; net selection is performed only by AnalysisSpec.
"""
from __future__ import annotations

import argparse
from ctypes import wintypes
import ctypes
from dataclasses import asdict
import faulthandler
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_BOARD = (
    ROOT / "build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb"
)
PINNED_BOARD_SHA256 = "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"
MESHER_SOURCE = ROOT / "python/spike_core/hybrid_mesh.py"
RUNTIME_SOURCES = (
    MESHER_SOURCE,
    ROOT / "python/spike_core/filled_copper_path.py",
    ROOT / "python/spike_core/boundary_spatial_index.py",
    ROOT / "python/spike_core/hybrid_owned_copper.py",
    ROOT / "python/spike_core/planar_polygon_topology.py",
    ROOT / "python/spike_core/source_filled_boundary.py",
    ROOT / "python/spike_core/kicad_importer.py",
    ROOT / "python/spike_core/zone_pad_connection_evidence.py",
    ROOT / "python/core/board_parser.py",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_source_hashes() -> dict[str, str]:
    return {_display_path(path).replace("\\", "/"): _sha_file(path) for path in RUNTIME_SOURCES}


def _python_runtime() -> dict[str, object]:
    return {
        "executable": str(Path(sys.executable).resolve(strict=False)),
        "version": sys.version,
        "version_info": list(sys.version_info[:5]),
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "platform": sys.platform,
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _current_memory() -> dict[str, int] | None:
    """Return correctly labelled counters for this process on Windows."""

    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
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


def _stack_summary(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {
            "sample_count": 0, "leaf_frame_counts": [], "inclusive_frame_counts": [],
            "raw_log_bytes": 0, "raw_log_sha256": None,
        }
    encoded = path.read_bytes()
    text = encoded.decode("utf-8", errors="replace")
    samples: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("Timeout ("):
            if current:
                samples.append(current)
            current = []
        elif line.lstrip().startswith('File "'):
            current.append(line.strip())
    if current:
        samples.append(current)
    leaf: dict[str, int] = {}
    inclusive: dict[str, int] = {}
    for frames in samples:
        if frames:
            leaf[frames[0]] = leaf.get(frames[0], 0) + 1
        for frame in set(frames):
            inclusive[frame] = inclusive.get(frame, 0) + 1

    def top(values: dict[str, int]) -> list[dict[str, object]]:
        return [
            {"frame": frame, "samples": count}
            for frame, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:15]
        ]

    return {
        "sample_count": len(samples),
        "interval_s": 5,
        "interpretation": (
            "Periodic wall-stack occupancy, not a CPU-time profile; native calls that hold "
            "the GIL may be under-observed."
        ),
        "leaf_frame_counts": top(leaf),
        "inclusive_frame_counts": top(inclusive),
        "raw_log_bytes": len(encoded),
        "raw_log_sha256": _sha_bytes(encoded),
    }


def _requested_geometry(design: object, net: str) -> tuple[dict[str, int], dict[str, set[str]]]:
    counts: dict[str, int] = {}
    identifiers: dict[str, set[str]] = {}
    for plural, singular in (("tracks", "track"), ("zones", "zone"),
                             ("vias", "via"), ("pads", "pad")):
        selected = [
            item for item in getattr(design, plural)
            if str(item.get("net_name") or item.get("net") or "") == net
        ]
        counts[singular] = len(selected)
        identifiers[singular] = {str(item.get("id", "")) for item in selected}
    return counts, identifiers


def _mesh_hashes(mesh: object) -> dict[str, str]:
    complete = asdict(mesh)
    topology = {
        "nodes": complete["nodes"],
        "branches": complete["branches"],
        "cells": complete["cells"],
        "geometry_counts": complete["geometry_counts"],
        "truncated": complete["truncated"],
    }
    connectivity = {
        "nodes": [
            (node.id, node.x_mm, node.y_mm, node.z_mm, node.layer, node.net)
            for node in mesh.nodes
        ],
        "branches": [
            (branch.id, branch.node_p, branch.node_n, branch.kind, branch.net,
             branch.layer, branch.source_id)
            for branch in mesh.branches
        ],
    }
    return {
        "complete_mesh_sha256": _sha_bytes(_canonical(complete)),
        "topology_and_cells_sha256": _sha_bytes(_canonical(topology)),
        "node_branch_connectivity_sha256": _sha_bytes(_canonical(connectivity)),
    }


def _write_phase_marker(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, allow_nan=False))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_new_text(path: Path, value: str) -> None:
    """Durably create evidence without replacing an existing path."""

    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _evidence_sidecars(output: Path) -> tuple[Path, Path, Path]:
    return (
        output.with_name(f"{output.stem}.phase.json"),
        output.with_name(f"{output.stem}.mesh-wall-stacks.log"),
        output.with_name(f"{output.stem}.selected-zone-polygons.json"),
    )


def _memory_heartbeat_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}.mesh-memory-heartbeat.json")


def _memory_heartbeat_payload(
    sample_count: int, memory: dict[str, int] | None, active_phase: str,
) -> dict[str, object]:
    return {
        "contract": "spike/retained-board-worker-memory-heartbeat/v1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "active_phase": active_phase,
        "sample_count": sample_count,
        "worker_process_memory": memory,
        "scope": (
            "GetProcessMemoryInfo counters from the actual isolated worker; "
            "OS peak counters are cumulative from worker start"
        ),
    }


def _require_repo_output(output: Path) -> Path:
    resolved = output.resolve(strict=False)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("output evidence must be written under the repository root") from error
    return resolved


def _missing_issue_matches(
    missing_ids: dict[str, list[str]], issues: list[dict[str, object]],
) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {
        kind: {
            source_id: [
                issue for issue in issues
                if source_id in str(issue.get("message", ""))
                or source_id in str(issue.get("path", ""))
            ]
            for source_id in identifiers
        }
        for kind, identifiers in missing_ids.items()
    }


def _zone_pad_connection_evidence_summary(
    report: dict[str, object],
) -> dict[str, object]:
    if not report:
        return {}
    records = report.get("records", [])
    if not isinstance(records, list):
        raise ValueError("zone-pad connection evidence records must be a list")
    return {
        **{key: value for key, value in report.items() if key != "records"},
        "record_count": len(records),
        "records_sha256": _sha_bytes(_canonical(records)),
        "full_report_sha256": _sha_bytes(_canonical(report)),
        "digest_encoding": "sorted compact finite JSON (UTF-8, ASCII escaped)",
    }


def _worker(payload: dict[str, object]) -> dict[str, object]:
    from python.spike_core.contracts import AnalysisSpec
    from python.spike_core.hybrid_mesh import _point, build_hybrid_mesh
    from python.spike_core.kicad_importer import import_kicad_design

    board = Path(str(payload["board"])).absolute()
    if not board.is_file():
        raise ValueError("staged board must be an existing regular file")
    expected_sha256 = str(payload["expected_board_sha256"])
    actual_sha256 = _sha_file(board)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"board SHA-256 {actual_sha256} does not match expected {expected_sha256}"
        )
    net = str(payload["net"])
    runtime_sources_before = _runtime_source_hashes()
    mesher_before = runtime_sources_before["python/spike_core/hybrid_mesh.py"]
    import_started = time.perf_counter_ns()
    design = import_kicad_design(str(board))
    import_elapsed_ns = time.perf_counter_ns() - import_started
    memory_after_import = _current_memory()
    marker = Path(str(payload["phase_marker"])).absolute()
    _write_phase_marker(marker, {
        "completed_phase": "import",
        "import_elapsed_ns": import_elapsed_ns,
        "memory_after_import": memory_after_import,
    })
    requested_counts, requested_ids = _requested_geometry(design, net)
    if not sum(requested_counts.values()):
        raise ValueError(f"selected net {net!r} has no imported conductor geometry")
    selected_zone_polygons = []
    for index, zone in enumerate(design.zones):
        if str(zone.get("net_name") or zone.get("net") or "") != net:
            continue
        points = [[float(x), float(y)] for x, y in (
            _point(value) for value in zone.get("points", [])
        )]
        selected_zone_polygons.append({
            "source_id": str(zone.get("id", f"zone-{index + 1}")),
            "layer": str(zone.get("layer", "")),
            "net": net,
            "importer_normalized_filled_polygon_points_mm": points,
            "points_sha256": _sha_bytes(_canonical(points)),
        })
    zone_polygon_path = Path(str(payload["selected_zone_polygons"])).absolute()
    _write_new_text(zone_polygon_path, json.dumps({
        "contract": "spike/retained-board-selected-zone-polygons/v1",
        "fixture": {
            "source_sha256": expected_sha256,
            "staged_copy_sha256": actual_sha256,
            "license_scope": (
                "BerkeleyLab Marble v1.4.4 retained upstream checkout; CERN-OHL-1.2"
            ),
        },
        "selection": {
            "net": net,
            "zone_count": len(selected_zone_polygons),
            "coordinate_semantics": (
                "Importer-normalized filled-zone coordinates supplied as input to "
                "_normalize_filled_zone_polygon; no design filtering or mutation."
            ),
            "zones": selected_zone_polygons,
        },
    }, indent=2, allow_nan=False) + "\n")
    spec = AnalysisSpec(
        mode="dc",
        net_names=[net],
        mesh={
            "target_size_mm": float(payload["target_size_mm"]),
            "zone_cell_mm": float(payload["zone_cell_mm"]),
            "max_zone_cells": int(payload["max_zone_cells"]),
            "max_pad_cells": int(payload["max_pad_cells"]),
            "max_conductors": int(payload["max_conductors"]),
            "solver_memory_limit_gb": float(payload["solver_memory_limit_gb"]),
        },
    )
    stack_log = Path(str(payload["stack_log"])).absolute()
    memory_heartbeat = Path(str(payload.get(
        "memory_heartbeat",
        marker.with_name(f"{marker.stem}.mesh-memory-heartbeat.json"),
    ))).absolute()
    faulthandler_enabled = bool(payload.get("faulthandler_enabled", True))
    _write_phase_marker(marker, {
        "completed_phase": "import",
        "active_phase": "mesh",
        "import_elapsed_ns": import_elapsed_ns,
        "memory_after_import": memory_after_import,
    })
    mesh_started = time.perf_counter_ns()
    heartbeat_state = {"sample_count": 1}
    _write_phase_marker(memory_heartbeat, _memory_heartbeat_payload(
        heartbeat_state["sample_count"], _current_memory(), "mesh",
    ))
    heartbeat_stop = threading.Event()

    def heartbeat() -> None:
        while not heartbeat_stop.wait(5.0):
            heartbeat_state["sample_count"] += 1
            _write_phase_marker(memory_heartbeat, _memory_heartbeat_payload(
                heartbeat_state["sample_count"], _current_memory(), "mesh",
            ))

    heartbeat_thread = threading.Thread(
        target=heartbeat, name="retained-board-memory-heartbeat", daemon=True,
    )
    heartbeat_thread.start()
    with stack_log.open("x", encoding="utf-8", buffering=1) as stack_stream:
        if faulthandler_enabled:
            faulthandler.dump_traceback_later(5, repeat=True, file=stack_stream)
        try:
            mesh = build_hybrid_mesh(design, spec)
        finally:
            if faulthandler_enabled:
                faulthandler.cancel_dump_traceback_later()
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)
    mesh_elapsed_ns = time.perf_counter_ns() - mesh_started
    stack_profile = _stack_summary(stack_log)
    memory_after_mesh = _current_memory()
    heartbeat_state["sample_count"] += 1
    _write_phase_marker(memory_heartbeat, _memory_heartbeat_payload(
        heartbeat_state["sample_count"], memory_after_mesh, "mesh_completed",
    ))
    runtime_sources_after = _runtime_source_hashes()
    _write_phase_marker(marker, {
        "completed_phase": "mesh",
        "import_elapsed_ns": import_elapsed_ns,
        "mesh_elapsed_ns": mesh_elapsed_ns,
        "memory_after_import": memory_after_import,
        "memory_after_mesh": memory_after_mesh,
        "wall_stack_profile": stack_profile,
        "runtime_sources_before_sha256": runtime_sources_before,
        "runtime_sources_after_sha256": runtime_sources_after,
    })
    if runtime_sources_after != runtime_sources_before:
        raise RuntimeError("mesher/import runtime sources changed during the profile")

    represented_ids = {
        str(branch.source_id) for branch in mesh.branches if str(branch.source_id)
    } | {
        str(cell.get("source_id", "")) for cell in mesh.cells if str(cell.get("source_id", ""))
    }
    missing_ids = {
        kind: sorted(identifiers - represented_ids)
        for kind, identifiers in requested_ids.items()
        if identifiers - represented_ids
    }
    issues = [asdict(issue) for issue in mesh.issues]
    errors = [issue for issue in issues if issue["severity"] == "error"]
    geometry_complete = dict(mesh.geometry_counts) == requested_counts and not missing_ids
    complete = geometry_complete and not mesh.truncated and not errors
    return {
        "status": "completed" if complete else "failed",
        "fixture": {
            "path": str(payload["source_board_display"]),
            "bytes": board.stat().st_size,
            "source_sha256": expected_sha256,
            "staged_copy_sha256": actual_sha256,
            "staged_copy_basename": board.name,
            "worker_input": "temporary exact-byte copy under repository root",
            "license_scope": "BerkeleyLab Marble v1.4.4 retained upstream checkout; CERN-OHL-1.2",
        },
        "selection": {
            "net": net,
            "full_imported_board_passed_to_mesher": True,
            "design_filtered_before_meshing": False,
            "requested_geometry_counts": requested_counts,
            "meshed_geometry_counts": dict(mesh.geometry_counts),
            "all_requested_geometry_represented": geometry_complete,
            "missing_requested_source_ids": missing_ids,
            "missing_requested_source_issue_matches": _missing_issue_matches(
                missing_ids, issues,
            ),
        },
        "mesh": {
            "nodes": len(mesh.nodes),
            "branches": len(mesh.branches),
            "cells": len(mesh.cells),
            "truncated": mesh.truncated,
            "issues": issues,
            "error_issues": errors,
            "all_issue_codes": [issue.code for issue in mesh.issues],
            "branch_admission": mesh.branch_admission,
            "zone_pad_connection_evidence": (
                _zone_pad_connection_evidence_summary(
                    mesh.zone_pad_connection_evidence
                )
            ),
            **_mesh_hashes(mesh),
        },
        "timing": {
            "unprofiled_import_elapsed_ns": import_elapsed_ns,
            "unprofiled_mesh_elapsed_ns": mesh_elapsed_ns,
        },
        "profile": {
            "faulthandler_enabled": faulthandler_enabled,
            "mesh_wall_stacks": stack_profile,
        },
        "memory": {
            "after_import": memory_after_import,
            "after_mesh": memory_after_mesh,
            "scope": (
                "actual isolated worker; OS peak counters are cumulative from worker start "
                "through the named stage"
            ),
        },
        "hybrid_mesher_source_sha256": mesher_before,
        "worker_python_runtime": _python_runtime(),
        "runtime_sources_before_sha256": runtime_sources_before,
        "runtime_sources_after_sha256": runtime_sources_after,
    }


def _git_head() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        timeout=10, check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 else None


def _controller(args: argparse.Namespace) -> dict[str, object]:
    from python.spike_core.sparselizard_process import (
        SparseLizardAdapterError,
        run_adapter_process,
    )

    # Avoid realpath traversal of the managed build/ fixture tree. The caller
    # has already required a regular file, and hashing the opened bytes binds
    # the source identity before it is copied into the supervised workspace.
    source_board = args.board.absolute()
    output = _require_repo_output(args.output)
    marker, stack_log, selected_zone_polygons = _evidence_sidecars(output)
    memory_heartbeat = _memory_heartbeat_path(output)
    for path in (
        output, marker, stack_log, selected_zone_polygons, memory_heartbeat,
        marker.with_suffix(marker.suffix + ".tmp"),
        memory_heartbeat.with_suffix(memory_heartbeat.suffix + ".tmp"),
    ):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing evidence: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_new_text(marker, json.dumps({
        "completed_phase": "controller_started",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, allow_nan=False))
    source_sha256 = _sha_file(source_board)
    if source_sha256 != args.expected_board_sha256:
        raise ValueError(
            f"board SHA-256 {source_sha256} does not match expected "
            f"{args.expected_board_sha256}"
        )
    payload = {
        "board": "",
        "source_board_display": _display_path(source_board),
        "expected_board_sha256": args.expected_board_sha256,
        "net": args.net,
        "target_size_mm": args.target_size_mm,
        "zone_cell_mm": args.zone_cell_mm,
        "max_zone_cells": args.max_zone_cells,
        "max_pad_cells": args.max_pad_cells,
        "max_conductors": args.max_conductors,
        "solver_memory_limit_gb": args.solver_memory_limit_gb,
        "faulthandler_enabled": args.faulthandler,
    }
    started = time.perf_counter_ns()
    # Path canonicalization inside the managed bounded worker was denied for
    # the retained build/ fixture during development. Stage verified identical
    # bytes in a bounded temporary directory removed after the worker exits;
    # the denial mechanism is not inferred from this observation.
    with tempfile.TemporaryDirectory(prefix="spike-marble-profile-", dir=ROOT) as temporary:
        staged_board = Path(temporary) / source_board.name
        shutil.copyfile(source_board, staged_board)
        if _sha_file(staged_board) != source_sha256:
            raise RuntimeError("temporary board copy failed the source hash check")
        payload["board"] = str(staged_board)
        payload["phase_marker"] = str(marker)
        payload["stack_log"] = str(stack_log)
        payload["selected_zone_polygons"] = str(selected_zone_polygons)
        payload["memory_heartbeat"] = str(memory_heartbeat)

        def artifact_record(path: Path) -> dict[str, object]:
            return {
                "path": _display_path(path),
                "retained": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": _sha_file(path) if path.is_file() else None,
            }

        def failed_result(message: str) -> dict[str, object]:
            phase = (
                json.loads(marker.read_text(encoding="utf-8"))
                if marker.is_file() else None
            )
            return {
                "contract": "spike/retained-board-mesher-profile/v1",
                "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "failed",
                "revision": {
                    "git_head": _git_head(),
                    "hybrid_mesher_source_sha256": _sha_file(MESHER_SOURCE),
                    "runtime_source_sha256": _runtime_source_hashes(),
                    "worker_python_runtime": _python_runtime(),
                    "worker_runtime_provenance": (
                        "controller runtime; worker command launches this exact sys.executable"
                    ),
                    "scope": "working-tree hybrid mesher plus pinned retained fixture",
                },
                "fixture": {
                    "path": _display_path(source_board),
                    "bytes": source_board.stat().st_size,
                    "source_sha256": source_sha256,
                    "staged_copy_sha256": _sha_file(staged_board),
                    "staged_copy_basename": staged_board.name,
                },
                "limits": {
                    "timeout_s": args.timeout_s,
                    "process_memory_limit_mb": args.process_memory_limit_mb,
                    "process_memory_limit_enforcement": "bounded adapter OS process-tree limit",
                    "solver_memory_limit_gb": args.solver_memory_limit_gb,
                },
                "settings": {
                    **{key: payload[key] for key in (
                        "net", "target_size_mm", "zone_cell_mm", "max_zone_cells",
                        "max_pad_cells", "max_conductors",
                    )},
                    "faulthandler_enabled": args.faulthandler,
                },
                "supervised_wall_elapsed_ns": time.perf_counter_ns() - started,
                "failure": {
                    "message": message,
                    "last_completed_phase": phase,
                    "mesh_result_available": False,
                    "wall_stack_profile": _stack_summary(stack_log),
                },
                "artifacts": {
                    "phase_marker": artifact_record(marker),
                    "raw_stack_log": artifact_record(stack_log),
                    "selected_zone_polygons": artifact_record(selected_zone_polygons),
                    "worker_memory_heartbeat": artifact_record(memory_heartbeat),
                },
            }

        try:
            execution = run_adapter_process(
                [sys.executable, str(Path(__file__).resolve()), "--worker"],
                cwd=ROOT,
                timeout_s=args.timeout_s,
                memory_limit_mb=args.process_memory_limit_mb,
                output_limit_bytes=16 * 1024 * 1024,
                stream_limit_bytes=4 * 1024 * 1024,
                stdin_payload=_canonical(payload),
                windows_active_process_limit=2,
            )
        except SparseLizardAdapterError as error:
            return failed_result(str(error))
        if execution["return_code"] != 0:
            return failed_result(
                f"profile worker exited {execution['return_code']}: "
                f"{execution['stderr'][-4000:]}"
            )
    wall_elapsed_ns = time.perf_counter_ns() - started
    worker_result = json.loads(execution["stdout"])
    return {
        "contract": "spike/retained-board-mesher-profile/v1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": worker_result["status"],
        "revision": {
            "git_head": _git_head(),
            "hybrid_mesher_source_sha256": worker_result["hybrid_mesher_source_sha256"],
            "runtime_sources_before_sha256": worker_result[
                "runtime_sources_before_sha256"
            ],
            "runtime_sources_after_sha256": worker_result[
                "runtime_sources_after_sha256"
            ],
            "worker_python_runtime": worker_result["worker_python_runtime"],
            "worker_runtime_provenance": "reported by the completed worker",
            "scope": "working-tree hybrid mesher plus pinned retained fixture",
        },
        "limits": {
            "timeout_s": args.timeout_s,
            "process_memory_limit_mb": args.process_memory_limit_mb,
            "process_memory_limit_enforced": execution["memory_limit_enforced"],
            "windows_suspended_before_job_assignment": execution.get(
                "suspended_before_job_assignment"
            ),
            "solver_memory_limit_gb": args.solver_memory_limit_gb,
        },
        "settings": {
            **{key: payload[key] for key in (
                "net", "target_size_mm", "zone_cell_mm", "max_zone_cells",
                "max_pad_cells", "max_conductors",
            )},
            "faulthandler_enabled": args.faulthandler,
        },
        "supervised_wall_elapsed_ns": wall_elapsed_ns,
        "artifacts": {
            "phase_marker": {
                "path": _display_path(marker),
                "retained": marker.is_file(),
                "bytes": marker.stat().st_size if marker.is_file() else 0,
                "sha256": _sha_file(marker) if marker.is_file() else None,
            },
            "raw_stack_log": {
                "path": _display_path(stack_log),
                "retained": stack_log.is_file(),
                "bytes": stack_log.stat().st_size if stack_log.is_file() else 0,
                "sha256": _sha_file(stack_log) if stack_log.is_file() else None,
            },
            "selected_zone_polygons": {
                "path": _display_path(selected_zone_polygons),
                "retained": selected_zone_polygons.is_file(),
                "bytes": (
                    selected_zone_polygons.stat().st_size
                    if selected_zone_polygons.is_file() else 0
                ),
                "sha256": (
                    _sha_file(selected_zone_polygons)
                    if selected_zone_polygons.is_file() else None
                ),
            },
            "worker_memory_heartbeat": {
                "path": _display_path(memory_heartbeat),
                "retained": memory_heartbeat.is_file(),
                "bytes": memory_heartbeat.stat().st_size if memory_heartbeat.is_file() else 0,
                "sha256": _sha_file(memory_heartbeat) if memory_heartbeat.is_file() else None,
            },
        },
        "worker": worker_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--expected-board-sha256", default=PINNED_BOARD_SHA256)
    parser.add_argument("--net", default="+1V0")
    parser.add_argument("--target-size-mm", type=float, default=2.0)
    parser.add_argument("--zone-cell-mm", type=float, default=2.0)
    parser.add_argument("--max-zone-cells", type=int, default=50_000)
    parser.add_argument("--max-pad-cells", type=int, default=10_000)
    parser.add_argument("--max-conductors", type=int, default=300_000)
    parser.add_argument("--solver-memory-limit-gb", type=float, default=2.0)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--process-memory-limit-mb", type=int, default=4096)
    parser.add_argument(
        "--faulthandler", action=argparse.BooleanOptionalAction, default=True,
        help="enable five-second Python wall-stack sampling during meshing",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(_worker(json.load(sys.stdin)), separators=(",", ":"), allow_nan=False))
            return 0
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 2
    if args.output is None:
        parser.error("--output is required and must name a path under the repository root")
    finite_positive = (
        args.target_size_mm, args.zone_cell_mm, args.solver_memory_limit_gb,
    )
    if any(not math.isfinite(value) or value <= 0 for value in finite_positive):
        parser.error("mesh sizes and solver memory limit must be finite and positive")
    if args.solver_memory_limit_gb < 2.0:
        parser.error("solver memory limit must be at least 2 GiB")
    if not args.board.is_file():
        parser.error("board must be an existing file")
    if (
        len(args.expected_board_sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in args.expected_board_sha256)
    ):
        parser.error("expected board SHA-256 must have 64 hexadecimal characters")
    if not args.net.strip():
        parser.error("net must be non-empty")
    integer_limits = (
        args.max_zone_cells, args.max_pad_cells, args.max_conductors,
        args.timeout_s, args.process_memory_limit_mb,
    )
    if any(value <= 0 for value in integer_limits):
        parser.error("counts, timeout, and memory limit must be positive")
    if args.timeout_s > 86_400:
        parser.error("timeout must not exceed 86400 seconds")
    if not 256 <= args.process_memory_limit_mb <= 1_048_576:
        parser.error("process memory limit must be from 256 through 1048576 MiB")
    args.output = _require_repo_output(args.output)
    marker, stack_log, selected_zone_polygons = _evidence_sidecars(args.output)
    memory_heartbeat = _memory_heartbeat_path(args.output)
    for path in (
        args.output, marker, stack_log, selected_zone_polygons, memory_heartbeat,
        marker.with_suffix(marker.suffix + ".tmp"),
        memory_heartbeat.with_suffix(memory_heartbeat.suffix + ".tmp"),
    ):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing evidence: {path}")
    result = _controller(args)
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_new_text(args.output, encoded)
    print(encoded, end="")
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
