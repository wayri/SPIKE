# SPDX-License-Identifier: Apache-2.0
"""Disk-backed lifecycle for Python workspace debug sessions."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from . import script_debug_child as _script_debug_child  # Frozen-worker inclusion.
from .extension_analysis_results import admit_analysis_result, design_binding
from .script_runtime import MAX_CODE_BYTES, MAX_REQUEST_BYTES
from .script_workspace_files import resolve_script_paths


CONTRACT = "spike/python-debug/v1"
IDLE_SECONDS = 30.0
RETENTION_SECONDS = 300.0
MAX_OUTPUT_BYTES = 1_000_000 + 64
COMMAND_ACK_WAIT_SECONDS = 0.25


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.005 * (attempt + 1))


def _session_root() -> Path:
    configured = os.environ.get("SPIKE_DEBUG_SESSION_ROOT")
    root = Path(configured) if configured else Path(tempfile.gettempdir()) / "spike-python-debug-v1"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Python debug session root may not be a symbolic link.")
    return root.resolve(strict=True)


def _session_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("A Python debug session_id is required.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Python debug session_id is invalid.") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("Python debug session_id is invalid.")
    return value


def _session_path(value: Any) -> Path:
    identifier = _session_id(value)
    root = _session_root()
    path = root / identifier
    if path.is_symlink():
        raise ValueError("Python debug session path is invalid.")
    resolved = path.resolve(strict=True)
    if resolved.parent != root or not resolved.is_dir():
        raise ValueError("Python debug session path is invalid.")
    return resolved


def _breakpoints(value: Any) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list) or any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
        raise ValueError("Python debug breakpoints must be positive line numbers.")
    return sorted(set(value))[:10_000]


def _read_json(path: Path) -> dict[str, Any]:
    last_error: BaseException | None = None
    for _ in range(20):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"Invalid Python debug file: {path.name}")
            return value
        except (FileNotFoundError, PermissionError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.005)
    assert last_error is not None
    raise last_error


def _touch_lease(directory: Path, token: str) -> None:
    _atomic_json(directory / "lease.json", {"token": token, "updated_at": time.time()})


def _read_output(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_OUTPUT_BYTES + 1)
    except FileNotFoundError:
        return ""
    if len(data) > MAX_OUTPUT_BYTES:
        data = data[:MAX_OUTPUT_BYTES]
    return data.decode("utf-8", errors="replace")


def _process_alive(pid: Any) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _state_pid(directory: Path, state: dict[str, Any]) -> Any:
    pid = state.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool):
        return pid
    try:
        return int((directory / "pid.txt").read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None


def _terminate_process(pid: Any) -> None:
    if not _process_alive(pid):
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        cutoff = time.monotonic() + 0.25
        while _process_alive(pid) and time.monotonic() < cutoff:
            time.sleep(0.01)
        try:
            if _process_alive(pid):
                os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
    cutoff = time.monotonic() + 1.0
    while _process_alive(pid) and time.monotonic() < cutoff:
        time.sleep(0.01)


def _write_terminal_state(directory: Path, state: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    updated = {
        "contract": CONTRACT,
        "session_id": state["session_id"],
        "token": state["token"],
        "status": status,
        "revision": int(state.get("revision", 0)) + 1,
        "command_ack": int(state.get("command_ack", 0)),
        "frames": [], "reason": reason, "return_code": 1,
        "updated_at": time.time(), "pid": state.get("pid"),
    }
    _atomic_json(directory / "state.json", updated)
    return updated


def _cleanup_sessions(*, keep: str | None = None) -> None:
    root = _session_root()
    now = time.time()
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink() or path.name == keep:
            continue
        try:
            _session_id(path.name)
            state = _read_json(path / "state.json")
            status = state.get("status")
            updated_at = float(state.get("updated_at", path.stat().st_mtime))
            if status in {"starting", "running", "paused"}:
                try:
                    lease = _read_json(path / "lease.json")
                    if lease.get("token") == state.get("token"):
                        updated_at = max(updated_at, float(lease.get("updated_at", 0)))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            age = now - updated_at
            if status in {"starting", "running", "paused"} and age > IDLE_SECONDS + 5:
                _terminate_process(_state_pid(path, state))
                state = _write_terminal_state(path, state, "failed", "Python debug session expired.")
                age = 0
            if status in {"completed", "failed", "stopped"} and age > RETENTION_SECONDS:
                shutil.rmtree(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue


def _snapshot(directory: Path, *, touch: bool = True) -> dict[str, Any]:
    request = _read_json(directory / "request.json")
    state = _read_json(directory / "state.json")
    if state.get("contract") != CONTRACT or state.get("session_id") != request.get("session_id") \
            or state.get("token") != request.get("token"):
        raise ValueError("Python debug session state failed token validation.")
    if touch and state.get("status") in {"starting", "running", "paused"}:
        _touch_lease(directory, str(request["token"]))
    if state.get("status") in {"starting", "running", "paused"} and not _process_alive(_state_pid(directory, state)):
        state = _write_terminal_state(directory, state, "failed", "Python debug child exited unexpectedly.")
    if state.get("status") in {"completed", "failed", "stopped"}:
        pid = _state_pid(directory, state)
        cutoff = time.monotonic() + 0.1
        while _process_alive(pid) and time.monotonic() < cutoff:
            time.sleep(0.005)
    result = {key: value for key, value in state.items() if key not in {"token", "pid", "updated_at"}}
    result["stdout"] = _read_output(directory / "stdout.txt")
    result["stderr"] = _read_output(directory / "stderr.txt")
    published = state.get("published_result")
    if published is not None:
        try:
            binding = request.get("context", {}).get("design_binding")
            if not isinstance(binding, dict):
                raise ValueError("A board is required to publish script analysis results.")
            result["published_result"] = admit_analysis_result(
                published, binding, extension_id="spike.python-workspace",
            )
        except (ValueError, TypeError) as exc:
            result.update({"status": "failed", "return_code": 1, "published_result": None,
                           "reason": "Published result was rejected.",
                           "stderr": f"{result['stderr']}\n{exc}".strip()})
    return result


def start_python_debug(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise TypeError("Python debug parameters must be an object.")
    code = params.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Python debug code must be a nonempty string.")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Python script exceeds the 512 KB editor limit.")
    timeout = params.get("timeout_seconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise ValueError("Python debug timeout must be between 1 and 600 seconds.")
    design = params.get("design")
    results = params.get("results")
    if design is not None and not isinstance(design, dict):
        raise ValueError("Python debug design context must be a SpiDeR object.")
    if results is not None and not isinstance(results, dict):
        raise ValueError("Python debug result context must be an object.")
    trusted = params.get("_trusted_extension_ids", [])
    if not isinstance(trusted, list) or any(not isinstance(item, str) for item in trusted):
        raise ValueError("Trusted extension IDs must be a string array.")
    working, filename = resolve_script_paths(params)
    identifier = str(uuid.uuid4())
    token = uuid.uuid4().hex + uuid.uuid4().hex
    now = time.time()
    context = {
        "design": design, "results": results,
        "design_binding": design_binding(design) if design is not None else None,
        "trusted_extension_ids": trusted,
    }
    request = {
        "contract": CONTRACT, "session_id": identifier, "token": token,
        "code": code, "filename": str(filename), "working_directory": str(working),
        "breakpoints": _breakpoints(params.get("breakpoints")), "context": context,
        "created_at": now, "deadline": now + float(timeout), "idle_seconds": IDLE_SECONDS,
    }
    encoded = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("Python debug context exceeds 64 MB.")
    root = _session_root()
    _cleanup_sessions(keep=identifier)
    directory = root / identifier
    directory.mkdir(mode=0o700)
    (directory / "commands").mkdir(mode=0o700)
    (directory / "request.json").write_bytes(encoded)
    (directory / "counter.txt").write_text("0", encoding="ascii")
    _touch_lease(directory, token)
    initial = {
        "contract": CONTRACT, "session_id": identifier, "token": token,
        "status": "starting", "revision": 1, "command_ack": 0, "frames": [],
        "updated_at": now, "pid": None,
    }
    _atomic_json(directory / "state.json", initial)
    if getattr(sys, "frozen", False):
        bootstrap = directory / "debug-entry.py"
        bootstrap.write_text(
            "from python.spike_core.script_debug_child import main\nraise SystemExit(main())\n",
            encoding="utf-8",
        )
        command = [sys.executable, "--extension-host", str(bootstrap)]
    else:
        command = [sys.executable, "-m", "python.spike_core.script_debug_child"]
    command.extend(["--session", str(directory)])
    popen_args: dict[str, Any] = {
        "cwd": str(working), "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        "shell": False, "close_fds": True,
    }
    child_environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[2])
    child_environment["PYTHONPATH"] = os.pathsep.join(filter(None, (
        source_root, child_environment.get("PYTHONPATH", ""),
    )))
    popen_args["env"] = child_environment
    if os.name == "nt":
        popen_args["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP |
            getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        popen_args["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **popen_args)
        (directory / "pid.txt").write_text(str(process.pid), encoding="ascii")
        process.returncode = 0  # The token-bound session, not this worker, owns its lifetime.
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    cutoff = time.monotonic() + 0.5
    while time.monotonic() < cutoff:
        snapshot = _snapshot(directory)
        if snapshot["status"] != "starting":
            return snapshot
        time.sleep(0.01)
    return _snapshot(directory)


def _enqueue(directory: Path, command: str, breakpoints: list[int] | None) -> int:
    request = _read_json(directory / "request.json")
    lock_path = directory / "command.lock"
    deadline = time.monotonic() + 1.0
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 2:
                    lock_path.unlink()
            except FileNotFoundError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Python debug command queue is busy.")
            time.sleep(0.01)
    try:
        counter_path = directory / "counter.txt"
        sequence = int(counter_path.read_text(encoding="ascii")) + 1
        if sequence > 10_000:
            raise RuntimeError("Python debug session command limit exceeded.")
        temporary = counter_path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(str(sequence), encoding="ascii")
        os.replace(temporary, counter_path)
        payload: dict[str, Any] = {
            "token": request["token"], "sequence": sequence, "command": command,
            "created_at": time.time(),
        }
        if breakpoints is not None:
            payload["breakpoints"] = breakpoints
        _atomic_json(directory / "commands" / f"{sequence:020d}.json", payload)
        _touch_lease(directory, str(request["token"]))
        return sequence
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def python_debug_command(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise TypeError("Python debug command parameters must be an object.")
    command = params.get("command")
    allowed = {"continue", "step_into", "step_over", "step_out", "pause", "stop", "breakpoints"}
    if command not in allowed:
        raise ValueError("Unknown Python debug command.")
    directory = _session_path(params.get("session_id"))
    before = _snapshot(directory)
    if before["status"] in {"completed", "failed", "stopped"}:
        return before
    if command in {"continue", "step_into", "step_over", "step_out"} and before["status"] != "paused":
        raise ValueError(f"Python debug command {command} requires a paused session.")
    points = _breakpoints(params.get("breakpoints")) if command == "breakpoints" else None
    sequence = _enqueue(directory, str(command), points)
    if command == "stop":
        state = _read_json(directory / "state.json")
        _terminate_process(_state_pid(directory, state))
        state["command_ack"] = sequence
        _write_terminal_state(directory, state, "stopped", "stopped by user")
        snapshot = _snapshot(directory, touch=False)
        snapshot["command_sequence"] = sequence
        return snapshot
    cutoff = time.monotonic() + COMMAND_ACK_WAIT_SECONDS
    snapshot = before
    while time.monotonic() < cutoff:
        snapshot = _snapshot(directory)
        if int(snapshot.get("command_ack", 0)) >= sequence:
            snapshot["command_sequence"] = sequence
            return snapshot
        time.sleep(0.01)
    snapshot["command_pending"] = sequence
    snapshot["command_sequence"] = sequence
    return snapshot


def python_debug_status(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise TypeError("Python debug status parameters must be an object.")
    identifier = _session_id(params.get("session_id"))
    _cleanup_sessions(keep=identifier)
    return _snapshot(_session_path(identifier))


__all__ = ["start_python_debug", "python_debug_command", "python_debug_status"]
