# SPDX-License-Identifier: MIT
"""OS-enforced supervisor for the dedicated owned-circuit worker.

This module is the trusted host-side boundary.  It admits exact worker/library
bytes before launch, uses a Windows Job Object or a POSIX process group with
resource limits, and publishes a bounded terminal result when the worker is
cancelled or exceeds its wall-time budget.  It never invokes a shell.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Callable, Sequence

from .owned_spice_process import (
    PROCESS_RESULT_CONTRACT,
    _atomic_publish,
    _normalized_job_relative,
    _reject_reparse_components,
)


MAX_TIMEOUT_SECONDS = 86_400
MIN_MEMORY_MIB = 16
MAX_MEMORY_MIB = 1_048_576


@dataclass(frozen=True)
class SupervisionResult:
    status: str
    returncode: int
    elapsed_seconds: float
    os_enforcement: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_identity(path: Path, expected_name: str, expected_sha256: str) -> Path:
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError(f"{expected_name} path must be absolute, normalized, and existing")
    stat = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & reparse):
        raise ValueError(f"{expected_name} path must not be a symlink or reparse point")
    if not path.is_file() or path.name != expected_name:
        raise ValueError(f"untrusted {expected_name} file")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError(f"{expected_name} identity must be lowercase SHA-256")
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"{expected_name} SHA-256 admission failed")
    return path


def _terminal_result(path: Path, status: str, code: str, message: str) -> None:
    _atomic_publish(path, {
        "contract": PROCESS_RESULT_CONTRACT,
        "status": status,
        "validation_state": "experimental",
        "circuit": None,
        "issues": [{"code": code, "severity": "error", "message": message}],
        "provenance": {
            "supervisor": "python.spike_core.circuit_worker_supervisor",
            "complete_process_tree_termination_requested": True,
        },
    })


def _validate_budget(timeout_seconds: float, memory_limit_mib: int) -> None:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        raise ValueError("timeout_seconds is outside the admitted range")
    if (
        isinstance(memory_limit_mib, bool)
        or not isinstance(memory_limit_mib, int)
        or memory_limit_mib < MIN_MEMORY_MIB
        or memory_limit_mib > MAX_MEMORY_MIB
    ):
        raise ValueError("memory_limit_mib is outside the admitted range")


def _supervise_posix(
    program: Path,
    arguments: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    memory_limit_mib: int,
    cancelled: Callable[[], bool],
) -> tuple[str, int]:
    import resource

    memory_bytes = memory_limit_mib * 1024 * 1024

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        if hasattr(resource, "RLIMIT_CORE"):
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    process = subprocess.Popen(
        [str(program), *arguments], cwd=cwd, shell=False, close_fds=True,
        start_new_session=True, preexec_fn=limits,
    )
    deadline = time.monotonic() + timeout_seconds
    status = "completed"
    while process.poll() is None:
        if cancelled():
            status = "cancelled"
            break
        if time.monotonic() >= deadline:
            status = "timeout"
            break
        time.sleep(0.02)
    if status != "completed":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return status, process.wait()


def _supervise_windows(
    program: Path,
    arguments: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    memory_limit_mib: int,
    cancelled: Callable[[], bool],
) -> tuple[str, int]:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    size_t = ctypes.c_size_t

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
        ]

    class BASIC_LIMITS(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", size_t), ("MaximumWorkingSetSize", size_t),
            ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", size_t),
            ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class EXTENDED_LIMITS(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMITS), ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", size_t), ("JobMemoryLimit", size_t),
            ("PeakProcessMemoryUsed", size_t), ("PeakJobMemoryUsed", size_t),
        ]

    CREATE_SUSPENDED = 0x00000004
    CREATE_NO_WINDOW = 0x08000000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    WAIT_TIMEOUT = 0x00000102

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = PROCESS_INFORMATION()
    try:
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_JOB_MEMORY |
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.JobMemoryLimit = memory_limit_mib * 1024 * 1024
        if not kernel32.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(program), *arguments]))
        startup = STARTUPINFO(cb=ctypes.sizeof(STARTUPINFO))
        if not kernel32.CreateProcessW(
            str(program), command, None, None, False,
            CREATE_SUSPENDED | CREATE_NO_WINDOW, None, str(cwd),
            ctypes.byref(startup), ctypes.byref(info),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(job, info.hProcess):
            kernel32.TerminateProcess(info.hProcess, 126)
            raise ctypes.WinError(ctypes.get_last_error())
        if kernel32.ResumeThread(info.hThread) == 0xFFFFFFFF:
            kernel32.TerminateJobObject(job, 126)
            raise ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(info.hThread)
        info.hThread = None
        deadline = time.monotonic() + timeout_seconds
        status = "completed"
        while kernel32.WaitForSingleObject(info.hProcess, 20) == WAIT_TIMEOUT:
            if cancelled():
                status = "cancelled"
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                break
        if status != "completed":
            kernel32.TerminateJobObject(job, 125 if status == "cancelled" else 124)
            kernel32.WaitForSingleObject(info.hProcess, 5_000)
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status, ctypes.c_int32(exit_code.value).value
    finally:
        if info.hThread:
            kernel32.CloseHandle(info.hThread)
        if info.hProcess:
            kernel32.CloseHandle(info.hProcess)
        kernel32.CloseHandle(job)


def supervise_process(
    program: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    memory_limit_mib: int,
    cancelled: Callable[[], bool] = lambda: False,
) -> SupervisionResult:
    """Run an already-admitted executable without a shell under OS limits."""

    _validate_budget(timeout_seconds, memory_limit_mib)
    if not program.is_absolute() or not program.is_file():
        raise ValueError("supervised program must be an absolute regular file")
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError("supervised cwd must be an absolute directory")
    started = time.monotonic()
    if os.name == "nt":
        status, returncode = _supervise_windows(
            program, arguments, cwd, timeout_seconds, memory_limit_mib, cancelled,
        )
        enforcement = "windows_job_object"
    else:
        status, returncode = _supervise_posix(
            program, arguments, cwd, timeout_seconds, memory_limit_mib, cancelled,
        )
        enforcement = "posix_process_group_rlimit"
    return SupervisionResult(status, returncode, time.monotonic() - started, enforcement)


def run_circuit_worker(
    *,
    worker_executable: Path,
    worker_sha256: str,
    library_path: Path,
    library_sha256: str,
    job_root: Path,
    request: str,
    result: str,
    timeout_seconds: float = 300,
    memory_limit_mib: int = 4096,
    cancelled: Callable[[], bool] = lambda: False,
) -> SupervisionResult:
    """Admit identities and supervise the worker's fixed four-argument ABI."""

    worker_name = "spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker"
    library_name = "spikes_c_api.dll" if os.name == "nt" else "libspikes_c_api.so"
    worker = _regular_identity(worker_executable, worker_name, worker_sha256)
    _regular_identity(library_path, library_name, library_sha256)
    root = job_root.resolve(strict=True)
    request_relative = _normalized_job_relative(request, "request.json")
    result_relative = _normalized_job_relative(result, "result.json")
    if request_relative.parent != result_relative.parent:
        raise ValueError("circuit controls must share one job directory")
    _reject_reparse_components(root, request_relative)
    _reject_reparse_components(root, result_relative.parent)
    request_path = root / request_relative
    result_path = root / result_relative
    if not request_path.is_file():
        raise ValueError("admitted circuit request is not a regular file")
    outcome = supervise_process(
        worker, ["--request", request, "--result", result], cwd=root,
        timeout_seconds=timeout_seconds, memory_limit_mib=memory_limit_mib,
        cancelled=cancelled,
    )
    if outcome.status == "cancelled":
        _terminal_result(result_path, "cancelled", "SPIKE-BE-SPICE-E-0055", "circuit job cancelled")
    elif outcome.status == "timeout":
        _terminal_result(result_path, "failed", "SPIKE-BE-SPICE-E-0056", "circuit job exceeded wall-time budget")
    return outcome
