# SPDX-License-Identifier: Apache-2.0
"""Measure bounded SPIKE package-open stages against an explicit local fixture."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _memory_bytes() -> dict[str, int | None]:
    """Return current/peak working set without adding a runtime dependency."""

    if os.name != "nt":
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return {"working_set": None, "peak_working_set": int(usage.ru_maxrss) * 1024}
        except (ImportError, OSError):
            return {"working_set": None, "peak_working_set": None}

    size_t = ctypes.c_size_t

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", size_t), ("WorkingSetSize", size_t),
            ("QuotaPeakPagedPoolUsage", size_t), ("QuotaPagedPoolUsage", size_t),
            ("QuotaPeakNonPagedPoolUsage", size_t), ("QuotaNonPagedPoolUsage", size_t),
            ("PagefileUsage", size_t), ("PeakPagefileUsage", size_t),
            ("PrivateUsage", size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = ctypes.c_void_p
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    get_memory.restype = ctypes.c_int
    ok = get_memory(get_process(), ctypes.byref(counters), counters.cb)
    if not ok:
        return {"working_set": None, "peak_working_set": None}
    return {
        "working_set": int(counters.WorkingSetSize),
        "peak_working_set": int(counters.PeakWorkingSetSize),
    }


class TimedPatches:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)
        self._restore: list[tuple[Any, str, Any]] = []

    def patch(self, owner: Any, attribute: str, stage: str) -> None:
        original = getattr(owner, attribute)

        def measured(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds[stage] += time.perf_counter() - started
                self.calls[stage] += 1

        self._restore.append((owner, attribute, original))
        setattr(owner, attribute, measured)

    def restore(self) -> None:
        for owner, attribute, original in reversed(self._restore):
            setattr(owner, attribute, original)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            stage: {"seconds": round(seconds, 6), "calls": self.calls[stage]}
            for stage, seconds in sorted(self.seconds.items())
        }


def _references(value: Any) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            if item.get("contract") == "spike/state-artifact-reference/v1":
                found.setdefault(str(item.get("path", "")), item)
            else:
                for child in item.values():
                    walk(child)

    walk(value)
    return list(found.values())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_frontend_envelopes(result: dict[str, Any], directory: Path) -> dict[str, dict[str, Any]]:
    """Write measured current and reconstructed pre-optimization desktop payloads."""

    directory.mkdir(parents=True, exist_ok=True)
    current = result["project"]
    legacy = dict(current)
    legacy_design = dict(current.get("design") or {})
    legacy_design["canonical_design"] = result["canonical"]["design_ir"]
    legacy["design"] = legacy_design
    outputs = {
        "before": (directory / "project-for-desktop-before.json", legacy),
        "after": (directory / "project-for-desktop-after.json", current),
    }
    records: dict[str, dict[str, Any]] = {}
    for name, (path, value) in outputs.items():
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, default=str)
            stream.write("\n")
        records[name] = {"path": str(path.resolve()), "bytes": path.stat().st_size,
                         "sha256": _file_sha256(path)}
    return records


def profile_once(fixture: Path, label: str, envelope_directory: Path | None = None) -> dict[str, Any]:
    import python.spike_core.project_package as package
    import python.spike_core.service_project_handlers as handlers
    from python.spike_core.service_project_persistence import read_persistent_artifact

    stages = TimedPatches()
    for owner, attribute, stage in [
        (package.json, "loads", "json_decode"),
        (package, "_validate_archive", "archive_index_and_limits"),
        (package, "_read_manifest", "manifest_json"),
        (package, "_verify_member_stream", "member_decompress_and_sha256"),
        (package, "validate_geometry_index", "geometry_binding_validation"),
        (package, "canonicalize_assembly_designs", "assembly_design_validation"),
        (package, "_validate_design_source_artifacts", "source_binding_validation"),
        (package, "canonicalize_model_index", "model_index_validation"),
        (package, "validate_model_artifacts", "model_artifact_validation"),
        (package, "canonicalize_assembly_package_shapes", "package_shape_validation"),
        (package, "validate_package_shape_artifacts", "package_shape_artifact_validation"),
        (package, "_validate_profile_content", "profile_validation"),
        (handlers, "read_project", "complete_secure_package_read"),
        (handlers, "project_for_desktop", "desktop_projection"),
        (handlers, "read_project_source_artifact", "active_source_restore"),
    ]:
        stages.patch(owner, attribute, stage)

    before = _memory_bytes()
    started = time.perf_counter()
    try:
        response = handlers.handle_project_request(
            "read_project_package",
            {"path": str(fixture), "defer_artifacts": True, "compact_normalized_source": True},
            request_id=f"profile-{label}", application_version="profile",
        )
    finally:
        stages.restore()
    handler_seconds = time.perf_counter() - started
    if not response or not response.get("ok"):
        raise RuntimeError(str((response or {}).get("error", "project open failed")))

    encode_started = time.perf_counter()
    encoded = json.dumps(response, default=str)
    encode_seconds = time.perf_counter() - encode_started
    encoded_bytes = len(encoded.encode("utf-8"))
    del encoded
    result = response["result"]
    envelopes = _write_frontend_envelopes(result, envelope_directory) if envelope_directory else None
    references = _references(result["project"])
    artifact_seconds = 0.0
    for reference in references:
        artifact_started = time.perf_counter()
        read_persistent_artifact("read_project_state_artifact", {
            "path": str(fixture),
            "reference": reference,
            "expected_manifest_payload_sha256": result["manifest"]["manifest_payload_sha256"],
        })
        artifact_seconds += time.perf_counter() - artifact_started
    after = _memory_bytes()
    return {
        "label": label,
        "handler_seconds": round(handler_seconds, 6),
        "worker_json_encode_seconds": round(encode_seconds, 6),
        "worker_response_utf8_bytes": encoded_bytes,
        "state_artifact_count": len(references),
        "state_artifact_restore_seconds": round(artifact_seconds, 6),
        "memory": {"before": before, "after": after},
        "stages": stages.snapshot(),
        "admission": {
            "manifest_payload_sha256": result["manifest"]["manifest_payload_sha256"],
            "project_has_duplicate_canonical_design": "canonical_design" in result["project"].get("design", {}),
            "retained_designs": len(result["project"].get("assembly_designs", {}).get("designs", [])),
            "board_occurrences": len(result["project"].get("assembly_ir", {}).get("boards", [])),
        },
        **({"frontend_envelopes": envelopes} if envelopes else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--envelope-output-directory", type=Path)
    args = parser.parse_args()
    if not args.fixture.is_file():
        parser.error(f"fixture does not exist: {args.fixture}")
    if not 1 <= args.iterations <= 10:
        parser.error("--iterations must be between 1 and 10")
    fixture_sha256 = _file_sha256(args.fixture)
    runs = [profile_once(args.fixture, "cold" if index == 0 else f"warm-{index}",
                         args.envelope_output_directory if index == 0 else None)
            for index in range(args.iterations)]
    report = {
        "schema": "spike/project-loading-profile/v1",
        "fixture": {"path": str(args.fixture.resolve()), "bytes": args.fixture.stat().st_size,
                    "sha256": fixture_sha256},
        "notes": [
            "Cold denotes the first read in a fresh profiler process; the OS file cache is not forcibly flushed.",
            "Stage timers overlap where a validation stage calls another measured function.",
            "member_decompress_and_sha256 preserves full streaming digest verification for every declared member.",
            "Peak working set is process-lifetime peak; use a fresh process when comparing implementations.",
            "Interaction, native visual export, frontend parsing and GPU scene construction are outside this backend profile.",
        ],
        "runs": runs,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
