"""Discover an OpenFOAM runtime without treating discovery as solver readiness."""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def _native_runtime() -> Dict[str, Any] | None:
    for name in ("openfoam2606", "openfoam", "foamRun", "chtMultiRegionFoam"):
        executable = shutil.which(name)
        if executable:
            return {
                "available": True,
                "transport": "native_process",
                "executable": str(Path(executable).resolve()),
                "version": "",
                "distribution": "",
            }
    return None


def _wsl_runtime() -> Dict[str, Any] | None:
    if not sys.platform.startswith("win"):
        return None
    launcher = shutil.which("wsl.exe") or shutil.which("wsl")
    if not launcher:
        return None
    distribution = os.environ.get("SPIKE_OPENFOAM_WSL_DISTRO", "Ubuntu").strip()
    if not distribution or len(distribution) > 128 or any(ord(character) < 32 for character in distribution):
        return None
    command = [launcher, "-d", distribution, "--", "/usr/bin/openfoam2606", "-show-api"]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=12,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    version = process.stdout.strip().splitlines()[-1] if process.returncode == 0 and process.stdout.strip() else ""
    if not version.isdigit():
        return None
    return {
        "available": True,
        "transport": "wsl_process",
        "executable": f"wsl://{distribution}/usr/bin/openfoam2606",
        "version": version,
        "distribution": distribution,
        "launcher": str(Path(launcher).resolve()),
        "command_prefix": [str(Path(launcher).resolve()), "-d", distribution, "--", "/usr/bin/openfoam2606"],
    }


@functools.lru_cache(maxsize=1)
def detect_openfoam_runtime() -> Dict[str, Any]:
    runtime = _native_runtime() or _wsl_runtime()
    return runtime or {
        "available": False,
        "transport": "none",
        "executable": "",
        "version": "",
        "distribution": "",
    }


__all__ = ["detect_openfoam_runtime"]
