# SPDX-License-Identifier: Apache-2.0
"""Worker routing for the integrated Python workspace services."""

from __future__ import annotations

import json
from typing import Any

from .script_debug import python_debug_command, python_debug_status, start_python_debug
from .script_runtime import run_python_script
from .script_workspace_files import python_workspace_files


def handle_script_workspace_request(
    method: Any,
    params: Any,
    *,
    trusted_extension_ids: list[str],
) -> dict[str, Any] | None:
    operations = {
        "run_python_script": run_python_script,
        "start_python_debug": start_python_debug,
        "python_debug_command": python_debug_command,
        "python_debug_status": python_debug_status,
        "python_workspace_files": python_workspace_files,
    }
    operation = operations.get(method)
    if operation is None:
        return None
    try:
        if not isinstance(params, dict):
            raise TypeError("Python workspace parameters must be an object.")
        effective = params
        if method in {"run_python_script", "start_python_debug"}:
            effective = {**params, "_trusted_extension_ids": trusted_extension_ids}
        return {"ok": True, "result": operation(effective)}
    except (ValueError, TypeError, FileExistsError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "type": type(exc).__name__}


__all__ = ["handle_script_workspace_request"]
