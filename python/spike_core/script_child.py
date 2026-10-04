# SPDX-License-Identifier: Apache-2.0
"""Child-side API for user-authored Python scripts in the desktop workspace."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
from importlib.metadata import PackageNotFoundError, version
import sys
import traceback
from pathlib import Path
from typing import Any

from .script_api import SpikeScriptAPI, bind_spike_module


MAX_OUTPUT = 1_000_000


class _CappedText(io.TextIOBase):
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def write(self, value: str) -> int:
        value = str(value)
        available = MAX_OUTPUT - self.length
        if available > 0:
            kept = value[:available]
            self.parts.append(kept)
            self.length += len(kept)
        if len(value) > available:
            self.truncated = True
        return len(value)

    def getvalue(self) -> str:
        return "".join(self.parts) + ("\n[output truncated]" if self.truncated else "")


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def run(request: dict[str, Any]) -> dict[str, Any]:
    output = _CappedText()
    errors = _CappedText()
    api = bind_spike_module(request.get("context", {}))
    code = request["code"]
    filename = str(request.get("filename") or "<SPIKE Python workspace>")
    working_directory = request.get("working_directory")
    if isinstance(working_directory, str):
        os.chdir(working_directory)
        if working_directory not in sys.path:
            sys.path.insert(0, working_directory)
    status = "completed"
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            compiled = compile(code, filename, "exec")
            exec(compiled, {"__name__": "__main__", "__file__": filename,
                            "__package__": None, "spike": api})
        except BaseException:
            status = "failed"
            traceback.print_exc(limit=12)
    return {"contract": "spike/python-script-result/v1", "status": status,
            "stdout": output.getvalue(), "stderr": errors.getvalue(),
            "return_code": 0 if status == "completed" else 1,
            "published_result": api.published_result if status == "completed" else None,
            "views": api.views if status == "completed" else [],
            "ui_actions": api.ui_actions if status == "completed" else [],
            "runtime": {"executable": sys.executable, "python_version": platform.python_version(),
                        "emerge_version": _package_version("emerge"),
                        "optycal_version": _package_version("optycal")}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = run(request)
    Path(args.result).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
