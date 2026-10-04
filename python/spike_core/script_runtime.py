# SPDX-License-Identifier: Apache-2.0
"""Bounded child-process execution for the in-app Python workspace."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from . import script_child as _script_child  # Static import for the frozen worker bundle.
from .extension_analysis_results import admit_analysis_result, design_binding
from .script_api_context import admit_ui_actions, normalize_script_workspace
from .script_workspace_files import resolve_script_paths
from .script_views import admit_views


MAX_CODE_BYTES = 512_000
MAX_REQUEST_BYTES = 64_000_000
MAX_RESULT_BYTES = 16_000_000
MAX_DIAGNOSTIC_BYTES = 32_000
EXTERNAL_BOOTSTRAP = """\
import runpy
import sys
import types
from pathlib import Path

root = Path(sys.argv.pop(1)).resolve()
required = (root / "python" / "spike_core" / "script_child.py",
            root / "extensions",
            root / "extension_sdk" / "python" / "spike_extension_sdk.py")
if not all(path.is_file() if path.suffix else path.is_dir() for path in required):
    raise SystemExit("SPIKE script runtime source is unavailable to this Python interpreter.")
packages = (("python", root / "python"),
            ("extensions", root / "extensions"),
            ("extension_sdk", root / "extension_sdk"),
            ("extension_sdk.python", root / "extension_sdk" / "python"))
for name, path in packages:
    module = types.ModuleType(name)
    module.__package__ = name
    module.__path__ = [str(path)]
    sys.modules[name] = module
