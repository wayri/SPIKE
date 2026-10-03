# SPDX-License-Identifier: Apache-2.0
"""Persistent child process for the integrated Python debugger."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from types import FrameType
from typing import Any

from .script_child import MAX_OUTPUT, SpikeScriptAPI


MAX_FRAMES = 24
MAX_LOCALS = 64
MAX_VALUE_CHARS = 512
MAX_PUBLISHED_RESULT_BYTES = 16_000_000
POLL_SECONDS = 0.025


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.005 * (attempt + 1))


class _SessionOutput(io.TextIOBase):
    def __init__(self, path: Path) -> None:
        self._stream = path.open("w", encoding="utf-8", buffering=1)
        self._length = 0
        self._truncated = False
        self._lock = threading.Lock()

    def write(self, value: str) -> int:
        value = str(value)
        with self._lock:
            available = MAX_OUTPUT - self._length
            if available > 0:
                kept = value[:available]
                self._stream.write(kept)
                self._stream.flush()
                self._length += len(kept)
            if len(value) > available and not self._truncated:
                self._stream.write("\n[output truncated]")
                self._stream.flush()
                self._truncated = True
        return len(value)

    def flush(self) -> None:
        with self._lock:
            self._stream.flush()

    def close(self) -> None:
        if not self.closed:
            self.flush()
            super().close()
            self._stream.close()


class DebugSession:
    def __init__(self, directory: Path, request: dict[str, Any]) -> None:
        self.directory = directory
        self.request = request
        self.session_id = str(request["session_id"])
        self.token = str(request["token"])
        self.filename = str(request["filename"])
        self.runtime_file = Path(__file__).resolve()
        self.working_directory = Path(request["working_directory"]).resolve(strict=True)
        self.breakpoints = set(request.get("breakpoints", []))
        self.deadline = float(request["deadline"])
        self.idle_seconds = float(request.get("idle_seconds", 30.0))
        self.state_path = directory / "state.json"
        self.lease_path = directory / "lease.json"
        self.commands = directory / "commands"
        self.stdout = _SessionOutput(directory / "stdout.txt")
        self.stderr = _SessionOutput(directory / "stderr.txt")
        self.revision = 0
        self.command_ack = 0
        self._state_lock = threading.Lock()
        self._pause_requested = False
        self._mode = "continue"
        self._step_depth = 0
        self._user_depth = 0
        self._stopping = False

    def _safe_repr(self, value: Any) -> str:
        try:
            rendered = repr(value)
        except BaseException as exc:
            rendered = f"<repr failed: {type(exc).__name__}>"
        if len(rendered) > MAX_VALUE_CHARS:
            rendered = rendered[:MAX_VALUE_CHARS] + "..."
        return rendered

    def _frames(self, frame: FrameType) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        current: FrameType | None = frame
        while current is not None and len(frames) < MAX_FRAMES:
            if self._is_user_frame(current):
                local_items = list(current.f_locals.items())[:MAX_LOCALS]
                frames.append({
                    "name": current.f_code.co_name,
                    "filename": current.f_code.co_filename,
                    "line": current.f_lineno,
                    "locals": {str(name): self._safe_repr(value) for name, value in local_items},
                })
            current = current.f_back
        return frames

    def _is_user_frame(self, frame: FrameType) -> bool:
        name = frame.f_code.co_filename
        if name == self.filename:
            return True
        if name.startswith("<"):
            return False
        try:
            resolved = Path(name).resolve(strict=False)
            if resolved == self.runtime_file:
                return False
            resolved.relative_to(self.working_directory)
            return True
        except (OSError, ValueError):
            return False

    def write_state(self, status: str, *, frame: FrameType | None = None,
                    reason: str | None = None, return_code: int | None = None,
                    published_result: dict[str, Any] | None = None) -> None:
        with self._state_lock:
            try:
                current_revision = int(json.loads(
                    self.state_path.read_text(encoding="utf-8"),
                ).get("revision", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                current_revision = 0
            self.revision = max(self.revision, current_revision)
            self.revision += 1
            snapshot: dict[str, Any] = {
                "contract": "spike/python-debug/v1",
                "session_id": self.session_id,
                "token": self.token,
                "status": status,
                "revision": self.revision,
                "command_ack": self.command_ack,
                "frames": self._frames(frame) if frame is not None else [],
                "updated_at": time.time(),
                "pid": os.getpid(),
            }
            if frame is not None:
                snapshot["line"] = frame.f_lineno
                snapshot["filename"] = frame.f_code.co_filename
            if reason:
                snapshot["reason"] = reason
            if return_code is not None:
                snapshot["return_code"] = return_code
            if published_result is not None:
                snapshot["published_result"] = published_result
            _atomic_json(self.state_path, snapshot)

    def _command_paths(self) -> list[Path]:
        return sorted(self.commands.glob("*.json"), key=lambda item: int(item.stem))

    def process_commands(self, frame: FrameType | None) -> str | None:
        action: str | None = None
        for path in self._command_paths():
            sequence = int(path.stem)
            if sequence <= self.command_ack:
                continue
            try:
                command = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if command.get("token") != self.token or command.get("sequence") != sequence:
                continue
            name = command.get("command")
            if name == "breakpoints":
                self.breakpoints = set(command.get("breakpoints", []))
            elif name == "pause":
                self._pause_requested = True
            elif name in {"continue", "step_into", "step_over", "step_out", "stop"}:
                action = str(name)
            self.command_ack = sequence
            if action is None:
                status = "paused" if frame is not None and self._mode == "paused" else "running"
                self.write_state(status, frame=frame)
        return action

    def _pause(self, frame: FrameType, reason: str) -> None:
        self._mode = "paused"
        self._pause_requested = False
        self.write_state("paused", frame=frame, reason=reason)
        while True:
            action = self.process_commands(frame)
            if action == "stop":
                self._stopping = True
                raise SystemExit(0)
            if action in {"continue", "step_into", "step_over", "step_out"}:
                self._mode = action
                self._step_depth = self._user_depth
                self.write_state("running", frame=frame)
                return
            time.sleep(POLL_SECONDS)

    def _should_pause(self, frame: FrameType) -> str | None:
        if self._pause_requested:
            return "pause requested"
        if frame.f_code.co_filename == self.filename and frame.f_lineno in self.breakpoints:
            return "breakpoint"
        if self._mode == "step_into":
            return "step"
        if self._mode == "step_over" and self._user_depth <= self._step_depth:
            return "step"
        if self._mode == "step_out" and self._user_depth < self._step_depth:
            return "step"
        return None

    def trace(self, frame: FrameType, event: str, arg: Any) -> Any:
        is_user = self._is_user_frame(frame)
        if event == "call" and is_user:
            self._user_depth += 1
        try:
            if not is_user:
                return self.trace
            action = self.process_commands(None)
            if action == "stop":
                self._stopping = True
                raise SystemExit(0)
            if action == "pause":
                self._pause_requested = True
            if event == "line":
                reason = self._should_pause(frame)
                if reason:
                    self._pause(frame, reason)
            return self.trace
        finally:
            if event == "return" and is_user:
                self._user_depth = max(0, self._user_depth - 1)

    def watchdog(self) -> None:
        last_lease = float(self.request.get("created_at", time.time()))
        while True:
            now = time.time()
            reason: str | None = None
            if now >= self.deadline:
                reason = "Python debug session exceeded its time limit."
            else:
                try:
                    lease = json.loads(self.lease_path.read_text(encoding="utf-8"))
                    if lease.get("token") == self.token:
                        last_lease = float(lease.get("updated_at", last_lease))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
                if now - last_lease >= self.idle_seconds:
                    reason = "Python debug session expired because its client stopped responding."
            if reason:
                try:
                    self.write_state("failed", reason=reason, return_code=124)
                    self.stdout.flush()
                    self.stderr.flush()
                finally:
                    os._exit(124)
            time.sleep(min(0.25, max(0.02, self.deadline - now)))

    def run(self) -> int:
        os.chdir(self.working_directory)
        directory_text = str(self.working_directory)
        if directory_text not in sys.path:
            sys.path.insert(0, directory_text)
        api = SpikeScriptAPI(self.request.get("context", {}))
        namespace = {
            "__name__": "__main__", "__file__": self.filename,
            "__package__": None, "spike": api,
        }
        self.write_state("running")
        threading.Thread(target=self.watchdog, daemon=True).start()
        status = "completed"
        return_code = 0
        reason: str | None = None
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
            try:
                compiled = compile(self.request["code"], self.filename, "exec")
                sys.settrace(self.trace)
                exec(compiled, namespace)
            except SystemExit:
                if self._stopping:
                    status, reason = "stopped", "stopped by user"
                else:
                    status, reason, return_code = "failed", "script called SystemExit", 1
            except BaseException:
                status, return_code = "failed", 1
                traceback.print_exc(limit=12)
                reason = "Python script raised an exception."
            finally:
                sys.settrace(None)
        published = api.published_result if status == "completed" else None
        if published is not None:
            try:
                published_size = len(json.dumps(
                    published, ensure_ascii=False, allow_nan=False,
                ).encode("utf-8"))
                if published_size > MAX_PUBLISHED_RESULT_BYTES:
                    raise ValueError("Published result exceeds the 16 MB debug-session limit.")
            except (TypeError, ValueError) as exc:
                status, return_code = "failed", 1
                reason = str(exc)
                self.stderr.write(reason + "\n")
                published = None
        self.stdout.close()
        self.stderr.close()
        self.write_state(status, reason=reason, return_code=return_code,
                         published_result=published)
        return return_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    directory = Path(args.session).resolve(strict=True)
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    return DebugSession(directory, request).run()


if __name__ == "__main__":
    raise SystemExit(main())
