# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Best-effort, stdlib-only memory observations for the current process.

Every byte field may be ``None`` when the operating system cannot report it.
The metric names deliberately distinguish resident memory from private commit.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import platform
from typing import Callable


def _linux_status(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and value.strip().endswith(" kB"):
            try:
                values[key] = int(value.strip().split()[0]) * 1024
            except ValueError:
                pass
    return values


def _linux_resource_peak_bytes() -> int | None:
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (ImportError, OSError, ValueError):
        return None


def _linux_observation(read_text: Callable[[], str]) -> dict[str, object]:
    try:
        status = _linux_status(read_text())
    except OSError:
        status = {}
    usage_peak = _linux_resource_peak_bytes()
    return {
        "platform": "linux",
        "source": "proc-self-status+getrusage",
        "resident_current_bytes": status.get("VmRSS"),
        "resident_peak_bytes": status.get("VmHWM", usage_peak),
        "resident_peak_resource_bytes": usage_peak,
        "private_commit_current_bytes": None,
        "private_commit_peak_bytes": None,
    }


def _windows_observation() -> dict[str, object]:
    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]
    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(counters)
    try:
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.argtypes = []
        get_process.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        get_memory.restype = wintypes.BOOL
        process = get_process()
        success = get_memory(
            process, ctypes.byref(counters), counters.cb
        )
    except (AttributeError, OSError):
        success = 0
    if not success:
        values = (None, None, None, None)
    else:
        values = (int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize),
                  int(counters.PrivateUsage), int(counters.PeakPagefileUsage))
    return {
        "platform": "windows",
        "source": "GetProcessMemoryInfo/PROCESS_MEMORY_COUNTERS_EX",
        "resident_current_bytes": values[0],
        "resident_peak_bytes": values[1],
        "resident_peak_resource_bytes": None,
        "private_commit_current_bytes": values[2],
        "private_commit_peak_bytes": values[3],
    }


def observe_process_memory() -> dict[str, object]:
    """Return an explicitly labelled snapshot for this process."""
    system = platform.system()
    if system == "Windows":
        return _windows_observation()
    if system == "Linux":
        return _linux_observation(lambda: Path("/proc/self/status").read_text(encoding="ascii"))
    return {
        "platform": system.lower() or "unknown", "source": "unsupported",
        "resident_current_bytes": None, "resident_peak_bytes": None,
        "resident_peak_resource_bytes": None,
        "private_commit_current_bytes": None, "private_commit_peak_bytes": None,
    }