sys.modules["extension_sdk"].python = sys.modules["extension_sdk.python"]
runpy.run_module("python.spike_core.script_child", run_name="__main__")
"""


def _failed(message: str, *, elapsed_ms: int = 0) -> dict[str, Any]:
    return {"contract": "spike/python-script-result/v1", "status": "failed", "stdout": "",
            "stderr": message, "return_code": 1, "duration_ms": elapsed_ms, "ui_actions": []}


def _external_source_root() -> Path:
    source = Path(__file__).resolve().parents[2]
    workspace = Path(os.environ.get("SPIKE_WORKSPACE") or source).expanduser().resolve()

    def complete(root: Path) -> bool:
        return ((root / "python/spike_core/script_child.py").is_file()
                and (root / "extensions").is_dir()
                and (root / "extension_sdk/python/spike_extension_sdk.py").is_file())

    if complete(source):
        return source
    if complete(workspace):
        return workspace
    raise ValueError("External Python execution requires the packaged SPIKE script runtime, extensions, and extension SDK sources.")


def run_python_script(params: dict[str, Any]) -> dict[str, Any]:
    code = params.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Python script code must be a nonempty string.")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Python script exceeds the 512 KB editor limit.")
    timeout = params.get("timeout_seconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise ValueError("Python script timeout must be between 1 and 600 seconds.")
    executable = params.get("python_executable")
    if executable is not None:
        if not isinstance(executable, str) or not executable.strip():
            raise ValueError("Python executable must be an absolute path to an existing file.")
        interpreter = Path(executable).expanduser()
        if not interpreter.is_absolute() or not interpreter.is_file():
            raise ValueError("Python executable must be an absolute path to an existing file.")
        executable = str(interpreter.resolve())
    design = params.get("design")
    if design is not None and not isinstance(design, dict):
        raise ValueError("Python script design context must be a SpiDeR object.")
    results = params.get("results")
    if results is not None and not isinstance(results, dict):
        raise ValueError("Python script result context must be an object.")
    workspace, selected_design = normalize_script_workspace(params.get("workspace"), design)
    binding = design_binding(selected_design) if selected_design is not None else None
    trusted = params.get("_trusted_extension_ids", [])
    if not isinstance(trusted, list) or any(not isinstance(item, str) for item in trusted):
        raise ValueError("Trusted extension IDs must be a string array.")
    working, filename = resolve_script_paths(params)
    context = {"design": selected_design, "workspace": workspace,
               "results": results, "design_binding": binding,
               "trusted_extension_ids": trusted}
    request = json.dumps({"code": code, "context": context, "filename": str(filename),
                         "working_directory": str(working)}, ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    if len(request) > MAX_REQUEST_BYTES:
        raise ValueError("Python script context exceeds 64 MB.")
    source_root = _external_source_root() if executable else None
    started = time.monotonic()
    directory = tempfile.mkdtemp(prefix="spike-python-")
    try:
        job = Path(directory)
        request_path = job / "request.json"
        result_path = job / "result.json"
        request_path.write_bytes(request)
        if executable:
            bootstrap = job / "external-script-entry.py"
            bootstrap.write_text(EXTERNAL_BOOTSTRAP, encoding="utf-8")
            command = [executable, "-I", "-B", str(bootstrap), str(source_root)]
        elif getattr(sys, "frozen", False):
            bootstrap = job / "script-entry.py"
            bootstrap.write_text("from python.spike_core.script_child import main\nraise SystemExit(main())\n",
                                 encoding="utf-8")
            command = [sys.executable, "--extension-host", str(bootstrap)]
        else:
            command = [sys.executable, "-m", "python.spike_core.script_child"]
        command.extend(["--request", str(request_path), "--result", str(result_path)])
        child_environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        child_environment["PYTHONPATH"] = os.pathsep.join(filter(None, (
            source_root, child_environment.get("PYTHONPATH", ""),
        )))
        process = subprocess.Popen(command, cwd=working, env=child_environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, shell=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        diagnostic_tail = bytearray()

        def drain_diagnostics() -> None:
            assert process.stdout is not None
            while chunk := process.stdout.read(64 * 1024):
                diagnostic_tail.extend(chunk)
                if len(diagnostic_tail) > MAX_DIAGNOSTIC_BYTES:
                    del diagnostic_tail[:-MAX_DIAGNOSTIC_BYTES]

        reader = threading.Thread(target=drain_diagnostics, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=float(timeout))
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=3, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            return_code = None
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if return_code is None:
            return _failed(f"Python script exceeded the {timeout:g}-second limit.",
                           elapsed_ms=int((time.monotonic() - started) * 1000))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        diagnostic = bytes(diagnostic_tail).decode("utf-8", errors="replace")
        if return_code or not result_path.is_file():
            return _failed(f"Python child exited with code {return_code}.\n{diagnostic}".strip(),
                           elapsed_ms=elapsed_ms)
        if result_path.stat().st_size > MAX_RESULT_BYTES:
            return _failed("Python script result exceeds 16 MB.", elapsed_ms=elapsed_ms)
        result: dict[str, Any] | None = None
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict) or result.get("contract") != "spike/python-script-result/v1":
                raise ValueError("Python child returned an invalid result contract.")
            published = result.get("published_result")
            result["views"] = admit_views(result.get("views", []))
            if published is not None:
                if binding is None:
                    raise ValueError("A board is required to publish script analysis results.")
                result["published_result"] = admit_analysis_result(
                    published, binding, extension_id="spike.python-workspace")
            result["ui_actions"] = admit_ui_actions(result.get("ui_actions"), workspace)
            result["duration_ms"] = elapsed_ms
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            if isinstance(result, dict) and result.get("contract") == "spike/python-script-result/v1":
                return {**result, "status": "failed", "return_code": 1,
                        "stderr": f"{result.get('stderr') or ''}\n{exc}".strip(),
                        "published_result": None, "views": [], "ui_actions": [], "duration_ms": elapsed_ms}
            return _failed(str(exc), elapsed_ms=elapsed_ms)
    finally:
        for attempt in range(8):
            try:
                shutil.rmtree(directory)
                break
            except PermissionError:
                if attempt == 7:
                    break
                time.sleep(0.05 * (attempt + 1))


__all__ = ["run_python_script"]
