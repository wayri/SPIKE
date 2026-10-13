# SPDX-License-Identifier: Apache-2.0
"""Supervised headless access to the existing worker, without a desktop."""
from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_STEPS = 64
WORKFLOW_CONTRACT = "spike/headless-workflow/v1"


def load_document(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        encoded = stream.read(MAX_INPUT_BYTES + 1)
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("Input document exceeds 2 MiB")
    value = json.loads(encoded, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    if not isinstance(value, dict):
        raise ValueError("Input document must be a JSON object")
    return value


def failure(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message,
            "type": "HeadlessExecutionError"}


def _timeout(value: float) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 < value <= 86400):
        raise ValueError("timeout_seconds must be finite, greater than zero and at most 86400")


class _WindowsProcessTree:
    """Own an inheritable process tree, not an inheritable Job handle.

    Assignment precedes resume, so the worker cannot spawn outside the Job.
    No breakaway flags or active-process limits are enabled: solver children
    are allowed and remain owned even after their immediate parent exits.
    """
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                        ("Flags", wintypes.DWORD), ("MinimumWorkingSet", ctypes.c_size_t),
                        ("MaximumWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                        ("Scheduling", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("Basic", BasicLimits), ("IoCounters", ctypes.c_uint64 * 6),
                        ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
                        ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        api.TerminateJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        api.CloseHandle.restype = wintypes.BOOL
        self.api, self.ctypes = api, ctypes
        self.handle = api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            self.handle = None


def _stop(process: subprocess.Popen, windows_job=None) -> str | None:
    """Terminate only the owned worker tree, including external solver children."""
    warning = None
    if os.name == "nt":
        try:
            if windows_job is not None:
                windows_job.terminate()
        except OSError as exc:
            warning = f"Process-tree termination failed: {exc}; descendant cleanup is unverified"
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            warning = f"Process-group termination failed: {exc}; descendant cleanup is unverified"
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    return warning


def run_request(request: dict[str, Any], timeout_seconds: float = 120,
                *, command: list[str] | None = None) -> dict[str, Any]:
    """Return the worker envelope unchanged; supervise finite IO and wall time."""
    _timeout(timeout_seconds)
    if (not isinstance(request, dict) or set(request) - {"id", "method", "params"}
            or not isinstance(request.get("method"), str) or not request["method"].strip()
            or not isinstance(request.get("params", {}), dict)):
        raise ValueError("Worker request requires method and object params; only id, method, params accepted")
    submitted = {**request, "id": uuid.uuid4().hex}
    encoded = (json.dumps(submitted, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("Worker request exceeds 2 MiB")
    if command is None:
        command = ([sys.executable] if getattr(sys, "frozen", False) else
                   [sys.executable, str(Path(__file__).resolve().parents[2] / "scripts/spike_worker_entry.py")])
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    windows_job, process = None, None
    try:
        if os.name == "nt":
            windows_job = _WindowsProcessTree()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment, shell=False,
                                   start_new_session=os.name != "nt",
                                   creationflags=(subprocess.CREATE_NO_WINDOW | 0x00000004) if windows_job else 0)
        if windows_job is not None:
            windows_job.assign(process)
            from .sparselizard_process import _resume_windows_process
            _resume_windows_process(process)
    except (OSError, RuntimeError, KeyboardInterrupt) as exc:
        # Failed assignment leaves the worker suspended, unable to spawn.
        try:
            if process is not None:
                _stop(process, windows_job)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
        finally:
            if windows_job is not None:
                windows_job.close()
        return failure("SPIKE-HEADLESS-CANCELLED" if isinstance(exc, KeyboardInterrupt) else "SPIKE-HEADLESS-START", str(exc))

    def drain(stream, buffer):
        while chunk := stream.read(65536):
            room = MAX_OUTPUT_BYTES - len(buffer)
            buffer.extend(chunk[:max(0, room)])
            if len(chunk) > room:
                overflow.set()
                return

    def send():
        try:
            process.stdin.write(encoded)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [threading.Thread(target=drain, args=(stream, buffer), daemon=True)
               for stream, buffer in zip((process.stdout, process.stderr), buffers)]
    writer = threading.Thread(target=send, daemon=True)
    deadline = time.monotonic() + timeout_seconds
    error = None
    try:
        for reader in readers:
            reader.start()
        writer.start()
        while process.poll() is None:
            if overflow.is_set():
                error = failure("SPIKE-HEADLESS-OUTPUT-LIMIT", "Worker output exceeded 32 MiB")
                break
            if time.monotonic() >= deadline:
                error = failure("SPIKE-HEADLESS-TIMEOUT", "Owned worker exceeded wall-time limit")
                break
            time.sleep(0.02)
    except KeyboardInterrupt:
        error = failure("SPIKE-HEADLESS-CANCELLED", "Owned worker cancelled")
    except (OSError, RuntimeError) as exc:
        error = failure("SPIKE-HEADLESS-START", f"Worker supervision failed: {exc}")
    finally:
        try:
            if error:
                warning = _stop(process, windows_job)
                if warning:
                    error["cleanup_warning"] = warning
        finally:
            if windows_job is not None:
                # Also contain descendants after normal/early parent exit,
                # before waiting for inherited pipe handles to reach EOF.
                windows_job.close()
        for thread in [writer, *readers]:
            if thread.ident is not None:
                thread.join(timeout=1)
        if not writer.is_alive() and all(not reader.is_alive() for reader in readers):
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
    if error:
        return error
    if overflow.is_set() or any(reader.is_alive() for reader in readers):
        _stop(process, windows_job)
        for reader in readers:
            reader.join(timeout=1)
        return failure("SPIKE-HEADLESS-OUTPUT-LIMIT", "Worker output exceeded limits or streams remained open")
    if process.returncode:
        return failure("SPIKE-HEADLESS-EXIT", f"Worker exited with code {process.returncode}: " +
                       buffers[1][-4096:].decode("utf-8", errors="replace"))
    try:
        response = json.loads(buffers[0], parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if (not isinstance(response, dict) or response.get("id") != submitted["id"]
                or not isinstance(response.get("ok"), bool)):
            raise ValueError("Invalid worker envelope or response identity")
        return response
    except (ValueError, UnicodeError, RecursionError) as exc:
        return failure("SPIKE-HEADLESS-PROTOCOL", str(exc))


def _resolve(value: Any, completed: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            reference = value["$ref"]
            if not isinstance(reference, str) or "#" not in reference:
                raise ValueError("Reference must be stepName#/JSON/pointer")
            name, pointer = reference.split("#", 1)
            result = completed[name]
            if pointer and not pointer.startswith("/"):
                raise ValueError("Reference must use a JSON pointer")
            for token in pointer.split("/")[1:]:
                if re.search(r"~(?![01])", token):
                    raise ValueError("Invalid JSON pointer escape")
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(result, list):
                    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                        raise ValueError("Invalid array index")
                    result = result[int(token)]
                else:
                    result = result[token]
            return result
        return {key: _resolve(item, completed) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, completed) for item in value]
    return value


def run_workflow(plan: dict[str, Any], timeout_seconds: float = 120, *, execute=run_request) -> dict[str, Any]:
    """Stop on the first failure; earlier mutations are not rolled back."""
    _timeout(timeout_seconds)
    if len(json.dumps(plan, allow_nan=False).encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Workflow document exceeds 2 MiB")
    if (not isinstance(plan, dict) or set(plan) != {"contract", "steps"}
            or plan.get("contract") != WORKFLOW_CONTRACT
            or not isinstance(plan.get("steps"), list) or not 1 <= len(plan["steps"]) <= MAX_STEPS):
        raise ValueError("Expected spike/headless-workflow/v1 with 1..64 steps")
    names = set()
    for step in plan["steps"]:
        if (not isinstance(step, dict) or set(step) != {"name", "method", "params"}
                or not isinstance(step["name"], str) or not step["name"] or "#" in step["name"]
                or step["name"] in names or not isinstance(step["method"], str)
                or not step["method"].strip() or not isinstance(step["params"], dict)):
            raise ValueError("Steps require unique names, method and object params")
        names.add(step["name"])
    completed = {}
    # Reserve metadata and an error receipt for every step, including long names.
    total = MAX_INPUT_BYTES + 1024 * MAX_STEPS
    for step in plan["steps"]:
        try:
            response = execute({"method": step["method"], "params": _resolve(step["params"], completed)}, timeout_seconds)
        except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
            response = failure("SPIKE-HEADLESS-REFERENCE", str(exc))
        total += len(json.dumps(response, allow_nan=False).encode("utf-8"))
        if total > MAX_OUTPUT_BYTES:
            response = failure("SPIKE-HEADLESS-OUTPUT-LIMIT", "Combined workflow output exceeds 32 MiB")
        completed[step["name"]] = response
        if not response.get("ok"):
            return {"contract": "spike/headless-workflow-result/v1", "ok": False,
                    "failed_step": step["name"], "steps": completed}
    return {"contract": "spike/headless-workflow-result/v1", "ok": True, "steps": completed}
