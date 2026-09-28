# SPDX-License-Identifier: Apache-2.0
"""Locate the optional OpenEMS runtime without implicit installation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from python.spike_core.runtime_locations import app_root, registered_engine_path


def openems_install_root() -> str:
    configured = os.environ.get("OPENEMS_INSTALL_PATH", "").strip()
    if configured and Path(configured).expanduser().is_dir():
        return str(Path(configured).expanduser().resolve())
    registered = registered_engine_path("external.openems")
    if registered:
        root = Path(registered).expanduser()
        if root.is_file():
            root = root.parent
        if root.is_dir():
            return str(root.resolve())
    runtime = app_root() / "runtime" / "external"
    candidates = [runtime / "openems" / "openEMS", runtime / "openEMS"]
    if runtime.is_dir():
        candidates.extend(sorted(runtime.glob("openems-*/openEMS"), reverse=True))
    for candidate in candidates:
        executables = (candidate / "openEMS", candidate / "openEMS.exe")
        if candidate.is_dir() and any(path.is_file() for path in executables):
            return str(candidate.resolve())
    return ""


def openems_python() -> str:
    configured = os.environ.get("SPIKE_OPENEMS_PYTHON", "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        return str(candidate) if candidate.is_file() else ""
    runtime = app_root() / "runtime" / "envs" / "openems-py311"
    for candidate in (runtime / "Scripts" / "python.exe", runtime / "bin" / "python"):
        if candidate.is_file():
            return str(candidate.resolve())
    return sys.executable
