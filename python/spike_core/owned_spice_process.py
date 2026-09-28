# SPDX-License-Identifier: Apache-2.0
"""Dedicated circuit-only process boundary for the release-owned SPIKES kernel."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import uuid
from typing import Any, Dict

from .contracts import DesignIR
from .owned_spice_workspace import run_owned_spice_workspace
from .spikes_runtime import engine_status


JOB_CONTRACT = "spike/owned-spice-process-job/v1"
PROCESS_RESULT_CONTRACT = "spike/owned-spice-process-result/v1"
CAPABILITY_CONTRACT = "spike/owned-spice-process-capability/v1"
MAX_CONTROL_BYTES = 8 * 1024 * 1024
MAX_CIRCUIT_RESULT_BYTES = 4 * 1024 * 1024
_JOB_KEYS = {"contract", "design", "circuit_request"}


def capability_manifest() -> Dict[str, Any]:
    status = engine_status()
    return {
        "contract": CAPABILITY_CONTRACT,
        "engine": "spike-circuit-worker",
        "interface": ["--request", "<job>/request.json", "--result", "<job>/result.json"],
        "input_contract": JOB_CONTRACT,
        "circuit_request_contract": "spike/owned-spice-workspace-request/v1",
        "result_contract": PROCESS_RESULT_CONTRACT,
        "validation_state": "experimental",
        "structured_workspace_only": True,
        "raw_netlist_accepted": False,
        "caller_selected_library": False,
        "shell_invoked": False,
        "trusted_host_supervision_required": True,
        "supported_supervision": ["windows_job_object", "posix_process_group_rlimit"],
        "binary_and_library_sha256_admission": True,
        "maximum_control_bytes": MAX_CONTROL_BYTES,
        "maximum_circuit_result_bytes": MAX_CIRCUIT_RESULT_BYTES,
        "owned_engine": {
            "available": bool(status.get("available")),
            "abi_version": status.get("abi_version"),
            "library_bytes": status.get("library_bytes"),
            "library_sha256": status.get("library_sha256"),
            "features": status.get("features", {}),
        },
    }


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value} is prohibited")


def _strict_object(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_job(path: Path) -> Dict[str, Any]:
    size = path.stat().st_size
    if not 0 < size <= MAX_CONTROL_BYTES:
        raise ValueError("request.json is empty or exceeds the 8 MiB control limit")
    try:
        value = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("request.json must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != _JOB_KEYS:
        raise ValueError("the process job must contain exactly contract, design, and circuit_request")
    if value.get("contract") != JOB_CONTRACT:
        raise ValueError(f"expected process job contract {JOB_CONTRACT}")
    if not isinstance(value.get("design"), dict) or not isinstance(value.get("circuit_request"), dict):
        raise ValueError("design and circuit_request must be objects")
    return value


def _has_reparse_point(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(stat, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse)


def _normalized_job_relative(value: str, expected_name: str) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("process control paths must be non-empty text")
    components = re.split(r"[\\/]", value)
    if any(component in {"", ".", ".."} for component in components):
        raise ValueError("process control paths must be normalized and job-relative")
    path = Path(*components)
    if path.is_absolute() or path.drive or path.root or path.name != expected_name:
        raise ValueError("process controls must be normalized job-relative paths")
    return path


def _reject_reparse_components(root: Path, relative_path: Path) -> None:
    current = root
    for component in relative_path.parts:
        current /= component
        if _has_reparse_point(current):
            raise ValueError("process control path contains a symlink or reparse point")


def _admit_paths(request: str, result: str) -> tuple[Path, Path]:
    request_relative = _normalized_job_relative(request, "request.json")
    result_relative = _normalized_job_relative(result, "result.json")
    if request_relative.parent != result_relative.parent:
        raise ValueError("request.json and result.json must share one job directory")
    root = Path.cwd().resolve(strict=True)
    _reject_reparse_components(root, request_relative)
    _reject_reparse_components(root, result_relative.parent)
    request_path = root / request_relative
    result_path = root / result_relative
    if not request_path.is_file():
        raise ValueError("request.json does not exist or is not a regular file")
    request_parent = request_path.parent.resolve(strict=True)
    result_parent = result_path.parent.resolve(strict=True)
    if request_parent != result_parent:
        raise ValueError("request.json and result.json must share one job directory")
    if result_path.exists() and (_has_reparse_point(result_path) or not result_path.is_file()):
        raise ValueError("existing result path is not an admitted regular file")
    return request_path.resolve(strict=True), result_parent / "result.json"


def _atomic_publish(path: Path, value: Dict[str, Any]) -> None:
    payload = json.dumps(
        value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > MAX_CONTROL_BYTES:
        raise ValueError("result.json exceeds the 8 MiB control limit")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def execute_job(request_path: Path, result_path: Path) -> Dict[str, Any]:
    job = _read_job(request_path)
    circuit_request = deepcopy(job["circuit_request"])
    raw_limits = circuit_request.get("resource_limits")
    if raw_limits is None:
        raw_limits = {}
        circuit_request["resource_limits"] = raw_limits
    if isinstance(raw_limits, dict):
        requested_limit = raw_limits.get("maximum_result_bytes", MAX_CIRCUIT_RESULT_BYTES)
        if (
            isinstance(requested_limit, bool)
            or not isinstance(requested_limit, int)
            or requested_limit < 1
            or requested_limit > MAX_CIRCUIT_RESULT_BYTES
        ):
            raise ValueError(
                "circuit maximum_result_bytes must fit the 4 MiB process-envelope budget"
            )
        raw_limits["maximum_result_bytes"] = requested_limit
    result = run_owned_spice_workspace(
        circuit_request, DesignIR(**job["design"]),
    )
    envelope = {
        "contract": PROCESS_RESULT_CONTRACT,
        "status": result.get("status", "failed"),
        "validation_state": "experimental",
        "circuit": result,
        "provenance": {
            "process": "python.spike_core.owned_spice_process",
            "atomic_result_publication": True,
            "raw_netlist_accepted": False,
            "caller_selected_library": False,
            "shell_invoked": False,
            "maximum_circuit_result_bytes": MAX_CIRCUIT_RESULT_BYTES,
        },
    }
    _atomic_publish(result_path, envelope)
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spike-circuit-worker")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--result")
    args = parser.parse_args(argv)
    if args.capabilities:
        if args.request or args.result:
            parser.error("--capabilities cannot be combined with job controls")
        sys.stdout.write(json.dumps(capability_manifest(), sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    if not args.request or not args.result:
        parser.error("--request and --result are required")
    result_path: Path | None = None
    try:
        request_path, result_path = _admit_paths(args.request, args.result)
        envelope = execute_job(request_path, result_path)
        return 0 if envelope["status"] == "completed" else 2
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        if result_path is not None:
            _atomic_publish(result_path, {
                "contract": PROCESS_RESULT_CONTRACT,
                "status": "failed",
                "validation_state": "experimental",
                "circuit": None,
                "issues": [{
                    "code": "SPIKE-BE-SPICE-E-0054",
                    "severity": "error",
                    "message": str(exc)[:4096],
                }],
            })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
